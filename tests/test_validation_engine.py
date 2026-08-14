from datetime import datetime
from decimal import Decimal

import pytest

from app.services.excel_reader import RawPurchaseTransactionRecord
from app.services.validation_engine import (
    INVALID_QUANTITY,
    INVALID_SUBTOTAL,
    INVALID_TRANSACTION_DATE,
    INVALID_UNIT_PRICE,
    MISSING_PRODUCT,
    MISSING_REFERENCE,
    ValidationEngine,
    ValidationResult,
    validate_transaction,
)


def make_record(**changes):
    values = {
        "source_file": "purchases.xlsx",
        "source_sheet": "Report",
        "source_row": 7,
        "transaction_date": datetime(2026, 1, 15, 10, 30),
        "reference": "PO-001",
        "supplier_raw": "Supplier A",
        "product_raw": "Product A",
        "destination_raw": "Warehouse A",
        "quantity_raw": 2,
        "unit_raw": "Each",
        "unit_price_raw": 10.5,
        "subtotal_raw": Decimal("21.0"),
    }
    values.update(changes)
    return RawPurchaseTransactionRecord(**values)


def codes(result):
    return [error.code for error in result.errors]


def test_valid_transaction_returns_immutable_valid_result():
    record = make_record()

    result = ValidationEngine().validate(record)

    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.errors == ()
    assert result.raw_record is record


def test_invalid_date_and_missing_reference_and_product_are_reported():
    result = validate_transaction(
        make_record(transaction_date="2026-01-15", reference=None, product_raw=" ")
    )

    assert codes(result) == [
        INVALID_TRANSACTION_DATE,
        MISSING_REFERENCE,
        MISSING_PRODUCT,
    ]
    assert result.valid is False


@pytest.mark.parametrize("reference", [None, "", "   "])
def test_missing_reference_values_are_rejected(reference):
    result = ValidationEngine().validate(make_record(reference=reference))

    assert codes(result) == [MISSING_REFERENCE]


@pytest.mark.parametrize("product", [None, "", "   "])
def test_missing_product_values_are_rejected(product):
    result = ValidationEngine().validate(make_record(product_raw=product))

    assert codes(result) == [MISSING_PRODUCT]


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("quantity_raw", INVALID_QUANTITY),
        ("unit_price_raw", INVALID_UNIT_PRICE),
        ("subtotal_raw", INVALID_SUBTOTAL),
    ],
)
@pytest.mark.parametrize("value", [True, 1 + 2j, "10", None, object()])
def test_invalid_numeric_values_are_rejected(field, code, value):
    result = ValidationEngine().validate(make_record(**{field: value}))

    assert codes(result) == [code]


@pytest.mark.parametrize("value", [1, 1.5, Decimal("1.5")])
@pytest.mark.parametrize(
    "field",
    ["quantity_raw", "unit_price_raw", "subtotal_raw"],
)
def test_int_float_and_decimal_values_are_accepted(field, value):
    result = ValidationEngine().validate(make_record(**{field: value}))

    assert result.valid is True


def test_multiple_errors_are_collected_without_short_circuiting():
    result = ValidationEngine().validate(
        make_record(
            transaction_date=None,
            reference="\t",
            product_raw=None,
            quantity_raw=False,
            unit_price_raw="10",
            subtotal_raw=None,
        )
    )

    assert codes(result) == [
        INVALID_TRANSACTION_DATE,
        MISSING_REFERENCE,
        MISSING_PRODUCT,
        INVALID_QUANTITY,
        INVALID_UNIT_PRICE,
        INVALID_SUBTOTAL,
    ]


def test_raw_values_and_source_traceability_are_preserved():
    record = make_record(
        supplier_raw=" Unmapped Supplier ",
        product_raw=" Raw Product ",
        destination_raw="Unmapped Destination",
    )

    result = ValidationEngine().validate(record)

    assert result.raw_record is record
    assert result.raw_record.supplier_raw == " Unmapped Supplier "
    assert result.raw_record.product_raw == " Raw Product "
    assert result.raw_record.destination_raw == "Unmapped Destination"
    assert result.source_file == "purchases.xlsx"
    assert result.source_sheet == "Report"
    assert result.source_row == 7


def test_supplier_and_destination_do_not_require_mapping():
    result = ValidationEngine().validate(
        make_record(supplier_raw="unknown", destination_raw="unknown")
    )

    assert result.valid is True


def test_input_is_not_mutated_and_repeated_validation_is_deterministic():
    record = make_record()
    before = record

    first = ValidationEngine().validate(record)
    second = ValidationEngine().validate(record)

    assert record is before
    assert record == before
    assert first == second