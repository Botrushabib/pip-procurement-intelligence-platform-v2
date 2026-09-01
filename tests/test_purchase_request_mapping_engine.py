import inspect
from decimal import Decimal

from app.services.purchase_request_reader import QuantityClassification
from app.services.purchase_request_mapping_engine import (
    MappingMethod,
    MappingStatus,
    ProductCandidate,
    PurchaseRequestMappingEngine,
    UnitCandidate,
)
from app.services.purchase_request_validation_engine import (
    PurchaseRequestValidationResult,
    ValidationStatus,
)


def make_validation_result(
    *,
    raw_internal_reference="161021",
    raw_product="Beef Tenderloin",
    raw_item_description="Fresh cut",
    raw_unit="kg",
    quantity_classification=QuantityClassification.PURE_NUMERIC,
    quantity_value=Decimal("500"),
    quantity_token=None,
    packaging_token=None,
    source_row=4,
) -> PurchaseRequestValidationResult:
    return PurchaseRequestValidationResult(
        source_file="PR 22.8.2026 freezer (5)(2).xlsx",
        source_sheet="Sheet1",
        source_row=source_row,
        status=ValidationStatus.VALID,
        eligible_for_next_stage=True,
        findings=(),
        quantity_classification=quantity_classification,
        raw_internal_reference=raw_internal_reference,
        raw_product=raw_product,
        raw_item_description=raw_item_description,
        raw_unit=raw_unit,
        raw_quantity="500",
        quantity_value=quantity_value,
        quantity_token=quantity_token,
        packaging_token=packaging_token,
    )


# ---------------------------------------------------------------- PRODUCT ---


def test_exact_internal_reference_match():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference="161021",
        raw_product="Beef Tenderloin",
        raw_item_description=None,
        products=[ProductCandidate(1, code="161021", name="Beef Tenderloin")],
    )

    assert result.status is MappingStatus.MAPPED
    assert result.normalized_product_id == 1
    assert result.mapping_method is MappingMethod.INTERNAL_REFERENCE_EXACT
    assert result.mapping_source_field == "raw_internal_reference"


def test_internal_reference_not_found_falls_back_to_unmapped_without_name():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference="999999",
        raw_product=None,
        raw_item_description=None,
        products=[ProductCandidate(1, code="161021", name="Beef Tenderloin")],
    )

    assert result.status is MappingStatus.UNMAPPED
    assert result.normalized_product_id is None


def test_duplicate_product_code_is_ambiguous():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference="161021",
        raw_product=None,
        raw_item_description=None,
        products=[
            ProductCandidate(2, code="161021", name="Beef A"),
            ProductCandidate(1, code="161021", name="Beef B"),
        ],
    )

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.normalized_product_id is None
    assert result.candidate_ids == (1, 2)


def test_exact_name_fallback_when_internal_reference_absent():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference=None,
        raw_product="Beef Tenderloin",
        raw_item_description=None,
        products=[ProductCandidate(5, code="200001", name="Beef Tenderloin")],
    )

    assert result.status is MappingStatus.MAPPED
    assert result.normalized_product_id == 5
    assert result.mapping_method is MappingMethod.NAME_EXACT
    assert result.mapping_source_field == "raw_product"


def test_name_not_found_is_unmapped():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference=None,
        raw_product="Nonexistent Product",
        raw_item_description=None,
        products=[ProductCandidate(5, code="200001", name="Beef Tenderloin")],
    )

    assert result.status is MappingStatus.UNMAPPED


def test_duplicate_product_name_is_ambiguous():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference=None,
        raw_product="Beef Tenderloin",
        raw_item_description=None,
        products=[
            ProductCandidate(2, code="A", name="Beef Tenderloin"),
            ProductCandidate(1, code="B", name="beef tenderloin"),
        ],
    )

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.candidate_ids == (1, 2)


def test_internal_reference_takes_priority_over_name():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference="161021",
        raw_product="Butter Block",
        raw_item_description=None,
        products=[
            ProductCandidate(1, code="161021", name="Beef Tenderloin"),
            ProductCandidate(2, code="999999", name="Butter Block"),
        ],
    )

    assert result.status is MappingStatus.MAPPED
    assert result.normalized_product_id == 1
    assert result.mapping_method is MappingMethod.INTERNAL_REFERENCE_EXACT


def test_no_product_identity_is_unmapped():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference=None,
        raw_product=None,
        raw_item_description="Fresh cut",
        products=[ProductCandidate(1, code="161021", name="Beef Tenderloin")],
    )

    assert result.status is MappingStatus.UNMAPPED
    assert "Neither Internal Reference nor Name" in result.reason


def test_item_description_never_maps_product():
    engine = PurchaseRequestMappingEngine()
    products = [ProductCandidate(1, code="161021", name="Beef Tenderloin")]

    result_a = engine.map_product(
        raw_internal_reference="161021",
        raw_product="Beef Tenderloin",
        raw_item_description="Fresh cut, grade A",
        products=products,
    )
    result_b = engine.map_product(
        raw_internal_reference="161021",
        raw_product="Beef Tenderloin",
        raw_item_description="Completely different description",
        products=products,
    )

    assert result_a.status == result_b.status == MappingStatus.MAPPED
    assert result_a.normalized_product_id == result_b.normalized_product_id == 1


def test_numeric_internal_reference_matches_string_product_code():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference=161021,
        raw_product=None,
        raw_item_description=None,
        products=[ProductCandidate(1, code="161021", name="Beef Tenderloin")],
    )

    assert result.status is MappingStatus.MAPPED
    assert result.normalized_product_id == 1


def test_leading_zeros_are_preserved_in_comparison():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference="00161021",
        raw_product=None,
        raw_item_description=None,
        products=[ProductCandidate(1, code="00161021", name="Beef Tenderloin")],
    )

    assert result.status is MappingStatus.MAPPED

    unmatched = engine.map_product(
        raw_internal_reference="00161021",
        raw_product=None,
        raw_item_description=None,
        products=[ProductCandidate(1, code="161021", name="Beef Tenderloin")],
    )
    assert unmatched.status is MappingStatus.UNMAPPED


def test_raw_internal_reference_remains_unchanged_in_output():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_product(
        raw_internal_reference="00161021",
        raw_product="Beef Tenderloin",
        raw_item_description=None,
        products=[ProductCandidate(1, code="00161021", name="Beef Tenderloin")],
    )

    assert result.raw_internal_reference == "00161021"


# ------------------------------------------------------------------- UNIT ---


def test_exact_unit_match():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_unit(raw_unit="kg", units=[UnitCandidate(1, name="kg")])

    assert result.status is MappingStatus.MAPPED
    assert result.normalized_unit_id == 1
    assert result.mapping_method is MappingMethod.UNIT_NAME_EXACT


def test_unit_not_found_is_unmapped():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_unit(raw_unit="kg", units=[UnitCandidate(1, name="L")])

    assert result.status is MappingStatus.UNMAPPED
    assert result.normalized_unit_id is None


def test_duplicate_unit_name_is_ambiguous():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_unit(
        raw_unit="kg", units=[UnitCandidate(2, name="kg"), UnitCandidate(1, name="KG")]
    )

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.candidate_ids == (1, 2)


def test_no_unit_is_unmapped():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_unit(raw_unit=None, units=[UnitCandidate(1, name="kg")])

    assert result.status is MappingStatus.UNMAPPED
    assert "not present" in result.reason


def test_unit_does_not_map_to_each():
    engine = PurchaseRequestMappingEngine()

    result = engine.map_unit(raw_unit="UNIT", units=[UnitCandidate(1, name="Each")])

    assert result.status is MappingStatus.UNMAPPED


def test_no_unit_conversion_is_ever_performed():
    engine = PurchaseRequestMappingEngine()

    box_result = engine.map_unit(raw_unit="box", units=[UnitCandidate(1, name="Piece")])
    kg_result = engine.map_unit(raw_unit="kg", units=[UnitCandidate(2, name="g")])

    assert box_result.status is MappingStatus.UNMAPPED
    assert kg_result.status is MappingStatus.UNMAPPED


# --------------------------------------------------------------- QUANTITY ---


def test_five_box_remains_unresolved_through_mapping():
    engine = PurchaseRequestMappingEngine()
    validation_result = make_validation_result(
        quantity_classification=QuantityClassification.QUANTITY_WITH_PACKAGING,
        quantity_value=None,
        quantity_token="5",
        packaging_token="box",
    )

    result = engine.map(
        validation_result,
        products=[ProductCandidate(1, code="161021", name="Beef Tenderloin")],
        units=[UnitCandidate(1, name="kg")],
    )

    assert result.quantity_classification is QuantityClassification.QUANTITY_WITH_PACKAGING
    assert result.quantity_value is None
    assert result.quantity_token == "5"
    assert result.packaging_token == "box"


def test_eight_gol_remains_unresolved_through_mapping():
    engine = PurchaseRequestMappingEngine()
    validation_result = make_validation_result(
        quantity_classification=QuantityClassification.UNKNOWN_QUANTITY_TOKEN,
        quantity_value=None,
        quantity_token="8",
        packaging_token="gol",
    )

    result = engine.map(validation_result)

    assert result.quantity_classification is QuantityClassification.UNKNOWN_QUANTITY_TOKEN
    assert result.quantity_value is None
    assert result.quantity_token == "8"
    assert result.packaging_token == "gol"


def test_textual_quantity_remains_unresolved_through_mapping():
    engine = PurchaseRequestMappingEngine()
    validation_result = make_validation_result(
        quantity_classification=QuantityClassification.TEXTUAL_QUANTITY,
        quantity_value=None,
    )

    result = engine.map(validation_result)

    assert result.quantity_classification is QuantityClassification.TEXTUAL_QUANTITY
    assert result.quantity_value is None


def test_explicit_zero_remains_zero_through_mapping():
    engine = PurchaseRequestMappingEngine()
    validation_result = make_validation_result(
        quantity_classification=QuantityClassification.EXPLICIT_ZERO,
        quantity_value=Decimal("0"),
    )

    result = engine.map(validation_result)

    assert result.quantity_classification is QuantityClassification.EXPLICIT_ZERO
    assert result.quantity_value == Decimal("0")


def test_blank_quantity_remains_blank_through_mapping():
    engine = PurchaseRequestMappingEngine()
    validation_result = make_validation_result(
        quantity_classification=QuantityClassification.BLANK_QUANTITY,
        quantity_value=None,
    )

    result = engine.map(validation_result)

    assert result.quantity_classification is QuantityClassification.BLANK_QUANTITY
    assert result.quantity_value is None


# ------------------------------------------------------------- LOCATION ---


def test_mapper_has_no_location_mapping_method():
    engine = PurchaseRequestMappingEngine()

    assert not hasattr(engine, "map_location")


def test_filename_cannot_affect_mapping_result():
    engine = PurchaseRequestMappingEngine()
    validation_result = make_validation_result()

    result_a = PurchaseRequestValidationResult(
        **{**validation_result.__dict__, "source_file": "PR 22.8.2026 freezer (5)(2).xlsx"}
    )
    result_b = PurchaseRequestValidationResult(
        **{**validation_result.__dict__, "source_file": "completely_unrelated_name.xlsx"}
    )

    products = [ProductCandidate(1, code="161021", name="Beef Tenderloin")]
    units = [UnitCandidate(1, name="kg")]

    mapped_a = engine.map(result_a, products=products, units=units)
    mapped_b = engine.map(result_b, products=products, units=units)

    assert mapped_a.product == mapped_b.product
    assert mapped_a.unit == mapped_b.unit


# --------------------------------------------------------------- QUALITY ---


def test_repeated_mapping_is_deterministic():
    engine = PurchaseRequestMappingEngine()
    validation_result = make_validation_result()
    products = [ProductCandidate(1, code="161021", name="Beef Tenderloin")]
    units = [UnitCandidate(1, name="kg")]

    first = engine.map(validation_result, products=products, units=units)
    second = engine.map(validation_result, products=products, units=units)

    assert first == second


def test_candidate_order_does_not_change_result():
    engine = PurchaseRequestMappingEngine()

    products_forward = [
        ProductCandidate(1, code="A", name="Beef"),
        ProductCandidate(2, code="A", name="Beef Other"),
    ]
    products_reversed = list(reversed(products_forward))

    result_forward = engine.map_product(
        raw_internal_reference="A",
        raw_product=None,
        raw_item_description=None,
        products=products_forward,
    )
    result_reversed = engine.map_product(
        raw_internal_reference="A",
        raw_product=None,
        raw_item_description=None,
        products=products_reversed,
    )

    assert result_forward == result_reversed
    assert result_forward.candidate_ids == (1, 2)


def test_raw_values_preserved_across_product_and_unit_mapping():
    engine = PurchaseRequestMappingEngine()
    validation_result = make_validation_result(
        raw_internal_reference="161021",
        raw_product="Beef Tenderloin",
        raw_item_description="Fresh cut",
        raw_unit="kg",
    )

    result = engine.map(validation_result)

    assert result.product.raw_internal_reference == "161021"
    assert result.product.raw_product == "Beef Tenderloin"
    assert result.product.raw_item_description == "Fresh cut"
    assert result.unit.raw_unit == "kg"


def test_no_database_imports():
    import app.services.purchase_request_mapping_engine as mapping_module

    source = inspect.getsource(mapping_module)
    assert "sqlalchemy" not in source.lower()
    assert "SessionLocal" not in source
    assert "app.core.database" not in source


def test_no_write_operations_in_source():
    import app.services.purchase_request_mapping_engine as mapping_module

    source = inspect.getsource(mapping_module)
    for forbidden in ("session.add", "session.commit", "session.flush", "INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert forbidden not in source
