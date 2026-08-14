from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.services.excel_reader import RawPurchaseTransactionRecord


INVALID_TRANSACTION_DATE = "INVALID_TRANSACTION_DATE"
MISSING_REFERENCE = "MISSING_REFERENCE"
MISSING_PRODUCT = "MISSING_PRODUCT"
INVALID_QUANTITY = "INVALID_QUANTITY"
INVALID_UNIT_PRICE = "INVALID_UNIT_PRICE"
INVALID_SUBTOTAL = "INVALID_SUBTOTAL"


@dataclass(frozen=True)
class ValidationError:
    code: str
    field: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    raw_record: RawPurchaseTransactionRecord
    source_file: str
    source_sheet: str
    source_row: int
    valid: bool
    errors: tuple[ValidationError, ...]
    warnings: tuple[str, ...] = ()

    @property
    def validation_errors(self) -> tuple[ValidationError, ...]:
        return self.errors

    @property
    def error_codes(self) -> tuple[str, ...]:
        return tuple(error.code for error in self.errors)


def _is_meaningful(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


class ValidationEngine:
    def validate(self, record: RawPurchaseTransactionRecord) -> ValidationResult:
        errors: list[ValidationError] = []

        if not isinstance(record.transaction_date, datetime):
            errors.append(
                ValidationError(
                    code=INVALID_TRANSACTION_DATE,
                    field="transaction_date",
                    message="Transaction date must be a datetime",
                )
            )
        if not _is_meaningful(record.reference):
            errors.append(
                ValidationError(
                    code=MISSING_REFERENCE,
                    field="reference",
                    message="Reference is required",
                )
            )
        if not _is_meaningful(record.product_raw):
            errors.append(
                ValidationError(
                    code=MISSING_PRODUCT,
                    field="product_raw",
                    message="Product is required",
                )
            )
        if not _is_numeric(record.quantity_raw):
            errors.append(
                ValidationError(
                    code=INVALID_QUANTITY,
                    field="quantity_raw",
                    message="Quantity must be an int, float, or Decimal",
                )
            )
        if not _is_numeric(record.unit_price_raw):
            errors.append(
                ValidationError(
                    code=INVALID_UNIT_PRICE,
                    field="unit_price_raw",
                    message="Unit price must be an int, float, or Decimal",
                )
            )
        if not _is_numeric(record.subtotal_raw):
            errors.append(
                ValidationError(
                    code=INVALID_SUBTOTAL,
                    field="subtotal_raw",
                    message="Subtotal must be an int, float, or Decimal",
                )
            )

        return ValidationResult(
            raw_record=record,
            source_file=record.source_file,
            source_sheet=record.source_sheet,
            source_row=record.source_row,
            valid=not errors,
            errors=tuple(errors),
        )

    validate_record = validate


def validate_transaction(record: RawPurchaseTransactionRecord) -> ValidationResult:
    return ValidationEngine().validate(record)