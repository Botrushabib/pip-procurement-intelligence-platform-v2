from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.purchase_transaction import PurchaseTransaction
from app.services.mapping_engine import MappedPurchaseTransaction, MappingStatus


DUPLICATE_STRATEGY = "Duplicate persistence strategy is not specified by blueprint."


@dataclass(frozen=True)
class PersistenceError:
    source_file: str | None
    source_sheet: str | None
    source_row: int | None
    error_type: str
    message: str
    exception_type: str | None = None


@dataclass(frozen=True)
class PersistenceResult:
    persisted_count: int
    skipped_count: int
    failed_count: int
    errors: tuple[PersistenceError, ...] = ()
    persisted_source_rows: tuple[tuple[str, str, int], ...] = ()


def _trace(mapped: MappedPurchaseTransaction) -> tuple[str, str, int]:
    raw = mapped.raw_record
    return raw.source_file, raw.source_sheet, raw.source_row


def _rejection_error(mapped: MappedPurchaseTransaction) -> PersistenceError | None:
    raw = mapped.raw_record
    trace = (raw.source_file, raw.source_sheet, raw.source_row)
    if not mapped.validation_result.valid:
        return PersistenceError(
            *trace,
            error_type="VALIDATION_REJECTED",
            message="ValidationResult is invalid",
        )

    mappings = {
        "supplier": mapped.supplier.status,
        "product": mapped.product.status,
        "unit": mapped.unit.status,
        "destination": mapped.destination.status,
    }
    rejected = [
        f"{field}={status.value}"
        for field, status in mappings.items()
        if status is not MappingStatus.MAPPED
    ]
    if rejected:
        return PersistenceError(
            *trace,
            error_type="MAPPING_REJECTED",
            message="Required mappings are not all MAPPED: " + ", ".join(rejected),
        )
    return None


def _to_model(mapped: MappedPurchaseTransaction) -> PurchaseTransaction:
    raw = mapped.raw_record
    destination = mapped.destination
    return PurchaseTransaction(
        supplier_id=mapped.supplier.resolved_id,
        product_id=mapped.product.resolved_id,
        unit_id=mapped.unit.resolved_id,
        branch_id=destination.branch_id,
        warehouse_id=destination.warehouse_id,
        sub_warehouse_name=destination.sub_warehouse_name,
        destination_type=mapped.destination.destination_type,
        transaction_date=raw.transaction_date,
        reference=raw.reference,
        quantity=raw.quantity_raw,
        unit_price=raw.unit_price_raw,
        subtotal=raw.subtotal_raw,
        source_file=raw.source_file,
        source_sheet=raw.source_sheet,
        source_row=raw.source_row,
        supplier_raw=raw.supplier_raw,
        product_raw=raw.product_raw,
        destination_raw=raw.destination_raw,
        unit_raw=raw.unit_raw,
    )


class PersistenceEngine:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.session_factory = session_factory

    def persist(self, mapped: MappedPurchaseTransaction) -> PersistenceResult:
        return self.persist_batch((mapped,))

    def persist_batch(
        self,
        mapped_transactions: Iterable[MappedPurchaseTransaction],
    ) -> PersistenceResult:
        skipped_count = 0
        errors: list[PersistenceError] = []
        accepted: list[MappedPurchaseTransaction] = []

        for mapped in mapped_transactions:
            rejection = _rejection_error(mapped)
            if rejection is not None:
                skipped_count += 1
                errors.append(rejection)
            else:
                accepted.append(mapped)

        if not accepted:
            return PersistenceResult(
                persisted_count=0,
                skipped_count=skipped_count,
                failed_count=0,
                errors=tuple(errors),
            )

        session = self.session_factory()
        persisted_source_rows: list[tuple[str, str, int]] = []
        current_mapped: MappedPurchaseTransaction | None = None
        try:
            with session.begin():
                for mapped in accepted:
                    current_mapped = mapped
                    session.add(_to_model(mapped))
                    session.flush()
                    persisted_source_rows.append(_trace(mapped))
        except SQLAlchemyError as error:
            session.rollback()
            failed = current_mapped or accepted[0]
            raw = failed.raw_record
            errors.append(
                PersistenceError(
                    raw.source_file,
                    raw.source_sheet,
                    raw.source_row,
                    error_type="DATABASE_ERROR",
                    message="Database persistence failed",
                    exception_type=type(error).__name__,
                )
            )
            return PersistenceResult(
                persisted_count=0,
                skipped_count=skipped_count,
                failed_count=1,
                errors=tuple(errors),
            )
        finally:
            session.close()

        return PersistenceResult(
            persisted_count=len(persisted_source_rows),
            skipped_count=skipped_count,
            failed_count=0,
            errors=tuple(errors),
            persisted_source_rows=tuple(persisted_source_rows),
        )


persist_mapped_transaction = PersistenceEngine().persist