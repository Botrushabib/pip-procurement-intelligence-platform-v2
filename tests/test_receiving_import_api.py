from datetime import datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.api.receiving_analytics_api import get_receiving_event_query_service
from app.api.receiving_import_api import (
    ReceivingImportPreview,
    get_receiving_candidates,
    get_receiving_persistence_engine,
    preview_store,
)
from app.main import app
from app.models.branch import Branch
from app.models.category import Category
from app.models.company import Company
from app.models.product import Product
from app.models.receiving_event import ReceivingEvent
from app.models.receiving_event_line import ReceivingEventLine
from app.models.supplier import Supplier
from app.models.unit import Unit
from app.models.warehouse import Warehouse
from app.services.receiving_event_mapping_result import (
    CompanyCandidate,
    ProductCandidate,
    SupplierCandidate,
    UnitCandidate,
    WarehouseCandidate,
)
from app.services.receiving_event_persistence_engine import ReceivingEventPersistenceEngine
from app.services.receiving_event_query_service import ReceivingEventQueryService
from tests.test_receiving_event_mapping_engine import make_row, mapped


TEST_SOURCE_FILE = "receiving-import-api-test.xlsx"
TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pip_db"
COMPANY_CODE = "RECEIVING_IMPORT_API_COMPANY"

HEADERS = [
    "Suppliers", "Date", "Receipt Date", "Reference", "Product",
    "To", "Qty", "Unit", "Unit Price", "Subtotal",
]


def workbook_bytes(reference="RIA-001"):
    # Mirrors the row-classification rules in receiving_event_reader.py: a
    # DETAIL row's supplier is only populated by inheriting from a preceding
    # SUPPLIER_HEADER row, so the workbook needs both rows.
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Report"
    worksheet.append(HEADERS)
    worksheet.append(
        ["Receiving Import API Supplier", datetime(2026, 8, 15), datetime(2026, 9, 1), None, None, None, None, None, None, None]
    )
    worksheet.append(
        [None, datetime(2026, 8, 15), datetime(2026, 9, 1), reference, "[162017] Receiving Import API Product", "Main Stores/Stock", 2, "kg", 10, 20]
    )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def fake_matching_candidates():
    """Candidates that match workbook_bytes() without touching the database."""
    return {
        "companies": [CompanyCandidate(1, code=COMPANY_CODE, name="Receiving Import API Company")],
        "suppliers": [SupplierCandidate(2, name="Receiving Import API Supplier")],
        "products": [ProductCandidate(3, code="162017", name="Receiving Import API Product")],
        "units": [UnitCandidate(4, name="kg")],
        "warehouses": [WarehouseCandidate(5, name="Main Stores/Stock", code="MS")],
    }


def load_candidates_from(session_factory):
    session = session_factory()
    try:
        return {
            "companies": [CompanyCandidate(row.id, code=row.code, name=row.name) for row in session.scalars(select(Company)).all()],
            "suppliers": [SupplierCandidate(row.id, name=row.name) for row in session.scalars(select(Supplier)).all()],
            "products": [ProductCandidate(row.id, code=row.code, name=row.name) for row in session.scalars(select(Product)).all()],
            "units": [UnitCandidate(row.id, name=row.name) for row in session.scalars(select(Unit)).all()],
            "warehouses": [WarehouseCandidate(row.id, name=row.name, code=row.code) for row in session.scalars(select(Warehouse)).all()],
        }
    finally:
        session.close()


@pytest.fixture(scope="module")
def database_fixture():
    """Real Postgres fixture, only used by tests that need actual persistence."""
    engine = create_engine(TEST_DATABASE_URL, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    company = Company(name="Receiving Import API Company", code=COMPANY_CODE)
    category = Category(name="Receiving Import API Category", code="RECEIVING_IMPORT_API_CATEGORY")
    unit = Unit(name="kg", code="RECEIVING_IMPORT_API_UNIT")
    supplier = Supplier(name="Receiving Import API Supplier", code="RECEIVING_IMPORT_API_SUPPLIER")
    session.add_all([company, category, unit, supplier])
    session.flush()
    branch = Branch(company_id=company.id, name="Receiving Import API Branch", code="RECEIVING_IMPORT_API_BRANCH")
    session.add(branch)
    session.flush()
    warehouse = Warehouse(branch_id=branch.id, name="Main Stores/Stock", code="RECEIVING_IMPORT_API_WAREHOUSE")
    product = Product(code="162017", name="Receiving Import API Product", category_id=category.id, unit_id=unit.id)
    session.add_all([warehouse, product])
    session.commit()
    ids = {
        "company": company.id, "category": category.id, "unit": unit.id,
        "supplier": supplier.id, "branch": branch.id, "warehouse": warehouse.id,
        "product": product.id,
    }
    session.close()

    yield session_factory, ids

    cleanup = session_factory()
    cleanup.execute(delete(ReceivingEventLine).where(ReceivingEventLine.source_file == "receiving.xlsx"))
    cleanup.execute(delete(ReceivingEvent).where(ReceivingEvent.source_file == "receiving.xlsx"))
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


def reset_receiving_rows(session_factory):
    """Clear previously committed rows for the shared test workbook filename."""
    session = session_factory()
    session.execute(delete(ReceivingEventLine).where(ReceivingEventLine.source_file == "receiving.xlsx"))
    session.execute(delete(ReceivingEvent).where(ReceivingEvent.source_file == "receiving.xlsx"))
    session.commit()
    session.close()


@pytest.fixture(autouse=True)
def isolate_api_state():
    preview_store._items.clear()
    yield
    preview_store._items.clear()
    app.dependency_overrides.clear()


def install_fake_dependencies():
    """Dependency overrides with no database access, for tests that only
    exercise request validation or in-memory mapping."""
    app.dependency_overrides[get_receiving_candidates] = fake_matching_candidates


def install_real_dependencies(session_factory):
    app.dependency_overrides[get_receiving_candidates] = lambda: load_candidates_from(session_factory)
    app.dependency_overrides[get_receiving_persistence_engine] = lambda: ReceivingEventPersistenceEngine(session_factory)
    app.dependency_overrides[get_receiving_event_query_service] = lambda: ReceivingEventQueryService(session_factory)


def preview(client, reference="RIA-001", company_code=COMPANY_CODE, filename="receiving.xlsx"):
    return client.post(
        "/api/receiving/import/preview",
        files={"file": (filename, workbook_bytes(reference), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"company_code": company_code},
    )


def test_preview_valid_workbook_succeeds_without_persisting():
    install_fake_dependencies()
    client = TestClient(app)

    response = preview(client)

    assert response.status_code == 200
    body = response.json()
    assert body["preview_token"]
    assert body["source_file"] == "receiving.xlsx"
    assert body["ready_count"] == 1
    assert body["review_count"] == 0
    # The SUPPLIER_HEADER row also produces a (non-detail) rejected decision.
    assert body["rejected_count"] == 1
    assert body["decisions"][-1]["decision_status"] == "READY"


def test_non_xlsx_file_is_rejected():
    install_fake_dependencies()
    client = TestClient(app)

    response = client.post(
        "/api/receiving/import/preview",
        files={"file": ("receiving.csv", b"not-xlsx", "text/csv")},
        data={"company_code": COMPANY_CODE},
    )

    assert response.status_code == 400
    assert "Only .xlsx files are supported" in response.json()["detail"]


def test_missing_company_code_is_rejected():
    install_fake_dependencies()
    client = TestClient(app)

    response = client.post(
        "/api/receiving/import/preview",
        files={"file": ("receiving.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 422


def test_blank_company_code_is_rejected():
    install_fake_dependencies()
    client = TestClient(app)

    response = preview(client, company_code="   ")

    assert response.status_code == 400
    assert "company_code is required" in response.json()["detail"]


def test_duplicate_source_identity_within_batch_is_blocked_on_commit():
    # Gate-level duplicate detection runs before any database access.
    result = mapped(
        make_row(source_file=TEST_SOURCE_FILE, source_row=7),
        make_row(source_file=TEST_SOURCE_FILE, source_row=7, raw_reference="WH/IN/00002"),
    )
    stored_preview = ReceivingImportPreview(
        source_file=TEST_SOURCE_FILE, source_sheet="Report", header_row=1, total_rows=2,
        mapping_result=result,
    )
    token = preview_store.create(stored_preview)
    client = TestClient(app)

    response = client.post("/api/receiving/import/commit", json={"preview_token": token})

    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is False
    assert "DUPLICATE_SOURCE_IDENTITY" in body["blocked_reasons"]


def test_commit_of_valid_preview_persists_event_and_line(database_fixture):
    session_factory, _ = database_fixture
    reset_receiving_rows(session_factory)
    install_real_dependencies(session_factory)
    client = TestClient(app)
    token = preview(client).json()["preview_token"]

    response = client.post("/api/receiving/import/commit", json={"preview_token": token})

    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    assert body["persisted_event_count"] == 1
    assert body["persisted_line_count"] == 1
    events = session_factory().scalars(
        select(ReceivingEvent).where(ReceivingEvent.source_file == "receiving.xlsx")
    ).all()
    assert len(events) == 1

    # Token is invalidated after a successful commit.
    replay = client.post("/api/receiving/import/commit", json={"preview_token": token})
    assert replay.status_code == 404


def test_exact_source_duplicate_is_detected_on_second_commit(database_fixture):
    session_factory, _ = database_fixture
    reset_receiving_rows(session_factory)
    install_real_dependencies(session_factory)
    client = TestClient(app)

    first_token = preview(client).json()["preview_token"]
    first_commit = client.post("/api/receiving/import/commit", json={"preview_token": first_token})
    assert first_commit.json()["persisted"] is True

    # Re-uploading the same workbook (same source file/sheet/row) must be skipped as an exact duplicate.
    second_token = preview(client).json()["preview_token"]
    second_commit = client.post("/api/receiving/import/commit", json={"preview_token": second_token})

    assert second_commit.status_code == 200
    body = second_commit.json()
    assert body["persisted"] is False
    assert body["error"] == "EXACT_SOURCE_DUPLICATE"
    events = session_factory().scalars(
        select(ReceivingEvent).where(ReceivingEvent.source_file == "receiving.xlsx")
    ).all()
    assert len(events) == 1


def test_committed_receiving_data_is_visible_through_analytics_api(database_fixture):
    session_factory, ids = database_fixture
    reset_receiving_rows(session_factory)
    install_real_dependencies(session_factory)
    client = TestClient(app)
    token = preview(client).json()["preview_token"]
    commit_body = client.post("/api/receiving/import/commit", json={"preview_token": token}).json()
    assert commit_body["persisted"] is True

    response = client.get("/api/receiving/analytics", params={"company_id": ids["company"]})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["distinct_event_count"] >= 1
    assert body["summary"]["eligible_lines"] >= 1
