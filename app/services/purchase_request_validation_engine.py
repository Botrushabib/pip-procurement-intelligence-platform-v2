from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable

from app.services.purchase_request_reader import (
    PurchaseRequestSourceRow,
    QuantityClassification,
    RowClassification,
)


# Finding codes (Phase 10B.2 approved contract). Source-level findings only;
# mapping conclusions (MAPPED/UNMAPPED/AMBIGUOUS) belong to Phase 10B.3.
MISSING_PRODUCT_IDENTITY = "MISSING_PRODUCT_IDENTITY"
MISSING_UNIT = "MISSING_UNIT"
MISSING_QUANTITY = "MISSING_QUANTITY"

QUANTITY_EXPRESSION_REQUIRES_REVIEW = "QUANTITY_EXPRESSION_REQUIRES_REVIEW"
UNKNOWN_QUANTITY_TOKEN = "UNKNOWN_QUANTITY_TOKEN"
TEXTUAL_QUANTITY_REQUIRES_REVIEW = "TEXTUAL_QUANTITY_REQUIRES_REVIEW"
MISSING_ITEM_DESCRIPTION = "MISSING_ITEM_DESCRIPTION"

EXPLICIT_ZERO = "EXPLICIT_ZERO"
INTERNAL_REFERENCE_PRESENT = "INTERNAL_REFERENCE_PRESENT"
RAW_VALUE_PRESERVED = "RAW_VALUE_PRESERVED"


class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    ERROR = "ERROR"


class PurchaseRequestValidationError(Exception):
    """Base exception for Purchase Request validation-engine failures."""


class NotAProductRowError(PurchaseRequestValidationError):
    """Raised when a non-PRODUCT_ROW row is submitted for validation.

    This is the deterministic signal that a category/blank row must not be
    turned into a product-request validation result.
    """


@dataclass(frozen=True)
class ValidationFinding:
    code: str
    severity: ValidationSeverity
    message: str
    field: str


@dataclass(frozen=True)
class PurchaseRequestValidationResult:
    source_file: str
    source_sheet: str
    source_row: int
    status: ValidationStatus
    eligible_for_next_stage: bool
    findings: tuple[ValidationFinding, ...]
    quantity_classification: QuantityClassification
    raw_internal_reference: Any
    raw_product: Any
    raw_item_description: Any
    raw_unit: Any
    raw_quantity: str | None
    quantity_value: Decimal | None = None
    quantity_token: str | None = None
    packaging_token: str | None = None

    @property
    def error_findings(self) -> tuple[ValidationFinding, ...]:
        return tuple(f for f in self.findings if f.severity is ValidationSeverity.ERROR)

    @property
    def warning_findings(self) -> tuple[ValidationFinding, ...]:
        return tuple(f for f in self.findings if f.severity is ValidationSeverity.WARNING)


def _is_meaningful(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _overall_status(findings: Iterable[ValidationFinding]) -> ValidationStatus:
    severities = {finding.severity for finding in findings}
    if ValidationSeverity.ERROR in severities:
        return ValidationStatus.ERROR
    if ValidationSeverity.WARNING in severities:
        return ValidationStatus.WARNING
    return ValidationStatus.VALID


class PurchaseRequestValidationEngine:
    def validate_row(self, row: PurchaseRequestSourceRow) -> PurchaseRequestValidationResult:
        if row.row_classification is not RowClassification.PRODUCT_ROW:
            raise NotAProductRowError(
                f"Row at {row.source_file}:{row.source_sheet}:{row.source_row} is "
                f"classified as {row.row_classification.value}, not PRODUCT_ROW"
            )

        findings: list[ValidationFinding] = []

        internal_reference_present = _is_meaningful(row.raw_internal_reference)
        name_present = _is_meaningful(row.raw_product)
        item_description_present = _is_meaningful(row.raw_item_description)
        unit_present = _is_meaningful(row.raw_unit)

        # Rules 1-3: product identity (source presence only, no mapping).
        if not internal_reference_present and not name_present:
            findings.append(
                ValidationFinding(
                    MISSING_PRODUCT_IDENTITY,
                    ValidationSeverity.ERROR,
                    "Neither Internal Reference nor Name is present",
                    "raw_internal_reference",
                )
            )
        elif internal_reference_present:
            findings.append(
                ValidationFinding(
                    INTERNAL_REFERENCE_PRESENT,
                    ValidationSeverity.INFO,
                    "Internal Reference is present",
                    "raw_internal_reference",
                )
            )

        # Rule 4: Item description is optional; never blocks eligibility.
        if not item_description_present:
            findings.append(
                ValidationFinding(
                    MISSING_ITEM_DESCRIPTION,
                    ValidationSeverity.WARNING,
                    "Item description is not present",
                    "raw_item_description",
                )
            )

        # Rules 5-6: Unit must be present; the validator does not map it.
        if not unit_present:
            findings.append(
                ValidationFinding(
                    MISSING_UNIT,
                    ValidationSeverity.ERROR,
                    "Unit is not present",
                    "raw_unit",
                )
            )

        # Rules 7-11: quantity classification, never converted to a number.
        quantity = row.quantity
        if quantity.classification is QuantityClassification.BLANK_QUANTITY:
            findings.append(
                ValidationFinding(
                    MISSING_QUANTITY,
                    ValidationSeverity.ERROR,
                    "Quantity is blank",
                    "quantity.raw_quantity",
                )
            )
        elif quantity.classification is QuantityClassification.EXPLICIT_ZERO:
            findings.append(
                ValidationFinding(
                    EXPLICIT_ZERO,
                    ValidationSeverity.INFO,
                    "Quantity is explicitly zero",
                    "quantity.raw_quantity",
                )
            )
        elif quantity.classification is QuantityClassification.QUANTITY_WITH_PACKAGING:
            findings.append(
                ValidationFinding(
                    QUANTITY_EXPRESSION_REQUIRES_REVIEW,
                    ValidationSeverity.WARNING,
                    "Quantity contains a packaging expression and is not resolved",
                    "quantity.raw_quantity",
                )
            )
        elif quantity.classification is QuantityClassification.UNKNOWN_QUANTITY_TOKEN:
            findings.append(
                ValidationFinding(
                    UNKNOWN_QUANTITY_TOKEN,
                    ValidationSeverity.WARNING,
                    "Quantity contains an unrecognized token and is not resolved",
                    "quantity.raw_quantity",
                )
            )
        elif quantity.classification is QuantityClassification.TEXTUAL_QUANTITY:
            findings.append(
                ValidationFinding(
                    TEXTUAL_QUANTITY_REQUIRES_REVIEW,
                    ValidationSeverity.WARNING,
                    "Quantity is textual and is not resolved",
                    "quantity.raw_quantity",
                )
            )
        # PURE_NUMERIC requires no additional finding beyond the unit check above.

        findings.append(
            ValidationFinding(
                RAW_VALUE_PRESERVED,
                ValidationSeverity.INFO,
                "Raw source values are preserved unmodified",
                "raw_values",
            )
        )

        status = _overall_status(findings)

        return PurchaseRequestValidationResult(
            source_file=row.source_file,
            source_sheet=row.source_sheet,
            source_row=row.source_row,
            status=status,
            eligible_for_next_stage=status is not ValidationStatus.ERROR,
            findings=tuple(findings),
            quantity_classification=quantity.classification,
            raw_internal_reference=row.raw_internal_reference,
            raw_product=row.raw_product,
            raw_item_description=row.raw_item_description,
            raw_unit=row.raw_unit,
            raw_quantity=quantity.raw_quantity,
            quantity_value=quantity.quantity_value,
            quantity_token=quantity.quantity_token,
            packaging_token=quantity.packaging_token,
        )

    def validate(
        self, rows: Iterable[PurchaseRequestSourceRow]
    ) -> tuple[PurchaseRequestValidationResult, ...]:
        return tuple(
            self.validate_row(row)
            for row in rows
            if row.row_classification is RowClassification.PRODUCT_ROW
        )
