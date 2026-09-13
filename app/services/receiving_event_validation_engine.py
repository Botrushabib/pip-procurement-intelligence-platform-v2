from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.receiving_event_reader import (
    ReceivingRowClassification,
    ReceivingSheetResult,
    ReceivingSourceRow,
)
from app.services.receiving_event_validation_result import (
    DETAIL_INVALID_DATE_1,
    DETAIL_INVALID_DATE_2,
    DETAIL_INVALID_PRODUCT_CODE,
    DETAIL_INVALID_QUANTITY,
    DETAIL_INVALID_SUBTOTAL,
    DETAIL_INVALID_UNIT_PRICE,
    DETAIL_MISSING_DATE_1,
    DETAIL_MISSING_DATE_2,
    DETAIL_MISSING_DESTINATION,
    DETAIL_MISSING_EVENT_DATE_CANDIDATE,
    DETAIL_MISSING_PRODUCT,
    DETAIL_MISSING_QUANTITY,
    DETAIL_MISSING_REFERENCE,
    DETAIL_MISSING_SUBTOTAL,
    DETAIL_MISSING_UNIT,
    DETAIL_MISSING_UNIT_PRICE,
    DETAIL_QUANTITY_NOT_POSITIVE,
    DETAIL_SUBTOTAL_MISMATCH,
    INVALID_ROW_CLASSIFICATION,
    MISSING_REQUIRED_HEADERS,
    MISSING_SUPPLIER_CONTEXT,
    PRESERVED_OTHER_ROW,
    ReceivingValidationIssue,
    ReceivingValidationResult,
    ReceivingValidationSummary,
    ValidationSeverity,
    ValidationStatus,
)


class ReceivingValidationEngine:
    def validate(self, sheet_result: ReceivingSheetResult) -> ReceivingValidationResult:
        issues: list[ReceivingValidationIssue] = []
        rows = tuple(sheet_result.rows)
        detail_rows = tuple(
            row
            for row in rows
            if row.row_classification is ReceivingRowClassification.DETAIL
        )
        preserved_other_rows = tuple(
            row
            for row in rows
            if row.row_classification is ReceivingRowClassification.OTHER
        )

        if not sheet_result.date_headers:
            issues.append(
                ReceivingValidationIssue(
                    code=MISSING_REQUIRED_HEADERS,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Required receiving headers are missing or unreadable.",
                    source_file=sheet_result.source_file,
                    source_sheet=sheet_result.source_sheet,
                    source_row=1,
                    row_classification=ReceivingRowClassification.OTHER,
                    field=None,
                    raw_value=None,
                    row=None,
                    supplier_context=None,
                    event_date_candidate=None,
                )
            )

        row_issue_map: dict[int, list[ReceivingValidationIssue]] = {}
        for row in rows:
            if row.row_classification is ReceivingRowClassification.OTHER:
                issue = ReceivingValidationIssue(
                    code=PRESERVED_OTHER_ROW,
                    severity=ValidationSeverity.INFO,
                    status=ValidationStatus.VALID,
                    message="Non-detail row was preserved without being treated as a transaction.",
                    source_file=row.source_file,
                    source_sheet=row.source_sheet,
                    source_row=row.source_row,
                    row_classification=row.row_classification,
                    field=None,
                    raw_value=row.raw_reference,
                    row=row,
                    supplier_context=row.raw_supplier,
                    event_date_candidate=row.event_date_candidate,
                )
                issues.append(issue)
                row_issue_map.setdefault(row.source_row, []).append(issue)
                continue

            if row.row_classification is not ReceivingRowClassification.DETAIL:
                issues.append(
                    ReceivingValidationIssue(
                        code=INVALID_ROW_CLASSIFICATION,
                        severity=ValidationSeverity.WARNING,
                        status=ValidationStatus.WARNING,
                        message=f"Unsupported row classification '{row.row_classification.value}' encountered during validation.",
                        source_file=row.source_file,
                        source_sheet=row.source_sheet,
                        source_row=row.source_row,
                        row_classification=row.row_classification,
                        field=None,
                        raw_value=row.raw_reference,
                        row=row,
                        supplier_context=row.raw_supplier,
                        event_date_candidate=row.event_date_candidate,
                    )
                )
                row_issue_map.setdefault(row.source_row, []).append(issues[-1])
                continue

            row_issues = self._validate_detail_row(row)
            if row_issues:
                row_issue_map.setdefault(row.source_row, []).extend(row_issues)
                issues.extend(row_issues)

        eligible_detail_rows = tuple(
            row
            for row in detail_rows
            if not self._has_blocking_issue(row.source_row, row_issue_map)
        )

        error_count = sum(1 for issue in issues if issue.severity is ValidationSeverity.ERROR)
        warning_count = sum(1 for issue in issues if issue.severity is ValidationSeverity.WARNING)
        info_count = sum(1 for issue in issues if issue.severity is ValidationSeverity.INFO)

        summary = ReceivingValidationSummary(
            total_rows=len(rows),
            detail_row_count=len(detail_rows),
            other_row_count=len(preserved_other_rows),
            eligible_detail_row_count=len(eligible_detail_rows),
            blocked_detail_row_count=sum(
                1
                for row in detail_rows
                if self._has_blocking_issue(row.source_row, row_issue_map)
            ),
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
        )

        return ReceivingValidationResult(
            rows=rows,
            issues=tuple(issues),
            detail_rows=detail_rows,
            eligible_detail_rows=eligible_detail_rows,
            preserved_other_rows=preserved_other_rows,
            summary=summary,
        )

    def _validate_detail_row(self, row: ReceivingSourceRow) -> list[ReceivingValidationIssue]:
        issues: list[ReceivingValidationIssue] = []

        if not self._is_meaningful(row.raw_supplier):
            issues.append(
                self._issue(
                    code=MISSING_SUPPLIER_CONTEXT,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Supplier context is required for DETAIL rows.",
                    row=row,
                    field="raw_supplier",
                    raw_value=row.raw_supplier,
                    supplier_context=row.raw_supplier,
                )
            )

        if not self._is_meaningful(row.raw_reference):
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_REFERENCE,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Reference is required for DETAIL rows.",
                    row=row,
                    field="raw_reference",
                    raw_value=row.raw_reference,
                    supplier_context=row.raw_supplier,
                )
            )

        if not self._is_meaningful(row.raw_product):
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_PRODUCT,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Product is required for DETAIL rows.",
                    row=row,
                    field="raw_product",
                    raw_value=row.raw_product,
                    supplier_context=row.raw_supplier,
                )
            )
        elif row.product_code is None:
            issues.append(
                self._issue(
                    code=DETAIL_INVALID_PRODUCT_CODE,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Product code must be a leading [digits] token only.",
                    row=row,
                    field="raw_product",
                    raw_value=row.raw_product,
                    supplier_context=row.raw_supplier,
                )
            )

        if not self._is_meaningful(row.raw_destination):
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_DESTINATION,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Destination (To) is required for DETAIL rows.",
                    row=row,
                    field="raw_destination",
                    raw_value=row.raw_destination,
                    supplier_context=row.raw_supplier,
                )
            )

        quantity = self._decimal_or_none(row.raw_quantity)
        if row.raw_quantity is None or row.raw_quantity == "":
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_QUANTITY,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Quantity is required for DETAIL rows.",
                    row=row,
                    field="raw_quantity",
                    raw_value=row.raw_quantity,
                    supplier_context=row.raw_supplier,
                )
            )
        elif quantity is None:
            issues.append(
                self._issue(
                    code=DETAIL_INVALID_QUANTITY,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Quantity must be a valid numeric value.",
                    row=row,
                    field="raw_quantity",
                    raw_value=row.raw_quantity,
                    supplier_context=row.raw_supplier,
                )
            )
        elif quantity <= 0:
            issues.append(
                self._issue(
                    code=DETAIL_QUANTITY_NOT_POSITIVE,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Quantity must be strictly positive.",
                    row=row,
                    field="raw_quantity",
                    raw_value=row.raw_quantity,
                    supplier_context=row.raw_supplier,
                )
            )

        if not self._is_meaningful(row.raw_unit):
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_UNIT,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Unit is required for DETAIL rows.",
                    row=row,
                    field="raw_unit",
                    raw_value=row.raw_unit,
                    supplier_context=row.raw_supplier,
                )
            )

        unit_price = self._decimal_or_none(row.raw_unit_price)
        if row.raw_unit_price is None or row.raw_unit_price == "":
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_UNIT_PRICE,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Unit Price is required for DETAIL rows.",
                    row=row,
                    field="raw_unit_price",
                    raw_value=row.raw_unit_price,
                    supplier_context=row.raw_supplier,
                )
            )
        elif unit_price is None:
            issues.append(
                self._issue(
                    code=DETAIL_INVALID_UNIT_PRICE,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Unit Price must be numeric.",
                    row=row,
                    field="raw_unit_price",
                    raw_value=row.raw_unit_price,
                    supplier_context=row.raw_supplier,
                )
            )

        subtotal = self._decimal_or_none(row.raw_subtotal)
        if row.raw_subtotal is None or row.raw_subtotal == "":
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_SUBTOTAL,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Subtotal is required for DETAIL rows.",
                    row=row,
                    field="raw_subtotal",
                    raw_value=row.raw_subtotal,
                    supplier_context=row.raw_supplier,
                )
            )
        elif subtotal is None:
            issues.append(
                self._issue(
                    code=DETAIL_INVALID_SUBTOTAL,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Subtotal must be numeric.",
                    row=row,
                    field="raw_subtotal",
                    raw_value=row.raw_subtotal,
                    supplier_context=row.raw_supplier,
                )
            )

        if quantity is not None and unit_price is not None and subtotal is not None:
            expected = quantity * unit_price
            if abs(expected - subtotal) > Decimal("0.02"):
                issues.append(
                    self._issue(
                        code=DETAIL_SUBTOTAL_MISMATCH,
                        severity=ValidationSeverity.ERROR,
                        status=ValidationStatus.BLOCKED,
                        message="Qty × Unit Price differs from Subtotal by more than 0.02.",
                        row=row,
                        field="raw_subtotal",
                        raw_value=row.raw_subtotal,
                        supplier_context=row.raw_supplier,
                    )
                )

        if row.raw_date_1 is None:
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_DATE_1,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Source date 1 is required for DETAIL rows.",
                    row=row,
                    field="raw_date_1",
                    raw_value=row.raw_date_1,
                    supplier_context=row.raw_supplier,
                    event_date_candidate=row.event_date_candidate,
                )
            )
        elif not self._is_date_value(row.raw_date_1):
            issues.append(
                self._issue(
                    code=DETAIL_INVALID_DATE_1,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Source date 1 is not a valid date/datetime value.",
                    row=row,
                    field="raw_date_1",
                    raw_value=row.raw_date_1,
                    supplier_context=row.raw_supplier,
                    event_date_candidate=row.event_date_candidate,
                )
            )

        if row.raw_date_2 is None:
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_DATE_2,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Source date 2 is required for DETAIL rows.",
                    row=row,
                    field="raw_date_2",
                    raw_value=row.raw_date_2,
                    supplier_context=row.raw_supplier,
                    event_date_candidate=row.event_date_candidate,
                )
            )
        elif not self._is_date_value(row.raw_date_2):
            issues.append(
                self._issue(
                    code=DETAIL_INVALID_DATE_2,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="Source date 2 is not a valid date/datetime value.",
                    row=row,
                    field="raw_date_2",
                    raw_value=row.raw_date_2,
                    supplier_context=row.raw_supplier,
                    event_date_candidate=row.event_date_candidate,
                )
            )

        if row.event_date_candidate is None:
            issues.append(
                self._issue(
                    code=DETAIL_MISSING_EVENT_DATE_CANDIDATE,
                    severity=ValidationSeverity.ERROR,
                    status=ValidationStatus.BLOCKED,
                    message="The approved Date column is required and remains the event_date_candidate.",
                    row=row,
                    field="event_date_candidate",
                    raw_value=row.event_date_candidate,
                    supplier_context=row.raw_supplier,
                    event_date_candidate=row.event_date_candidate,
                )
            )

        return issues

    @staticmethod
    def _issue(
        *,
        code: str,
        severity: ValidationSeverity,
        status: ValidationStatus,
        message: str,
        row: ReceivingSourceRow,
        field: str | None,
        raw_value: Any,
        supplier_context: Any,
        event_date_candidate: Any | None = None,
    ) -> ReceivingValidationIssue:
        return ReceivingValidationIssue(
            code=code,
            severity=severity,
            status=status,
            message=message,
            source_file=row.source_file,
            source_sheet=row.source_sheet,
            source_row=row.source_row,
            row_classification=row.row_classification,
            field=field,
            raw_value=raw_value,
            row=row,
            supplier_context=supplier_context,
            event_date_candidate=event_date_candidate,
        )

    @staticmethod
    def _has_blocking_issue(
        source_row: int,
        row_issue_map: dict[int, list[ReceivingValidationIssue]],
    ) -> bool:
        for issue in row_issue_map.get(source_row, ()):
            if issue.status is ValidationStatus.BLOCKED or issue.severity is ValidationSeverity.ERROR:
                return True
        return False

    @staticmethod
    def _is_meaningful(value: Any) -> bool:
        return value is not None and (not isinstance(value, str) or bool(value.strip()))

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, int):
            return Decimal(value)
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return Decimal(stripped)
            except InvalidOperation:
                return None
        return None

    @staticmethod
    def _is_date_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, (datetime, date)):
            return True
        if not isinstance(value, str):
            return False
        text = value.strip()
        if not text:
            return False
        try:
            datetime.fromisoformat(text)
            return True
        except ValueError:
            pass
        try:
            date.fromisoformat(text)
            return True
        except ValueError:
            return False


validate_receiving_sheet = ReceivingValidationEngine().validate

__all__ = [
    "ReceivingValidationEngine",
    "validate_receiving_sheet",
]
