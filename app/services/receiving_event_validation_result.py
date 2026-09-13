from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.services.receiving_event_reader import (
    ReceivingRowClassification,
    ReceivingSheetResult,
    ReceivingSourceRow,
)


MISSING_REQUIRED_HEADERS = "MISSING_REQUIRED_HEADERS"
MISSING_SUPPLIER_CONTEXT = "MISSING_SUPPLIER_CONTEXT"
INVALID_ROW_CLASSIFICATION = "INVALID_ROW_CLASSIFICATION"
DETAIL_MISSING_REFERENCE = "DETAIL_MISSING_REFERENCE"
DETAIL_MISSING_PRODUCT = "DETAIL_MISSING_PRODUCT"
DETAIL_INVALID_PRODUCT_CODE = "DETAIL_INVALID_PRODUCT_CODE"
DETAIL_MISSING_DESTINATION = "DETAIL_MISSING_DESTINATION"
DETAIL_MISSING_QUANTITY = "DETAIL_MISSING_QUANTITY"
DETAIL_INVALID_QUANTITY = "DETAIL_INVALID_QUANTITY"
DETAIL_QUANTITY_NOT_POSITIVE = "DETAIL_QUANTITY_NOT_POSITIVE"
DETAIL_MISSING_UNIT = "DETAIL_MISSING_UNIT"
DETAIL_MISSING_UNIT_PRICE = "DETAIL_MISSING_UNIT_PRICE"
DETAIL_INVALID_UNIT_PRICE = "DETAIL_INVALID_UNIT_PRICE"
DETAIL_MISSING_SUBTOTAL = "DETAIL_MISSING_SUBTOTAL"
DETAIL_INVALID_SUBTOTAL = "DETAIL_INVALID_SUBTOTAL"
DETAIL_SUBTOTAL_MISMATCH = "DETAIL_SUBTOTAL_MISMATCH"
DETAIL_MISSING_DATE_1 = "DETAIL_MISSING_DATE_1"
DETAIL_INVALID_DATE_1 = "DETAIL_INVALID_DATE_1"
DETAIL_MISSING_DATE_2 = "DETAIL_MISSING_DATE_2"
DETAIL_INVALID_DATE_2 = "DETAIL_INVALID_DATE_2"
DETAIL_MISSING_EVENT_DATE_CANDIDATE = "DETAIL_MISSING_EVENT_DATE_CANDIDATE"
PRESERVED_OTHER_ROW = "PRESERVED_OTHER_ROW"


class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ReceivingValidationIssue:
    code: str
    severity: ValidationSeverity
    status: ValidationStatus
    message: str
    source_file: str
    source_sheet: str
    source_row: int
    row_classification: ReceivingRowClassification
    field: str | None = None
    raw_value: Any = None
    row: ReceivingSourceRow | None = None
    supplier_context: Any = None
    event_date_candidate: Any = None


@dataclass(frozen=True)
class ReceivingValidationSummary:
    total_rows: int
    detail_row_count: int
    other_row_count: int
    eligible_detail_row_count: int
    blocked_detail_row_count: int
    error_count: int
    warning_count: int
    info_count: int


@dataclass(frozen=True)
class ReceivingValidationResult:
    rows: tuple[ReceivingSourceRow, ...]
    issues: tuple[ReceivingValidationIssue, ...]
    detail_rows: tuple[ReceivingSourceRow, ...]
    eligible_detail_rows: tuple[ReceivingSourceRow, ...]
    preserved_other_rows: tuple[ReceivingSourceRow, ...]
    summary: ReceivingValidationSummary

    @property
    def error_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


__all__ = [
    "MISSING_REQUIRED_HEADERS",
    "MISSING_SUPPLIER_CONTEXT",
    "INVALID_ROW_CLASSIFICATION",
    "DETAIL_MISSING_REFERENCE",
    "DETAIL_MISSING_PRODUCT",
    "DETAIL_INVALID_PRODUCT_CODE",
    "DETAIL_MISSING_DESTINATION",
    "DETAIL_MISSING_QUANTITY",
    "DETAIL_INVALID_QUANTITY",
    "DETAIL_QUANTITY_NOT_POSITIVE",
    "DETAIL_MISSING_UNIT",
    "DETAIL_MISSING_UNIT_PRICE",
    "DETAIL_INVALID_UNIT_PRICE",
    "DETAIL_MISSING_SUBTOTAL",
    "DETAIL_INVALID_SUBTOTAL",
    "DETAIL_SUBTOTAL_MISMATCH",
    "DETAIL_MISSING_DATE_1",
    "DETAIL_INVALID_DATE_1",
    "DETAIL_MISSING_DATE_2",
    "DETAIL_INVALID_DATE_2",
    "DETAIL_MISSING_EVENT_DATE_CANDIDATE",
    "PRESERVED_OTHER_ROW",
    "ValidationSeverity",
    "ValidationStatus",
    "ReceivingValidationIssue",
    "ReceivingValidationSummary",
    "ReceivingValidationResult",
]
