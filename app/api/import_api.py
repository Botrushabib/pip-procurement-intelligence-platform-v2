from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import os
from pathlib import Path
import secrets
from tempfile import NamedTemporaryFile
from threading import Lock
import time
from types import SimpleNamespace
from typing import Annotated, Any, Iterable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.branch import Branch
from app.models.product import Product
from app.models.purchase_transaction import PurchaseTransaction
from app.models.supplier import Supplier
from app.models.unit import Unit
from app.models.warehouse import Warehouse
from app.services.excel_reader import ExcelInspectionResult, ExcelReader
from app.services.mapping_engine import DestinationCandidate, MappingCandidate
from app.services.odoo_import_engine import (
    BusinessFingerprint,
    DuplicateClassification,
    ExistingTransaction,
    ImportCommitResult,
    ImportError as ServiceImportError,
    ImportPreview,
    ImportRowResult,
    ImportRowStatus,
    OdooImportEngine,
    SourceIdentity,
    business_fingerprint_from_transaction,
)


router = APIRouter(prefix="/api/import/odoo", tags=["import"])


class SourceIdentityDTO(BaseModel):
    source_file: str
    source_sheet: str
    source_row: int = Field(ge=1)


class CommitRequest(BaseModel):
    preview_token: str = Field(min_length=1)
    accepted_source_identities: list[SourceIdentityDTO]


class ErrorDTO(BaseModel):
    source_file: str | None
    source_sheet: str | None
    source_row: int | None
    error_type: str
    message: str


class DuplicateInfoDTO(BaseModel):
    classification: str
    matching_source_identities: list[SourceIdentityDTO]


class RowResultDTO(BaseModel):
    source_identity: SourceIdentityDTO
    status: str
    business_fingerprint: dict[str, Any] | None
    duplicate_info: DuplicateInfoDTO | None
    errors: list[ErrorDTO]
    eligible_for_commit: bool


class PreviewResponse(BaseModel):
    preview_token: str
    source_file: str
    source_sheet: str | None
    header_row: int | None
    rows_read: int
    structurally_invalid_count: int
    validation_failure_count: int
    unmapped_count: int
    ambiguous_count: int
    source_duplicate_count: int
    potential_business_duplicate_count: int
    eligible_for_commit_count: int
    row_results: list[RowResultDTO]
    errors: list[ErrorDTO]


class CommitResponse(BaseModel):
    requested_count: int
    persisted_count: int
    skipped_count: int
    failed_count: int
    row_results: list[RowResultDTO]
    errors: list[ErrorDTO]


class PreviewStore:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, tuple[float, ImportPreview]] = {}
        self._lock = Lock()

    def create(self, preview: ImportPreview) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._purge()
            self._items[token] = (time.monotonic() + self.ttl_seconds, preview)
        return token

    def get(self, token: str) -> ImportPreview | None:
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
    ttl_seconds=int(os.getenv("PIP_IMPORT_PREVIEW_TTL_SECONDS", "300"))
)


class OriginalFilenameReader:
    def __init__(self, original_filename: str) -> None:
        self.original_filename = original_filename
        self.reader = ExcelReader()

    def read(self, source_file: str, worksheet_name: str | None = None) -> ExcelInspectionResult:
        inspection = self.reader.read(source_file, worksheet_name)
        records = tuple(
            replace(record, source_file=self.original_filename)
            for record in inspection.records
        )
        return replace(
            inspection,
            source_file=self.original_filename,
            records=records,
        )


def _load_candidates() -> tuple[list[Any], list[Any], list[Any], list[DestinationCandidate]]:
    session = SessionLocal()
    try:
        suppliers = [
            MappingCandidate(row.name, row.id)
            for row in session.scalars(select(Supplier)).all()
        ]
        products = [
            MappingCandidate(row.name, row.id)
            for row in session.scalars(select(Product)).all()
        ]
        units = [
            MappingCandidate(row.name, row.id)
            for row in session.scalars(select(Unit)).all()
        ]
        destinations = [
            DestinationCandidate(row.name, "BRANCH", branch_id=row.id)
            for row in session.scalars(select(Branch)).all()
        ] + [
            DestinationCandidate(row.name, "WAREHOUSE", warehouse_id=row.id)
            for row in session.scalars(select(Warehouse)).all()
        ]
        return suppliers, products, units, destinations
    finally:
        session.close()


def _duplicate_lookup(
    source_identities: tuple[SourceIdentity, ...],
    fingerprints: tuple[BusinessFingerprint, ...],
) -> Iterable[ExistingTransaction]:
    session = SessionLocal()
    try:
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
        return tuple(
            ExistingTransaction(
                SourceIdentity(row.source_file, row.source_sheet, row.source_row),
                business_fingerprint_from_transaction(SimpleNamespace(**row._mapping)),
            )
            for row in rows
        )
    finally:
        session.close()


def get_import_engine() -> OdooImportEngine:
    suppliers, products, units, destinations = _load_candidates()
    return OdooImportEngine(
        duplicate_lookup=_duplicate_lookup,
        suppliers=suppliers,
        products=products,
        units=units,
        destinations=destinations,
    )


def _error_dto(error: ServiceImportError) -> ErrorDTO:
    return ErrorDTO(
        source_file=error.source_file,
        source_sheet=error.source_sheet,
        source_row=error.source_row,
        error_type=error.error_type,
        message=error.message,
    )


def _identity_dto(identity: SourceIdentity) -> SourceIdentityDTO:
    return SourceIdentityDTO(
        source_file=identity.source_file,
        source_sheet=identity.source_sheet,
        source_row=identity.source_row,
    )


def _row_dto(row: ImportRowResult) -> RowResultDTO:
    duplicate_info = None
    if row.duplicate_info:
        duplicate_info = DuplicateInfoDTO(
            classification=row.duplicate_info.classification.value,
            matching_source_identities=[
                _identity_dto(identity)
                for identity in row.duplicate_info.matching_source_identities
            ],
        )
    fingerprint = None
    if row.business_fingerprint:
        fingerprint = row.business_fingerprint.__dict__.copy()
    return RowResultDTO(
        source_identity=_identity_dto(row.source_identity),
        status=row.status.value,
        business_fingerprint=fingerprint,
        duplicate_info=duplicate_info,
        errors=[_error_dto(error) for error in row.errors],
        eligible_for_commit=row.eligible_for_commit,
    )


def _preview_response(token: str, preview: ImportPreview) -> PreviewResponse:
    return PreviewResponse(
        preview_token=token,
        source_file=preview.source_file,
        source_sheet=preview.source_sheet,
        header_row=preview.header_row,
        rows_read=preview.rows_read,
        structurally_invalid_count=preview.structurally_invalid_count,
        validation_failure_count=preview.validation_failure_count,
        unmapped_count=preview.unmapped_count,
        ambiguous_count=preview.ambiguous_count,
        source_duplicate_count=preview.source_duplicate_count,
        potential_business_duplicate_count=preview.potential_business_duplicate_count,
        eligible_for_commit_count=preview.eligible_for_commit_count,
        row_results=[_row_dto(row) for row in preview.row_results],
        errors=[_error_dto(error) for error in preview.errors],
    )


def _commit_response(result: ImportCommitResult) -> CommitResponse:
    return CommitResponse(
        requested_count=result.requested_count,
        persisted_count=result.persisted_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
        row_results=[_row_dto(row) for row in result.row_results],
        errors=[_error_dto(error) for error in result.errors],
    )


@router.post("/preview", response_model=PreviewResponse)
async def preview_import(
    file: Annotated[UploadFile, File(...)],
    worksheet_name: Annotated[str | None, Form()] = None,
    import_engine: OdooImportEngine = Depends(get_import_engine),
) -> PreviewResponse:
    filename = Path(file.filename or "upload.xlsx").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .xlsx files are supported")
    temporary_path: str | None = None
    try:
        with NamedTemporaryFile(suffix=".xlsx", delete=False) as temporary_file:
            temporary_path = temporary_file.name
            while chunk := await file.read(1024 * 1024):
                temporary_file.write(chunk)
        import_engine.reader = OriginalFilenameReader(filename)
        preview = import_engine.preview(temporary_path, worksheet_name)
        if preview.errors and not preview.row_results:
            message = preview.errors[0].message.replace(temporary_path, filename)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
        token = preview_store.create(preview)
        return _preview_response(token, preview)
    finally:
        await file.close()
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


@router.post("/commit", response_model=CommitResponse)
def commit_import(
    request: CommitRequest,
    import_engine: OdooImportEngine = Depends(get_import_engine),
) -> CommitResponse:
    preview = preview_store.get(request.preview_token)
    if preview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or expired preview token")
    accepted = [
        SourceIdentity(item.source_file, item.source_sheet, item.source_row)
        for item in request.accepted_source_identities
    ]
    result = import_engine.commit(preview, accepted)
    if result.failed_count:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Import persistence failed",
        )
    preview_store.remove(request.preview_token)
    return _commit_response(result)