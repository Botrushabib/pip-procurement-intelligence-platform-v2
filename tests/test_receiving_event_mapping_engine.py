from datetime import date, datetime
from decimal import Decimal

from app.services.receiving_event_mapping_engine import ReceivingEventMappingEngine
from app.services.receiving_event_mapping_decision import (
    ReceivingDecisionStatus,
    ReceivingReasonCode,
)
from app.services.receiving_event_mapping_result import (
    CompanyCandidate,
    CompanyMetadata,
    ProductCandidate,
    ReceivingMappingMethod,
    ReceivingMappingStatus,
    SupplierCandidate,
    UnitCandidate,
    WarehouseCandidate,
)
from app.services.receiving_event_reader import (
    ReceivingRowClassification,
    ReceivingSheetResult,
    ReceivingSourceRow,
)
from app.services.receiving_event_validation_engine import ReceivingValidationEngine
from app.services.receiving_event_validation_result import (
    ReceivingValidationResult,
    ReceivingValidationSummary,
)


def make_row(**overrides):
    values = dict(
        source_file="receiving.xlsx", source_sheet="Report", source_row=2,
        row_classification=ReceivingRowClassification.DETAIL, raw_supplier="Biotech",
        raw_date_1=datetime(2026, 8, 15), raw_date_2=datetime(2026, 9, 3),
        event_date_candidate=datetime(2026, 8, 15), raw_reference="WH/IN/00001",
        raw_product="[162017] Sugar Brown Portion TLT", product_code="162017",
        raw_item_description="Brown sugar", raw_destination="Main Stores/Stock",
        raw_quantity=Decimal("2"), raw_unit="kg", raw_unit_price=Decimal("10"),
        raw_subtotal=Decimal("20"),
    )
    values.update(overrides)
    return ReceivingSourceRow(**values)


def validated(*rows):
    sheet = ReceivingSheetResult(
        source_file="receiving.xlsx", source_sheet="Report", header_row=1,
        total_rows=len(rows),
        detail_row_count=sum(row.row_classification is ReceivingRowClassification.DETAIL for row in rows),
        non_detail_row_count=sum(row.row_classification is not ReceivingRowClassification.DETAIL for row in rows),
        date_headers=("date", "receipt date"), rows=tuple(rows),
    )
    return ReceivingValidationEngine().validate(sheet)


def candidates():
    return dict(
        company_metadata=CompanyMetadata("PIP"),
        companies=[CompanyCandidate(1, code="PIP", name="PIP Company")],
        suppliers=[SupplierCandidate(2, name="Biotech")],
        products=[ProductCandidate(3, code="162017", name="Different product name")],
        units=[UnitCandidate(4, name="kg")],
        warehouses=[WarehouseCandidate(5, name="Main Stores/Stock", code="MS")],
    )


def mapped(*rows, **overrides):
    values = candidates()
    values.update(overrides)
    return ReceivingEventMappingEngine().map(validated(*rows), **values)


def defensively_eligible(row):
    return ReceivingValidationResult(
        rows=(row,),
        issues=(),
        detail_rows=(row,),
        eligible_detail_rows=(row,),
        preserved_other_rows=(),
        summary=ReceivingValidationSummary(1, 1, 0, 1, 0, 0, 0, 0),
    )


def test_unique_master_data_and_approved_date_map_ready():
    result = mapped(make_row())
    line = result.line_results[0]
    decision = result.decisions[0]

    assert [line.company.normalized_id, line.supplier.normalized_id, line.product.normalized_id, line.unit.normalized_id, line.warehouse.normalized_id] == [1, 2, 3, 4, 5]
    assert line.product.mapping_method is ReceivingMappingMethod.PRODUCT_CODE_EXACT
    assert line.event_date == date(2026, 8, 15)
    assert line.event_date_method is ReceivingMappingMethod.EVENT_DATE_APPROVED_DATE_COLUMN
    assert decision.eligible_for_persistence is True


def test_unmapped_and_ambiguous_candidates_are_deterministic():
    unmapped = mapped(make_row(), suppliers=[])
    assert unmapped.line_results[0].supplier.status is ReceivingMappingStatus.UNMAPPED
    assert unmapped.decisions[0].eligible_for_persistence is False

    first = mapped(make_row(), units=[UnitCandidate(9, "KG"), UnitCandidate(4, "kg")])
    second = mapped(make_row(), units=[UnitCandidate(4, "kg"), UnitCandidate(9, "KG")])
    assert first.line_results[0].unit.status is ReceivingMappingStatus.AMBIGUOUS
    assert first.line_results[0].unit.candidate_ids == (4, 9)
    assert first.decisions[0] == second.decisions[0]


def test_product_uses_only_bracket_code_and_preserves_leading_zeros():
    row = make_row(raw_product="[00162017] Sugar", product_code="00162017")
    result = mapped(row, products=[ProductCandidate(3, code="00162017", name="Other")])
    assert result.line_results[0].product.normalized_id == 3
    assert result.line_results[0].row.raw_product == "[00162017] Sugar"

    malformed_row = make_row(product_code=None)
    defensive_validation_result = defensively_eligible(malformed_row)
    missing_code = ReceivingEventMappingEngine().map(
        defensive_validation_result,
        **{
            **candidates(),
            "products": [
                ProductCandidate(3, code="162017", name="Sugar Brown Portion TLT")
            ],
        },
    )
    assert missing_code.line_results[0].product.status is ReceivingMappingStatus.UNMAPPED
    assert missing_code.decisions[0].eligible_for_persistence is False


def test_product_name_and_description_are_never_fallbacks():
    result = mapped(
        make_row(product_code="999999", raw_item_description="Exact product name"),
        products=[ProductCandidate(3, code="162017", name="[162017] Sugar Brown Portion TLT")],
    )
    assert result.line_results[0].product.status is ReceivingMappingStatus.UNMAPPED


def test_unit_conversion_and_warehouse_code_or_context_are_not_used():
    unit_result = mapped(make_row(raw_unit="kg"), units=[UnitCandidate(4, "g")])
    assert unit_result.line_results[0].unit.status is ReceivingMappingStatus.UNMAPPED

    warehouse_result = mapped(
        make_row(raw_destination="Main Store Sahel"),
        warehouses=[WarehouseCandidate(5, name="Other", code="Main Store Sahel")],
    )
    assert warehouse_result.line_results[0].warehouse.status is ReceivingMappingStatus.UNMAPPED


def test_company_is_explicit_and_never_inferred():
    missing = mapped(make_row(), company_metadata=CompanyMetadata())
    assert missing.decisions[0].decision_status.value == "REJECTED"

    unmapped = mapped(make_row(), company_metadata=CompanyMetadata("OTHER"))
    assert unmapped.line_results[0].company.status is ReceivingMappingStatus.UNMAPPED
    assert unmapped.decisions[0].decision_status.value == "REVIEW"

    ambiguous = mapped(make_row(), companies=[CompanyCandidate(2, "PIP"), CompanyCandidate(1, "PIP")])
    assert ambiguous.line_results[0].company.status is ReceivingMappingStatus.AMBIGUOUS
    assert ambiguous.line_results[0].company.candidate_ids == (1, 2)


def test_date_comes_only_from_event_date_candidate_not_file_sheet_or_second_date():
    first = mapped(make_row(source_file="August.xlsx", source_sheet="August", raw_date_2=datetime(2030, 1, 1)))
    second = mapped(make_row(source_file="unrelated.xlsx", source_sheet="Other", raw_date_2=datetime(1990, 1, 1)))
    assert first.line_results[0].event_date == second.line_results[0].event_date == date(2026, 8, 15)


def test_blocked_and_non_detail_rows_are_preserved_not_remapped():
    blocked = make_row(raw_product="invalid", product_code=None)
    other = make_row(source_row=3, row_classification=ReceivingRowClassification.OTHER, raw_reference=None, raw_product=None)
    result = mapped(blocked, other)
    assert len(result.preserved_rows) == 2
    assert all(line.product.status is ReceivingMappingStatus.NOT_ATTEMPTED for line in result.line_results)
    assert all(decision.eligible_for_persistence is False for decision in result.decisions)


def test_reference_repeats_without_collapsing_lines_and_grouping_key_is_created():
    result = mapped(make_row(source_row=2), make_row(source_row=3))
    assert len(result.line_results) == 2
    assert result.line_results[0].event_grouping_key == result.line_results[1].event_grouping_key
    assert [decision.source_row for decision in result.decisions] == [2, 3]


def test_mapping_is_side_effect_free_and_preserves_provenance():
    row = make_row()
    supplied = candidates()
    before = tuple(supplied["products"])
    result = ReceivingEventMappingEngine().map(validated(row), **supplied)
    line = result.line_results[0]
    assert supplied["products"] == list(before)
    assert (line.source_file, line.source_sheet, line.source_row) == ("receiving.xlsx", "Report", 2)
    assert line.row.raw_supplier == "Biotech"
    assert line.row.raw_destination == "Main Stores/Stock"
    assert line.row.raw_date_1 == datetime(2026, 8, 15)
    assert line.row.raw_date_2 == datetime(2026, 9, 3)
    assert line.company_metadata.company_code == "PIP"


def test_invalid_or_missing_event_date_candidate_is_rejected():
    for value in ("not-a-date", None):
        result = ReceivingEventMappingEngine().map(
            defensively_eligible(make_row(event_date_candidate=value)), **candidates()
        )
        assert result.decisions[0].decision_status is ReceivingDecisionStatus.REJECTED
        assert result.decisions[0].reason_codes == (
            ReceivingReasonCode.INVALID_EVENT_DATE.value,
        )


def test_ambiguous_supplier_product_and_warehouse_become_review_deterministically():
    supplier_first = mapped(
        make_row(), suppliers=[SupplierCandidate(9, "BIOTECH"), SupplierCandidate(2, "Biotech")]
    )
    supplier_second = mapped(
        make_row(), suppliers=[SupplierCandidate(2, "Biotech"), SupplierCandidate(9, "BIOTECH")]
    )
    assert supplier_first.line_results[0].supplier.status is ReceivingMappingStatus.AMBIGUOUS
    assert supplier_first.line_results[0].supplier.candidate_ids == (2, 9)
    assert supplier_first.decisions[0].reason_codes == supplier_second.decisions[0].reason_codes == (
        ReceivingReasonCode.SUPPLIER_AMBIGUOUS.value,
    )

    product = mapped(
        make_row(),
        products=[
            ProductCandidate(9, code="162017", name="A different name"),
            ProductCandidate(3, code="162017", name="Brown sugar"),
        ],
    )
    assert product.line_results[0].product.status is ReceivingMappingStatus.AMBIGUOUS
    assert product.line_results[0].product.candidate_ids == (3, 9)
    assert product.decisions[0].reason_codes == (ReceivingReasonCode.PRODUCT_AMBIGUOUS.value,)

    warehouse_first = mapped(
        make_row(),
        warehouses=[WarehouseCandidate(9, "MAIN STORES/STOCK"), WarehouseCandidate(5, "Main Stores/Stock")],
    )
    warehouse_second = mapped(
        make_row(),
        warehouses=[WarehouseCandidate(5, "Main Stores/Stock"), WarehouseCandidate(9, "MAIN STORES/STOCK")],
    )
    assert warehouse_first.line_results[0].warehouse.status is ReceivingMappingStatus.AMBIGUOUS
    assert warehouse_first.line_results[0].warehouse.candidate_ids == (5, 9)
    assert warehouse_first.decisions[0].reason_codes == warehouse_second.decisions[0].reason_codes == (
        ReceivingReasonCode.WAREHOUSE_AMBIGUOUS.value,
    )


def test_missing_supplier_unit_or_warehouse_is_review_when_defensively_eligible():
    expected = (
        ("raw_supplier", ReceivingReasonCode.SUPPLIER_UNMAPPED),
        ("raw_unit", ReceivingReasonCode.UNIT_UNMAPPED),
        ("raw_destination", ReceivingReasonCode.WAREHOUSE_UNMAPPED),
    )
    for field, reason in expected:
        result = ReceivingEventMappingEngine().map(
            defensively_eligible(make_row(**{field: None})), **candidates()
        )
        assert result.decisions[0].decision_status is ReceivingDecisionStatus.REVIEW
        assert result.decisions[0].eligible_for_persistence is False
        assert result.decisions[0].reason_codes == (reason.value,)


def test_raw_source_values_are_preserved_without_normalization():
    row = make_row(
        raw_product="[162017] Sugar Brown Portion TLT ", raw_unit=" kg ",
        raw_destination=" Main Stores/Stock ", raw_reference=" WH/IN/00001 ",
        raw_quantity="2.00", raw_unit_price="10.00", raw_subtotal="20.00",
        raw_date_1="2026-08-15", raw_date_2="2026-09-03",
    )
    result = mapped(row)
    mapped_row = result.line_results[0].row
    assert (
        mapped_row.raw_product, mapped_row.raw_unit, mapped_row.raw_destination,
        mapped_row.raw_reference, mapped_row.raw_quantity, mapped_row.raw_unit_price,
        mapped_row.raw_subtotal, mapped_row.raw_date_1, mapped_row.raw_date_2,
    ) == (
        "[162017] Sugar Brown Portion TLT ", " kg ", " Main Stores/Stock ",
        " WH/IN/00001 ", "2.00", "10.00", "20.00", "2026-08-15", "2026-09-03",
    )