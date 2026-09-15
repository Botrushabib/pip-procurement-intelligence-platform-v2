from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.receiving_event import ReceivingEvent
from app.models.receiving_event_line import ReceivingEventLine
from app.services.receiving_event_mapping_decision import (
    ReceivingDecisionStatus,
    ReceivingEventMappingDecision,
)


MIXED_SOURCE_BATCH = "MIXED_SOURCE_BATCH"
NO_READY_LINES = "NO_READY_LINES"
DUPLICATE_SOURCE_IDENTITY = "DUPLICATE_SOURCE_IDENTITY"
EXACT_SOURCE_DUPLICATE = "EXACT_SOURCE_DUPLICATE"
GATE_BLOCKED = "GATE_BLOCKED"
NOT_CONFIRMED = "NOT_CONFIRMED"


SourceIdentity = tuple[str, str, int]
EventGroupingKey = tuple[int, int, int, object, object]


@dataclass(frozen=True)
class ReceivingPersistenceGateResult:
    ready_decisions: tuple[ReceivingEventMappingDecision, ...]
    review_decisions: tuple[ReceivingEventMappingDecision, ...]
    rejected_decisions: tuple[ReceivingEventMappingDecision, ...]
    duplicate_source_rows: tuple[SourceIdentity, ...]
    blocked_reasons: tuple[str, ...]
    can_persist: bool
    requires_confirmation: bool

    @property
    def eligible_ready_count(self) -> int:
        return len(self.ready_decisions)

    @property
    def review_count(self) -> int:
        return len(self.review_decisions)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_decisions)


@dataclass(frozen=True)
class ReceivingPersistenceResult:
    persisted: bool
    persisted_event_count: int
    persisted_line_count: int
    duplicate_source_rows: tuple[SourceIdentity, ...]
    gate: ReceivingPersistenceGateResult
    error: str | None = None


class ReceivingEventPersistenceEngine:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.session_factory = session_factory

    def gate(
        self,
        decisions: Iterable[ReceivingEventMappingDecision],
    ) -> ReceivingPersistenceGateResult:
        decisions = tuple(decisions)
        ready = tuple(
            decision
            for decision in decisions
            if (
                decision.decision_status is ReceivingDecisionStatus.READY
                and decision.eligible_for_persistence
            )
        )
        review = tuple(
            decision
            for decision in decisions
            if decision.decision_status is ReceivingDecisionStatus.REVIEW
        )
        rejected = tuple(
            decision
            for decision in decisions
            if decision.decision_status is ReceivingDecisionStatus.REJECTED
        )

        blocked_reasons: list[str] = []
        source_batches = {
            (decision.source_file, decision.source_sheet) for decision in ready
        }
        if len(source_batches) > 1:
            blocked_reasons.append(MIXED_SOURCE_BATCH)

        source_identities = [self._source_identity(decision) for decision in ready]
        duplicate_source_rows = tuple(
            sorted(
                {
                    identity
                    for identity in source_identities
                    if source_identities.count(identity) > 1
                }
            )
        )
        if duplicate_source_rows:
            blocked_reasons.append(DUPLICATE_SOURCE_IDENTITY)

        if not ready:
            blocked_reasons.append(NO_READY_LINES)

        can_persist = bool(ready) and not blocked_reasons
        return ReceivingPersistenceGateResult(
            ready_decisions=ready,
            review_decisions=review,
            rejected_decisions=rejected,
            duplicate_source_rows=duplicate_source_rows,
            blocked_reasons=tuple(blocked_reasons),
            can_persist=can_persist,
            requires_confirmation=can_persist,
        )

    def persist(
        self,
        decisions: Iterable[ReceivingEventMappingDecision],
        *,
        confirmed: bool,
    ) -> ReceivingPersistenceResult:
        gate_result = self.gate(decisions)
        if not gate_result.can_persist:
            return self._unwritten_result(gate_result, GATE_BLOCKED)
        if not confirmed:
            return self._unwritten_result(gate_result, NOT_CONFIRMED)

        session = self.session_factory()
        duplicate_source_rows: tuple[SourceIdentity, ...] = ()
        persisted_event_count = 0
        persisted_line_count = 0
        try:
            with session.begin():
                duplicate_source_rows = self._find_existing_source_rows(
                    session, gate_result.ready_decisions
                )
                duplicate_set = set(duplicate_source_rows)
                ready_decisions = tuple(
                    decision
                    for decision in gate_result.ready_decisions
                    if self._source_identity(decision) not in duplicate_set
                )
                if not ready_decisions:
                    return ReceivingPersistenceResult(
                        persisted=False,
                        persisted_event_count=0,
                        persisted_line_count=0,
                        duplicate_source_rows=duplicate_source_rows,
                        gate=gate_result,
                        error=EXACT_SOURCE_DUPLICATE,
                    )

                grouped: dict[EventGroupingKey, list[ReceivingEventMappingDecision]] = {}
                for decision in ready_decisions:
                    grouped.setdefault(self._grouping_key(decision), []).append(decision)

                for group_decisions in grouped.values():
                    first = group_decisions[0]
                    event = self._to_event(first)
                    session.add(event)
                    session.flush()
                    persisted_event_count += 1

                    for line_number, decision in enumerate(group_decisions, start=1):
                        session.add(self._to_line(decision, event.id, line_number))
                        persisted_line_count += 1
                session.flush()
        except SQLAlchemyError as error:
            session.rollback()
            return ReceivingPersistenceResult(
                persisted=False,
                persisted_event_count=0,
                persisted_line_count=0,
                duplicate_source_rows=duplicate_source_rows,
                gate=gate_result,
                error=type(error).__name__,
            )
        finally:
            session.close()

        return ReceivingPersistenceResult(
            persisted=True,
            persisted_event_count=persisted_event_count,
            persisted_line_count=persisted_line_count,
            duplicate_source_rows=duplicate_source_rows,
            gate=gate_result,
        )

    @staticmethod
    def _source_identity(
        decision: ReceivingEventMappingDecision,
    ) -> SourceIdentity:
        return decision.source_file, decision.source_sheet, decision.source_row

    @staticmethod
    def _grouping_key(
        decision: ReceivingEventMappingDecision,
    ) -> EventGroupingKey:
        return (
            decision.company_id,
            decision.supplier_id,
            decision.warehouse_id,
            decision.event_date,
            decision.receiving_reference,
        )

    @staticmethod
    def _find_existing_source_rows(
        session: Session,
        decisions: tuple[ReceivingEventMappingDecision, ...],
    ) -> tuple[SourceIdentity, ...]:
        source_files = {decision.source_file for decision in decisions}
        source_sheets = {decision.source_sheet for decision in decisions}
        source_rows = {decision.source_row for decision in decisions}
        rows = session.execute(
            select(
                ReceivingEventLine.source_file,
                ReceivingEventLine.source_sheet,
                ReceivingEventLine.source_row,
            ).where(
                ReceivingEventLine.source_file.in_(source_files),
                ReceivingEventLine.source_sheet.in_(source_sheets),
                ReceivingEventLine.source_row.in_(source_rows),
            )
        ).all()
        candidates = {
            (decision.source_file, decision.source_sheet, decision.source_row)
            for decision in decisions
        }
        existing = {(row[0], row[1], row[2]) for row in rows}
        return tuple(sorted(candidates & existing))

    @staticmethod
    def _to_event(decision: ReceivingEventMappingDecision) -> ReceivingEvent:
        row = decision.line_result.row
        return ReceivingEvent(
            company_id=decision.company_id,
            supplier_id=decision.supplier_id,
            warehouse_id=decision.warehouse_id,
            receiving_reference=str(decision.receiving_reference),
            event_date=decision.event_date,
            raw_reference=_raw_text(row.raw_reference),
            raw_supplier=_raw_text(row.raw_supplier),
            raw_destination=_raw_text(row.raw_destination),
            raw_date_1=_raw_text(row.raw_date_1),
            raw_date_2=_raw_text(row.raw_date_2),
            source_file=row.source_file,
            source_sheet=row.source_sheet,
            source_row=None,
        )

    @staticmethod
    def _to_line(
        decision: ReceivingEventMappingDecision,
        receiving_event_id: int,
        line_number: int,
    ) -> ReceivingEventLine:
        row = decision.line_result.row
        return ReceivingEventLine(
            receiving_event_id=receiving_event_id,
            line_number=line_number,
            product_id=decision.product_id,
            unit_id=decision.unit_id,
            quantity=row.raw_quantity,
            unit_price=row.raw_unit_price,
            subtotal=row.raw_subtotal,
            raw_product=_raw_text(row.raw_product),
            raw_item_description=_raw_text(row.raw_item_description),
            raw_reference=_raw_text(row.raw_reference),
            raw_quantity=_raw_text(row.raw_quantity),
            raw_unit=_raw_text(row.raw_unit),
            raw_unit_price=_raw_text(row.raw_unit_price),
            raw_subtotal=_raw_text(row.raw_subtotal),
            raw_destination=_raw_text(row.raw_destination),
            raw_supplier=_raw_text(row.raw_supplier),
            raw_date_1=_raw_text(row.raw_date_1),
            raw_date_2=_raw_text(row.raw_date_2),
            source_file=row.source_file,
            source_sheet=row.source_sheet,
            source_row=row.source_row,
        )

    @staticmethod
    def _unwritten_result(
        gate_result: ReceivingPersistenceGateResult,
        error: str,
    ) -> ReceivingPersistenceResult:
        return ReceivingPersistenceResult(
            persisted=False,
            persisted_event_count=0,
            persisted_line_count=0,
            duplicate_source_rows=gate_result.duplicate_source_rows,
            gate=gate_result,
            error=error,
        )


def _raw_text(value: object) -> str | None:
    return None if value is None else str(value)


persist_receiving_events = ReceivingEventPersistenceEngine().persist


__all__ = [
    "DUPLICATE_SOURCE_IDENTITY",
    "EXACT_SOURCE_DUPLICATE",
    "GATE_BLOCKED",
    "MIXED_SOURCE_BATCH",
    "NO_READY_LINES",
    "NOT_CONFIRMED",
    "ReceivingEventPersistenceEngine",
    "ReceivingPersistenceGateResult",
    "ReceivingPersistenceResult",
    "persist_receiving_events",
]
