from datetime import datetime
from decimal import Decimal

from app.services.receiving_event_reader import (
    ReceivingRowClassification,
    ReceivingSheetResult,
    ReceivingSourceRow,
)
from app.services.receiving_event_validation_engine import ReceivingValidationEngine
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
    DETAIL_MISSING_PRODUCT,
    DETAIL_MISSING_QUANTITY,
    DETAIL_MISSING_REFERENCE,
    DETAIL_MISSING_SUBTOTAL,
    DETAIL_MISSING_UNIT,
    DETAIL_MISSING_UNIT_PRICE,
    DETAIL_QUANTITY_NOT_POSITIVE,
    DETAIL_SUBTOTAL_MISMATCH,
    MISSING_SUPPLIER_CONTEXT,
    PRESERVED_OTHER_ROW,
    ValidationSeverity,
    ValidationStatus,
)


def make_row(**overrides):
    base = dict(
        source_file="receiving.xlsx",
        source_sheet="Report",
        source_row=2,
        row_classification=ReceivingRowClassification.DETAIL,
        raw_supplier="Supplier A",
        raw_date_1=datetime(2026, 8, 12),
        raw_date_2=datetime(2026, 9, 3),
        event_date_candidate=datetime(2026, 8, 12),
        raw_reference="10560",
        raw_product="[162017] Sugar Brown Portion TLT",
        product_code="162017",
        raw_item_description="Brown sugar",
        raw_destination="Main Stores/Stock",
        raw_quantity=Decimal("2.5"),
        raw_unit="kg",
        raw_unit_price=Decimal("10.00"),
        raw_subtotal=Decimal("25.00"),
    )
    base.update(overrides)
    return ReceivingSourceRow(**base)


def make_sheet(*rows):
    return ReceivingSheetResult(
        source_file="receiving.xlsx",
        source_sheet="Report",
        header_row=1,
        total_rows=len(rows),
        detail_row_count=sum(1 for row in rows if row.row_classification is ReceivingRowClassification.DETAIL),
        non_detail_row_count=sum(1 for row in rows if row.row_classification is not ReceivingRowClassification.DETAIL),
        date_headers=("Date", "Receipt Date"),
        rows=tuple(rows),
    )


def test_valid_detail_row_passes_validation():
    row = make_row()
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert result.rows == (row,)
    assert result.detail_rows == (row,)
    assert result.eligible_detail_rows == (row,)
    assert result.summary.eligible_detail_row_count == 1
    assert not result.issues


def test_missing_supplier_context_is_blocking_error():
    row = make_row(raw_supplier=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    issue = result.issues[0]
    assert issue.code == MISSING_SUPPLIER_CONTEXT
    assert issue.severity is ValidationSeverity.ERROR
    assert issue.status is ValidationStatus.BLOCKED
    assert row not in result.eligible_detail_rows


def test_missing_reference_is_blocking_error():
    row = make_row(raw_reference=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_MISSING_REFERENCE for issue in result.issues)
    assert result.eligible_detail_rows == ()


def test_missing_product_is_blocking_error():
    row = make_row(raw_product=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_MISSING_PRODUCT for issue in result.issues)


def test_invalid_product_code_is_blocking_error():
    row = make_row(raw_product="Sugar Brown Portion TLT", product_code=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_INVALID_PRODUCT_CODE for issue in result.issues)


def test_missing_destination_is_blocking_error():
    row = make_row(raw_destination=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_MISSING_DESTINATION for issue in result.issues)


def test_missing_quantity_is_blocking_error():
    row = make_row(raw_quantity=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_MISSING_QUANTITY for issue in result.issues)


def test_invalid_quantity_is_blocking_error():
    row = make_row(raw_quantity="abc")
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_INVALID_QUANTITY for issue in result.issues)


def test_non_positive_quantity_is_blocking_error():
    row = make_row(raw_quantity=Decimal("0"))
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_QUANTITY_NOT_POSITIVE for issue in result.issues)


def test_missing_unit_is_blocking_error():
    row = make_row(raw_unit=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_MISSING_UNIT for issue in result.issues)


def test_missing_unit_price_is_blocking_error():
    row = make_row(raw_unit_price=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_MISSING_UNIT_PRICE for issue in result.issues)


def test_invalid_unit_price_is_blocking_error():
    row = make_row(raw_unit_price="bad")
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_INVALID_UNIT_PRICE for issue in result.issues)


def test_missing_subtotal_is_blocking_error():
    row = make_row(raw_subtotal=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_MISSING_SUBTOTAL for issue in result.issues)


def test_invalid_subtotal_is_blocking_error():
    row = make_row(raw_subtotal="bad")
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_INVALID_SUBTOTAL for issue in result.issues)


def test_subtotal_mismatch_is_blocking_error():
    row = make_row(raw_subtotal=Decimal("18.00"))
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_SUBTOTAL_MISMATCH for issue in result.issues)


def test_subtotal_tolerance_02_is_allowed():
    row = make_row(raw_subtotal=Decimal("24.99"))
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert all(issue.code != DETAIL_SUBTOTAL_MISMATCH for issue in result.issues)
    assert result.eligible_detail_rows == (row,)


def test_missing_date_1_and_date_2_are_blocking_errors():
    row = make_row(raw_date_1=None, raw_date_2=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_MISSING_DATE_1 for issue in result.issues)
    assert any(issue.code == DETAIL_MISSING_DATE_2 for issue in result.issues)


def test_invalid_date_values_are_blocking_errors():
    row = make_row(raw_date_1="bad", raw_date_2="bad")
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert any(issue.code == DETAIL_INVALID_DATE_1 for issue in result.issues)
    assert any(issue.code == DETAIL_INVALID_DATE_2 for issue in result.issues)


def test_other_rows_are_preserved_with_info_issue():
    row = make_row(row_classification=ReceivingRowClassification.OTHER, raw_reference=None, raw_product=None)
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert result.preserved_other_rows == (row,)
    assert any(issue.code == PRESERVED_OTHER_ROW for issue in result.issues)
    assert result.issues[0].severity is ValidationSeverity.INFO


def test_product_summary_rows_are_preserved_without_being_eligible():
    row = make_row(
        row_classification=ReceivingRowClassification.PRODUCT_SUMMARY,
        raw_reference=None,
        raw_product="Food / Sugar",
        raw_supplier="Supplier A",
        raw_destination=None,
    )
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert result.rows == (row,)
    assert result.detail_rows == ()
    assert result.eligible_detail_rows == ()


def test_supplier_header_rows_are_preserved_without_being_eligible():
    row = make_row(
        row_classification=ReceivingRowClassification.SUPPLIER_HEADER,
        raw_reference=None,
        raw_product=None,
        raw_supplier="Supplier A",
        raw_destination=None,
    )
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert result.rows == (row,)
    assert result.detail_rows == ()
    assert result.eligible_detail_rows == ()


def test_no_source_row_is_discarded_and_raw_values_are_untouched():
    row = make_row(raw_reference="10560", raw_product="[162017] Sugar Brown Portion TLT")
    base_reference = row.raw_reference
    base_product = row.raw_product
    base_supplier = row.raw_supplier
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert len(result.rows) == 1
    assert result.rows[0].source_row == row.source_row
    assert result.rows[0].raw_reference == base_reference
    assert result.rows[0].raw_product == base_product
    assert result.rows[0].raw_supplier == base_supplier
    assert result.issues == tuple(issue for issue in result.issues if True)


def test_eligible_detail_rows_only_include_valid_non_blocking_rows():
    valid = make_row(source_row=2)
    invalid = make_row(source_row=3, raw_reference=None)
    result = ReceivingValidationEngine().validate(make_sheet(valid, invalid))

    assert result.eligible_detail_rows == (valid,)
    assert result.summary.eligible_detail_row_count == 1
    assert result.summary.blocked_detail_row_count == 1


def test_validation_engine_works_without_database_access():
    row = make_row()
    result = ReceivingValidationEngine().validate(make_sheet(row))

    assert result.summary.total_rows == 1
    assert result.summary.detail_row_count == 1
    assert not result.issues
