from datetime import datetime
from decimal import Decimal

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
from app.services.excel_reader import RawPurchaseTransactionRecord
from app.services.mapping_engine import (
    BRANCH,
    SUB_WAREHOUSE,
    WAREHOUSE,
    DestinationCandidate,
    MappingCandidate,
    MappingEngine,
    MappingStatus,
)
from app.services.persistence_engine import (
    DUPLICATE_STRATEGY,
    PersistenceEngine,
)
from app.services.validation_engine import ValidationEngine


TEST_SOURCE_FILE = "persistence-test.xlsx"
TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pip_db"


@pytest.fixture(scope="module")
def database_fixture():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    company = Company(name="Persistence Test Company", code="PERSIST_COMPANY")
    category = Category(name="Persistence Test Category", code="PERSIST_CATEGORY")
    unit = Unit(name="Persistence Test Unit", code="PERSIST_UNIT")
    supplier = Supplier(name="Persistence Test Supplier", code="PERSIST_SUPPLIER")
    session.add_all([company, category, unit, supplier])
    session.flush()
    branch = Branch(company_id=company.id, name="Persistence Test Branch", code="PERSIST_BRANCH")
    session.add(branch)
    session.flush()
    warehouse = Warehouse(branch_id=branch.id, name="Persistence Test Warehouse", code="PERSIST_WAREHOUSE")
    product = Product(
        code="PERSIST_PRODUCT",
        name="Persistence Test Product",
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
    cleanup.execute(delete(PurchaseTransaction).where(PurchaseTransaction.source_file == TEST_SOURCE_FILE))
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
            PurchaseTransaction.source_file == TEST_SOURCE_FILE
        )
    )
    session.commit()
    session.close()


def make_record(row=7, **changes):
    values = {
        "source_file": TEST_SOURCE_FILE,
        "source_sheet": "Report",
        "source_row": row,
        "transaction_date": datetime(2026, 1, 15, 10, 30),
        "reference": f"PO-{row}",
        "supplier_raw": "Persistence Test Supplier",
        "product_raw": "Persistence Test Product",
        "destination_raw": "Persistence Test Warehouse",
        "quantity_raw": Decimal("2.50"),
        "unit_raw": "Persistence Test Unit",
        "unit_price_raw": Decimal("10.25"),
        "subtotal_raw": Decimal("25.625"),
    }
    values.update(changes)
    return RawPurchaseTransactionRecord(**values)


def make_mapped(
    ids,
    record=None,
    *,
    destination_type=WAREHOUSE,
    suppliers=None,
    products=None,
    units=None,
    destinations=None,
    **mapping_changes,
):
    raw = record or make_record()
    destination_values = {
        "destination_name": raw.destination_raw,
        "destination_type": destination_type,
        "warehouse_id": ids["warehouse"],
    }
    if destination_type == BRANCH:
        destination_values.update(branch_id=ids["branch"], warehouse_id=None)
    elif destination_type == SUB_WAREHOUSE:
        destination_values["sub_warehouse_name"] = "Persistence Test SubWarehouse"
    destination_values.update(mapping_changes.pop("destination", {}))
    if suppliers is None:
        suppliers = [MappingCandidate("Persistence Test Supplier", ids["supplier"])]
    if products is None:
        products = [MappingCandidate("Persistence Test Product", ids["product"])]
    if units is None:
        units = [MappingCandidate("Persistence Test Unit", ids["unit"])]
    if destinations is None:
        destinations = [DestinationCandidate(**destination_values)]
    mapping = MappingEngine().map(
        ValidationEngine().validate(raw),
        suppliers=suppliers,
        products=products,
        units=units,
        destinations=destinations,
    )
    return mapping


def fetch_transactions(session_factory, source_file=TEST_SOURCE_FILE):
    session = session_factory()
    rows = session.scalars(
        select(PurchaseTransaction).where(PurchaseTransaction.source_file == source_file)
    ).all()
    session.close()
    return rows


def test_valid_mapped_transaction_persists_all_fields(database_fixture):
    session_factory, ids = database_fixture
    mapped = make_mapped(ids)

    result = PersistenceEngine(session_factory).persist(mapped)
    row = fetch_transactions(session_factory)[0]

    assert result.persisted_count == 1
    assert result.skipped_count == 0
    assert result.failed_count == 0
    assert row.supplier_id == ids["supplier"]
    assert row.product_id == ids["product"]
    assert row.unit_id == ids["unit"]
    assert row.warehouse_id == ids["warehouse"]
    assert row.destination_type == WAREHOUSE
    assert row.source_file == TEST_SOURCE_FILE
    assert row.source_sheet == "Report"
    assert row.source_row == 7
    assert row.supplier_raw == "Persistence Test Supplier"
    assert row.product_raw == "Persistence Test Product"
    assert row.destination_raw == "Persistence Test Warehouse"
    assert row.unit_raw == "Persistence Test Unit"
    assert row.quantity == Decimal("2.50")
    assert row.unit_price == Decimal("10.25")
    assert row.subtotal == Decimal("25.625")


@pytest.mark.parametrize(
    "mapped_change",
    [
        {"record": make_record(quantity_raw="invalid")},
        {"suppliers": []},
    ],
)
def test_rejected_records_are_skipped(database_fixture, mapped_change):
    session_factory, ids = database_fixture
    mapped = (
        make_mapped(ids, mapped_change["record"])
        if "record" in mapped_change
        else make_mapped(ids)
    )
    if "suppliers" in mapped_change:
        mapped = MappingEngine().map(
            mapped.validation_result,
            suppliers=[],
            products=[MappingCandidate("Persistence Test Product", ids["product"])],
            units=[MappingCandidate("Persistence Test Unit", ids["unit"])],
            destinations=[DestinationCandidate("Persistence Test Warehouse", WAREHOUSE, warehouse_id=ids["warehouse"])],
        )

    result = PersistenceEngine(session_factory).persist(mapped)

    assert result.persisted_count == 0
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert fetch_transactions(session_factory) == []


@pytest.mark.parametrize("field", ["supplier", "product", "unit", "destination"])
def test_unmapped_and_ambiguous_required_mappings_are_skipped(database_fixture, field):
    session_factory, ids = database_fixture
    mapped = make_mapped(ids)
    if field == "supplier":
        mapped = make_mapped(ids, suppliers=[])
    elif field == "product":
        mapped = make_mapped(ids, products=[])
    elif field == "unit":
        mapped = make_mapped(ids, units=[])
    else:
        mapped = make_mapped(ids, destinations=[])

    result = PersistenceEngine(session_factory).persist(mapped)

    assert result.skipped_count == 1
    assert result.persisted_count == 0
    assert result.failed_count == 0


@pytest.mark.parametrize("field", ["supplier", "product", "unit", "destination"])
def test_ambiguous_mapping_is_skipped(database_fixture, field):
    session_factory, ids = database_fixture
    mapped = make_mapped(ids)
    if field == "supplier":
        mapped = make_mapped(
            ids,
            suppliers=[
                MappingCandidate("Persistence Test Supplier", ids["supplier"]),
                MappingCandidate("Persistence Test Supplier", 999999),
            ],
        )
    elif field == "product":
        mapped = make_mapped(
            ids,
            products=[
                MappingCandidate("Persistence Test Product", ids["product"]),
                MappingCandidate("Persistence Test Product", 999999),
            ],
        )
    elif field == "unit":
        mapped = make_mapped(
            ids,
            units=[
                MappingCandidate("Persistence Test Unit", ids["unit"]),
                MappingCandidate("Persistence Test Unit", 999999),
            ],
        )
    else:
        mapped = make_mapped(
            ids,
            destinations=[
                DestinationCandidate(
                    "Persistence Test Warehouse", WAREHOUSE, warehouse_id=ids["warehouse"]
                ),
                DestinationCandidate(
                    "Persistence Test Warehouse", WAREHOUSE, warehouse_id=999999
                ),
            ],
        )

    result = PersistenceEngine(session_factory).persist(mapped)

    assert result.skipped_count == 1
    assert result.persisted_count == 0


def test_all_destination_types_persist_explicitly(database_fixture):
    session_factory, ids = database_fixture
    branch = make_mapped(ids, make_record(row=21, destination_raw="Persistence Test Branch"), destination_type=BRANCH)
    warehouse = make_mapped(ids, make_record(row=22), destination_type=WAREHOUSE)
    subwarehouse = make_mapped(ids, make_record(row=23, destination_raw="Persistence Test SubWarehouse"), destination_type=SUB_WAREHOUSE)

    result = PersistenceEngine(session_factory).persist_batch([branch, warehouse, subwarehouse])
    rows = sorted(fetch_transactions(session_factory), key=lambda row: row.source_row)

    assert result.persisted_count == 3
    assert [(row.destination_type, row.branch_id, row.warehouse_id, row.sub_warehouse_name) for row in rows] == [
        (BRANCH, ids["branch"], None, None),
        (WAREHOUSE, None, ids["warehouse"], None),
        (SUB_WAREHOUSE, None, ids["warehouse"], "Persistence Test SubWarehouse"),
    ]


def test_database_failure_rolls_back_entire_batch_and_reports_failure(database_fixture):
    session_factory, ids = database_fixture
    good = make_mapped(ids, make_record(row=31))
    bad = make_mapped(ids, make_record(row=32), destination={"warehouse_id": 999999})

    result = PersistenceEngine(session_factory).persist_batch([good, bad])

    assert result.persisted_count == 0
    assert result.failed_count == 1
    assert result.errors[-1].error_type == "DATABASE_ERROR"
    assert fetch_transactions(session_factory) == []


def test_database_error_is_explicit(database_fixture):
    session_factory, ids = database_fixture
    bad = make_mapped(ids, make_record(row=41), destination={"warehouse_id": 999999})

    result = PersistenceEngine(session_factory).persist(bad)

    assert result.failed_count == 1
    assert result.errors[0].message == "Database persistence failed"
    assert result.errors[0].exception_type == "IntegrityError"


def test_input_order_and_traceability_are_returned(database_fixture):
    session_factory, ids = database_fixture
    first = make_mapped(ids, make_record(row=51))
    second = make_mapped(ids, make_record(row=52))

    result = PersistenceEngine(session_factory).persist_batch([first, second])

    assert result.persisted_source_rows == (
        (TEST_SOURCE_FILE, "Report", 51),
        (TEST_SOURCE_FILE, "Report", 52),
    )


def test_inputs_are_immutable_and_results_are_deterministic(database_fixture):
    session_factory, ids = database_fixture
    mapped = make_mapped(ids, make_record(row=61))
    before = mapped

    result = PersistenceEngine(session_factory).persist(mapped)

    assert mapped is before
    assert mapped.raw_record.source_row == 61
    assert result.persisted_source_rows == ((TEST_SOURCE_FILE, "Report", 61),)
    assert DUPLICATE_STRATEGY == "Duplicate persistence strategy is not specified by blueprint."


def test_no_master_data_is_created_automatically(database_fixture):
    session_factory, ids = database_fixture
    before = fetch_transactions(session_factory)
    mapped = make_mapped(ids, make_record(row=71), suppliers=[])

    PersistenceEngine(session_factory).persist(mapped)

    after = fetch_transactions(session_factory)
    assert before == after