from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.purchase_request import PurchaseRequest, PurchaseRequestStatus
from app.models.purchase_request_line import PurchaseRequestLine
from app.services.mapping_engine import BRANCH, SUB_WAREHOUSE, WAREHOUSE
from app.services.purchase_request_mapping_decision import (
    DecisionStatus,
    PurchaseRequestMappingDecision,
)
from app.services.purchase_request_reader import QuantityClassification


# Header blocked-reason codes.
MISSING_COMPANY_ID = "MISSING_COMPANY_ID"
MISSING_DESTINATION_TYPE = "MISSING_DESTINATION_TYPE"
MISSING_REQUEST_DATE = "MISSING_REQUEST_DATE"
MISSING_BRANCH_FOR_DESTINATION = "MISSING_BRANCH_FOR_DESTINATION"
MISSING_WAREHOUSE_FOR_DESTINATION = "MISSING_WAREHOUSE_FOR_DESTINATION"
MISSING_SUB_WAREHOUSE_NAME_FOR_DESTINATION = "MISSING_SUB_WAREHOUSE_NAME_FOR_DESTINATION"

# Batch/line blocked-reason codes.
MIXED_SOURCE_BATCH = "MIXED_SOURCE_BATCH"
NO_READY_LINES = "NO_READY_LINES"
EXACT_SOURCE_DUPLICATE = "EXACT_SOURCE_DUPLICATE"

# Business-duplicate detection is explicitly deferred: the current schema
# has no field capable of safely establishing "same real-world ask" beyond
# exact source identity, so this is reported rather than guessed.
BUSINESS_DUPLICATE_CHECK_STATUS = "NOT_IMPLEMENTED"

# persist() outcome codes when no database write occurs.
GATE_BLOCKED = "GATE_BLOCKED"
NOT_CONFIRMED = "NOT_CONFIRMED"

_HEADER_ACCEPTABLE_QUANTITY_CLASSIFICATIONS = frozenset(
    {QuantityClassification.PURE_NUMERIC, QuantityClassification.EXPLICIT_ZERO}
)


@dataclass(frozen=True)
class ImportMetadata:
    company_id: int | None
    destination_type: str | None
    request_date: date | None
    branch_id: int | None = None
    warehouse_id: int | None = None
    sub_warehouse_name: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class PersistenceGateResult:
    header_ready: bool
    metadata: ImportMetadata
    ready_lines: tuple[PurchaseRequestMappingDecision, ...]
    review_lines: tuple[PurchaseRequestMappingDecision, ...]
    rejected_lines: tuple[PurchaseRequestMappingDecision, ...]
    duplicate_blocked_lines: tuple[PurchaseRequestMappingDecision, ...]
    blocked_reasons: tuple[str, ...]
    can_persist: bool
    requires_confirmation: bool
    business_duplicate_check: str = BUSINESS_DUPLICATE_CHECK_STATUS


@dataclass(frozen=True)
class PersistenceResult:
    persisted: bool
    purchase_request_id: int | None
    persisted_line_count: int
    review_count: int
    rejected_count: int
    duplicate_blocked_count: int
    gate: PersistenceGateResult
    error: str | None = None


def _line_is_persistence_ready(decision: PurchaseRequestMappingDecision) -> bool:
    return (
        decision.decision_status is DecisionStatus.READY
        and decision.eligible_for_persistence
        and decision.normalized_product_id is not None
        and decision.normalized_unit_id is not None
        and decision.quantity_value is not None
    )


def _requested_quantity(decision: PurchaseRequestMappingDecision):
    if decision.quantity_classification in _HEADER_ACCEPTABLE_QUANTITY_CLASSIFICATIONS:
        return decision.quantity_value
    return None


class PurchaseRequestPersistenceEngine:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self.session_factory = session_factory

    def gate(
        self,
        decisions: Iterable[PurchaseRequestMappingDecision],
        metadata: ImportMetadata,
    ) -> PersistenceGateResult:
        decisions = tuple(decisions)
        blocked_reasons: list[str] = list(self._header_blocked_reasons(metadata))
        header_ready = not blocked_reasons

        batch_keys = {(d.source_file, d.source_sheet) for d in decisions}
        if len(batch_keys) > 1:
            blocked_reasons.append(MIXED_SOURCE_BATCH)

        ready = tuple(d for d in decisions if _line_is_persistence_ready(d))
        review = tuple(d for d in decisions if d.decision_status is DecisionStatus.REVIEW)
        rejected = tuple(d for d in decisions if d.decision_status is DecisionStatus.REJECTED)

        duplicate_blocked: tuple[PurchaseRequestMappingDecision, ...] = ()
        if ready and len(batch_keys) <= 1:
            existing_keys = self._find_existing_source_keys(ready)
            if existing_keys:
                duplicate_blocked = tuple(
                    d for d in ready if (d.source_file, d.source_sheet, d.source_row) in existing_keys
                )
                if duplicate_blocked:
                    blocked_reasons.append(EXACT_SOURCE_DUPLICATE)
                    duplicate_set = set(duplicate_blocked)
                    ready = tuple(d for d in ready if d not in duplicate_set)

        if not ready:
            blocked_reasons.append(NO_READY_LINES)

        can_persist = header_ready and len(batch_keys) <= 1 and bool(ready)

        return PersistenceGateResult(
            header_ready=header_ready,
            metadata=metadata,
            ready_lines=ready,
            review_lines=review,
            rejected_lines=rejected,
            duplicate_blocked_lines=duplicate_blocked,
            blocked_reasons=tuple(dict.fromkeys(blocked_reasons)),
            can_persist=can_persist,
            requires_confirmation=can_persist,
        )

    def persist(
        self,
        decisions: Iterable[PurchaseRequestMappingDecision],
        metadata: ImportMetadata,
        *,
        confirmed: bool,
    ) -> PersistenceResult:
        gate_result = self.gate(decisions, metadata)

        if not gate_result.can_persist:
            return self._unwritten_result(gate_result, error=GATE_BLOCKED)
        if not confirmed:
            return self._unwritten_result(gate_result, error=NOT_CONFIRMED)

        session = self.session_factory()
        try:
            with session.begin():
                first_line = gate_result.ready_lines[0]
                header = PurchaseRequest(
                    company_id=metadata.company_id,
                    branch_id=metadata.branch_id,
                    warehouse_id=metadata.warehouse_id,
                    destination_type=metadata.destination_type,
                    sub_warehouse_name=metadata.sub_warehouse_name,
                    request_date=metadata.request_date,
                    reference=metadata.reference,
                    status=PurchaseRequestStatus.DRAFT.value,
                    source_file=first_line.source_file,
                    source_sheet=first_line.source_sheet,
                    source_row=None,
                )
                session.add(header)
                session.flush()

                for decision in gate_result.ready_lines:
                    session.add(
                        PurchaseRequestLine(
                            request_id=header.id,
                            product_id=decision.normalized_product_id,
                            unit_id=decision.normalized_unit_id,
                            requested_quantity=_requested_quantity(decision),
                            approved_quantity=None,
                            status=PurchaseRequestStatus.DRAFT.value,
                            raw_product=decision.raw_product,
                            raw_unit=decision.raw_unit,
                            raw_quantity=decision.raw_quantity,
                            raw_packaging=decision.packaging_token,
                            source_file=decision.source_file,
                            source_sheet=decision.source_sheet,
                            source_row=decision.source_row,
                        )
                    )
                session.flush()
                purchase_request_id = header.id
        except SQLAlchemyError as error:
            session.rollback()
            return self._unwritten_result(gate_result, error=type(error).__name__)
        finally:
            session.close()

        return PersistenceResult(
            persisted=True,
            purchase_request_id=purchase_request_id,
            persisted_line_count=len(gate_result.ready_lines),
            review_count=len(gate_result.review_lines),
            rejected_count=len(gate_result.rejected_lines),
            duplicate_blocked_count=len(gate_result.duplicate_blocked_lines),
            gate=gate_result,
        )

    def _unwritten_result(
        self, gate_result: PersistenceGateResult, *, error: str
    ) -> PersistenceResult:
        return PersistenceResult(
            persisted=False,
            purchase_request_id=None,
            persisted_line_count=0,
            review_count=len(gate_result.review_lines),
            rejected_count=len(gate_result.rejected_lines),
            duplicate_blocked_count=len(gate_result.duplicate_blocked_lines),
            gate=gate_result,
            error=error,
        )

    def _header_blocked_reasons(self, metadata: ImportMetadata) -> list[str]:
        reasons: list[str] = []
        if metadata.company_id is None:
            reasons.append(MISSING_COMPANY_ID)
        if metadata.destination_type is None:
            reasons.append(MISSING_DESTINATION_TYPE)
        elif metadata.destination_type == BRANCH:
            if metadata.branch_id is None:
                reasons.append(MISSING_BRANCH_FOR_DESTINATION)
        elif metadata.destination_type == WAREHOUSE:
            if metadata.warehouse_id is None:
                reasons.append(MISSING_WAREHOUSE_FOR_DESTINATION)
        elif metadata.destination_type == SUB_WAREHOUSE:
            if metadata.warehouse_id is None:
                reasons.append(MISSING_WAREHOUSE_FOR_DESTINATION)
            if not metadata.sub_warehouse_name:
                reasons.append(MISSING_SUB_WAREHOUSE_NAME_FOR_DESTINATION)
        if metadata.request_date is None:
            reasons.append(MISSING_REQUEST_DATE)
        return reasons

    def _find_existing_source_keys(
        self, decisions: tuple[PurchaseRequestMappingDecision, ...]
    ) -> set[tuple[str, str, int]]:
        session = self.session_factory()
        try:
            rows = session.execute(
                select(
                    PurchaseRequestLine.source_file,
                    PurchaseRequestLine.source_sheet,
                    PurchaseRequestLine.source_row,
                )
            ).all()
        finally:
            session.close()
        existing = {(row.source_file, row.source_sheet, row.source_row) for row in rows}
        candidates = {(d.source_file, d.source_sheet, d.source_row) for d in decisions}
        return candidates & existing
