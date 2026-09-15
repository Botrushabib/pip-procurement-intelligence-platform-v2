from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.models.branch import Branch
from app.models.category import Category
from app.models.company import Company
from app.models.product import Product
from app.models.purchase_request import PurchaseRequest
from app.models.purchase_transaction import PurchaseTransaction
from app.models.receiving_event import ReceivingEvent
from app.models.receiving_event_line import ReceivingEventLine
from app.models.supplier import Supplier
from app.models.unit import Unit
from app.models.warehouse import Warehouse
from app.services.receiving_event_mapping_engine import ReceivingEventMappingEngine
from app.services.receiving_event_mapping_result import (
    CompanyCandidate,
    CompanyMetadata,
    ProductCandidate,
    SupplierCandidate,
    UnitCandidate,
    WarehouseCandidate,
)
from app.services.receiving_event_persistence_engine import (
    DUPLICATE_SOURCE_IDENTITY,
    EXACT_SOURCE_DUPLICATE,
    GATE_BLOCKED,
    MIXED_SOURCE_BATCH,
    NO_READY_LINES,
    NOT_CONFIRMED,
    ReceivingEventPersistenceEngine,
)
from tests.test_receiving_event_mapping_engine import make_row, validated


TEST_SOURCE_FILE = "receiving-event-persistence-test.xlsx"
TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pip_db"


@pytest.fixture(scope="module")
def database_fixture():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    company = Company(name="Receiving Persistence Company", code="RECEIVING_PERSIST")
    category = Category(name="Receiving Persistence Category", code="RECEIVING_CATEGORY")
    unit = Unit(name="Receiving Persistence Unit", code="RECEIVING_UNIT")
    supplier = Supplier(name="Receiving Persistence Supplier", code="RECEIVING_SUPPLIER")
    session.add_all([company, category, unit, supplier])
    session.flush()
    branch = Branch(
        company_id=company.id,
        name="Receiving Persistence Branch",
        code="RECEIVING_BRANCH",
    )
    session.add(branch)
    session.flush()
    warehouse = Warehouse(
        branch_id=branch.id,
        name="Receiving Persistence Warehouse",
        code="RECEIVING_WAREHOUSE",
    )
    product = Product(
        code="RECEIVING_PRODUCT",
        name="Receiving Persistence Product",
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
        delete(ReceivingEventLine).where(
            ReceivingEventLine.source_file == TEST_SOURCE_FILE
        )
    )
    cleanup.execute(
        delete(ReceivingEvent).where(ReceivingEvent.source_file == TEST_SOURCE_FILE)
    )
    cleanup.execute(
        delete(PurchaseTransaction).where(
            PurchaseTransaction.source_file == TEST_SOURCE_FILE
        )
    )
    cleanup.execute(
        delete(PurchaseRequest).where(PurchaseRequest.source_file == TEST_SOURCE_FILE)
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
def clear_test_data(database_fixture):
    session_factory, _ = database_fixture
    session = session_factory()
    session.execute(
        delete(ReceivingEventLine).where(
            ReceivingEventLine.source_file == TEST_SOURCE_FILE
        )
    )
    session.execute(
        delete(ReceivingEvent).where(ReceivingEvent.source_file == TEST_SOURCE_FILE)
    )
    session.execute(
        delete(PurchaseTransaction).where(
            PurchaseTransaction.source_file == TEST_SOURCE_FILE
        )
    )
    session.execute(
        delete(PurchaseRequest).where(PurchaseRequest.source_file == TEST_SOURCE_FILE)
    )
    session.commit()
    session.close()


def make_ready_decisions(ids, *rows, **changes):
    values = {
        "company_metadata": CompanyMetadata("RECEIVING_PERSIST"),
        "companies": [CompanyCandidate(ids["company"], code="RECEIVING_PERSIST")],
        "suppliers": [SupplierCandidate(ids["supplier"], name="Biotech")],
        "products": [ProductCandidate(ids["product"], code="162017", name="Receiving Persistence Product")],
        "units": [UnitCandidate(ids["unit"], name="kg")],
        "warehouses": [WarehouseCandidate(ids["warehouse"], name="Main Stores/Stock")],
    }
    values.update(changes)
    result = ReceivingEventMappingEngine().map(validated(*rows), **values)
    return tuple(result.decisions)


def fetch_events(session_factory):
    session = session_factory()
    rows = session.scalars(
        select(ReceivingEvent).where(ReceivingEvent.source_file == TEST_SOURCE_FILE)
    ).all()
    session.close()
    return rows


def fetch_lines(session_factory):
    session = session_factory()
    rows = session.scalars(
        select(ReceivingEventLine).where(
            ReceivingEventLine.source_file == TEST_SOURCE_FILE
        )
    ).all()
    session.close()
    return rows


def test_ready_decision_persists_one_event_and_one_line(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(ids, make_row(source_file=TEST_SOURCE_FILE))

    result = ReceivingEventPersistenceEngine(session_factory).persist(
        decisions, confirmed=True
    )
    events = fetch_events(session_factory)
    lines = fetch_lines(session_factory)

    assert result.persisted is True
    assert result.persisted_event_count == 1
    assert result.persisted_line_count == 1
    assert len(events) == 1
    assert len(lines) == 1


def test_same_grouping_key_creates_one_event_with_multiple_lines(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(
        ids,
        make_row(source_file=TEST_SOURCE_FILE, source_row=2),
        make_row(source_file=TEST_SOURCE_FILE, source_row=3),
    )

    result = ReceivingEventPersistenceEngine(session_factory).persist(
        decisions, confirmed=True
    )
    lines = sorted(fetch_lines(session_factory), key=lambda line: line.source_row)

    assert result.persisted_event_count == 1
    assert result.persisted_line_count == 2
    assert len(fetch_events(session_factory)) == 1
    assert [(line.line_number, line.source_row) for line in lines] == [(1, 2), (2, 3)]


def test_different_grouping_keys_create_separate_events(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(
        ids,
        make_row(source_file=TEST_SOURCE_FILE, source_row=2, raw_reference="WH/IN/00001"),
        make_row(source_file=TEST_SOURCE_FILE, source_row=3, raw_reference="WH/IN/00002"),
    )

    result = ReceivingEventPersistenceEngine(session_factory).persist(
        decisions, confirmed=True
    )

    assert result.persisted_event_count == 2
    assert result.persisted_line_count == 2
    assert len(fetch_events(session_factory)) == 2


def test_review_and_rejected_are_never_persisted(database_fixture):
    session_factory, ids = database_fixture
    review = make_ready_decisions(
        ids, make_row(source_file=TEST_SOURCE_FILE), suppliers=[]
    )[0]
    rejected = make_ready_decisions(
        ids,
        make_row(source_file=TEST_SOURCE_FILE, source_row=3),
        company_metadata=CompanyMetadata(),
    )[0]

    result = ReceivingEventPersistenceEngine(session_factory).persist(
        (review, rejected), confirmed=True
    )

    assert result.persisted is False
    assert result.gate.review_count == 1
    assert result.gate.rejected_count == 1
    assert result.error == GATE_BLOCKED
    assert fetch_events(session_factory) == []
    assert fetch_lines(session_factory) == []


def test_zero_ready_decisions_create_no_event(database_fixture):
    session_factory, ids = database_fixture
    review = make_ready_decisions(
        ids, make_row(source_file=TEST_SOURCE_FILE), suppliers=[]
    )[0]

    result = ReceivingEventPersistenceEngine(session_factory).persist(
        (review,), confirmed=True
    )

    assert result.gate.eligible_ready_count == 0
    assert NO_READY_LINES in result.gate.blocked_reasons
    assert fetch_events(session_factory) == []


def test_unconfirmed_persistence_performs_zero_writes(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(ids, make_row(source_file=TEST_SOURCE_FILE))

    result = ReceivingEventPersistenceEngine(session_factory).persist(
        decisions, confirmed=False
    )

    assert result.persisted is False
    assert result.error == NOT_CONFIRMED
    assert fetch_events(session_factory) == []
    assert fetch_lines(session_factory) == []


def test_gate_performs_no_database_access_or_writes(database_fixture):
    _, ids = database_fixture
    decisions = make_ready_decisions(ids, make_row(source_file=TEST_SOURCE_FILE))

    def fail_if_session_created():
        raise AssertionError("gate must not access the database")

    engine = ReceivingEventPersistenceEngine(fail_if_session_created)
    result = engine.gate(decisions)

    assert result.can_persist is True
    assert result.requires_confirmation is True


def test_existing_exact_source_duplicate_is_blocked(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(
        ids, make_row(source_file=TEST_SOURCE_FILE, source_row=22)
    )
    engine = ReceivingEventPersistenceEngine(session_factory)
    engine.persist(decisions, confirmed=True)

    result = engine.persist(decisions, confirmed=True)

    assert result.persisted is False
    assert result.error == EXACT_SOURCE_DUPLICATE
    assert result.duplicate_source_rows == ((TEST_SOURCE_FILE, "Report", 22),)
    assert len(fetch_events(session_factory)) == 1
    assert len(fetch_lines(session_factory)) == 1


def test_duplicate_source_identity_inside_batch_is_blocked(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(
        ids,
        make_row(source_file=TEST_SOURCE_FILE, source_row=23),
        make_row(source_file=TEST_SOURCE_FILE, source_row=23),
    )

    result = ReceivingEventPersistenceEngine(session_factory).persist(
        decisions, confirmed=True
    )

    assert result.persisted is False
    assert DUPLICATE_SOURCE_IDENTITY in result.gate.blocked_reasons
    assert result.duplicate_source_rows == ((TEST_SOURCE_FILE, "Report", 23),)
    assert fetch_events(session_factory) == []


def test_mixed_source_batch_is_blocked_before_database_access(database_fixture):
    _, ids = database_fixture
    decisions = make_ready_decisions(
        ids,
        make_row(source_file=TEST_SOURCE_FILE, source_row=24),
        make_row(source_file="other-receiving.xlsx", source_row=25),
    )

    def fail_if_session_created():
        raise AssertionError("mixed source batch must be blocked before database access")

    result = ReceivingEventPersistenceEngine(fail_if_session_created).persist(
        decisions, confirmed=True
    )

    assert result.persisted is False
    assert result.error == GATE_BLOCKED
    assert MIXED_SOURCE_BATCH in result.gate.blocked_reasons


def test_raw_provenance_and_raw_values_are_preserved(database_fixture):
    session_factory, ids = database_fixture
    row = make_row(
        source_file=TEST_SOURCE_FILE,
        raw_supplier="Raw Supplier",
        raw_product="[162017] Raw Product",
        raw_item_description="Raw Description",
        raw_destination="Raw Destination",
        raw_unit="raw kg",
        raw_quantity=Decimal("2.50"),
        raw_unit_price=Decimal("10.25"),
        raw_subtotal=Decimal("25.625"),
    )
    decisions = make_ready_decisions(
        ids,
        row,
        suppliers=[SupplierCandidate(ids["supplier"], name="Raw Supplier")],
        units=[UnitCandidate(ids["unit"], name="raw kg")],
        warehouses=[WarehouseCandidate(ids["warehouse"], name="Raw Destination")],
    )
    ReceivingEventPersistenceEngine(session_factory).persist(decisions, confirmed=True)

    event = fetch_events(session_factory)[0]
    line = fetch_lines(session_factory)[0]

    assert (line.source_file, line.source_sheet, line.source_row) == (
        TEST_SOURCE_FILE,
        "Report",
        row.source_row,
    )
    assert event.raw_supplier == "Raw Supplier"
    assert line.raw_product == "[162017] Raw Product"
    assert line.raw_item_description == "Raw Description"
    assert line.raw_destination == "Raw Destination"
    assert line.raw_unit == "raw kg"
    assert line.raw_quantity == "2.50"
    assert line.raw_unit_price == "10.25"
    assert line.raw_subtotal == "25.625"


def test_normalized_ids_and_numeric_values_are_preserved(database_fixture):
    session_factory, ids = database_fixture
    row = make_row(
        source_file=TEST_SOURCE_FILE,
        raw_quantity=Decimal("2.50"),
        raw_unit_price=Decimal("10.25"),
        raw_subtotal=Decimal("25.625"),
    )
    decisions = make_ready_decisions(ids, row)
    ReceivingEventPersistenceEngine(session_factory).persist(decisions, confirmed=True)

    event = fetch_events(session_factory)[0]
    line = fetch_lines(session_factory)[0]

    assert (event.company_id, event.supplier_id, event.warehouse_id) == (
        ids["company"],
        ids["supplier"],
        ids["warehouse"],
    )
    assert (line.product_id, line.unit_id) == (ids["product"], ids["unit"])
    assert line.quantity == Decimal("2.50")
    assert line.unit_price == Decimal("10.25")
    assert line.subtotal == Decimal("25.625")
    assert event.event_date == date(2026, 8, 15)


def test_database_failure_rolls_back_complete_batch(database_fixture):
    session_factory, ids = database_fixture
    good, bad = make_ready_decisions(
        ids,
        make_row(source_file=TEST_SOURCE_FILE, source_row=26),
        make_row(
            source_file=TEST_SOURCE_FILE,
            source_row=27,
            raw_product="[162018] Invalid Product",
            product_code="162018",
        ),
        products=[
            ProductCandidate(ids["product"], code="162017"),
            ProductCandidate(999999, code="162018"),
        ],
    )
    result = ReceivingEventPersistenceEngine(session_factory).persist(
        (good, bad), confirmed=True
    )

    assert result.persisted is False
    assert result.error == "IntegrityError"
    assert result.persisted_event_count == 0
    assert result.persisted_line_count == 0
    assert fetch_events(session_factory) == []
    assert fetch_lines(session_factory) == []


def test_business_duplicates_remain_distinct_lines(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(
        ids,
        make_row(source_file=TEST_SOURCE_FILE, source_row=28),
        make_row(source_file=TEST_SOURCE_FILE, source_row=29),
    )

    ReceivingEventPersistenceEngine(session_factory).persist(
        decisions, confirmed=True
    )

    lines = sorted(fetch_lines(session_factory), key=lambda line: line.source_row)
    assert len(fetch_events(session_factory)) == 1
    assert [(line.source_row, line.line_number) for line in lines] == [(28, 1), (29, 2)]


def test_reference_is_document_level_and_shared_by_multiple_lines(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(
        ids,
        make_row(source_file=TEST_SOURCE_FILE, source_row=30, raw_reference="WH/IN/SHARED"),
        make_row(source_file=TEST_SOURCE_FILE, source_row=31, raw_reference="WH/IN/SHARED"),
    )

    ReceivingEventPersistenceEngine(session_factory).persist(
        decisions, confirmed=True
    )

    event = fetch_events(session_factory)[0]
    lines = fetch_lines(session_factory)
    assert event.receiving_reference == "WH/IN/SHARED"
    assert len(lines) == 2
    assert {line.raw_reference for line in lines} == {"WH/IN/SHARED"}


def test_unrelated_purchase_records_are_not_modified(database_fixture):
    session_factory, ids = database_fixture
    session = session_factory()
    request = PurchaseRequest(
        company_id=ids["company"],
        warehouse_id=ids["warehouse"],
        destination_type="WAREHOUSE",
        request_date=date(2026, 8, 15),
        status="DRAFT",
        source_file=TEST_SOURCE_FILE,
    )
    transaction = PurchaseTransaction(
        supplier_id=ids["supplier"],
        product_id=ids["product"],
        unit_id=ids["unit"],
        warehouse_id=ids["warehouse"],
        transaction_date=date(2026, 8, 15),
        source_file=TEST_SOURCE_FILE,
    )
    session.add_all([request, transaction])
    session.commit()
    request_id, transaction_id = request.id, transaction.id
    session.close()

    decisions = make_ready_decisions(ids, make_row(source_file=TEST_SOURCE_FILE, source_row=32))
    ReceivingEventPersistenceEngine(session_factory).persist(decisions, confirmed=True)

    session = session_factory()
    persisted_request = session.get(PurchaseRequest, request_id)
    persisted_transaction = session.get(PurchaseTransaction, transaction_id)
    session.close()
    assert persisted_request is not None
    assert persisted_transaction is not None
    assert persisted_request.status == "DRAFT"
    assert persisted_transaction.product_id == ids["product"]


def test_persistence_requires_explicit_confirmation(database_fixture):
    session_factory, ids = database_fixture
    decisions = make_ready_decisions(ids, make_row(source_file=TEST_SOURCE_FILE))
    engine = ReceivingEventPersistenceEngine(session_factory)

    preview = engine.gate(decisions)
    result = engine.persist(decisions, confirmed=False)

    assert preview.requires_confirmation is True
    assert result.error == NOT_CONFIRMED
    assert fetch_events(session_factory) == []
