from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.models.branch import Branch
from app.models.category import Category
from app.models.company import Company
from app.models.product import Product
from app.models.purchase_request import PurchaseRequest, PurchaseRequestStatus
from app.models.purchase_request_line import PurchaseRequestLine
from app.models.unit import Unit
from app.models.warehouse import Warehouse
from app.services.mapping_engine import WAREHOUSE
from app.services.purchase_request_mapping_decision import (
    DecisionStatus,
    PurchaseRequestMappingDecisionEngine,
    ReasonCode,
)
from app.services.purchase_request_mapping_engine import (
    MappingMethod,
    MappingStatus,
    ProductCandidate,
    PurchaseRequestMappingEngine,
    UnitCandidate,
)
from app.services.purchase_request_persistence_engine import (
    GATE_BLOCKED,
    NO_READY_LINES,
    NOT_CONFIRMED,
    ImportMetadata,
    PurchaseRequestPersistenceEngine,
)
from app.services.purchase_request_reader import (
    PurchaseRequestExcelReader,
    QuantityClassification,
    RowClassification,
)
from app.services.purchase_request_validation_engine import (
    PurchaseRequestValidationEngine,
    ValidationStatus,
)


TEST_SOURCE_FILENAME = "pr_e2e_integration.xlsx"
TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pip_db"

HEADERS = ["Internal Reference", "Name", "Item description", "Unit", "pr"]

PRODUCT_CODE = "PR_E2E_PRODUCT"
PRODUCT_NAME = "PR E2E Test Product"
ITEM_DESCRIPTION = "PR E2E Description"
UNIT_NAME = "PR E2E Test Unit"
QUANTITY = 500


@pytest.fixture(scope="module")
def database_fixture():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    company = Company(name="PR E2E Test Company", code="PR_E2E_COMPANY")
    category = Category(name="PR E2E Test Category", code="PR_E2E_CATEGORY")
    unit = Unit(name=UNIT_NAME, code="PR_E2E_UNIT")
    session.add_all([company, category, unit])
    session.flush()
    branch = Branch(company_id=company.id, name="PR E2E Test Branch", code="PR_E2E_BRANCH")
    session.add(branch)
    session.flush()
    warehouse = Warehouse(
        branch_id=branch.id, name="PR E2E Test Warehouse", code="PR_E2E_WAREHOUSE"
    )
    product = Product(
        code=PRODUCT_CODE,
        name=PRODUCT_NAME,
        category_id=category.id,
        unit_id=unit.id,
    )
    session.add_all([warehouse, product])
    session.commit()
    ids = {
        "company": company.id,
        "category": category.id,
        "unit": unit.id,
        "branch": branch.id,
        "warehouse": warehouse.id,
        "product": product.id,
    }
    session.close()

    yield session_factory, ids

    cleanup = session_factory()
    cleanup.execute(
        delete(PurchaseRequestLine).where(
            PurchaseRequestLine.source_file.endswith(TEST_SOURCE_FILENAME)
        )
    )
    cleanup.execute(
        delete(PurchaseRequest).where(
            PurchaseRequest.source_file.endswith(TEST_SOURCE_FILENAME)
        )
    )
    cleanup.execute(delete(Product).where(Product.id == ids["product"]))
    cleanup.execute(delete(Warehouse).where(Warehouse.id == ids["warehouse"]))
    cleanup.execute(delete(Branch).where(Branch.id == ids["branch"]))
    cleanup.execute(delete(Unit).where(Unit.id == ids["unit"]))
    cleanup.execute(delete(Category).where(Category.id == ids["category"]))
    cleanup.execute(delete(Company).where(Company.id == ids["company"]))
    cleanup.commit()
    cleanup.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def clear_test_requests(database_fixture):
    session_factory, _ = database_fixture
    session = session_factory()
    session.execute(
        delete(PurchaseRequestLine).where(
            PurchaseRequestLine.source_file.endswith(TEST_SOURCE_FILENAME)
        )
    )
    session.execute(
        delete(PurchaseRequest).where(
            PurchaseRequest.source_file.endswith(TEST_SOURCE_FILENAME)
        )
    )
    session.commit()
    session.close()

    yield

    session = session_factory()
    session.execute(
        delete(PurchaseRequestLine).where(
            PurchaseRequestLine.source_file.endswith(TEST_SOURCE_FILENAME)
        )
    )
    session.execute(
        delete(PurchaseRequest).where(
            PurchaseRequest.source_file.endswith(TEST_SOURCE_FILENAME)
        )
    )
    session.commit()
    session.close()


def create_workbook(path: Path, rows: list[list], sheet_name: str = "Sheet1") -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append(HEADERS)
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def load_candidates(session_factory):
    session = session_factory()
    try:
        products = [
            ProductCandidate(id=product.id, code=product.code, name=product.name)
            for product in session.scalars(select(Product)).all()
        ]
        units = [
            UnitCandidate(id=unit.id, name=unit.name)
            for unit in session.scalars(select(Unit)).all()
        ]
    finally:
        session.close()
    return products, units


def fetch_requests(session_factory):
    session = session_factory()
    requests = session.scalars(
        select(PurchaseRequest).where(
            PurchaseRequest.source_file.endswith(TEST_SOURCE_FILENAME)
        )
    ).all()
    session.close()
    return requests


def fetch_lines(session_factory):
    session = session_factory()
    lines = session.scalars(
        select(PurchaseRequestLine).where(
            PurchaseRequestLine.source_file.endswith(TEST_SOURCE_FILENAME)
        )
    ).all()
    session.close()
    return lines


def test_full_pipeline_persists_ready_line_end_to_end(database_fixture, tmp_path):
    session_factory, ids = database_fixture
    source_path = tmp_path / TEST_SOURCE_FILENAME
    create_workbook(
        source_path,
        [[PRODUCT_CODE, PRODUCT_NAME, ITEM_DESCRIPTION, UNIT_NAME, QUANTITY]],
    )

    # Stage 1: real Excel reader
    sheet = PurchaseRequestExcelReader().read(source_path)
    assert sheet.source_file == str(source_path)
    assert sheet.source_sheet == "Sheet1"
    assert sheet.product_row_count == 1
    row = sheet.product_rows[0]
    assert row.row_classification is RowClassification.PRODUCT_ROW
    assert row.source_row == 2
    assert row.quantity.classification is QuantityClassification.PURE_NUMERIC
    assert row.quantity.quantity_value == Decimal("500")

    # Stage 2: real validation engine
    validations = PurchaseRequestValidationEngine().validate(sheet.rows)
    assert len(validations) == 1
    validation = validations[0]
    assert validation.status is ValidationStatus.VALID
    assert validation.eligible_for_next_stage is True

    # Stage 3: real mapping engine against real master data
    products, units = load_candidates(session_factory)
    mapping = PurchaseRequestMappingEngine().map(validation, products=products, units=units)
    assert mapping.product.status is MappingStatus.MAPPED
    assert mapping.product.mapping_method is MappingMethod.INTERNAL_REFERENCE_EXACT
    assert mapping.product.normalized_product_id == ids["product"]
    assert mapping.unit.status is MappingStatus.MAPPED
    assert mapping.unit.mapping_method is MappingMethod.UNIT_NAME_EXACT
    assert mapping.unit.normalized_unit_id == ids["unit"]

    # Stage 4: real decision engine
    decision = PurchaseRequestMappingDecisionEngine().decide(validation, mapping)
    assert decision.decision_status is DecisionStatus.READY
    assert decision.eligible_for_persistence is True
    assert decision.reason_codes == ()

    # Stage 5a: real persistence gate
    engine = PurchaseRequestPersistenceEngine(session_factory)
    metadata = ImportMetadata(
        company_id=ids["company"],
        destination_type=WAREHOUSE,
        request_date=date(2026, 9, 7),
        warehouse_id=ids["warehouse"],
        reference="E2E-REF-001",
    )
    gate = engine.gate([decision], metadata)
    assert gate.header_ready is True
    assert gate.can_persist is True
    assert gate.requires_confirmation is True
    assert len(gate.ready_lines) == 1
    assert gate.blocked_reasons == ()

    # Stage 5b: no writes without explicit confirmation
    unconfirmed = engine.persist([decision], metadata, confirmed=False)
    assert unconfirmed.persisted is False
    assert unconfirmed.error == NOT_CONFIRMED
    assert fetch_requests(session_factory) == []
    assert fetch_lines(session_factory) == []

    # Stage 5c: real persistence with explicit confirmation
    result = engine.persist([decision], metadata, confirmed=True)
    assert result.persisted is True
    assert result.purchase_request_id is not None
    assert result.persisted_line_count == 1
    assert result.review_count == 0
    assert result.rejected_count == 0
    assert result.duplicate_blocked_count == 0
    assert result.error is None

    # Header assertions: metadata and provenance preserved exactly
    headers = fetch_requests(session_factory)
    assert len(headers) == 1
    header = headers[0]
    assert header.id == result.purchase_request_id
    assert header.company_id == ids["company"]
    assert header.destination_type == WAREHOUSE
    assert header.request_date == date(2026, 9, 7)
    assert header.reference == "E2E-REF-001"
    assert header.warehouse_id == ids["warehouse"]
    assert header.status == PurchaseRequestStatus.DRAFT.value
    assert header.source_file == str(source_path)
    assert header.source_sheet == "Sheet1"
    assert header.source_row is None

    # Line assertions: identity, quantity, status, raw values, provenance
    lines = fetch_lines(session_factory)
    assert len(lines) == 1
    line = lines[0]
    assert line.request_id == header.id
    assert line.product_id == ids["product"]
    assert line.unit_id == ids["unit"]
    assert line.requested_quantity == Decimal("500")
    assert line.approved_quantity is None
    assert line.status == PurchaseRequestStatus.DRAFT.value
    assert line.raw_product == PRODUCT_NAME
    assert line.raw_unit == UNIT_NAME
    assert line.raw_quantity == "500"
    assert line.raw_packaging is None
    assert line.source_file == str(source_path)
    assert line.source_sheet == "Sheet1"
    assert line.source_row == 2


def test_missing_master_data_never_produces_ready_or_persists(database_fixture, tmp_path):
    session_factory, _ = database_fixture
    source_path = tmp_path / TEST_SOURCE_FILENAME
    create_workbook(
        source_path,
        [["PR_E2E_MISSING_PRODUCT", "PR E2E Missing Product", ITEM_DESCRIPTION, "PR E2E Missing Unit", QUANTITY]],
    )

    # Stage 1: real Excel reader
    sheet = PurchaseRequestExcelReader().read(source_path)
    assert sheet.product_row_count == 1

    # Stage 2: real validation engine (source presence only, no mapping)
    validations = PurchaseRequestValidationEngine().validate(sheet.rows)
    assert len(validations) == 1
    validation = validations[0]
    assert validation.status is ValidationStatus.VALID
    assert validation.eligible_for_next_stage is True

    # Stage 3: real mapping engine against real master data (no matching rows)
    products, units = load_candidates(session_factory)
    mapping = PurchaseRequestMappingEngine().map(validation, products=products, units=units)
    assert mapping.product.status is MappingStatus.UNMAPPED
    assert mapping.product.normalized_product_id is None
    assert mapping.unit.status is MappingStatus.UNMAPPED
    assert mapping.unit.normalized_unit_id is None

    # Stage 4: real decision engine must not produce READY
    decision = PurchaseRequestMappingDecisionEngine().decide(validation, mapping)
    assert decision.decision_status is DecisionStatus.REVIEW
    assert decision.eligible_for_persistence is False
    assert ReasonCode.PRODUCT_UNMAPPED in decision.reason_codes
    assert ReasonCode.UNIT_UNMAPPED in decision.reason_codes

    # Stage 5: gate blocks, persistence never occurs even when confirmed
    engine = PurchaseRequestPersistenceEngine(session_factory)
    metadata = ImportMetadata(
        company_id=database_fixture[1]["company"],
        destination_type=WAREHOUSE,
        request_date=date(2026, 9, 7),
        warehouse_id=database_fixture[1]["warehouse"],
    )
    gate = engine.gate([decision], metadata)
    assert gate.can_persist is False
    assert gate.ready_lines == ()
    assert NO_READY_LINES in gate.blocked_reasons

    result = engine.persist([decision], metadata, confirmed=True)
    assert result.persisted is False
    assert result.error == GATE_BLOCKED

    # No header and no line may exist in PostgreSQL
    assert fetch_requests(session_factory) == []
    assert fetch_lines(session_factory) == []
