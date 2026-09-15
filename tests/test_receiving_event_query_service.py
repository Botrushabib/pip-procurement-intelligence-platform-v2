from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete, func, select
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
from app.services.receiving_event_query_service import (
    ReceivingEventFilter,
    ReceivingEventLineRead,
    ReceivingEventLineReadDTO,
    ReceivingEventQueryFilter,
    ReceivingEventQueryService,
    ReceivingEventRead,
    ReceivingEventReadDTO,
)


TEST_SOURCE_FILE = "receiving-event-query-test.xlsx"
TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pip_db"


@pytest.fixture(scope="module")
def database_fixture():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()

    company_1 = Company(name="Query Test Company 1", code="QUERY_CO_1")
    company_2 = Company(name="Query Test Company 2", code="QUERY_CO_2")
    category = Category(name="Query Test Category", code="QUERY_CATEGORY")
    unit_1 = Unit(name="kg", code="QUERY_UNIT_KG")
    unit_2 = Unit(name="pcs", code="QUERY_UNIT_PCS")
    supplier_1 = Supplier(name="Query Supplier 1", code="QUERY_SUPPLIER_1")
    supplier_2 = Supplier(name="Query Supplier 2", code="QUERY_SUPPLIER_2")

    session.add_all([company_1, company_2, category, unit_1, unit_2, supplier_1, supplier_2])
    session.flush()

    branch_1 = Branch(
        company_id=company_1.id,
        name="Query Test Branch 1",
        code="QUERY_BRANCH_1",
    )
    branch_2 = Branch(
        company_id=company_2.id,
        name="Query Test Branch 2",
        code="QUERY_BRANCH_2",
    )
    session.add_all([branch_1, branch_2])
    session.flush()

    warehouse_1 = Warehouse(
        branch_id=branch_1.id,
        name="Query Warehouse 1",
        code="QUERY_WH_1",
    )
    warehouse_2 = Warehouse(
        branch_id=branch_2.id,
        name="Query Warehouse 2",
        code="QUERY_WH_2",
    )
    product_1 = Product(
        code="QUERY_PROD_1",
        name="Query Test Product 1",
        category_id=category.id,
        unit_id=unit_1.id,
    )
    product_2 = Product(
        code="QUERY_PROD_2",
        name="Query Test Product 2",
        category_id=category.id,
        unit_id=unit_2.id,
    )
    session.add_all([warehouse_1, warehouse_2, product_1, product_2])
    session.commit()

    ids = {
        "company_1": company_1.id,
        "company_2": company_2.id,
        "category": category.id,
        "unit_1": unit_1.id,
        "unit_2": unit_2.id,
        "supplier_1": supplier_1.id,
        "supplier_2": supplier_2.id,
        "branch_1": branch_1.id,
        "branch_2": branch_2.id,
        "warehouse_1": warehouse_1.id,
        "warehouse_2": warehouse_2.id,
        "product_1": product_1.id,
        "product_2": product_2.id,
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
    cleanup.execute(delete(Product).where(Product.id.in_([ids["product_1"], ids["product_2"]])))
    cleanup.execute(delete(Warehouse).where(Warehouse.id.in_([ids["warehouse_1"], ids["warehouse_2"]])))
    cleanup.execute(delete(Branch).where(Branch.id.in_([ids["branch_1"], ids["branch_2"]])))
    cleanup.execute(delete(Supplier).where(Supplier.id.in_([ids["supplier_1"], ids["supplier_2"]])))
    cleanup.execute(delete(Unit).where(Unit.id.in_([ids["unit_1"], ids["unit_2"]])))
    cleanup.execute(delete(Category).where(Category.id == ids["category"]))
    cleanup.execute(delete(Company).where(Company.id.in_([ids["company_1"], ids["company_2"]])))
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


def create_event_with_lines(
    session_factory,
    ids,
    receiving_reference: str = "REC-001",
    event_date: date = date(2026, 3, 1),
    company_key: str = "company_1",
    supplier_key: str = "supplier_1",
    warehouse_key: str = "warehouse_1",
    source_file: str = TEST_SOURCE_FILE,
    source_sheet: str = "Sheet1",
    source_row: int | None = 2,
    raw_reference: str | None = "RAW-REF-001",
    raw_supplier: str | None = "Raw Supplier One",
    raw_destination: str | None = "Raw Destination WH1",
    raw_date_1: str | None = "2026-03-01",
    raw_date_2: str | None = None,
    lines_data: list[dict] | None = None,
) -> int:
    session = session_factory()
    event = ReceivingEvent(
        company_id=ids[company_key],
        supplier_id=ids[supplier_key],
        warehouse_id=ids[warehouse_key],
        receiving_reference=receiving_reference,
        event_date=event_date,
        raw_reference=raw_reference,
        raw_supplier=raw_supplier,
        raw_destination=raw_destination,
        raw_date_1=raw_date_1,
        raw_date_2=raw_date_2,
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
    )
    session.add(event)
    session.flush()

    if lines_data is None:
        lines_data = [
            {
                "line_number": 1,
                "product_key": "product_1",
                "unit_key": "unit_1",
                "quantity": Decimal("100.50"),
                "unit_price": Decimal("25.00"),
                "subtotal": Decimal("2512.50"),
                "source_row": 2,
                "raw_product": "Raw Product 1",
                "raw_item_description": "Item Description 1",
                "raw_reference": "RAW-REF-001",
                "raw_quantity": "100.50",
                "raw_unit": "kg",
                "raw_unit_price": "25.00",
                "raw_subtotal": "2512.50",
                "raw_destination": "Raw Destination WH1",
                "raw_supplier": "Raw Supplier One",
                "raw_date_1": "2026-03-01",
                "raw_date_2": None,
            }
        ]

    for ld in lines_data:
        line = ReceivingEventLine(
            receiving_event_id=event.id,
            line_number=ld.get("line_number", 1),
            product_id=ids[ld.get("product_key", "product_1")],
            unit_id=ids[ld.get("unit_key", "unit_1")],
            quantity=ld.get("quantity", Decimal("10.0")),
            unit_price=ld.get("unit_price", Decimal("5.0")),
            subtotal=ld.get("subtotal", Decimal("50.0")),
            raw_product=ld.get("raw_product", "Raw Prod"),
            raw_item_description=ld.get("raw_item_description", "Raw Desc"),
            raw_reference=ld.get("raw_reference", "RAW-REF"),
            raw_quantity=ld.get("raw_quantity", "10.0"),
            raw_unit=ld.get("raw_unit", "kg"),
            raw_unit_price=ld.get("raw_unit_price", "5.0"),
            raw_subtotal=ld.get("raw_subtotal", "50.0"),
            raw_destination=ld.get("raw_destination", "Raw Dest"),
            raw_supplier=ld.get("raw_supplier", "Raw Sup"),
            raw_date_1=ld.get("raw_date_1", "2026-03-01"),
            raw_date_2=ld.get("raw_date_2"),
            source_file=source_file,
            source_sheet=source_sheet,
            source_row=ld.get("source_row", 2),
        )
        session.add(line)

    session.commit()
    event_id = event.id
    session.close()
    return event_id


def test_empty_result_behavior(database_fixture):
    session_factory, ids = database_fixture
    service = ReceivingEventQueryService(session_factory=session_factory)

    result = service.query()
    assert isinstance(result, tuple)
    assert len(result) == 0

    single = service.get_by_id(999999)
    assert single is None

    filtered = service.query(ReceivingEventQueryFilter(event_id=999999))
    assert isinstance(filtered, tuple)
    assert len(filtered) == 0


def test_query_by_event_id(database_fixture):
    session_factory, ids = database_fixture
    ev1_id = create_event_with_lines(session_factory, ids, receiving_reference="REC-EV-1")
    ev2_id = create_event_with_lines(session_factory, ids, receiving_reference="REC-EV-2")

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.query(ReceivingEventQueryFilter(event_id=ev1_id))

    assert len(res) == 1
    assert res[0].id == ev1_id
    assert res[0].receiving_reference == "REC-EV-1"

    single = service.get_by_id(ev2_id)
    assert single is not None
    assert single.id == ev2_id
    assert single.receiving_reference == "REC-EV-2"


def test_query_by_company_id(database_fixture):
    session_factory, ids = database_fixture
    ev1_id = create_event_with_lines(session_factory, ids, company_key="company_1", receiving_reference="REC-CO-1")
    create_event_with_lines(session_factory, ids, company_key="company_2", receiving_reference="REC-CO-2")

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.query(ReceivingEventQueryFilter(company_id=ids["company_1"]))

    assert len(res) == 1
    assert res[0].id == ev1_id
    assert res[0].company_id == ids["company_1"]


def test_query_by_supplier_id(database_fixture):
    session_factory, ids = database_fixture
    ev1_id = create_event_with_lines(session_factory, ids, supplier_key="supplier_1", receiving_reference="REC-SUP-1")
    create_event_with_lines(session_factory, ids, supplier_key="supplier_2", receiving_reference="REC-SUP-2")

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.query(ReceivingEventQueryFilter(supplier_id=ids["supplier_1"]))

    assert len(res) == 1
    assert res[0].id == ev1_id
    assert res[0].supplier_id == ids["supplier_1"]


def test_query_by_warehouse_id(database_fixture):
    session_factory, ids = database_fixture
    ev1_id = create_event_with_lines(session_factory, ids, warehouse_key="warehouse_1", receiving_reference="REC-WH-1")
    create_event_with_lines(session_factory, ids, warehouse_key="warehouse_2", receiving_reference="REC-WH-2")

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.query(ReceivingEventQueryFilter(warehouse_id=ids["warehouse_1"]))

    assert len(res) == 1
    assert res[0].id == ev1_id
    assert res[0].warehouse_id == ids["warehouse_1"]


def test_query_by_date_from_and_date_to(database_fixture):
    session_factory, ids = database_fixture
    ev1_id = create_event_with_lines(session_factory, ids, event_date=date(2026, 1, 10), receiving_reference="REC-D1")
    ev2_id = create_event_with_lines(session_factory, ids, event_date=date(2026, 2, 15), receiving_reference="REC-D2")
    ev3_id = create_event_with_lines(session_factory, ids, event_date=date(2026, 3, 20), receiving_reference="REC-D3")

    service = ReceivingEventQueryService(session_factory=session_factory)

    res_from = service.query(ReceivingEventQueryFilter(date_from=date(2026, 2, 1)))
    assert [e.id for e in res_from] == [ev2_id, ev3_id]

    res_to = service.query(ReceivingEventQueryFilter(date_to=date(2026, 2, 28)))
    assert [e.id for e in res_to] == [ev1_id, ev2_id]

    res_between = service.query(
        ReceivingEventQueryFilter(date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))
    )
    assert [e.id for e in res_between] == [ev2_id]


def test_query_by_receiving_reference(database_fixture):
    session_factory, ids = database_fixture
    ev1_id = create_event_with_lines(session_factory, ids, receiving_reference="REC-REF-AAA")
    create_event_with_lines(session_factory, ids, receiving_reference="REC-REF-BBB")

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.query(ReceivingEventQueryFilter(receiving_reference="REC-REF-AAA"))

    assert len(res) == 1
    assert res[0].id == ev1_id
    assert res[0].receiving_reference == "REC-REF-AAA"


def test_query_by_source_file_sheet_row(database_fixture):
    session_factory, ids = database_fixture
    ev1_id = create_event_with_lines(
        session_factory,
        ids,
        source_file=TEST_SOURCE_FILE,
        source_sheet="SheetA",
        source_row=10,
        receiving_reference="REC-SRC-1",
    )
    create_event_with_lines(
        session_factory,
        ids,
        source_file=TEST_SOURCE_FILE,
        source_sheet="SheetB",
        source_row=20,
        receiving_reference="REC-SRC-2",
    )
    create_event_with_lines(
        session_factory,
        ids,
        source_file=TEST_SOURCE_FILE,
        source_sheet="SheetA",
        source_row=None,
        receiving_reference="REC-SRC-3",
    )

    service = ReceivingEventQueryService(session_factory=session_factory)

    res_sheet = service.query(ReceivingEventQueryFilter(source_sheet="SheetA"))
    assert len(res_sheet) == 2

    res_row = service.query(ReceivingEventQueryFilter(source_row=10))
    assert len(res_row) == 1
    assert res_row[0].id == ev1_id
    assert res_row[0].source_row == 10

    res_all_three = service.query(
        ReceivingEventQueryFilter(
            source_file=TEST_SOURCE_FILE,
            source_sheet="SheetA",
            source_row=10,
        )
    )
    assert len(res_all_three) == 1
    assert res_all_three[0].id == ev1_id


def test_multiple_optional_filters_compose_correctly(database_fixture):
    session_factory, ids = database_fixture
    ev_target_id = create_event_with_lines(
        session_factory,
        ids,
        company_key="company_1",
        supplier_key="supplier_1",
        warehouse_key="warehouse_1",
        event_date=date(2026, 4, 15),
        receiving_reference="REC-COMPOSE-1",
        source_file=TEST_SOURCE_FILE,
        source_sheet="SheetCompose",
        source_row=5,
    )
    # Different company
    create_event_with_lines(
        session_factory,
        ids,
        company_key="company_2",
        supplier_key="supplier_1",
        warehouse_key="warehouse_1",
        event_date=date(2026, 4, 15),
        receiving_reference="REC-COMPOSE-2",
        source_file=TEST_SOURCE_FILE,
        source_sheet="SheetCompose",
        source_row=5,
    )
    # Different date
    create_event_with_lines(
        session_factory,
        ids,
        company_key="company_1",
        supplier_key="supplier_1",
        warehouse_key="warehouse_1",
        event_date=date(2026, 5, 15),
        receiving_reference="REC-COMPOSE-3",
        source_file=TEST_SOURCE_FILE,
        source_sheet="SheetCompose",
        source_row=5,
    )

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.query(
        ReceivingEventQueryFilter(
            company_id=ids["company_1"],
            supplier_id=ids["supplier_1"],
            warehouse_id=ids["warehouse_1"],
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
            source_file=TEST_SOURCE_FILE,
            source_sheet="SheetCompose",
            source_row=5,
        )
    )

    assert len(res) == 1
    assert res[0].id == ev_target_id
    assert res[0].receiving_reference == "REC-COMPOSE-1"


def test_nested_lines_returned_correctly(database_fixture):
    session_factory, ids = database_fixture
    lines_input = [
        {
            "line_number": 1,
            "product_key": "product_1",
            "unit_key": "unit_1",
            "quantity": Decimal("50.00"),
            "unit_price": Decimal("10.00"),
            "subtotal": Decimal("500.00"),
            "source_row": 2,
        },
        {
            "line_number": 2,
            "product_key": "product_2",
            "unit_key": "unit_2",
            "quantity": Decimal("20.00"),
            "unit_price": Decimal("15.00"),
            "subtotal": Decimal("300.00"),
            "source_row": 3,
        },
    ]
    ev_id = create_event_with_lines(
        session_factory, ids, receiving_reference="REC-NESTED", lines_data=lines_input
    )

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.get_by_id(ev_id)

    assert res is not None
    assert isinstance(res.lines, tuple)
    assert len(res.lines) == 2
    assert isinstance(res.lines[0], ReceivingEventLineReadDTO)
    assert isinstance(res.lines[1], ReceivingEventLineReadDTO)
    assert res.lines[0].receiving_event_id == ev_id
    assert res.lines[1].receiving_event_id == ev_id
    assert res.lines[0].line_number == 1
    assert res.lines[1].line_number == 2


def test_lines_ordered_deterministically_by_line_number(database_fixture):
    session_factory, ids = database_fixture
    # Insert intentionally out-of-order line numbers: 3, 1, 2
    lines_input = [
        {"line_number": 3, "quantity": Decimal("30"), "source_row": 4},
        {"line_number": 1, "quantity": Decimal("10"), "source_row": 2},
        {"line_number": 2, "quantity": Decimal("20"), "source_row": 3},
    ]
    ev_id = create_event_with_lines(
        session_factory, ids, receiving_reference="REC-SORT-LINES", lines_data=lines_input
    )

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.get_by_id(ev_id)

    assert res is not None
    assert [line.line_number for line in res.lines] == [1, 2, 3]


def test_events_ordered_deterministically(database_fixture):
    session_factory, ids = database_fixture
    # Create events with varied dates and references
    ev1 = create_event_with_lines(session_factory, ids, event_date=date(2026, 3, 2), receiving_reference="REC-B")
    ev2 = create_event_with_lines(session_factory, ids, event_date=date(2026, 3, 1), receiving_reference="REC-Z")
    ev3 = create_event_with_lines(session_factory, ids, event_date=date(2026, 3, 1), receiving_reference="REC-A")
    ev4 = create_event_with_lines(session_factory, ids, event_date=date(2026, 3, 1), receiving_reference="REC-A")

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.query()

    # Deterministic order: event_date, receiving_reference, id
    expected_order = [ev3, ev4, ev2, ev1]
    assert [e.id for e in res] == expected_order


def test_normalized_ids_and_numeric_values_preserved(database_fixture):
    session_factory, ids = database_fixture
    lines_input = [
        {
            "line_number": 1,
            "product_key": "product_1",
            "unit_key": "unit_1",
            "quantity": Decimal("123.456"),
            "unit_price": Decimal("78.90"),
            "subtotal": Decimal("9740.6784"),
            "source_row": 2,
        }
    ]
    ev_id = create_event_with_lines(
        session_factory,
        ids,
        company_key="company_1",
        supplier_key="supplier_1",
        warehouse_key="warehouse_1",
        receiving_reference="REC-NORM-1",
        lines_data=lines_input,
    )

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.get_by_id(ev_id)

    assert res is not None
    assert res.company_id == ids["company_1"]
    assert res.supplier_id == ids["supplier_1"]
    assert res.warehouse_id == ids["warehouse_1"]
    assert len(res.lines) == 1

    line = res.lines[0]
    assert line.product_id == ids["product_1"]
    assert line.unit_id == ids["unit_1"]
    assert line.quantity == Decimal("123.456")
    assert line.unit_price == Decimal("78.90")
    assert line.subtotal == Decimal("9740.6784")


def test_raw_values_and_source_provenance_preserved(database_fixture):
    session_factory, ids = database_fixture
    lines_input = [
        {
            "line_number": 1,
            "raw_product": "Raw P1 Description",
            "raw_item_description": "Item detailed desc",
            "raw_reference": "RAW-PO-99",
            "raw_quantity": "123.456",
            "raw_unit": "KG-RAW",
            "raw_unit_price": "78.90",
            "raw_subtotal": "9740.6784",
            "raw_destination": "Main Warehouse Stock",
            "raw_supplier": "Biotech Supplier Corp",
            "raw_date_1": "01/03/2026",
            "raw_date_2": "02/03/2026",
            "source_row": 15,
        }
    ]
    ev_id = create_event_with_lines(
        session_factory,
        ids,
        source_file=TEST_SOURCE_FILE,
        source_sheet="CustomSheet",
        source_row=12,
        raw_reference="RAW-PO-99",
        raw_supplier="Biotech Supplier Corp",
        raw_destination="Main Warehouse Stock",
        raw_date_1="01/03/2026",
        raw_date_2="02/03/2026",
        lines_data=lines_input,
    )

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.get_by_id(ev_id)

    assert res is not None
    # Event raw values and source provenance
    assert res.source_file == TEST_SOURCE_FILE
    assert res.source_sheet == "CustomSheet"
    assert res.source_row == 12
    assert res.raw_reference == "RAW-PO-99"
    assert res.raw_supplier == "Biotech Supplier Corp"
    assert res.raw_destination == "Main Warehouse Stock"
    assert res.raw_date_1 == "01/03/2026"
    assert res.raw_date_2 == "02/03/2026"

    # Line raw values and source provenance
    line = res.lines[0]
    assert line.source_file == TEST_SOURCE_FILE
    assert line.source_sheet == "CustomSheet"
    assert line.source_row == 15
    assert line.raw_product == "Raw P1 Description"
    assert line.raw_item_description == "Item detailed desc"
    assert line.raw_reference == "RAW-PO-99"
    assert line.raw_quantity == "123.456"
    assert line.raw_unit == "KG-RAW"
    assert line.raw_unit_price == "78.90"
    assert line.raw_subtotal == "9740.6784"
    assert line.raw_destination == "Main Warehouse Stock"
    assert line.raw_supplier == "Biotech Supplier Corp"
    assert line.raw_date_1 == "01/03/2026"
    assert line.raw_date_2 == "02/03/2026"


def test_multiple_events_and_business_duplicates_remain_distinct(database_fixture):
    session_factory, ids = database_fixture
    # Create two events with identical business keys (same supplier, warehouse, date, ref)
    ev1_id = create_event_with_lines(
        session_factory,
        ids,
        receiving_reference="DUP-REF-100",
        event_date=date(2026, 3, 1),
        source_row=2,
    )
    ev2_id = create_event_with_lines(
        session_factory,
        ids,
        receiving_reference="DUP-REF-100",
        event_date=date(2026, 3, 1),
        source_row=3,
    )

    service = ReceivingEventQueryService(session_factory=session_factory)
    res = service.query(ReceivingEventQueryFilter(receiving_reference="DUP-REF-100"))

    assert len(res) == 2
    assert res[0].id == ev1_id
    assert res[1].id == ev2_id
    assert res[0].id != res[1].id
    assert res[0].source_row == 2
    assert res[1].source_row == 3


def test_query_performs_no_writes_and_data_remains_unchanged(database_fixture):
    session_factory, ids = database_fixture
    ev_id = create_event_with_lines(
        session_factory,
        ids,
        receiving_reference="REC-NO-WRITE",
        event_date=date(2026, 3, 1),
    )

    session = session_factory()
    event_count_before = session.scalar(
        select(func.count(ReceivingEvent.id)).where(ReceivingEvent.source_file == TEST_SOURCE_FILE)
    )
    line_count_before = session.scalar(
        select(func.count(ReceivingEventLine.id)).where(ReceivingEventLine.source_file == TEST_SOURCE_FILE)
    )
    session.close()

    service = ReceivingEventQueryService(session_factory=session_factory)
    result = service.query()
    assert len(result) == 1

    single = service.get_by_id(ev_id)
    assert single is not None

    session = session_factory()
    event_count_after = session.scalar(
        select(func.count(ReceivingEvent.id)).where(ReceivingEvent.source_file == TEST_SOURCE_FILE)
    )
    line_count_after = session.scalar(
        select(func.count(ReceivingEventLine.id)).where(ReceivingEventLine.source_file == TEST_SOURCE_FILE)
    )
    # Verify entity fields in DB are completely unmodified
    db_event = session.get(ReceivingEvent, ev_id)
    assert db_event is not None
    assert db_event.receiving_reference == "REC-NO-WRITE"
    session.close()

    assert event_count_before == event_count_after
    assert line_count_before == line_count_after


def test_dtos_are_immutable(database_fixture):
    session_factory, ids = database_fixture
    ev_id = create_event_with_lines(session_factory, ids, receiving_reference="REC-IMMUTABLE")

    service = ReceivingEventQueryService(session_factory=session_factory)
    ev_dto = service.get_by_id(ev_id)
    assert ev_dto is not None

    with pytest.raises(FrozenInstanceError):
        ev_dto.receiving_reference = "MUTATED"

    with pytest.raises(FrozenInstanceError):
        ev_dto.lines[0].quantity = Decimal("999")

    filter_dto = ReceivingEventQueryFilter(event_id=123)
    with pytest.raises(FrozenInstanceError):
        filter_dto.event_id = 456
