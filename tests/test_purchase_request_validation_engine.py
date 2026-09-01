import inspect
from decimal import Decimal

from app.services.purchase_request_reader import (
    PurchaseRequestSourceRow,
    QuantityClassification,
    QuantityReading,
    RowClassification,
)
from app.services.purchase_request_validation_engine import (
    EXPLICIT_ZERO,
    INTERNAL_REFERENCE_PRESENT,
    MISSING_ITEM_DESCRIPTION,
    MISSING_PRODUCT_IDENTITY,
    MISSING_QUANTITY,
    MISSING_UNIT,
    NotAProductRowError,
    PurchaseRequestValidationEngine,
    QUANTITY_EXPRESSION_REQUIRES_REVIEW,
    TEXTUAL_QUANTITY_REQUIRES_REVIEW,
    UNKNOWN_QUANTITY_TOKEN,
    ValidationSeverity,
    ValidationStatus,
)


def make_row(
    *,
    row_classification=RowClassification.PRODUCT_ROW,
    raw_internal_reference="161021",
    raw_product="Beef Tenderloin",
    raw_item_description="Fresh cut",
    raw_unit="kg",
    quantity: QuantityReading,
    source_row: int = 4,
) -> PurchaseRequestSourceRow:
    return PurchaseRequestSourceRow(
        source_file="PR 22.8.2026 freezer (5)(2).xlsx",
        source_sheet="Sheet1",
        source_row=source_row,
        row_classification=row_classification,
        raw_internal_reference=raw_internal_reference,
        raw_product=raw_product,
        raw_item_description=raw_item_description,
        raw_unit=raw_unit,
        quantity=quantity,
    )


def numeric_quantity(value: str) -> QuantityReading:
    return QuantityReading(
        QuantityClassification.PURE_NUMERIC, raw_quantity=value, quantity_value=Decimal(value)
    )


def zero_quantity() -> QuantityReading:
    return QuantityReading(
        QuantityClassification.EXPLICIT_ZERO, raw_quantity="0", quantity_value=Decimal("0")
    )


def blank_quantity() -> QuantityReading:
    return QuantityReading(QuantityClassification.BLANK_QUANTITY, raw_quantity=None)


def packaging_quantity(quantity_token: str, packaging_token: str) -> QuantityReading:
    return QuantityReading(
        QuantityClassification.QUANTITY_WITH_PACKAGING,
        raw_quantity=f"{quantity_token} {packaging_token}",
        quantity_token=quantity_token,
        packaging_token=packaging_token,
    )


def unknown_token_quantity(quantity_token: str, packaging_token: str) -> QuantityReading:
    return QuantityReading(
        QuantityClassification.UNKNOWN_QUANTITY_TOKEN,
        raw_quantity=f"{quantity_token} {packaging_token}",
        quantity_token=quantity_token,
        packaging_token=packaging_token,
    )


def textual_quantity(text: str) -> QuantityReading:
    return QuantityReading(QuantityClassification.TEXTUAL_QUANTITY, raw_quantity=text)


def test_valid_numeric_quantity_with_unit():
    row = make_row(quantity=numeric_quantity("500"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert result.status is ValidationStatus.VALID
    assert result.eligible_for_next_stage is True
    assert not result.error_findings
    assert not result.warning_findings


def test_numeric_quantity_missing_unit_is_error():
    row = make_row(raw_unit=None, quantity=numeric_quantity("500"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert result.status is ValidationStatus.ERROR
    assert result.eligible_for_next_stage is False
    assert any(f.code == MISSING_UNIT for f in result.findings)


def test_explicit_zero_is_info_and_eligible():
    row = make_row(quantity=zero_quantity())

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert result.quantity_classification is QuantityClassification.EXPLICIT_ZERO
    assert any(
        f.code == EXPLICIT_ZERO and f.severity is ValidationSeverity.INFO
        for f in result.findings
    )
    assert result.status is ValidationStatus.VALID
    assert result.eligible_for_next_stage is True


def test_blank_quantity_is_error_and_ineligible():
    row = make_row(quantity=blank_quantity())

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert any(f.code == MISSING_QUANTITY for f in result.findings)
    assert result.status is ValidationStatus.ERROR
    assert result.eligible_for_next_stage is False


def test_zero_and_blank_produce_different_results():
    zero_result = PurchaseRequestValidationEngine().validate_row(make_row(quantity=zero_quantity()))
    blank_result = PurchaseRequestValidationEngine().validate_row(
        make_row(quantity=blank_quantity())
    )

    assert zero_result.status is ValidationStatus.VALID
    assert zero_result.eligible_for_next_stage is True
    assert blank_result.status is ValidationStatus.ERROR
    assert blank_result.eligible_for_next_stage is False


def test_one_box_is_warning_and_eligible_without_conversion():
    row = make_row(quantity=packaging_quantity("1", "box"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert any(f.code == QUANTITY_EXPRESSION_REQUIRES_REVIEW for f in result.findings)
    assert result.status is ValidationStatus.WARNING
    assert result.eligible_for_next_stage is True
    assert result.quantity_value is None
    assert result.raw_quantity == "1 box"


def test_five_box_is_warning_and_eligible_without_conversion():
    row = make_row(quantity=packaging_quantity("5", "box"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert any(f.code == QUANTITY_EXPRESSION_REQUIRES_REVIEW for f in result.findings)
    assert result.status is ValidationStatus.WARNING
    assert result.eligible_for_next_stage is True
    assert result.quantity_value is None


def test_eight_gol_is_warning_and_never_converted_to_numeric():
    row = make_row(quantity=unknown_token_quantity("8", "gol"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert any(f.code == UNKNOWN_QUANTITY_TOKEN for f in result.findings)
    assert result.status is ValidationStatus.WARNING
    assert result.eligible_for_next_stage is True
    assert result.quantity_value is None
    assert result.raw_quantity == "8 gol"


def test_textual_quantity_requires_review():
    row = make_row(quantity=textual_quantity("مطلوب"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert any(f.code == TEXTUAL_QUANTITY_REQUIRES_REVIEW for f in result.findings)
    assert result.status is ValidationStatus.WARNING
    assert result.eligible_for_next_stage is True
    assert result.raw_quantity == "مطلوب"


def test_missing_product_identity_is_error():
    row = make_row(
        raw_internal_reference=None, raw_product=None, quantity=numeric_quantity("500")
    )

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert any(f.code == MISSING_PRODUCT_IDENTITY for f in result.findings)
    assert result.status is ValidationStatus.ERROR
    assert result.eligible_for_next_stage is False


def test_internal_reference_present_and_name_missing_is_not_rejected():
    row = make_row(raw_internal_reference="161021", raw_product=None, quantity=numeric_quantity("500"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert not any(f.code == MISSING_PRODUCT_IDENTITY for f in result.findings)
    assert any(f.code == INTERNAL_REFERENCE_PRESENT for f in result.findings)
    assert result.eligible_for_next_stage is True


def test_name_present_and_internal_reference_missing_is_not_rejected():
    row = make_row(
        raw_internal_reference=None, raw_product="Beef Tenderloin", quantity=numeric_quantity("500")
    )

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert not any(f.code == MISSING_PRODUCT_IDENTITY for f in result.findings)
    assert not any(f.code == INTERNAL_REFERENCE_PRESENT for f in result.findings)
    assert result.eligible_for_next_stage is True


def test_missing_item_description_is_warning_but_still_eligible():
    row = make_row(raw_item_description=None, quantity=numeric_quantity("500"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert any(f.code == MISSING_ITEM_DESCRIPTION for f in result.findings)
    assert result.status is ValidationStatus.WARNING
    assert result.eligible_for_next_stage is True


def test_raw_values_are_preserved_unmodified():
    row = make_row(
        raw_internal_reference="161021",
        raw_product="Beef Tenderloin",
        raw_item_description="Fresh cut",
        raw_unit="kg",
        quantity=packaging_quantity("5", "box"),
    )

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert result.raw_internal_reference == "161021"
    assert result.raw_product == "Beef Tenderloin"
    assert result.raw_item_description == "Fresh cut"
    assert result.raw_unit == "kg"
    assert result.raw_quantity == "5 box"
    assert result.packaging_token == "box"


def test_provenance_is_preserved_even_when_invalid():
    row = make_row(quantity=blank_quantity(), source_row=42)

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert result.source_file == "PR 22.8.2026 freezer (5)(2).xlsx"
    assert result.source_sheet == "Sheet1"
    assert result.source_row == 42
    assert result.status is ValidationStatus.ERROR


def test_multiple_findings_can_exist_on_one_row():
    row = make_row(raw_unit=None, raw_item_description=None, quantity=numeric_quantity("500"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    codes = {f.code for f in result.findings}
    assert MISSING_UNIT in codes
    assert MISSING_ITEM_DESCRIPTION in codes
    assert len(result.findings) >= 2


def test_repeated_validation_is_deterministic():
    row = make_row(quantity=packaging_quantity("5", "box"))
    engine = PurchaseRequestValidationEngine()

    assert engine.validate_row(row) == engine.validate_row(row)


def test_batch_validation_returns_results_for_all_product_rows():
    rows = [
        make_row(quantity=numeric_quantity("500"), source_row=2),
        make_row(quantity=zero_quantity(), source_row=3),
    ]

    results = PurchaseRequestValidationEngine().validate(rows)

    assert len(results) == 2
    assert [r.source_row for r in results] == [2, 3]


def test_category_row_does_not_become_product_validation():
    row = make_row(
        row_classification=RowClassification.CATEGORY_ROW,
        raw_internal_reference=None,
        raw_product="Food / Beef",
        raw_unit=None,
        quantity=blank_quantity(),
    )

    engine = PurchaseRequestValidationEngine()
    try:
        engine.validate_row(row)
        assert False, "expected NotAProductRowError"
    except NotAProductRowError:
        pass

    # Batch validation must silently exclude non-product rows.
    assert engine.validate([row]) == ()


def test_no_database_dependency():
    import app.services.purchase_request_validation_engine as validation_module

    source = inspect.getsource(validation_module)
    assert "sqlalchemy" not in source.lower()
    assert "SessionLocal" not in source
    assert "app.core.database" not in source


def test_error_takes_precedence_over_warning_and_valid():
    row = make_row(raw_unit=None, quantity=packaging_quantity("5", "box"))

    result = PurchaseRequestValidationEngine().validate_row(row)

    assert any(f.severity is ValidationSeverity.ERROR for f in result.findings)
    assert any(f.severity is ValidationSeverity.WARNING for f in result.findings)
    assert result.status is ValidationStatus.ERROR
    assert result.eligible_for_next_stage is False
