from datetime import datetime
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.api.import_api import get_import_engine, preview_store
from app.main import app
from app.services.excel_reader import RawPurchaseTransactionRecord
from app.services.mapping_engine import DestinationCandidate, MappingCandidate, MappingEngine, WAREHOUSE
from app.services.odoo_import_engine import ExistingTransaction, SourceIdentity, business_fingerprint
from app.services.odoo_import_engine import OdooImportEngine
from app.services.persistence_engine import PersistenceResult
from app.services.validation_engine import ValidationEngine


class RecordingPersistence:
    def __init__(self, failed=False):
        self.calls = []
        self.failed = failed

    def persist_batch(self, mapped_transactions):
        mapped_transactions = tuple(mapped_transactions)
        self.calls.append(mapped_transactions)
        if self.failed:
            return PersistenceResult(
                persisted_count=0,
                skipped_count=0,
                failed_count=1,
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


class ReaderEngine(OdooImportEngine):
    pass


def workbook_bytes():
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Report"
    worksheet.append(["Suppliers", "Date", "Reference", "Product", "To", "Qty", "Unit", "Unit Price", "Subtotal"])
    worksheet.append(["Supplier A", datetime(2026, 1, 15), "PO-001", "Product A", "Warehouse A", 2, "Each", 10, 20])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def engine_factory(persistence=None, lookup=None):
    persistence = persistence or RecordingPersistence()
    lookup = lookup or (lambda source_ids, fingerprints: ())
    return OdooImportEngine(
        duplicate_lookup=lookup,
        persistence=persistence,
        suppliers=[MappingCandidate("Supplier A", 1)],
        products=[MappingCandidate("Product A", 2)],
        units=[MappingCandidate("Each", 3)],
        destinations=[DestinationCandidate("Warehouse A", WAREHOUSE, warehouse_id=4)],
    )


@pytest.fixture(autouse=True)
def isolate_api_state():
    preview_store._items.clear()
    yield
    preview_store._items.clear()
    app.dependency_overrides.clear()


def install_engine(engine):
    app.dependency_overrides[get_import_engine] = lambda: engine


def preview(client, filename="purchases.xlsx", worksheet_name=None):
    data = {}
    if worksheet_name is not None:
        data["worksheet_name"] = worksheet_name
    return client.post(
        "/api/import/odoo/preview",
        files={"file": (filename, workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data=data,
    )


def test_preview_accepts_xlsx_and_returns_opaque_token_without_persisting():
    persistence = RecordingPersistence()
    install_engine(engine_factory(persistence))
    client = TestClient(app)

    response = preview(client)

    assert response.status_code == 200
    body = response.json()
    assert body["preview_token"]
    assert "/tmp" not in body["source_file"]
    assert body["rows_read"] == 1
    assert body["eligible_for_commit_count"] == 1
    assert persistence.calls == []
    assert body["preview_token"] != "purchases.xlsx"


def test_invalid_xlsx_and_missing_worksheet_return_400():
    install_engine(engine_factory())
    client = TestClient(app)

    invalid = client.post(
        "/api/import/odoo/preview",
        files={"file": ("bad.xlsx", b"not-xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    missing_sheet = preview(client, worksheet_name="Missing")

    assert invalid.status_code == 400
    assert "Invalid XLSX workbook" in invalid.json()["detail"]
    assert missing_sheet.status_code == 400
    assert "Worksheet not found" in missing_sheet.json()["detail"]


def test_commit_requires_valid_token_and_only_persists_accepted_identity():
    persistence = RecordingPersistence()
    engine = engine_factory(persistence)
    install_engine(engine)
    client = TestClient(app)
    preview_response = preview(client)
    body = preview_response.json()
    identity = body["row_results"][0]["source_identity"]

    commit = client.post(
        "/api/import/odoo/commit",
        json={"preview_token": body["preview_token"], "accepted_source_identities": [identity]},
    )
    unknown = client.post(
        "/api/import/odoo/commit",
        json={"preview_token": "unknown", "accepted_source_identities": []},
    )

    assert commit.status_code == 200
    assert commit.json()["persisted_count"] == 1
    assert len(persistence.calls) == 1
    assert unknown.status_code == 404


def test_successful_commit_removes_preview_and_failed_commit_keeps_it():
    persistence = RecordingPersistence()
    install_engine(engine_factory(persistence))
    client = TestClient(app)
    body = preview(client).json()
    identity = body["row_results"][0]["source_identity"]

    first = client.post(
        "/api/import/odoo/commit",
        json={"preview_token": body["preview_token"], "accepted_source_identities": [identity]},
    )
    second = client.post(
        "/api/import/odoo/commit",
        json={"preview_token": body["preview_token"], "accepted_source_identities": [identity]},
    )

    assert first.status_code == 200
    assert second.status_code == 404

    failed_persistence = RecordingPersistence(failed=True)
    install_engine(engine_factory(failed_persistence))
    failed_body = preview(client).json()
    failed_identity = failed_body["row_results"][0]["source_identity"]
    failed = client.post(
        "/api/import/odoo/commit",
        json={"preview_token": failed_body["preview_token"], "accepted_source_identities": [failed_identity]},
    )
    retry = client.post(
        "/api/import/odoo/commit",
        json={"preview_token": failed_body["preview_token"], "accepted_source_identities": [failed_identity]},
    )

    assert failed.status_code == 500
    assert failed.json()["detail"] == "Import persistence failed"
    assert retry.status_code == 500


def test_validation_and_mapping_findings_are_returned():
    install_engine(engine_factory())
    client = TestClient(app)
    invalid_engine = OdooImportEngine(
        duplicate_lookup=lambda source_ids, fingerprints: (),
        persistence=RecordingPersistence(),
        suppliers=[],
        products=[],
        units=[],
        destinations=[],
    )
    install_engine(invalid_engine)

    response = preview(client)
    row = response.json()["row_results"][0]

    assert response.status_code == 200
    assert row["status"] == "UNMAPPED"
    assert any(error["error_type"] == "MAPPING_ERROR" for error in row["errors"])


def test_potential_business_duplicate_requires_explicit_acceptance():
    source = RawPurchaseTransactionRecord(
        source_file="existing.xlsx",
        source_sheet="Report",
        source_row=2,
        transaction_date=datetime(2026, 1, 15),
        reference="PO-001",
        supplier_raw="Supplier A",
        product_raw="Product A",
        destination_raw="Warehouse A",
        quantity_raw=Decimal("2"),
        unit_raw="Each",
        unit_price_raw=Decimal("10"),
        subtotal_raw=Decimal("20"),
    )
    mapped = MappingEngine().map(
        ValidationEngine().validate(source),
        suppliers=[MappingCandidate("Supplier A", 1)],
        products=[MappingCandidate("Product A", 2)],
        units=[MappingCandidate("Each", 3)],
        destinations=[DestinationCandidate("Warehouse A", WAREHOUSE, warehouse_id=4)],
    )
    existing = ExistingTransaction(SourceIdentity("existing.xlsx", "Report", 2), business_fingerprint(mapped))
    persistence = RecordingPersistence()
    install_engine(engine_factory(persistence, lambda source_ids, fingerprints: [existing]))
    client = TestClient(app)

    body = preview(client, filename="copy.xlsx").json()
    identity = body["row_results"][0]["source_identity"]
    assert body["row_results"][0]["status"] == "POTENTIAL_BUSINESS_DUPLICATE"

    skipped = client.post(
        "/api/import/odoo/commit",
        json={"preview_token": body["preview_token"], "accepted_source_identities": []},
    )
    assert skipped.json()["persisted_count"] == 0

    body = preview(client, filename="copy-accepted.xlsx").json()
    accepted = client.post(
        "/api/import/odoo/commit",
        json={"preview_token": body["preview_token"], "accepted_source_identities": [body["row_results"][0]["source_identity"]]},
    )
    assert accepted.json()["persisted_count"] == 1


def test_commit_does_not_use_purchase_transaction_directly():
    source = open("app/api/import_api.py").read()

    assert "PurchaseTransaction(" not in source
    assert "SessionLocal" in source
