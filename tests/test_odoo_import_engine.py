from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.models.branch import Branch
from app.models.category import Category
from app.models.company import Company
from app.models.product import Product
from app.models.purchase_transaction import PurchaseTransaction
from app.models.supplier import Supplier
from app.models.unit import Unit
from app.models.warehouse import Warehouse
from app.services.excel_reader import (
    ExcelInspectionResult,
    RawPurchaseTransactionRecord,
)
from app.services.mapping_engine import (
    BRANCH,
    SUB_WAREHOUSE,
    WAREHOUSE,
    DestinationCandidate,
    MappingCandidate,
    MappingEngine,
)
from app.services.odoo_import_engine import (
    BusinessFingerprint,
    DuplicateClassification,
    ExistingTransaction,
    ImportRowStatus,
    OdooImportEngine,
    SourceIdentity,
    business_fingerprint,
    business_fingerprint_from_transaction,
)
from app.services.persistence_engine import PersistenceEngine, PersistenceResult
from app.services.validation_engine import ValidationEngine


TEST_SOURCE_PREFIX = "odoo-import-test-"
TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pip_db"


@dataclass
class StubReader:
    inspection: ExcelInspectionResult
    calls: int = 0

    def read(self, source_file, worksheet_name=None):
        self.calls += 1
        return self.inspection


class RecordingMapper:
    def __init__(self):
        self.delegate = MappingEngine()
        self.calls = 0

    def map(self, *args, **kwargs):
        self.calls += 1
        return self.delegate.map(*args, **kwargs)


class RecordingPersistence:
    def __init__(self, failure=False):
        self.calls = []
        self.failure = failure

    def persist_batch(self, mapped_transactions):
        mapped_transactions = tuple(mapped_transactions)
        self.calls.append(mapped_transactions)
        if self.failure:
            return PersistenceResult(
                persisted_count=0,
                skipped_count=0,
                failed_count=1,
                errors=(),
            )
        return PersistenceResult(
            persisted_count=len(mapped_transactions),
            skipped_count=0,
            failed_count=0,
            persisted_source_rows=tuple(
                (
                    mapped.raw_record.source_file,
                    mapped.raw_record.source_sheet,
                    mapped.raw_record.source_row,
                )
                for mapped in mapped_transactions
            ),
        )


@pytest.fixture(scope="module")
def database_fixture():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    company = Company(name="Odoo Import Test Company", code="ODOO_IMPORT_COMPANY")
    category = Category(name="Odoo Import Test Category", code="ODOO_IMPORT_CATEGORY")
    unit = Unit(name="Odoo Import Test Unit", code="ODOO_IMPORT_UNIT")
    supplier = Supplier(name="Odoo Import Test Supplier", code="ODOO_IMPORT_SUPPLIER")
    session.add_all([company, category, unit, supplier])
    session.flush()
    branch = Branch(company_id=company.id, name="Odoo Import Test Branch", code="ODOO_IMPORT_BRANCH")
    session.add(branch)
    session.flush()
    warehouse = Warehouse(
        branch_id=branch.id,
        name="Odoo Import Test Warehouse",
        code="ODOO_IMPORT_WAREHOUSE",
    )
    product = Product(
        code="ODOO_IMPORT_PRODUCT",
        name="Odoo Import Test Product",
        category_id=category.id,
        unit_id=unit.id,
    )
    session.add_all([warehouse, product])
    session.commit()
    ids = {
        "company": company.id,
        "category": category.id,
        "unit": unit.id,
        "supplier": supplier.id,
        "branch": branch.id,
        "warehouse": warehouse.id,
        "product": product.id,
    }
    session.close()

    yield session_factory, ids

    cleanup = session_factory()
    cleanup.execute(
        delete(PurchaseTransaction).where(
            PurchaseTransaction.source_file.like(f"{TEST_SOURCE_PREFIX}%")
        )
    )
    cleanup.execute(delete(Product).where(Product.id == ids["product"]))
    cleanup.execute(delete(Warehouse).where(Warehouse.id == ids["warehouse"]))
    cleanup.execute(delete(Branch).where(Branch.id == ids["branch"]))
    cleanup.execute(delete(Supplier).where(Supplier.id == ids["supplier"]))
    cleanup.execute(delete(Unit).where(Unit.id == ids["unit"]))
    cleanup.execute(delete(Category).where(Category.id == ids["category"]))
    cleanup.execute(delete(Company).where(Company.id == ids["company"]))
    cleanup.commit()
    cleanup.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def clear_test_transactions(database_fixture):
    session_factory, _ = database_fixture
    session = session_factory()
    session.execute(
        delete(PurchaseTransaction).where(
            PurchaseTransaction.source_file.like(f"{TEST_SOURCE_PREFIX}%")
        )
    )
    session.commit()
    session.close()


def make_raw(
    row=2,
    source_file="odoo-import-test.xlsx",
    source_sheet="Report",
    **changes,
):
    values = {
        "source_file": f"{TEST_SOURCE_PREFIX}{source_file}",
        "source_sheet": source_sheet,
        "source_row": row,
        "transaction_date": datetime(2026, 1, 15, 10, 30),
        "reference": "PO-001",
        "supplier_raw": "Odoo Import Test Supplier",
        "product_raw": "Odoo Import Test Product",
        "destination_raw": "Odoo Import Test Warehouse",
        "quantity_raw": Decimal("2.50"),
        "unit_raw": "Odoo Import Test Unit",
        "unit_price_raw": Decimal("10.25"),
        "subtotal_raw": Decimal("25.625"),
    }
    values.update(changes)
    return RawPurchaseTransactionRecord(**values)


def make_inspection(records):
    return ExcelInspectionResult(
        source_file=records[0].source_file if records else "empty.xlsx",
        source_sheet=records[0].source_sheet if records else "Report",
        header_row=1,
        total_rows=len(records),
        transaction_rows=len(records),
        skipped_rows=0,
        records=tuple(records),
    )


def make_engine(
    ids,
    records,
    *,
    persistence=None,
    mapper=None,
    lookup=None,
    suppliers=None,
    products=None,
    units=None,
    destinations=None,
):
    reader = StubReader(make_inspection(records))

    def default_lookup(source_identities, fingerprints):
        return lookup(source_identities, fingerprints) if lookup else ()

    return (
        OdooImportEngine(
            reader=reader,
            mapper=mapper or MappingEngine(),
            persistence=persistence or RecordingPersistence(),
            duplicate_lookup=default_lookup,
            suppliers=suppliers
            or [MappingCandidate("Odoo Import Test Supplier", ids["supplier"])],
            products=products
            or [MappingCandidate("Odoo Import Test Product", ids["product"])],
            units=units or [MappingCandidate("Odoo Import Test Unit", ids["unit"])],
            destinations=destinations
            or [
                DestinationCandidate(
                    "Odoo Import Test Warehouse",
                    WAREHOUSE,
                    warehouse_id=ids["warehouse"],
                ),
                DestinationCandidate(
                    "Odoo Import Test Branch",
                    BRANCH,
                    branch_id=ids["branch"],
                ),
            ],
        ),
        reader,
    )


def make_db_lookup(session_factory):
    def lookup(source_identities, fingerprints):
        session = session_factory()
        rows = session.execute(
            select(
                PurchaseTransaction.source_file,
                PurchaseTransaction.source_sheet,
                PurchaseTransaction.source_row,
                PurchaseTransaction.transaction_date,
                PurchaseTransaction.reference,
                PurchaseTransaction.supplier_id,
                PurchaseTransaction.product_id,
                PurchaseTransaction.unit_id,
                PurchaseTransaction.destination_type,
                PurchaseTransaction.branch_id,
                PurchaseTransaction.warehouse_id,
                PurchaseTransaction.sub_warehouse_name,
                PurchaseTransaction.quantity,
                PurchaseTransaction.unit_price,
                PurchaseTransaction.subtotal,
            )
        ).all()
        session.close()
        return tuple(
            ExistingTransaction(
                SourceIdentity(row.source_file, row.source_sheet, row.source_row),
                business_fingerprint_from_transaction(SimpleNamespace(**row._mapping)),
            )
            for row in rows
        )

    return lookup


def mapped_for_ids(ids, record):
    from app.services.validation_engine import ValidationEngine

    return MappingEngine().map(
        ValidationEngine().validate(record),
        suppliers=[MappingCandidate("Odoo Import Test Supplier", ids["supplier"])],
        products=[MappingCandidate("Odoo Import Test Product", ids["product"])],
        units=[MappingCandidate("Odoo Import Test Unit", ids["unit"])],
        destinations=[
            DestinationCandidate(
                "Odoo Import Test Warehouse", WAREHOUSE, warehouse_id=ids["warehouse"]
            )
        ],
    )


def persist_existing(session_factory, ids, record):
    result = PersistenceEngine(session_factory).persist(mapped_for_ids(ids, record))
    assert result.persisted_count == 1


def test_successful_preview_is_non_persistent(database_fixture):
    session_factory, ids = database_fixture
    engine, _ = make_engine(ids, [make_raw()])

    preview = engine.preview("ignored.xlsx")

    assert preview.rows_read == 1
    assert preview.validation_failure_count == 0
    assert preview.ready_for_commit_count == 0
    assert preview.eligible_for_commit_count == 1
    assert preview.row_results[0].status is ImportRowStatus.VALID
    assert len(engine.persistence.calls) == 0
    assert len(make_db_lookup(session_factory)((), ())) == 0


def test_validation_failure_is_preserved(database_fixture):
    _, ids = database_fixture
    engine, _ = make_engine(ids, [make_raw(quantity_raw="2")])

    row = engine.preview("ignored.xlsx").row_results[0]

    assert row.status is ImportRowStatus.INVALID
    assert row.errors[0].error_type == "INVALID_QUANTITY"


def test_mapping_and_ambiguous_failures_remain_visible(database_fixture):
    _, ids = database_fixture
    engine, _ = make_engine(ids, [make_raw()])
    engine.suppliers = ()
    assert engine.preview("ignored.xlsx").row_results[0].status is ImportRowStatus.UNMAPPED

    engine, _ = make_engine(ids, [make_raw()])
    engine.suppliers = (
        MappingCandidate("Odoo Import Test Supplier", ids["supplier"]),
        MappingCandidate("Odoo Import Test Supplier", 999999),
    )
    assert engine.preview("ignored.xlsx").row_results[0].status is ImportRowStatus.AMBIGUOUS


def test_source_duplicate_takes_precedence(database_fixture):
    session_factory, ids = database_fixture
    record = make_raw(row=10)
    persist_existing(session_factory, ids, record)
    engine, _ = make_engine(ids, [record], lookup=make_db_lookup(session_factory))

    row = engine.preview("ignored.xlsx").row_results[0]

    assert row.status is ImportRowStatus.DUPLICATE_SOURCE
    assert row.duplicate_info.classification is DuplicateClassification.DUPLICATE_SOURCE


def test_business_duplicate_is_potential_only(database_fixture):
    session_factory, ids = database_fixture
    persist_existing(session_factory, ids, make_raw(row=11, source_file="old.xlsx"))
    incoming = make_raw(row=12, source_file="new.xlsx")
    engine, _ = make_engine(ids, [incoming], lookup=make_db_lookup(session_factory))

    row = engine.preview("ignored.xlsx").row_results[0]

    assert row.status is ImportRowStatus.POTENTIAL_BUSINESS_DUPLICATE
    assert row.eligible_for_commit is True
    assert row.duplicate_info.classification is DuplicateClassification.POTENTIAL_BUSINESS_DUPLICATE


def test_same_business_rows_in_one_import_are_not_collapsed(database_fixture):
    _, ids = database_fixture
    first = make_raw(row=20, source_file="same.xlsx")
    second = make_raw(row=21, source_file="same.xlsx")
    engine, _ = make_engine(ids, [first, second])

    preview = engine.preview("ignored.xlsx")

    assert len(preview.row_results) == 2
    assert preview.potential_business_duplicate_count == 2
    assert {row.source_identity.source_row for row in preview.row_results} == {20, 21}


@pytest.mark.parametrize(
    "changed",
    [
        {"source_file": "copy.xlsx"},
        {"source_sheet": "Renamed"},
        {"source_row": 35},
    ],
)
def test_source_changes_do_not_change_fingerprint(database_fixture, changed):
    _, ids = database_fixture
    base = make_raw(row=20, source_file="base.xlsx")
    other_values = {
        "row": changed.get("source_row", base.source_row),
        "source_file": changed.get("source_file", "base.xlsx"),
        "source_sheet": changed.get("source_sheet", base.source_sheet),
    }
    other = make_raw(**other_values)
    engine, _ = make_engine(ids, [base, other])

    preview = engine.preview("ignored.xlsx")

    assert preview.row_results[0].business_fingerprint == preview.row_results[1].business_fingerprint
    assert preview.potential_business_duplicate_count == 2


def test_fingerprint_changes_for_business_fields(database_fixture):
    _, ids = database_fixture
    base = make_raw()
    engine, _ = make_engine(ids, [base])
    base_mapped = engine.preview("ignored.xlsx").row_results[0].mapped_transaction
    base_fingerprint = business_fingerprint(base_mapped)

    changed_cases = [
        ("reference", "PO-002", {}),
        ("transaction_date", datetime(2026, 1, 16, 10, 30), {}),
        ("supplier_raw", "Other Supplier", {"suppliers": [MappingCandidate("Other Supplier", 99)]}),
        ("product_raw", "Other Product", {"products": [MappingCandidate("Other Product", 98)]}),
        ("destination_raw", "Other Warehouse", {"destinations": [DestinationCandidate("Other Warehouse", WAREHOUSE, warehouse_id=97)]}),
        ("quantity_raw", Decimal("3"), {}),
        ("unit_price_raw", Decimal("11"), {}),
        ("subtotal_raw", Decimal("33"), {}),
    ]
    for changed_case in changed_cases:
        field, value, dependencies = changed_case
        changed_engine, _ = make_engine(
            ids,
            [make_raw(**{field: value})],
            **dependencies,
        )
        changed = changed_engine.preview("ignored.xlsx").row_results[0].business_fingerprint
        assert changed != base_fingerprint


def test_decimal_fingerprint_canonicalization_does_not_round(database_fixture):
    _, ids = database_fixture
    first_engine, _ = make_engine(ids, [make_raw(quantity_raw=Decimal("2.50"))])
    second_engine, _ = make_engine(ids, [make_raw(quantity_raw=Decimal("2.5"))])

    first = first_engine.preview("ignored.xlsx").row_results[0].business_fingerprint
    second = second_engine.preview("ignored.xlsx").row_results[0].business_fingerprint

    assert first == second
    assert first.quantity == "2.5"


def test_commit_uses_only_explicitly_accepted_rows_and_does_not_reread_or_remap(database_fixture):
    _, ids = database_fixture
    mapper = RecordingMapper()
    persistence = RecordingPersistence()
    engine, reader = make_engine(ids, [make_raw(row=30), make_raw(row=31)], persistence=persistence, mapper=mapper)
    preview = engine.preview("ignored.xlsx")
    mapper_calls = mapper.calls

    result = engine.commit(preview, [preview.row_results[1].source_identity])

    assert reader.calls == 1
    assert mapper.calls == mapper_calls
    assert len(persistence.calls) == 1
    assert len(persistence.calls[0]) == 1
    assert persistence.calls[0][0].raw_record.source_row == 31
    assert result.requested_count == 1
    assert result.persisted_count == 1


def test_potential_business_duplicate_requires_explicit_acceptance(database_fixture):
    session_factory, ids = database_fixture
    existing = make_raw(row=40, source_file="existing.xlsx")
    persist_existing(session_factory, ids, existing)
    incoming = make_raw(row=41, source_file="incoming.xlsx")
    persistence = RecordingPersistence()
    engine, _ = make_engine(ids, [incoming], persistence=persistence, lookup=make_db_lookup(session_factory))
    preview = engine.preview("ignored.xlsx")

    not_accepted = engine.commit(preview, [])
    accepted = engine.commit(preview, [preview.row_results[0].source_identity])

    assert not_accepted.persisted_count == 0
    assert len(persistence.calls) == 1
    assert len(persistence.calls[0]) == 1
    assert accepted.persisted_count == 1


def test_source_duplicate_cannot_be_committed(database_fixture):
    session_factory, ids = database_fixture
    record = make_raw(row=50)
    persist_existing(session_factory, ids, record)
    persistence = RecordingPersistence()
    engine, _ = make_engine(ids, [record], persistence=persistence, lookup=make_db_lookup(session_factory))
    preview = engine.preview("ignored.xlsx")

    result = engine.commit(preview, [preview.row_results[0].source_identity])

    assert result.persisted_count == 0
    assert result.skipped_count == 1
    assert persistence.calls == []


def test_persistence_failure_is_propagated(database_fixture):
    _, ids = database_fixture
    persistence = RecordingPersistence(failure=True)
    engine, _ = make_engine(ids, [make_raw(row=60)], persistence=persistence)

    preview = engine.preview("ignored.xlsx")
    result = engine.commit(preview, [preview.row_results[0].source_identity])

    assert result.failed_count == 1
    assert result.persisted_count == 0
    assert result.row_results[0].status is ImportRowStatus.FAILED


def test_import_is_immutable_and_commit_order_is_stable(database_fixture):
    _, ids = database_fixture
    records = [make_raw(row=70), make_raw(row=71)]
    persistence = RecordingPersistence()
    engine, _ = make_engine(ids, records, persistence=persistence)
    preview = engine.preview("ignored.xlsx")
    before = preview.row_results

    result = engine.commit(preview, [row.source_identity for row in reversed(preview.row_results)])

    assert preview.row_results is before
    assert [row.raw_record.source_row for row in result.row_results if row.status is ImportRowStatus.PERSISTED] == [70, 71]
    assert isinstance(preview.row_results[0].business_fingerprint, BusinessFingerprint)


def test_import_engine_has_no_direct_database_session_or_insert_logic():
    source = open("app/services/odoo_import_engine.py").read()

    assert "SessionLocal" not in source
    assert "create_engine" not in source
    assert "PurchaseTransaction(" not in source
    assert "sessionmaker" not in source
