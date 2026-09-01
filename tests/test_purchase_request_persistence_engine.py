from datetime import date
from decimal import Decimal

import pytest
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
from app.services.mapping_engine import BRANCH, SUB_WAREHOUSE, WAREHOUSE
from app.services.purchase_request_mapping_decision import (
    DecisionStatus,
    LocationStatus,
    PurchaseRequestMappingDecision,
)
from app.services.purchase_request_persistence_engine import (
    EXACT_SOURCE_DUPLICATE,
    GATE_BLOCKED,
    MISSING_COMPANY_ID,
    MISSING_DESTINATION_TYPE,
    MISSING_REQUEST_DATE,
    MIXED_SOURCE_BATCH,
    NOT_CONFIRMED,
    NO_READY_LINES,
    ImportMetadata,
    PurchaseRequestPersistenceEngine,
)
from app.services.purchase_request_reader import QuantityClassification


TEST_SOURCE_FILE = "persistence-request-test.xlsx"
TEST_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pip_db"


@pytest.fixture(scope="module")
def database_fixture():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    company = Company(name="PR Persistence Test Company", code="PR_PERSIST_COMPANY")
    category = Category(name="PR Persistence Test Category", code="PR_PERSIST_CATEGORY")
    unit = Unit(name="PR Persistence Test Unit", code="PR_PERSIST_UNIT")
    session.add_all([company, category, unit])
    session.flush()
    branch = Branch(company_id=company.id, name="PR Persistence Test Branch", code="PR_PERSIST_BRANCH")
    session.add(branch)
    session.flush()
    warehouse = Warehouse(branch_id=branch.id, name="PR Persistence Test Warehouse", code="PR_PERSIST_WAREHOUSE")
    product = Product(
        code="PR_PERSIST_PRODUCT",
        name="PR Persistence Test Product",
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
        delete(PurchaseRequestLine).where(PurchaseRequestLine.source_file == TEST_SOURCE_FILE)
    )
    cleanup.execute(delete(PurchaseRequest).where(PurchaseRequest.source_file == TEST_SOURCE_FILE))
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
    session.execute(delete(PurchaseRequestLine).where(PurchaseRequestLine.source_file == TEST_SOURCE_FILE))
    session.execute(delete(PurchaseRequest).where(PurchaseRequest.source_file == TEST_SOURCE_FILE))
    session.commit()
    session.close()


def make_decision(
    ids,
    *,
    source_row=2,
    decision_status=DecisionStatus.READY,
    normalized_product_id=None,
    normalized_unit_id=None,
    quantity_classification=QuantityClassification.PURE_NUMERIC,
    quantity_value=Decimal("500"),
    quantity_token=None,
    packaging_token=None,
    raw_product="PR Persistence Test Product",
    raw_unit="PR Persistence Test Unit",
    raw_quantity="500",
    raw_internal_reference="PR_PERSIST_PRODUCT",
    raw_item_description="Fresh",
    source_file=TEST_SOURCE_FILE,
    source_sheet="Sheet1",
) -> PurchaseRequestMappingDecision:
    if decision_status is DecisionStatus.READY and normalized_product_id is None:
        normalized_product_id = ids["product"]
    if decision_status is DecisionStatus.READY and normalized_unit_id is None:
        normalized_unit_id = ids["unit"]
    eligible = decision_status is DecisionStatus.READY
    return PurchaseRequestMappingDecision(
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
        normalized_product_id=normalized_product_id,
        normalized_unit_id=normalized_unit_id,
        quantity_classification=quantity_classification,
        quantity_value=quantity_value,
        quantity_token=quantity_token,
        packaging_token=packaging_token,
        raw_internal_reference=raw_internal_reference,
        raw_product=raw_product,
        raw_item_description=raw_item_description,
        raw_unit=raw_unit,
        raw_quantity=raw_quantity,
        decision_status=decision_status,
        eligible_for_persistence=eligible,
        reason_codes=(),
        location_status=LocationStatus.DEFERRED,
    )


def make_metadata(ids, **changes):
    values = {
        "company_id": ids["company"],
        "destination_type": WAREHOUSE,
        "request_date": date(2026, 8, 22),
        "warehouse_id": ids["warehouse"],
    }
    values.update(changes)
    return ImportMetadata(**values)


def fetch_requests(session_factory):
    session = session_factory()
    requests = session.scalars(
        select(PurchaseRequest).where(PurchaseRequest.source_file == TEST_SOURCE_FILE)
    ).all()
    session.close()
    return requests


def fetch_lines(session_factory):
    session = session_factory()
    lines = session.scalars(
        select(PurchaseRequestLine).where(PurchaseRequestLine.source_file == TEST_SOURCE_FILE)
    ).all()
    session.close()
    return lines


# --------------------------------------------------------------- HEADER ---


def test_complete_header_metadata_is_ready(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    result = engine.gate([make_decision(ids)], make_metadata(ids))

    assert result.header_ready is True


def test_missing_company_id_blocks_header(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    result = engine.gate([make_decision(ids)], make_metadata(ids, company_id=None))

    assert result.header_ready is False
    assert MISSING_COMPANY_ID in result.blocked_reasons
    assert result.can_persist is False


def test_missing_destination_type_blocks_header(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    result = engine.gate([make_decision(ids)], make_metadata(ids, destination_type=None, warehouse_id=None))

    assert result.header_ready is False
    assert MISSING_DESTINATION_TYPE in result.blocked_reasons


def test_missing_request_date_blocks_header(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    result = engine.gate([make_decision(ids)], make_metadata(ids, request_date=None))

    assert result.header_ready is False
    assert MISSING_REQUEST_DATE in result.blocked_reasons


def test_branch_and_warehouse_metadata_preserved_exactly(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    metadata = make_metadata(
        ids, destination_type=BRANCH, branch_id=ids["branch"], warehouse_id=None
    )

    result = engine.persist([make_decision(ids)], metadata, confirmed=True)
    header = fetch_requests(session_factory)[0]

    assert result.persisted is True
    assert header.branch_id == ids["branch"]
    assert header.warehouse_id is None
    assert header.destination_type == BRANCH


def test_explicit_reference_is_persisted(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    metadata = make_metadata(ids, reference="EXT-REF-001")

    engine.persist([make_decision(ids)], metadata, confirmed=True)
    header = fetch_requests(session_factory)[0]

    assert header.reference == "EXT-REF-001"


def test_omitted_reference_is_null(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)

    engine.persist([make_decision(ids)], make_metadata(ids), confirmed=True)
    header = fetch_requests(session_factory)[0]

    assert header.reference is None


def test_internal_reference_never_becomes_header_reference(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(ids, raw_internal_reference="PR_PERSIST_PRODUCT")

    engine.persist([decision], make_metadata(ids), confirmed=True)
    header = fetch_requests(session_factory)[0]

    assert header.reference is None
    assert header.reference != decision.raw_internal_reference


# ----------------------------------------------------------------- LINE ---


def test_ready_numeric_line_is_persistence_candidate(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    result = engine.gate([make_decision(ids)], make_metadata(ids))

    assert len(result.ready_lines) == 1
    assert result.can_persist is True


def test_ready_zero_line_is_persistence_candidate(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(
        ids,
        quantity_classification=QuantityClassification.EXPLICIT_ZERO,
        quantity_value=Decimal("0"),
        raw_quantity="0",
    )

    result = engine.gate([decision], make_metadata(ids))

    assert len(result.ready_lines) == 1


def test_review_line_never_persisted(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(ids, decision_status=DecisionStatus.REVIEW, normalized_product_id=None)

    result = engine.persist([decision], make_metadata(ids), confirmed=True)

    assert result.persisted is False
    assert fetch_lines(session_factory) == []


def test_rejected_line_never_persisted(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(
        ids,
        decision_status=DecisionStatus.REJECTED,
        normalized_product_id=None,
        normalized_unit_id=None,
        quantity_classification=QuantityClassification.BLANK_QUANTITY,
        quantity_value=None,
        raw_quantity=None,
    )

    result = engine.persist([decision], make_metadata(ids), confirmed=True)

    assert result.persisted is False
    assert fetch_lines(session_factory) == []


def test_zero_ready_lines_creates_no_header(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(ids, decision_status=DecisionStatus.REVIEW, normalized_product_id=None)

    result = engine.persist([decision], make_metadata(ids), confirmed=True)

    assert result.persisted is False
    assert result.error == GATE_BLOCKED
    assert NO_READY_LINES in result.gate.blocked_reasons
    assert fetch_requests(session_factory) == []


def test_mixed_ready_review_rejected_only_selected_ready_lines_persist(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    ready = make_decision(ids, source_row=10)
    review = make_decision(ids, source_row=11, decision_status=DecisionStatus.REVIEW, normalized_product_id=None)
    rejected = make_decision(
        ids,
        source_row=12,
        decision_status=DecisionStatus.REJECTED,
        normalized_product_id=None,
        normalized_unit_id=None,
        quantity_classification=QuantityClassification.BLANK_QUANTITY,
        quantity_value=None,
        raw_quantity=None,
    )

    result = engine.persist([ready, review, rejected], make_metadata(ids), confirmed=True)

    assert result.persisted is True
    assert result.persisted_line_count == 1
    assert result.review_count == 1
    assert result.rejected_count == 1
    assert len(fetch_lines(session_factory)) == 1


def test_review_and_rejected_provenance_retained_in_result(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    review = make_decision(ids, source_row=21, decision_status=DecisionStatus.REVIEW, normalized_product_id=None)
    rejected = make_decision(
        ids,
        source_row=22,
        decision_status=DecisionStatus.REJECTED,
        normalized_product_id=None,
        normalized_unit_id=None,
        quantity_classification=QuantityClassification.BLANK_QUANTITY,
        quantity_value=None,
        raw_quantity=None,
    )
    ready = make_decision(ids, source_row=23)

    result = engine.gate([ready, review, rejected], make_metadata(ids))

    assert result.review_lines[0].source_row == 21
    assert result.rejected_lines[0].source_row == 22


# ------------------------------------------------------------ RAW DATA ---


def test_raw_product_preserved(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids, raw_product="Exact Raw Name")], make_metadata(ids), confirmed=True)

    assert fetch_lines(session_factory)[0].raw_product == "Exact Raw Name"


def test_raw_unit_preserved(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids, raw_unit="Exact Raw Unit")], make_metadata(ids), confirmed=True)

    assert fetch_lines(session_factory)[0].raw_unit == "Exact Raw Unit"


def test_raw_quantity_preserved(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids, raw_quantity="500")], make_metadata(ids), confirmed=True)

    assert fetch_lines(session_factory)[0].raw_quantity == "500"


def test_raw_packaging_preserved(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(ids, packaging_token=None)

    engine.persist([decision], make_metadata(ids), confirmed=True)

    assert fetch_lines(session_factory)[0].raw_packaging is None


def test_source_file_preserved(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids)], make_metadata(ids), confirmed=True)

    assert fetch_lines(session_factory)[0].source_file == TEST_SOURCE_FILE


def test_source_sheet_preserved(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids, source_sheet="Sheet2")], make_metadata(ids), confirmed=True)

    assert fetch_lines(session_factory)[0].source_sheet == "Sheet2"


def test_source_row_preserved(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids, source_row=99)], make_metadata(ids), confirmed=True)

    assert fetch_lines(session_factory)[0].source_row == 99


def test_approved_quantity_remains_null(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids)], make_metadata(ids), confirmed=True)

    assert fetch_lines(session_factory)[0].approved_quantity is None


def test_draft_status_used_for_header_and_line(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids)], make_metadata(ids), confirmed=True)

    header = fetch_requests(session_factory)[0]
    line = fetch_lines(session_factory)[0]

    assert header.status == PurchaseRequestStatus.DRAFT.value
    assert line.status == PurchaseRequestStatus.DRAFT.value


# ------------------------------------------------------------ QUANTITY ---


def test_packaging_quantity_never_persisted(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(
        ids,
        decision_status=DecisionStatus.REVIEW,
        normalized_product_id=None,
        quantity_classification=QuantityClassification.QUANTITY_WITH_PACKAGING,
        quantity_value=None,
        quantity_token="5",
        packaging_token="box",
        raw_quantity="5 box",
    )

    result = engine.persist([decision], make_metadata(ids), confirmed=True)

    assert result.persisted is False
    assert fetch_lines(session_factory) == []


def test_unknown_quantity_token_never_persisted(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(
        ids,
        decision_status=DecisionStatus.REVIEW,
        normalized_product_id=None,
        quantity_classification=QuantityClassification.UNKNOWN_QUANTITY_TOKEN,
        quantity_value=None,
        quantity_token="8",
        packaging_token="gol",
        raw_quantity="8 gol",
    )

    result = engine.persist([decision], make_metadata(ids), confirmed=True)

    assert result.persisted is False
    assert fetch_lines(session_factory) == []


def test_textual_quantity_never_persisted(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(
        ids,
        decision_status=DecisionStatus.REVIEW,
        normalized_product_id=None,
        quantity_classification=QuantityClassification.TEXTUAL_QUANTITY,
        quantity_value=None,
        raw_quantity="مطلوب",
    )

    result = engine.persist([decision], make_metadata(ids), confirmed=True)

    assert result.persisted is False
    assert fetch_lines(session_factory) == []


def test_blank_quantity_never_persisted(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(
        ids,
        decision_status=DecisionStatus.REJECTED,
        normalized_product_id=None,
        normalized_unit_id=None,
        quantity_classification=QuantityClassification.BLANK_QUANTITY,
        quantity_value=None,
        raw_quantity=None,
    )

    result = engine.persist([decision], make_metadata(ids), confirmed=True)

    assert result.persisted is False
    assert fetch_lines(session_factory) == []


# ------------------------------------------------------------- MAPPING ---


def test_no_candidate_selection_from_ambiguous_mapping(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(ids, decision_status=DecisionStatus.REVIEW, normalized_product_id=None)

    result = engine.gate([decision], make_metadata(ids))

    assert result.ready_lines == ()
    assert result.review_lines == (decision,)


def test_no_unit_conversion_ever_performed(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.persist([make_decision(ids)], make_metadata(ids), confirmed=True)

    line = fetch_lines(session_factory)[0]
    assert line.unit_id == ids["unit"]
    assert line.raw_unit == "PR Persistence Test Unit"


# ----------------------------------------------------------- DUPLICATE ---


def test_exact_source_duplicate_is_blocked(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decision = make_decision(ids, source_row=55)
    engine.persist([decision], make_metadata(ids), confirmed=True)

    second_decision = make_decision(ids, source_row=55)
    result = engine.gate([second_decision], make_metadata(ids))

    assert EXACT_SOURCE_DUPLICATE in result.blocked_reasons
    assert second_decision in result.duplicate_blocked_lines
    assert result.ready_lines == ()


def test_business_duplicate_is_not_automatically_rejected(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    first = make_decision(ids, source_row=61)
    engine.persist([first], make_metadata(ids), confirmed=True)

    second = make_decision(ids, source_row=62)
    result = engine.gate([second], make_metadata(ids))

    assert result.can_persist is True
    assert result.business_duplicate_check == "NOT_IMPLEMENTED"


# ------------------------------------------------------------ CONTROLS ---


def test_preview_causes_zero_database_writes(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.gate([make_decision(ids)], make_metadata(ids))

    assert fetch_requests(session_factory) == []
    assert fetch_lines(session_factory) == []


def test_gate_causes_zero_database_writes(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    engine.gate([make_decision(ids)], make_metadata(ids, company_id=None))

    assert fetch_requests(session_factory) == []


def test_persistence_without_confirmation_causes_zero_database_writes(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    result = engine.persist([make_decision(ids)], make_metadata(ids), confirmed=False)

    assert result.persisted is False
    assert result.error == NOT_CONFIRMED
    assert fetch_requests(session_factory) == []


def test_persistence_with_confirmation_writes(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    result = engine.persist([make_decision(ids)], make_metadata(ids), confirmed=True)

    assert result.persisted is True
    assert len(fetch_requests(session_factory)) == 1
    assert len(fetch_lines(session_factory)) == 1


def test_atomic_rollback_on_line_failure(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    bad_decision = make_decision(ids, source_row=71, normalized_unit_id=999999)

    result = engine.persist([bad_decision], make_metadata(ids), confirmed=True)

    assert result.persisted is False
    assert result.error is not None
    assert fetch_requests(session_factory) == []
    assert fetch_lines(session_factory) == []


def test_unrelated_source_batches_cannot_be_combined(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    first = make_decision(ids, source_row=81, source_file="unrelated-a.xlsx")
    second = make_decision(ids, source_row=82, source_file="unrelated-b.xlsx")

    result = engine.gate([first, second], make_metadata(ids))

    assert MIXED_SOURCE_BATCH in result.blocked_reasons
    assert result.can_persist is False


def test_import_metadata_is_immutable(database_fixture):
    session_factory, ids = database_fixture
    metadata = make_metadata(ids)

    with pytest.raises(Exception):
        metadata.company_id = 999


def test_gate_result_is_immutable(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    result = engine.gate([make_decision(ids)], make_metadata(ids))

    with pytest.raises(Exception):
        result.can_persist = False


def test_repeated_gate_is_deterministic(database_fixture):
    session_factory, ids = database_fixture
    engine = PurchaseRequestPersistenceEngine(session_factory)
    decisions = [make_decision(ids)]
    metadata = make_metadata(ids)

    first = engine.gate(decisions, metadata)
    second = engine.gate(decisions, metadata)

    assert first == second
