from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from app.services.receiving_event_mapping_result import (
    ReceivingEventLineMappingResult,
    ReceivingMappingStatus,
)


class ReceivingDecisionStatus(str, Enum):
    READY = "READY"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


class ReceivingReasonCode(str, Enum):
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"
    NON_DETAIL_ROW = "NON_DETAIL_ROW"
    MISSING_COMPANY_METADATA = "MISSING_COMPANY_METADATA"
    COMPANY_UNMAPPED = "COMPANY_UNMAPPED"
    COMPANY_AMBIGUOUS = "COMPANY_AMBIGUOUS"
    SUPPLIER_UNMAPPED = "SUPPLIER_UNMAPPED"
    SUPPLIER_AMBIGUOUS = "SUPPLIER_AMBIGUOUS"
    PRODUCT_UNMAPPED = "PRODUCT_UNMAPPED"
    PRODUCT_AMBIGUOUS = "PRODUCT_AMBIGUOUS"
    UNIT_UNMAPPED = "UNIT_UNMAPPED"
    UNIT_AMBIGUOUS = "UNIT_AMBIGUOUS"
    WAREHOUSE_UNMAPPED = "WAREHOUSE_UNMAPPED"
    WAREHOUSE_AMBIGUOUS = "WAREHOUSE_AMBIGUOUS"
    INVALID_EVENT_DATE = "INVALID_EVENT_DATE"
    DOCUMENT_GROUPING_CONFLICT = "DOCUMENT_GROUPING_CONFLICT"


@dataclass(frozen=True)
class ReceivingEventMappingDecision:
    line_result: ReceivingEventLineMappingResult
    company_id: int | None
    supplier_id: int | None
    warehouse_id: int | None
    product_id: int | None
    unit_id: int | None
    event_date: date | None
    receiving_reference: object
    decision_status: ReceivingDecisionStatus
    eligible_for_persistence: bool
    reason_codes: tuple[str, ...]

    @property
    def source_file(self) -> str:
        return self.line_result.source_file

    @property
    def source_sheet(self) -> str:
        return self.line_result.source_sheet

    @property
    def source_row(self) -> int:
        return self.line_result.source_row


class ReceivingEventMappingDecisionEngine:
    def decide(
        self,
        line_result: ReceivingEventLineMappingResult,
        *,
        validation_blocked: bool = False,
        non_detail: bool = False,
        validation_reason_codes: tuple[str, ...] = (),
        grouping_conflict: bool = False,
    ) -> ReceivingEventMappingDecision:
        reasons: list[str] = []
        if validation_blocked:
            reasons.extend((ReceivingReasonCode.VALIDATION_BLOCKED.value, *validation_reason_codes))
            return self._build(line_result, ReceivingDecisionStatus.REJECTED, reasons)
        if non_detail:
            return self._build(line_result, ReceivingDecisionStatus.REJECTED, [ReceivingReasonCode.NON_DETAIL_ROW.value])
        if line_result.company.raw_value is None or (
            isinstance(line_result.company.raw_value, str)
            and not line_result.company.raw_value.strip()
        ):
            return self._build(
                line_result,
                ReceivingDecisionStatus.REJECTED,
                [ReceivingReasonCode.MISSING_COMPANY_METADATA.value],
            )
        if line_result.event_date is None:
            return self._build(
                line_result,
                ReceivingDecisionStatus.REJECTED,
                [ReceivingReasonCode.INVALID_EVENT_DATE.value],
            )

        for mapping, unmapped, ambiguous in (
            (line_result.company, ReceivingReasonCode.COMPANY_UNMAPPED, ReceivingReasonCode.COMPANY_AMBIGUOUS),
            (line_result.supplier, ReceivingReasonCode.SUPPLIER_UNMAPPED, ReceivingReasonCode.SUPPLIER_AMBIGUOUS),
            (line_result.product, ReceivingReasonCode.PRODUCT_UNMAPPED, ReceivingReasonCode.PRODUCT_AMBIGUOUS),
            (line_result.unit, ReceivingReasonCode.UNIT_UNMAPPED, ReceivingReasonCode.UNIT_AMBIGUOUS),
            (line_result.warehouse, ReceivingReasonCode.WAREHOUSE_UNMAPPED, ReceivingReasonCode.WAREHOUSE_AMBIGUOUS),
        ):
            if mapping.status is ReceivingMappingStatus.UNMAPPED:
                reasons.append(unmapped.value)
            elif mapping.status is ReceivingMappingStatus.AMBIGUOUS:
                reasons.append(ambiguous.value)
            elif mapping.status is ReceivingMappingStatus.NOT_ATTEMPTED:
                reasons.append(unmapped.value)
        if grouping_conflict:
            reasons.append(ReceivingReasonCode.DOCUMENT_GROUPING_CONFLICT.value)
        status = ReceivingDecisionStatus.REVIEW if reasons else ReceivingDecisionStatus.READY
        return self._build(line_result, status, reasons)

    @staticmethod
    def _build(
        line_result: ReceivingEventLineMappingResult,
        status: ReceivingDecisionStatus,
        reasons: list[str],
    ) -> ReceivingEventMappingDecision:
        return ReceivingEventMappingDecision(
            line_result=line_result,
            company_id=line_result.company.normalized_id,
            supplier_id=line_result.supplier.normalized_id,
            warehouse_id=line_result.warehouse.normalized_id,
            product_id=line_result.product.normalized_id,
            unit_id=line_result.unit.normalized_id,
            event_date=line_result.event_date,
            receiving_reference=line_result.receiving_reference,
            decision_status=status,
            eligible_for_persistence=status is ReceivingDecisionStatus.READY,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )


__all__ = [
    "ReceivingDecisionStatus",
    "ReceivingEventMappingDecision",
    "ReceivingEventMappingDecisionEngine",
    "ReceivingReasonCode",
]