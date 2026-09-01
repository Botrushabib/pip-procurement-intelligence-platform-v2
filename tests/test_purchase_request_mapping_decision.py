import inspect
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.services.purchase_request_mapping_decision import (
    DecisionStatus,
    LocationStatus,
    PurchaseRequestMappingDecisionEngine,
    ReasonCode,
)
from app.services.purchase_request_mapping_engine import (
    MappingMethod,
    MappingStatus,
    ProductMappingResult,
    PurchaseRequestMappingResult,
    UnitMappingResult,
)
from app.services.purchase_request_reader import QuantityClassification
from app.services.purchase_request_validation_engine import (
    MISSING_ITEM_DESCRIPTION,
    MISSING_PRODUCT_IDENTITY,
    MISSING_QUANTITY,
    MISSING_UNIT,
    PurchaseRequestValidationResult,
    ValidationFinding,
    ValidationSeverity,
    ValidationStatus,
)


def make_validation_result(
    *,
    status=ValidationStatus.VALID,
    findings=(),
    quantity_classification=QuantityClassification.PURE_NUMERIC,
    raw_internal_reference="161021",
    raw_product="Beef Tenderloin",
    raw_item_description="Fresh cut",
    raw_unit="kg",
    raw_quantity="500",
    quantity_value=Decimal("500"),
    quantity_token=None,
    packaging_token=None,
    source_row=4,
) -> PurchaseRequestValidationResult:
    return PurchaseRequestValidationResult(
        source_file="PR 22.8.2026 freezer (5)(2).xlsx",
        source_sheet="Sheet1",
        source_row=source_row,
        status=status,
        eligible_for_next_stage=status is not ValidationStatus.ERROR,
        findings=findings,
        quantity_classification=quantity_classification,
        raw_internal_reference=raw_internal_reference,
        raw_product=raw_product,
        raw_item_description=raw_item_description,
        raw_unit=raw_unit,
        raw_quantity=raw_quantity,
        quantity_value=quantity_value,
        quantity_token=quantity_token,
        packaging_token=packaging_token,
    )


def make_product_result(
    *,
    status=MappingStatus.MAPPED,
    normalized_product_id=1,
    raw_internal_reference="161021",
    raw_product="Beef Tenderloin",
    raw_item_description="Fresh cut",
    candidate_ids=(1,),
    candidate_names=("161021",),
) -> ProductMappingResult:
    return ProductMappingResult(
        status=status,
        normalized_product_id=normalized_product_id,
        mapping_method=MappingMethod.INTERNAL_REFERENCE_EXACT if status is MappingStatus.MAPPED else None,
        mapping_source_field="raw_internal_reference" if status is MappingStatus.MAPPED else None,
        raw_internal_reference=raw_internal_reference,
        raw_product=raw_product,
        raw_item_description=raw_item_description,
        candidate_ids=candidate_ids,
        candidate_names=candidate_names,
        reason="test",
    )


def make_unit_result(
    *,
    status=MappingStatus.MAPPED,
    normalized_unit_id=1,
    raw_unit="kg",
    candidate_ids=(1,),
    candidate_names=("kg",),
) -> UnitMappingResult:
    return UnitMappingResult(
        status=status,
        normalized_unit_id=normalized_unit_id,
        mapping_method=MappingMethod.UNIT_NAME_EXACT if status is MappingStatus.MAPPED else None,
        mapping_source_field="raw_unit" if status is MappingStatus.MAPPED else None,
        raw_unit=raw_unit,
        candidate_ids=candidate_ids,
        candidate_names=candidate_names,
        reason="test",
    )


def make_mapping_result(
    *,
    product=None,
    unit=None,
    quantity_classification=QuantityClassification.PURE_NUMERIC,
    quantity_value=Decimal("500"),
    quantity_token=None,
    packaging_token=None,
    source_row=4,
) -> PurchaseRequestMappingResult:
    return PurchaseRequestMappingResult(
        source_file="PR 22.8.2026 freezer (5)(2).xlsx",
        source_sheet="Sheet1",
        source_row=source_row,
        product=product or make_product_result(),
        unit=unit or make_unit_result(),
        quantity_classification=quantity_classification,
        quantity_value=quantity_value,
        quantity_token=quantity_token,
        packaging_token=packaging_token,
    )


def decide(validation_result=None, mapping_result=None):
    return PurchaseRequestMappingDecisionEngine().decide(
        validation_result or make_validation_result(),
        mapping_result or make_mapping_result(),
    )


def test_fully_mapped_numeric_row_is_ready():
    decision = decide()

    assert decision.decision_status is DecisionStatus.READY
    assert decision.eligible_for_persistence is True
    assert decision.reason_codes == ()


def test_fully_mapped_explicit_zero_is_ready():
    validation_result = make_validation_result(
        quantity_classification=QuantityClassification.EXPLICIT_ZERO,
        raw_quantity="0",
        quantity_value=Decimal("0"),
    )
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.EXPLICIT_ZERO,
        quantity_value=Decimal("0"),
    )

    decision = decide(validation_result, mapping_result)

    assert decision.decision_status is DecisionStatus.READY
    assert decision.eligible_for_persistence is True
    assert decision.quantity_value == Decimal("0")


def test_product_unmapped_is_review():
    mapping_result = make_mapping_result(product=make_product_result(status=MappingStatus.UNMAPPED, normalized_product_id=None))

    decision = decide(mapping_result=mapping_result)

    assert decision.decision_status is DecisionStatus.REVIEW
    assert decision.eligible_for_persistence is False
    assert ReasonCode.PRODUCT_UNMAPPED in decision.reason_codes


def test_product_ambiguous_is_review():
    mapping_result = make_mapping_result(
        product=make_product_result(status=MappingStatus.AMBIGUOUS, normalized_product_id=None, candidate_ids=(1, 2))
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.decision_status is DecisionStatus.REVIEW
    assert ReasonCode.PRODUCT_AMBIGUOUS in decision.reason_codes


def test_unit_unmapped_is_review():
    mapping_result = make_mapping_result(unit=make_unit_result(status=MappingStatus.UNMAPPED, normalized_unit_id=None))

    decision = decide(mapping_result=mapping_result)

    assert decision.decision_status is DecisionStatus.REVIEW
    assert ReasonCode.UNIT_UNMAPPED in decision.reason_codes


def test_unit_ambiguous_is_review():
    mapping_result = make_mapping_result(
        unit=make_unit_result(status=MappingStatus.AMBIGUOUS, normalized_unit_id=None, candidate_ids=(1, 2))
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.decision_status is DecisionStatus.REVIEW
    assert ReasonCode.UNIT_AMBIGUOUS in decision.reason_codes


def test_packaging_quantity_is_review():
    validation_result = make_validation_result(
        status=ValidationStatus.WARNING,
        quantity_classification=QuantityClassification.QUANTITY_WITH_PACKAGING,
        raw_quantity="5 box",
        quantity_value=None,
        quantity_token="5",
        packaging_token="box",
    )
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.QUANTITY_WITH_PACKAGING,
        quantity_value=None,
        quantity_token="5",
        packaging_token="box",
    )

    decision = decide(validation_result, mapping_result)

    assert decision.decision_status is DecisionStatus.REVIEW
    assert ReasonCode.QUANTITY_PACKAGING_REVIEW in decision.reason_codes
    assert decision.quantity_value is None


def test_unknown_quantity_token_is_review():
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.UNKNOWN_QUANTITY_TOKEN,
        quantity_value=None,
        quantity_token="8",
        packaging_token="gol",
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.decision_status is DecisionStatus.REVIEW
    assert ReasonCode.QUANTITY_UNKNOWN_TOKEN in decision.reason_codes


def test_textual_quantity_is_review():
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.TEXTUAL_QUANTITY, quantity_value=None
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.decision_status is DecisionStatus.REVIEW
    assert ReasonCode.QUANTITY_TEXTUAL_REVIEW in decision.reason_codes


def test_blank_quantity_is_rejected():
    validation_result = make_validation_result(
        status=ValidationStatus.ERROR,
        findings=(ValidationFinding(MISSING_QUANTITY, ValidationSeverity.ERROR, "msg", "quantity.raw_quantity"),),
        quantity_classification=QuantityClassification.BLANK_QUANTITY,
        raw_quantity=None,
        quantity_value=None,
    )
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.BLANK_QUANTITY, quantity_value=None
    )

    decision = decide(validation_result, mapping_result)

    assert decision.decision_status is DecisionStatus.REJECTED
    assert decision.eligible_for_persistence is False
    assert ReasonCode.MISSING_QUANTITY in decision.reason_codes


def test_validation_error_is_rejected():
    validation_result = make_validation_result(
        status=ValidationStatus.ERROR,
        findings=(ValidationFinding(MISSING_UNIT, ValidationSeverity.ERROR, "msg", "raw_unit"),),
    )

    decision = decide(validation_result)

    assert decision.decision_status is DecisionStatus.REJECTED
    assert decision.eligible_for_persistence is False


def test_missing_product_identity_is_rejected():
    validation_result = make_validation_result(
        status=ValidationStatus.ERROR,
        findings=(
            ValidationFinding(
                MISSING_PRODUCT_IDENTITY, ValidationSeverity.ERROR, "msg", "raw_internal_reference"
            ),
        ),
    )

    decision = decide(validation_result)

    assert decision.decision_status is DecisionStatus.REJECTED
    assert ReasonCode.MISSING_PRODUCT_IDENTITY in decision.reason_codes


def test_missing_unit_is_rejected():
    validation_result = make_validation_result(
        status=ValidationStatus.ERROR,
        findings=(ValidationFinding(MISSING_UNIT, ValidationSeverity.ERROR, "msg", "raw_unit"),),
    )

    decision = decide(validation_result)

    assert decision.decision_status is DecisionStatus.REJECTED
    assert ReasonCode.MISSING_UNIT in decision.reason_codes


def test_validation_warning_with_otherwise_safe_mapping_is_ready():
    validation_result = make_validation_result(
        status=ValidationStatus.WARNING,
        findings=(
            ValidationFinding(
                MISSING_ITEM_DESCRIPTION, ValidationSeverity.WARNING, "msg", "raw_item_description"
            ),
        ),
    )

    decision = decide(validation_result)

    assert decision.decision_status is DecisionStatus.READY
    assert decision.eligible_for_persistence is True
    assert decision.reason_codes == ()


def test_multiple_review_reasons_are_deterministic():
    mapping_result = make_mapping_result(
        product=make_product_result(status=MappingStatus.UNMAPPED, normalized_product_id=None),
        unit=make_unit_result(status=MappingStatus.UNMAPPED, normalized_unit_id=None),
        quantity_classification=QuantityClassification.QUANTITY_WITH_PACKAGING,
        quantity_value=None,
        quantity_token="5",
        packaging_token="box",
    )

    first = decide(mapping_result=mapping_result)
    second = decide(mapping_result=mapping_result)

    assert first.reason_codes == second.reason_codes
    assert first.reason_codes == (
        ReasonCode.PRODUCT_UNMAPPED,
        ReasonCode.UNIT_UNMAPPED,
        ReasonCode.QUANTITY_PACKAGING_REVIEW,
    )


def test_reason_ordering_includes_supplementary_codes_last():
    validation_result = make_validation_result(
        status=ValidationStatus.WARNING,
        findings=(
            ValidationFinding(
                MISSING_ITEM_DESCRIPTION, ValidationSeverity.WARNING, "msg", "raw_item_description"
            ),
        ),
    )
    mapping_result = make_mapping_result(
        product=make_product_result(status=MappingStatus.UNMAPPED, normalized_product_id=None)
    )

    decision = decide(validation_result, mapping_result)

    assert decision.reason_codes == (
        ReasonCode.PRODUCT_UNMAPPED,
        ReasonCode.VALIDATION_WARNING,
        ReasonCode.MISSING_ITEM_DESCRIPTION,
    )


def test_location_remains_deferred():
    decision = decide()

    assert decision.location_status is LocationStatus.DEFERRED


def test_filename_cannot_influence_decision():
    validation_a = make_validation_result()
    validation_b = PurchaseRequestValidationResult(
        **{**validation_a.__dict__, "source_file": "unrelated_name.xlsx"}
    )
    mapping_a = make_mapping_result()
    mapping_b = PurchaseRequestMappingResult(
        **{**mapping_a.__dict__, "source_file": "unrelated_name.xlsx"}
    )

    decision_a = decide(validation_a, mapping_a)
    decision_b = decide(validation_b, mapping_b)

    assert decision_a.decision_status == decision_b.decision_status
    assert decision_a.reason_codes == decision_b.reason_codes
    assert decision_a.location_status == decision_b.location_status is LocationStatus.DEFERRED


def test_raw_internal_reference_is_preserved():
    validation_result = make_validation_result(raw_internal_reference="00161021")
    mapping_result = make_mapping_result(
        product=make_product_result(raw_internal_reference="00161021")
    )

    decision = decide(validation_result, mapping_result)

    assert decision.raw_internal_reference == "00161021"


def test_raw_quantity_is_preserved():
    validation_result = make_validation_result(raw_quantity="5 box")

    decision = decide(validation_result)

    assert decision.raw_quantity == "5 box"


def test_item_description_preserved_but_does_not_affect_mapping():
    mapping_a = make_mapping_result(product=make_product_result(raw_item_description="Fresh cut"))
    mapping_b = make_mapping_result(product=make_product_result(raw_item_description="Totally different"))

    decision_a = decide(mapping_result=mapping_a)
    decision_b = decide(mapping_result=mapping_b)

    assert decision_a.raw_item_description == "Fresh cut"
    assert decision_b.raw_item_description == "Totally different"
    assert decision_a.decision_status == decision_b.decision_status
    assert decision_a.normalized_product_id == decision_b.normalized_product_id


def test_normalized_ids_exposed_correctly():
    mapping_result = make_mapping_result(
        product=make_product_result(normalized_product_id=42),
        unit=make_unit_result(normalized_unit_id=7),
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.normalized_product_id == 42
    assert decision.normalized_unit_id == 7


def test_quantity_value_is_not_invented_for_pure_numeric():
    decision = decide()

    assert decision.quantity_value == Decimal("500")


def test_five_box_quantity_value_remains_none():
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.QUANTITY_WITH_PACKAGING,
        quantity_value=None,
        quantity_token="5",
        packaging_token="box",
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.quantity_value is None
    assert decision.quantity_token == "5"
    assert decision.packaging_token == "box"


def test_eight_gol_quantity_value_remains_none():
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.UNKNOWN_QUANTITY_TOKEN,
        quantity_value=None,
        quantity_token="8",
        packaging_token="gol",
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.quantity_value is None


def test_textual_quantity_value_remains_none():
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.TEXTUAL_QUANTITY, quantity_value=None
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.quantity_value is None


def test_zero_remains_decimal_zero():
    mapping_result = make_mapping_result(
        quantity_classification=QuantityClassification.EXPLICIT_ZERO, quantity_value=Decimal("0")
    )

    decision = decide(mapping_result=mapping_result)

    assert decision.quantity_value == Decimal("0")


def test_decision_result_is_immutable():
    decision = decide()

    with pytest.raises(FrozenInstanceError):
        decision.decision_status = DecisionStatus.REVIEW


def test_repeated_decision_is_deterministic():
    validation_result = make_validation_result()
    mapping_result = make_mapping_result()

    first = decide(validation_result, mapping_result)
    second = decide(validation_result, mapping_result)

    assert first == second


def test_mapping_and_validation_results_are_not_mutated():
    validation_result = make_validation_result()
    mapping_result = make_mapping_result()

    validation_snapshot = validation_result
    mapping_snapshot = mapping_result

    decide(validation_result, mapping_result)

    assert validation_result == validation_snapshot
    assert mapping_result == mapping_snapshot


def test_no_database_imports():
    import app.services.purchase_request_mapping_decision as decision_module

    source = inspect.getsource(decision_module)
    assert "sqlalchemy" not in source.lower()
    assert "SessionLocal" not in source
    assert "app.core.database" not in source


def test_no_write_operations_in_source():
    import app.services.purchase_request_mapping_decision as decision_module

    source = inspect.getsource(decision_module)
    for forbidden in (
        "session.add",
        "session.commit",
        "session.flush",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
    ):
        assert forbidden not in source
