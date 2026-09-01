from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from app.services.purchase_request_mapping_engine import (
    MappingStatus,
    PurchaseRequestMappingResult,
)
from app.services.purchase_request_reader import QuantityClassification
from app.services.purchase_request_validation_engine import (
    MISSING_ITEM_DESCRIPTION,
    MISSING_PRODUCT_IDENTITY,
    MISSING_QUANTITY,
    MISSING_UNIT,
    PurchaseRequestValidationResult,
    ValidationSeverity,
    ValidationStatus,
)


class DecisionStatus(str, Enum):
    READY = "READY"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


class LocationStatus(str, Enum):
    # Location mapping is deferred until a trusted import metadata contract
    # exists (Phase 10B.3.0). This is the only value this phase may use.
    DEFERRED = "DEFERRED"


class ReasonCode(str, Enum):
    # Reject reasons, derived from validation ERROR findings only.
    VALIDATION_ERROR = "VALIDATION_ERROR"
    MISSING_QUANTITY = "MISSING_QUANTITY"
    MISSING_PRODUCT_IDENTITY = "MISSING_PRODUCT_IDENTITY"
    MISSING_UNIT = "MISSING_UNIT"

    # Review reasons, derived from mapping/quantity conditions.
    PRODUCT_UNMAPPED = "PRODUCT_UNMAPPED"
    PRODUCT_AMBIGUOUS = "PRODUCT_AMBIGUOUS"
    UNIT_UNMAPPED = "UNIT_UNMAPPED"
    UNIT_AMBIGUOUS = "UNIT_AMBIGUOUS"
    QUANTITY_PACKAGING_REVIEW = "QUANTITY_PACKAGING_REVIEW"
    QUANTITY_UNKNOWN_TOKEN = "QUANTITY_UNKNOWN_TOKEN"
    QUANTITY_TEXTUAL_REVIEW = "QUANTITY_TEXTUAL_REVIEW"

    # Supplementary review context, never a sole trigger by themselves.
    VALIDATION_WARNING = "VALIDATION_WARNING"
    MISSING_ITEM_DESCRIPTION = "MISSING_ITEM_DESCRIPTION"


# Known validation-finding codes mapped to reject reasons. Any other
# ERROR-severity finding falls back to the generic VALIDATION_ERROR code.
_REJECT_REASON_BY_FINDING_CODE = {
    MISSING_QUANTITY: ReasonCode.MISSING_QUANTITY,
    MISSING_PRODUCT_IDENTITY: ReasonCode.MISSING_PRODUCT_IDENTITY,
    MISSING_UNIT: ReasonCode.MISSING_UNIT,
}

_ACCEPTABLE_QUANTITY_CLASSIFICATIONS = frozenset(
    {QuantityClassification.PURE_NUMERIC, QuantityClassification.EXPLICIT_ZERO}
)

_QUANTITY_REVIEW_REASON_BY_CLASSIFICATION = {
    QuantityClassification.QUANTITY_WITH_PACKAGING: ReasonCode.QUANTITY_PACKAGING_REVIEW,
    QuantityClassification.UNKNOWN_QUANTITY_TOKEN: ReasonCode.QUANTITY_UNKNOWN_TOKEN,
    QuantityClassification.TEXTUAL_QUANTITY: ReasonCode.QUANTITY_TEXTUAL_REVIEW,
}


def _dedupe_preserving_order(codes: list[ReasonCode]) -> tuple[ReasonCode, ...]:
    seen: set[ReasonCode] = set()
    ordered: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return tuple(ordered)


@dataclass(frozen=True)
class PurchaseRequestMappingDecision:
    source_file: str
    source_sheet: str
    source_row: int

    normalized_product_id: int | None
    normalized_unit_id: int | None

    quantity_classification: QuantityClassification
    quantity_value: Decimal | None
    quantity_token: str | None
    packaging_token: str | None

    raw_internal_reference: Any
    raw_product: Any
    raw_item_description: Any
    raw_unit: Any
    raw_quantity: str | None

    decision_status: DecisionStatus
    eligible_for_persistence: bool
    reason_codes: tuple[ReasonCode, ...]
    location_status: LocationStatus


class PurchaseRequestMappingDecisionEngine:
    def decide(
        self,
        validation_result: PurchaseRequestValidationResult,
        mapping_result: PurchaseRequestMappingResult,
    ) -> PurchaseRequestMappingDecision:
        if validation_result.status is ValidationStatus.ERROR:
            reject_reasons = self._reject_reasons(validation_result)
            return self._build(
                validation_result,
                mapping_result,
                status=DecisionStatus.REJECTED,
                reason_codes=reject_reasons,
            )

        if mapping_result.quantity_classification is QuantityClassification.BLANK_QUANTITY:
            return self._build(
                validation_result,
                mapping_result,
                status=DecisionStatus.REJECTED,
                reason_codes=(ReasonCode.MISSING_QUANTITY,),
            )

        review_reasons = self._review_reasons(validation_result, mapping_result)
        if review_reasons:
            return self._build(
                validation_result,
                mapping_result,
                status=DecisionStatus.REVIEW,
                reason_codes=review_reasons,
            )

        return self._build(
            validation_result,
            mapping_result,
            status=DecisionStatus.READY,
            reason_codes=(),
        )

    def _reject_reasons(
        self, validation_result: PurchaseRequestValidationResult
    ) -> tuple[ReasonCode, ...]:
        codes = [
            _REJECT_REASON_BY_FINDING_CODE.get(finding.code, ReasonCode.VALIDATION_ERROR)
            for finding in validation_result.findings
            if finding.severity is ValidationSeverity.ERROR
        ]
        if not codes:
            codes = [ReasonCode.VALIDATION_ERROR]
        return _dedupe_preserving_order(codes)

    def _review_reasons(
        self,
        validation_result: PurchaseRequestValidationResult,
        mapping_result: PurchaseRequestMappingResult,
    ) -> tuple[ReasonCode, ...]:
        codes: list[ReasonCode] = []

        if mapping_result.product.status is MappingStatus.UNMAPPED:
            codes.append(ReasonCode.PRODUCT_UNMAPPED)
        elif mapping_result.product.status is MappingStatus.AMBIGUOUS:
            codes.append(ReasonCode.PRODUCT_AMBIGUOUS)

        if mapping_result.unit.status is MappingStatus.UNMAPPED:
            codes.append(ReasonCode.UNIT_UNMAPPED)
        elif mapping_result.unit.status is MappingStatus.AMBIGUOUS:
            codes.append(ReasonCode.UNIT_AMBIGUOUS)

        quantity_reason = _QUANTITY_REVIEW_REASON_BY_CLASSIFICATION.get(
            mapping_result.quantity_classification
        )
        if quantity_reason is not None:
            codes.append(quantity_reason)

        # These are supplementary context, never a sole trigger: a validation
        # WARNING (e.g. missing optional Item description) does not by
        # itself force REVIEW unless another unresolved condition already
        # does. They are only appended once the row is already under review.
        if codes:
            if validation_result.status is ValidationStatus.WARNING:
                codes.append(ReasonCode.VALIDATION_WARNING)
            if any(
                finding.code == MISSING_ITEM_DESCRIPTION for finding in validation_result.findings
            ):
                codes.append(ReasonCode.MISSING_ITEM_DESCRIPTION)

        return _dedupe_preserving_order(codes)

    def _build(
        self,
        validation_result: PurchaseRequestValidationResult,
        mapping_result: PurchaseRequestMappingResult,
        *,
        status: DecisionStatus,
        reason_codes: tuple[ReasonCode, ...],
    ) -> PurchaseRequestMappingDecision:
        return PurchaseRequestMappingDecision(
            source_file=mapping_result.source_file,
            source_sheet=mapping_result.source_sheet,
            source_row=mapping_result.source_row,
            normalized_product_id=mapping_result.product.normalized_product_id,
            normalized_unit_id=mapping_result.unit.normalized_unit_id,
            quantity_classification=mapping_result.quantity_classification,
            quantity_value=mapping_result.quantity_value,
            quantity_token=mapping_result.quantity_token,
            packaging_token=mapping_result.packaging_token,
            raw_internal_reference=mapping_result.product.raw_internal_reference,
            raw_product=mapping_result.product.raw_product,
            raw_item_description=mapping_result.product.raw_item_description,
            raw_unit=mapping_result.unit.raw_unit,
            raw_quantity=validation_result.raw_quantity,
            decision_status=status,
            eligible_for_persistence=status is DecisionStatus.READY,
            reason_codes=reason_codes,
            location_status=LocationStatus.DEFERRED,
        )
