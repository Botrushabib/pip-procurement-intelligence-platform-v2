from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Iterable, Sequence

from app.services.excel_reader import (
    ExcelInspectionResult,
    ExcelReader,
    ExcelReaderError,
    RawPurchaseTransactionRecord,
)
from app.services.mapping_engine import (
    DestinationCandidate,
    MappedPurchaseTransaction,
    MappingEngine,
    MappingStatus,
)
from app.services.persistence_engine import (
    PersistenceEngine,
    PersistenceError,
    PersistenceResult,
)
from app.services.validation_engine import ValidationEngine, ValidationResult


class DuplicateClassification(str, Enum):
    DUPLICATE_SOURCE = "DUPLICATE_SOURCE"
    POTENTIAL_BUSINESS_DUPLICATE = "POTENTIAL_BUSINESS_DUPLICATE"


class ImportRowStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNMAPPED = "UNMAPPED"
    AMBIGUOUS = "AMBIGUOUS"
    DUPLICATE_SOURCE = "DUPLICATE_SOURCE"
    POTENTIAL_BUSINESS_DUPLICATE = "POTENTIAL_BUSINESS_DUPLICATE"
    READY_FOR_COMMIT = "READY_FOR_COMMIT"
    PERSISTED = "PERSISTED"
    FAILED = "FAILED"


@dataclass(frozen=True, order=True)
class SourceIdentity:
    source_file: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True)
class BusinessFingerprint:
    transaction_date: str | None
    reference: str | None
    supplier_id: int | None
    product_id: int | None
    unit_id: int | None
    destination_type: str | None
    branch_id: int | None
    warehouse_id: int | None
    sub_warehouse_name: str | None
    quantity: str | None
    unit_price: str | None
    subtotal: str | None


@dataclass(frozen=True)
class DuplicateInfo:
    classification: DuplicateClassification
    matching_source_identities: tuple[SourceIdentity, ...]


@dataclass(frozen=True)
class ImportError:
    source_file: str | None
    source_sheet: str | None
    source_row: int | None
    error_type: str
    message: str


@dataclass(frozen=True)
class ImportRowResult:
    source_identity: SourceIdentity
    raw_record: RawPurchaseTransactionRecord
    validation_result: ValidationResult
    mapped_transaction: MappedPurchaseTransaction | None
    business_fingerprint: BusinessFingerprint | None
    status: ImportRowStatus
    duplicate_info: DuplicateInfo | None = None
    errors: tuple[ImportError, ...] = ()
    eligible_for_commit: bool = False


@dataclass(frozen=True)
class ImportPreview:
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
    ready_for_commit_count: int
    row_results: tuple[ImportRowResult, ...] = ()
    errors: tuple[ImportError, ...] = ()
    mapped_records: tuple[MappedPurchaseTransaction, ...] = ()
    eligible_for_commit_count: int = 0


@dataclass(frozen=True)
class ImportCommitResult:
    requested_count: int
    persisted_count: int
    skipped_count: int
    failed_count: int
    row_results: tuple[ImportRowResult, ...] = ()
    errors: tuple[ImportError, ...] = ()


@dataclass(frozen=True)
class ExistingTransaction:
    source_identity: SourceIdentity
    business_fingerprint: BusinessFingerprint


DuplicateLookup = Callable[
    [tuple[SourceIdentity, ...], tuple[BusinessFingerprint, ...]],
    Iterable[ExistingTransaction],
]


def _canonical_text(value: Any) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).strip().split()).casefold()


def _canonical_date(value: date | datetime | Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _canonical_decimal(value: Any) -> str | None:
    if value is None:
        return None
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    return format(decimal_value.normalize(), "f")


def _fingerprint_values(
    *,
    transaction_date: Any,
    reference: Any,
    supplier_id: int | None,
    product_id: int | None,
    unit_id: int | None,
    destination_type: Any,
    branch_id: int | None,
    warehouse_id: int | None,
    sub_warehouse_name: Any,
    quantity: Any,
    unit_price: Any,
    subtotal: Any,
) -> BusinessFingerprint:
    return BusinessFingerprint(
        transaction_date=_canonical_date(transaction_date),
        reference=_canonical_text(reference),
        supplier_id=supplier_id,
        product_id=product_id,
        unit_id=unit_id,
        destination_type=_canonical_text(destination_type),
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        sub_warehouse_name=_canonical_text(sub_warehouse_name),
        quantity=_canonical_decimal(quantity),
        unit_price=_canonical_decimal(unit_price),
        subtotal=_canonical_decimal(subtotal),
    )


def business_fingerprint(mapped: MappedPurchaseTransaction) -> BusinessFingerprint:
    raw = mapped.raw_record
    return _fingerprint_values(
        transaction_date=raw.transaction_date,
        reference=raw.reference,
        supplier_id=mapped.supplier.resolved_id,
        product_id=mapped.product.resolved_id,
        unit_id=mapped.unit.resolved_id,
        destination_type=mapped.destination.destination_type,
        branch_id=mapped.destination.branch_id,
        warehouse_id=mapped.destination.warehouse_id,
        sub_warehouse_name=mapped.destination.sub_warehouse_name,
        quantity=raw.quantity_raw,
        unit_price=raw.unit_price_raw,
        subtotal=raw.subtotal_raw,
    )


def business_fingerprint_from_transaction(transaction: Any) -> BusinessFingerprint:
    return _fingerprint_values(
        transaction_date=transaction.transaction_date,
        reference=transaction.reference,
        supplier_id=transaction.supplier_id,
        product_id=transaction.product_id,
        unit_id=transaction.unit_id,
        destination_type=transaction.destination_type,
        branch_id=transaction.branch_id,
        warehouse_id=transaction.warehouse_id,
        sub_warehouse_name=transaction.sub_warehouse_name,
        quantity=transaction.quantity,
        unit_price=transaction.unit_price,
        subtotal=transaction.subtotal,
    )


def _source_identity(record: RawPurchaseTransactionRecord) -> SourceIdentity:
    return SourceIdentity(record.source_file, record.source_sheet, record.source_row)


def _row_error(row: ImportRowResult, error_type: str, message: str) -> ImportError:
    identity = row.source_identity
    return ImportError(
        identity.source_file,
        identity.source_sheet,
        identity.source_row,
        error_type,
        message,
    )


class OdooImportEngine:
    def __init__(
        self,
        *,
        duplicate_lookup: DuplicateLookup,
        reader: ExcelReader | None = None,
        validator: ValidationEngine | None = None,
        mapper: MappingEngine | None = None,
        persistence: PersistenceEngine | None = None,
        suppliers: Iterable[Any] = (),
        products: Iterable[Any] = (),
        units: Iterable[Any] = (),
        destinations: Iterable[DestinationCandidate] = (),
    ) -> None:
        self.reader = reader or ExcelReader()
        self.validator = validator or ValidationEngine()
        self.mapper = mapper or MappingEngine()
        self.persistence = persistence or PersistenceEngine()
        self.duplicate_lookup = duplicate_lookup
        self.suppliers = tuple(suppliers)
        self.products = tuple(products)
        self.units = tuple(units)
        self.destinations = tuple(destinations)

    def preview(
        self,
        source_file: str,
        worksheet_name: str | None = None,
    ) -> ImportPreview:
        try:
            inspection = self.reader.read(source_file, worksheet_name)
        except ExcelReaderError as error:
            return ImportPreview(
                source_file=source_file,
                source_sheet=worksheet_name,
                header_row=None,
                rows_read=0,
                structurally_invalid_count=0,
                validation_failure_count=0,
                unmapped_count=0,
                ambiguous_count=0,
                source_duplicate_count=0,
                potential_business_duplicate_count=0,
                ready_for_commit_count=0,
                errors=(ImportError(source_file, worksheet_name, None, type(error).__name__, str(error)),),
            )

        rows = []
        for record in inspection.records:
            validation = self.validator.validate(record)
            source_identity = _source_identity(record)
            if not validation.valid:
                errors = tuple(
                    ImportError(
                        record.source_file,
                        record.source_sheet,
                        record.source_row,
                        error.code,
                        error.message,
                    )
                    for error in validation.errors
                )
                rows.append(
                    ImportRowResult(
                        source_identity,
                        record,
                        validation,
                        None,
                        None,
                        ImportRowStatus.INVALID,
                        errors=errors,
                    )
                )
                continue

            mapped = self.mapper.map(
                validation,
                suppliers=self.suppliers,
                products=self.products,
                units=self.units,
                destinations=self.destinations,
            )
            mapping_statuses = (
                mapped.supplier.status,
                mapped.product.status,
                mapped.unit.status,
                mapped.destination.status,
            )
            if any(status is MappingStatus.UNMAPPED for status in mapping_statuses):
                status = ImportRowStatus.UNMAPPED
            elif any(status is MappingStatus.AMBIGUOUS for status in mapping_statuses):
                status = ImportRowStatus.AMBIGUOUS
            else:
                status = ImportRowStatus.VALID

            mapping_errors = ()
            if status in {ImportRowStatus.UNMAPPED, ImportRowStatus.AMBIGUOUS}:
                mapping_errors = (
                    _row_error(
                        ImportRowResult(source_identity, record, validation, mapped, None, status),
                        "MAPPING_ERROR",
                        "Required mappings are not all MAPPED",
                    ),
                )
            rows.append(
                ImportRowResult(
                    source_identity,
                    record,
                    validation,
                    mapped,
                    business_fingerprint(mapped) if status is ImportRowStatus.VALID else None,
                    status,
                    errors=mapping_errors,
                        eligible_for_commit=status is ImportRowStatus.VALID,
                )
            )

        valid_rows = [row for row in rows if row.business_fingerprint is not None]
        source_groups: dict[SourceIdentity, list[ImportRowResult]] = defaultdict(list)
        fingerprint_groups: dict[BusinessFingerprint, list[ImportRowResult]] = defaultdict(list)
        for row in valid_rows:
            source_groups[row.source_identity].append(row)
            fingerprint_groups[row.business_fingerprint].append(row)

        source_identities = tuple(row.source_identity for row in valid_rows)
        fingerprints = tuple(row.business_fingerprint for row in valid_rows)
        existing = tuple(self.duplicate_lookup(source_identities, fingerprints))
        existing_sources = {row.source_identity for row in existing}
        existing_fingerprints: dict[BusinessFingerprint, list[SourceIdentity]] = defaultdict(list)
        for transaction in existing:
            existing_fingerprints[transaction.business_fingerprint].append(transaction.source_identity)

        classified_rows: list[ImportRowResult] = []
        for row in rows:
            if row.business_fingerprint is None:
                classified_rows.append(row)
                continue
            source_matches = list(existing_sources.intersection({row.source_identity}))
            source_matches.extend(
                peer.source_identity
                for peer in source_groups[row.source_identity]
                if peer is not row
            )
            source_matches = tuple(sorted(set(source_matches)))
            fingerprint_matches = list(existing_fingerprints[row.business_fingerprint])
            fingerprint_matches.extend(
                peer.source_identity
                for peer in fingerprint_groups[row.business_fingerprint]
                if peer is not row
            )
            fingerprint_matches = tuple(sorted(set(fingerprint_matches)))

            if source_matches:
                info = DuplicateInfo(DuplicateClassification.DUPLICATE_SOURCE, source_matches)
                classified_rows.append(
                    replace(
                        row,
                        status=ImportRowStatus.DUPLICATE_SOURCE,
                        duplicate_info=info,
                        errors=row.errors
                        + (_row_error(row, info.classification.value, "Source Identity already exists"),),
                    )
                )
            elif fingerprint_matches:
                info = DuplicateInfo(DuplicateClassification.POTENTIAL_BUSINESS_DUPLICATE, fingerprint_matches)
                classified_rows.append(
                    replace(
                        row,
                        status=ImportRowStatus.POTENTIAL_BUSINESS_DUPLICATE,
                        duplicate_info=info,
                        errors=row.errors
                        + (_row_error(row, info.classification.value, "Business Fingerprint matches another transaction"),),
                        eligible_for_commit=True,
                    )
                )
            else:
                classified_rows.append(row)

        return self._preview_result(inspection, tuple(classified_rows))

    def commit(
        self,
        preview: ImportPreview,
        accepted_source_identities: Iterable[SourceIdentity],
    ) -> ImportCommitResult:
        accepted = tuple(dict.fromkeys(accepted_source_identities))
        rows_by_identity = {row.source_identity: row for row in preview.row_results}
        selected = []
        result_rows = list(preview.row_results)
        errors = list(preview.errors)

        for identity in accepted:
            row = rows_by_identity.get(identity)
            if row is None:
                errors.append(ImportError(identity.source_file, identity.source_sheet, identity.source_row, "NOT_IN_PREVIEW", "Source Identity is not present in preview"))
            elif row.status is ImportRowStatus.DUPLICATE_SOURCE:
                errors.append(_row_error(row, "DUPLICATE_SOURCE", "Source Identity cannot be committed"))
            elif row.mapped_transaction is None or row.status in {ImportRowStatus.INVALID, ImportRowStatus.UNMAPPED, ImportRowStatus.AMBIGUOUS}:
                errors.append(_row_error(row, "NOT_COMMIT_READY", "Row is not eligible for commit"))
            else:
                selected.append(row)

        persistence_result = (
            self.persistence.persist_batch(
                tuple(row.mapped_transaction for row in selected)
            )
            if selected
            else PersistenceResult(0, 0, 0)
        )
        persisted_identities = {
            SourceIdentity(*source_row) for source_row in persistence_result.persisted_source_rows
        }
        failed_identities = {
            SourceIdentity(error.source_file, error.source_sheet, error.source_row)
            for error in persistence_result.errors
            if error.error_type == "DATABASE_ERROR" and error.source_file is not None and error.source_sheet is not None and error.source_row is not None
        }

        for index, row in enumerate(result_rows):
            if row.source_identity in persisted_identities:
                result_rows[index] = replace(row, status=ImportRowStatus.PERSISTED)
            elif row.source_identity in failed_identities or (persistence_result.failed_count and row.source_identity in {candidate.source_identity for candidate in selected}):
                result_rows[index] = replace(row, status=ImportRowStatus.FAILED)

        errors.extend(
            ImportError(
                error.source_file,
                error.source_sheet,
                error.source_row,
                error.error_type,
                error.message,
            )
            for error in persistence_result.errors
        )
        return ImportCommitResult(
            requested_count=len(accepted),
            persisted_count=persistence_result.persisted_count,
            skipped_count=len(accepted) - len(selected) + persistence_result.skipped_count,
            failed_count=persistence_result.failed_count,
            row_results=tuple(result_rows),
            errors=tuple(errors),
        )

    @staticmethod
    def _preview_result(
        inspection: ExcelInspectionResult,
        rows: tuple[ImportRowResult, ...],
    ) -> ImportPreview:
        eligible = sum(
            row.status in {ImportRowStatus.VALID, ImportRowStatus.POTENTIAL_BUSINESS_DUPLICATE}
            for row in rows
        )
        return ImportPreview(
            source_file=inspection.source_file,
            source_sheet=inspection.source_sheet,
            header_row=inspection.header_row,
            rows_read=inspection.total_rows,
            structurally_invalid_count=inspection.skipped_rows,
            validation_failure_count=sum(row.status is ImportRowStatus.INVALID for row in rows),
            unmapped_count=sum(row.status is ImportRowStatus.UNMAPPED for row in rows),
            ambiguous_count=sum(row.status is ImportRowStatus.AMBIGUOUS for row in rows),
            source_duplicate_count=sum(row.status is ImportRowStatus.DUPLICATE_SOURCE for row in rows),
            potential_business_duplicate_count=sum(row.status is ImportRowStatus.POTENTIAL_BUSINESS_DUPLICATE for row in rows),
            ready_for_commit_count=0,
            row_results=rows,
            errors=tuple(error for row in rows for error in row.errors),
            mapped_records=tuple(row.mapped_transaction for row in rows if row.mapped_transaction is not None),
            eligible_for_commit_count=eligible,
        )