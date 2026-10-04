from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
import os
import secrets
from tempfile import NamedTemporaryFile
from threading import Lock
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.company import Company
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.unit import Unit
from app.models.warehouse import Warehouse
from app.services.receiving_event_mapping_decision import ReceivingEventMappingDecision
from app.services.receiving_event_mapping_engine import ReceivingEventMappingEngine
from app.services.receiving_event_mapping_result import (
    CompanyCandidate,
    CompanyMetadata,
    ProductCandidate,
    ReceivingEventMappingResult,
    SupplierCandidate,
    UnitCandidate,
    WarehouseCandidate,
)
from app.services.receiving_event_persistence_engine import (
    ReceivingEventPersistenceEngine,
    ReceivingPersistenceResult,
)
from app.services.receiving_event_reader import (
    InvalidWorkbookError,
    ReceivingExcelReader,
    ReceivingSheetResult,
    RequiredHeadersNotFoundError,
    SourceFileNotFoundError,
    WorksheetNotFoundError,
)
from app.services.receiving_event_validation_engine import ReceivingValidationEngine


router = APIRouter(prefix="/api/receiving/import", tags=["receiving-import"])

# Maximum uploaded workbook size: 25 MiB, enforced while streaming to disk.
MAX_RECEIVING_WORKBOOK_SIZE_BYTES = 25 * 1024 * 1024
_commit_lock = Lock()


class SourceIdentityDTO(BaseModel):
    source_file: str
    source_sheet: str
    source_row: int = Field(ge=1)


class DecisionDTO(BaseModel):
    source_identity: SourceIdentityDTO
    decision_status: str
    reason_codes: list[str]
    company_id: int | None
    supplier_id: int | None
    warehouse_id: int | None
    product_id: int | None
    unit_id: int | None
    event_date: date | None
    receiving_reference: str | None


class PreviewResponse(BaseModel):
    preview_token: str
    source_file: str
    source_sheet: str
    header_row: int
    total_rows: int
    total_row_count: int
    eligible_detail_row_count: int
    ready_count: int
    review_count: int
    rejected_count: int
    decisions: list[DecisionDTO]


class CommitRequest(BaseModel):
    preview_token: str = Field(min_length=1)


class CommitResponse(BaseModel):
    persisted: bool
    persisted_event_count: int
    persisted_line_count: int
    ready_count: int
    review_count: int
    rejected_count: int
    duplicate_source_rows: list[SourceIdentityDTO]
    blocked_reasons: list[str]
    error: str | None


@dataclass(frozen=True)
class ReceivingImportPreview:
    source_file: str
    source_sheet: str
    header_row: int
    total_rows: int
    mapping_result: ReceivingEventMappingResult


class PreviewStore:
    """Opaque, TTL-based token store for pending receiving import previews.

    Mirrors the preview/commit token pattern used by app/api/import_api.py.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, tuple[float, ReceivingImportPreview]] = {}
        self._lock = Lock()

    def create(self, preview: ReceivingImportPreview) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._purge()
            self._items[token] = (time.monotonic() + self.ttl_seconds, preview)
        return token

    def get(self, token: str) -> ReceivingImportPreview | None:
        with self._lock:
            self._purge()
            item = self._items.get(token)
            return item[1] if item else None

    def remove(self, token: str) -> None:
        with self._lock:
            self._items.pop(token, None)

    def _purge(self) -> None:
        now = time.monotonic()
        expired = [token for token, (deadline, _) in self._items.items() if deadline <= now]
        for token in expired:
            del self._items[token]


preview_store = PreviewStore(
    ttl_seconds=int(os.getenv("PIP_RECEIVING_IMPORT_PREVIEW_TTL_SECONDS", "300"))
)


def load_receiving_candidates() -> dict[str, list[Any]]:
    """Load Supplier/Product/Unit/Warehouse/Company candidates from the database."""
    session = SessionLocal()
    try:
        return {
            "companies": [
                CompanyCandidate(row.id, code=row.code, name=row.name)
                for row in session.scalars(select(Company)).all()
            ],
            "suppliers": [
                SupplierCandidate(row.id, name=row.name)
                for row in session.scalars(select(Supplier)).all()
            ],
            "products": [
                ProductCandidate(row.id, code=row.code, name=row.name)
                for row in session.scalars(select(Product)).all()
            ],
            "units": [
                UnitCandidate(row.id, name=row.name)
                for row in session.scalars(select(Unit)).all()
            ],
            "warehouses": [
                WarehouseCandidate(row.id, name=row.name, code=row.code)
                for row in session.scalars(select(Warehouse)).all()
            ],
        }
    finally:
        session.close()


def get_receiving_candidates() -> dict[str, list[Any]]:
    return load_receiving_candidates()


def get_receiving_persistence_engine() -> ReceivingEventPersistenceEngine:
    return ReceivingEventPersistenceEngine()


def _rename_source_file(sheet_result: ReceivingSheetResult, original_filename: str) -> ReceivingSheetResult:
    """Replace the temporary upload path with the caller-supplied filename.

    Source identity (used for duplicate protection) must reflect the original
    workbook name, not an ephemeral temp path, mirroring OriginalFilenameReader
    in app/api/import_api.py.
    """
    rows = tuple(replace(row, source_file=original_filename) for row in sheet_result.rows)
    return replace(sheet_result, source_file=original_filename, rows=rows)


def _company_code_matches(company_code: str, candidates: list[Any]) -> bool:
    normalized_code = " ".join(company_code.strip().split()).lower()
    return any(
        candidate.code is not None
        and " ".join(candidate.code.strip().split()).lower() == normalized_code
        for candidate in candidates
    )


def _identity_dto(decision: ReceivingEventMappingDecision) -> SourceIdentityDTO:
    return SourceIdentityDTO(
        source_file=decision.source_file,
        source_sheet=decision.source_sheet,
        source_row=decision.source_row,
    )


def _decision_dto(decision: ReceivingEventMappingDecision) -> DecisionDTO:
    return DecisionDTO(
        source_identity=_identity_dto(decision),
        decision_status=decision.decision_status.value,
        reason_codes=list(decision.reason_codes),
        company_id=decision.company_id,
        supplier_id=decision.supplier_id,
        warehouse_id=decision.warehouse_id,
        product_id=decision.product_id,
        unit_id=decision.unit_id,
        event_date=decision.event_date,
        receiving_reference=(
            str(decision.receiving_reference) if decision.receiving_reference is not None else None
        ),
    )


def _preview_response(token: str, preview: ReceivingImportPreview) -> PreviewResponse:
    summary = preview.mapping_result.summary
    return PreviewResponse(
        preview_token=token,
        source_file=preview.source_file,
        source_sheet=preview.source_sheet,
        header_row=preview.header_row,
        total_rows=preview.total_rows,
        total_row_count=summary.total_row_count,
        eligible_detail_row_count=summary.eligible_detail_row_count,
        ready_count=summary.ready_count,
        review_count=summary.review_count,
        rejected_count=summary.rejected_count,
        decisions=[_decision_dto(decision) for decision in preview.mapping_result.decisions],
    )


def _commit_response(result: ReceivingPersistenceResult) -> CommitResponse:
    return CommitResponse(
        persisted=result.persisted,
        persisted_event_count=result.persisted_event_count,
        persisted_line_count=result.persisted_line_count,
        ready_count=result.gate.eligible_ready_count,
        review_count=result.gate.review_count,
        rejected_count=result.gate.rejected_count,
        duplicate_source_rows=[
            SourceIdentityDTO(source_file=row[0], source_sheet=row[1], source_row=row[2])
            for row in result.duplicate_source_rows
        ],
        blocked_reasons=list(result.gate.blocked_reasons),
        error=result.error,
    )


@router.post("/preview", response_model=PreviewResponse)
async def preview_receiving_import(
    file: Annotated[UploadFile, File(...)],
    company_code: Annotated[str, Form(min_length=1)],
    worksheet_name: Annotated[str | None, Form()] = None,
    candidates: dict[str, list[Any]] = Depends(get_receiving_candidates),
) -> PreviewResponse:
    filename = Path(file.filename or "upload.xlsx").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .xlsx files are supported")
    if not company_code.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_code is required")
    if not _company_code_matches(company_code, candidates["companies"]):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown company_code")

    temporary_path: str | None = None
    try:
        with NamedTemporaryFile(suffix=".xlsx", delete=False) as temporary_file:
            temporary_path = temporary_file.name
            uploaded_size = 0
            while chunk := await file.read(1024 * 1024):
                uploaded_size += len(chunk)
                if uploaded_size > MAX_RECEIVING_WORKBOOK_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=(
                            "Workbook exceeds the maximum upload size of "
                            f"{MAX_RECEIVING_WORKBOOK_SIZE_BYTES // (1024 * 1024)} MiB"
                        ),
                    )
                temporary_file.write(chunk)

        try:
            sheet_result = ReceivingExcelReader().read(temporary_path, worksheet_name)
        except (
            SourceFileNotFoundError,
            InvalidWorkbookError,
            WorksheetNotFoundError,
            RequiredHeadersNotFoundError,
        ) as error:
            message = str(error).replace(temporary_path, filename)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from error

        sheet_result = _rename_source_file(sheet_result, filename)
        validation_result = ReceivingValidationEngine().validate(sheet_result)
        mapping_result = ReceivingEventMappingEngine().map(
            validation_result,
            company_metadata=CompanyMetadata(company_code=company_code.strip()),
            **candidates,
        )
        preview = ReceivingImportPreview(
            source_file=filename,
            source_sheet=sheet_result.source_sheet,
            header_row=sheet_result.header_row,
            total_rows=sheet_result.total_rows,
            mapping_result=mapping_result,
        )
        token = preview_store.create(preview)
        return _preview_response(token, preview)
    finally:
        await file.close()
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


@router.post("/commit", response_model=CommitResponse)
def commit_receiving_import(
    request: CommitRequest,
    persistence_engine: ReceivingEventPersistenceEngine = Depends(get_receiving_persistence_engine),
) -> CommitResponse:
    # The in-memory preview store is single-process; serialize the entire commit
    # lifecycle for the supported single-worker MVP deployment.
    with _commit_lock:
        preview = preview_store.get(request.preview_token)
        if preview is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or expired preview token")

        result = persistence_engine.persist(preview.mapping_result.decisions, confirmed=True)
        if result.persisted:
            preview_store.remove(request.preview_token)
    return _commit_response(result)
