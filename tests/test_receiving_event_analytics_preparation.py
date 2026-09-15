from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ProductMasterData,
    ReceivingAnalyticsDataQualityReport,
    ReceivingAnalyticsEligibility,
    ReceivingAnalyticsPreparationResult,
    ReceivingEventAnalyticsPreparation,
    ReceivingMasterDataEnrichment,
    prepare_receiving_events,
)
from app.services.receiving_event_query_service import (
    ReceivingEventLineReadDTO,
    ReceivingEventReadDTO,
)


def make_sample_line(
    id: int = 101,
    receiving_event_id: int = 1,
    line_number: int = 1,
    product_id: int = 201,
    unit_id: int = 301,
    quantity: Decimal = Decimal("50.00"),
    unit_price: Decimal = Decimal("12.50"),
    subtotal: Decimal = Decimal("625.00"),
    raw_product: str | None = "Raw Prod",
    raw_item_description: str | None = "Item Desc",
    raw_reference: str | None = "RAW-REF",
    raw_quantity: str | None = "50.00",
    raw_unit: str | None = "kg",
    raw_unit_price: str | None = "12.50",
    raw_subtotal: str | None = "625.00",
    raw_destination: str | None = "Main WH",
    raw_supplier: str | None = "Supplier One",
    raw_date_1: str | None = "2026-03-15",
    raw_date_2: str | None = None,
    source_file: str = "receiving_test.xlsx",
    source_sheet: str = "Sheet1",
    source_row: int = 2,
) -> ReceivingEventLineReadDTO:
    return ReceivingEventLineReadDTO(
        id=id,
        receiving_event_id=receiving_event_id,
        line_number=line_number,
        product_id=product_id,
        unit_id=unit_id,
        quantity=quantity,
        unit_price=unit_price,
        subtotal=subtotal,
        raw_product=raw_product,
        raw_item_description=raw_item_description,
        raw_reference=raw_reference,
        raw_quantity=raw_quantity,
        raw_unit=raw_unit,
        raw_unit_price=raw_unit_price,
        raw_subtotal=raw_subtotal,
        raw_destination=raw_destination,
        raw_supplier=raw_supplier,
        raw_date_1=raw_date_1,
        raw_date_2=raw_date_2,
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
    )


def make_sample_event(
    id: int = 1,
    company_id: int = 11,
    supplier_id: int = 21,
    warehouse_id: int = 31,
    receiving_reference: str = "REC-REF-001",
    event_date: date | None = date(2026, 3, 15),
    raw_reference: str | None = "RAW-REF-001",
    raw_supplier: str | None = "Supplier One",
    raw_destination: str | None = "Main WH",
    raw_date_1: str | None = "2026-03-15",
    raw_date_2: str | None = None,
    source_file: str = "receiving_test.xlsx",
    source_sheet: str = "Sheet1",
    source_row: int | None = 2,
    lines: tuple[ReceivingEventLineReadDTO, ...] | None = None,
) -> ReceivingEventReadDTO:
    if lines is None:
        lines = (make_sample_line(receiving_event_id=id),)
    return ReceivingEventReadDTO(
        id=id,
        company_id=company_id,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        receiving_reference=receiving_reference,
        event_date=event_date,
        raw_reference=raw_reference,
        raw_supplier=raw_supplier,
        raw_destination=raw_destination,
        raw_date_1=raw_date_1,
        raw_date_2=raw_date_2,
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
        lines=lines,
    )


def test_empty_input():
    prep = ReceivingEventAnalyticsPreparation()
    result = prep.prepare([])

    assert isinstance(result, ReceivingAnalyticsPreparationResult)
    assert result.records == ()
    assert result.eligible_records == ()
    assert result.ineligible_records == ()
    assert result.data_quality == ReceivingAnalyticsDataQualityReport(
        total_lines=0,
        eligible_lines=0,
        ineligible_lines=0,
        missing_date_count=0,
        missing_product_count=0,
        missing_quantity_count=0,
        missing_price_count=0,
        missing_supplier_count=0,
        missing_warehouse_count=0,
    )


def test_fully_eligible_receiving_line():
    event = make_sample_event()
    result = prepare_receiving_events([event])

    assert len(result.records) == 1
    record = result.records[0]
    assert record.eligibility.has_event_date is True
    assert record.eligibility.has_product is True
    assert record.eligibility.has_quantity is True
    assert record.eligibility.has_unit_price is True
    assert record.eligibility.has_supplier is True
    assert record.eligibility.has_warehouse is True
    assert record.eligibility.eligible_for_analytics is True

    assert result.data_quality.total_lines == 1
    assert result.data_quality.eligible_lines == 1
    assert result.data_quality.ineligible_lines == 0
    assert result.data_quality.missing_date_count == 0
    assert result.data_quality.missing_product_count == 0
    assert result.data_quality.missing_quantity_count == 0
    assert result.data_quality.missing_price_count == 0
    assert result.data_quality.missing_supplier_count == 0
    assert result.data_quality.missing_warehouse_count == 0


def test_missing_event_date():
    event = make_sample_event(event_date=None)
    prep = ReceivingEventAnalyticsPreparation()
    result = prep.prepare([event])

    assert len(result.records) == 1
    record = result.records[0]
    assert record.event_date is None
    assert record.year is None
    assert record.month is None
    assert record.eligibility.has_event_date is False
    assert record.eligibility.eligible_for_analytics is False

    assert result.data_quality.total_lines == 1
    assert result.data_quality.eligible_lines == 0
    assert result.data_quality.ineligible_lines == 1
    assert result.data_quality.missing_date_count == 1
    assert result.data_quality.missing_product_count == 0


def test_missing_product():
    line = make_sample_line(product_id=None)  # type: ignore[arg-type]
    event = make_sample_event(lines=(line,))
    result = prepare_receiving_events([event])

    assert len(result.records) == 1
    record = result.records[0]
    assert record.product_id is None
    assert record.eligibility.has_product is False
    assert record.eligibility.eligible_for_analytics is False

    assert result.data_quality.eligible_lines == 0
    assert result.data_quality.ineligible_lines == 1
    assert result.data_quality.missing_product_count == 1


def test_missing_zero_negative_quantity():
    line_zero = make_sample_line(id=1, quantity=Decimal("0.00"))
    line_neg = make_sample_line(id=2, quantity=Decimal("-10.00"))
    line_none = make_sample_line(id=3, quantity=None)  # type: ignore[arg-type]
    event = make_sample_event(lines=(line_zero, line_neg, line_none))

    result = prepare_receiving_events([event])

    assert len(result.records) == 3
    assert result.records[0].eligibility.has_quantity is False
    assert result.records[1].eligibility.has_quantity is False
    assert result.records[2].eligibility.has_quantity is False
    assert result.data_quality.missing_quantity_count == 3
    assert result.data_quality.eligible_lines == 0
    assert result.data_quality.ineligible_lines == 3


def test_missing_negative_and_zero_unit_price():
    line_zero_price = make_sample_line(id=1, unit_price=Decimal("0.00"))
    line_neg_price = make_sample_line(id=2, unit_price=Decimal("-5.00"))
    line_none_price = make_sample_line(id=3, unit_price=None)  # type: ignore[arg-type]
    event = make_sample_event(lines=(line_zero_price, line_neg_price, line_none_price))

    result = prepare_receiving_events([event])

    assert len(result.records) == 3
    # unit_price >= 0 is eligible!
    assert result.records[0].eligibility.has_unit_price is True
    assert result.records[0].eligibility.eligible_for_analytics is True
    # Negative price is ineligible
    assert result.records[1].eligibility.has_unit_price is False
    assert result.records[1].eligibility.eligible_for_analytics is False
    # None price is ineligible
    assert result.records[2].eligibility.has_unit_price is False
    assert result.records[2].eligibility.eligible_for_analytics is False

    assert result.data_quality.missing_price_count == 2
    assert result.data_quality.eligible_lines == 1
    assert result.data_quality.ineligible_lines == 2


def test_missing_supplier():
    event = make_sample_event(supplier_id=None)  # type: ignore[arg-type]
    result = prepare_receiving_events([event])

    record = result.records[0]
    assert record.supplier_id is None
    assert record.eligibility.has_supplier is False
    assert record.eligibility.eligible_for_analytics is False
    assert result.data_quality.missing_supplier_count == 1


def test_missing_warehouse():
    event = make_sample_event(warehouse_id=None)  # type: ignore[arg-type]
    result = prepare_receiving_events([event])

    record = result.records[0]
    assert record.warehouse_id is None
    assert record.eligibility.has_warehouse is False
    assert record.eligibility.eligible_for_analytics is False
    assert result.data_quality.missing_warehouse_count == 1


def test_multiple_missing_fields_and_independent_counters():
    line_all_bad = make_sample_line(
        product_id=None,  # type: ignore[arg-type]
        quantity=Decimal("-10"),
        unit_price=Decimal("-5"),
    )
    event = make_sample_event(
        event_date=None,
        supplier_id=None,  # type: ignore[arg-type]
        warehouse_id=None,  # type: ignore[arg-type]
        lines=(line_all_bad,),
    )
    result = prepare_receiving_events([event])

    record = result.records[0]
    assert record.eligibility.has_event_date is False
    assert record.eligibility.has_product is False
    assert record.eligibility.has_quantity is False
    assert record.eligibility.has_unit_price is False
    assert record.eligibility.has_supplier is False
    assert record.eligibility.has_warehouse is False
    assert record.eligibility.eligible_for_analytics is False

    assert result.data_quality.total_lines == 1
    assert result.data_quality.eligible_lines == 0
    assert result.data_quality.ineligible_lines == 1
    assert result.data_quality.missing_date_count == 1
    assert result.data_quality.missing_product_count == 1
    assert result.data_quality.missing_quantity_count == 1
    assert result.data_quality.missing_price_count == 1
    assert result.data_quality.missing_supplier_count == 1
    assert result.data_quality.missing_warehouse_count == 1


def test_eligible_and_ineligible_lines_both_remain_in_output():
    line_good = make_sample_line(id=1, line_number=1, quantity=Decimal("10"))
    line_bad = make_sample_line(id=2, line_number=2, quantity=Decimal("-5"))
    event = make_sample_event(lines=(line_good, line_bad))

    result = prepare_receiving_events([event])

    assert len(result.records) == 2
    assert len(result.eligible_records) == 1
    assert len(result.ineligible_records) == 1
    assert result.eligible_records[0].line_id == 1
    assert result.ineligible_records[0].line_id == 2
    assert result.data_quality.eligible_lines + result.data_quality.ineligible_lines == result.data_quality.total_lines == 2


def test_decimal_precision_preserved():
    quantity = Decimal("12345.67890123")
    unit_price = Decimal("987.654321")
    subtotal = Decimal("12193259.954718428583")
    line = make_sample_line(quantity=quantity, unit_price=unit_price, subtotal=subtotal)
    event = make_sample_event(lines=(line,))

    result = prepare_receiving_events([event])
    record = result.records[0]

    assert record.quantity == quantity
    assert record.unit_price == unit_price
    assert record.subtotal == subtotal
    assert isinstance(record.quantity, Decimal)
    assert isinstance(record.unit_price, Decimal)
    assert isinstance(record.subtotal, Decimal)


def test_source_provenance_preserved():
    line = make_sample_line(
        source_file="batch_2026_03.xlsx",
        source_sheet="Intake_Log",
        source_row=42,
    )
    event = make_sample_event(
        receiving_reference="PO-REC-9988",
        lines=(line,),
    )

    result = prepare_receiving_events([event])
    record = result.records[0]

    assert record.receiving_reference == "PO-REC-9988"
    assert record.source_file == "batch_2026_03.xlsx"
    assert record.source_sheet == "Intake_Log"
    assert record.source_row == 42


def test_year_month_derived_correctly_from_event_date():
    event1 = make_sample_event(event_date=date(2025, 1, 1))
    event2 = make_sample_event(event_date=date(2026, 12, 31))

    result = prepare_receiving_events([event1, event2])

    assert result.records[0].year == 2025
    assert result.records[0].month == 1
    assert result.records[1].year == 2026
    assert result.records[1].month == 12


def test_category_may_be_none():
    enrichment = ReceivingMasterDataEnrichment(
        products={
            201: ProductMasterData(
                code="PRD-01",
                name="Product Without Category",
                category_id=None,
                category_name=None,
            )
        }
    )
    event = make_sample_event()
    result = prepare_receiving_events([event], enrichment=enrichment)

    record = result.records[0]
    assert record.category_id is None
    assert record.category_name is None
    assert record.product_code == "PRD-01"
    assert record.product_name == "Product Without Category"
    assert record.eligibility.eligible_for_analytics is True


def test_master_data_enrichment_from_explicit_mappings():
    enrichment = ReceivingMasterDataEnrichment(
        company_names={11: "Alpha Corp"},
        supplier_names={21: "Beta Supplier"},
        warehouse_names={31: "Gamma Central WH"},
        unit_names={301: "kg"},
        products={
            201: ProductMasterData(
                code="PROD-XYZ",
                name="Special Lubricant",
                category_id=55,
                category_name="Chemicals",
            )
        },
    )
    event = make_sample_event()
    result = prepare_receiving_events([event], enrichment=enrichment)

    record = result.records[0]
    assert record.company_name == "Alpha Corp"
    assert record.supplier_name == "Beta Supplier"
    assert record.warehouse_name == "Gamma Central WH"
    assert record.unit_name == "kg"
    assert record.product_code == "PROD-XYZ"
    assert record.product_name == "Special Lubricant"
    assert record.category_id == 55
    assert record.category_name == "Chemicals"


def test_missing_master_data_descriptive_values_do_not_trigger_inference():
    event = make_sample_event()
    # No enrichment lookups provided
    result = prepare_receiving_events([event])

    record = result.records[0]
    assert record.company_name is None
    assert record.supplier_name is None
    assert record.warehouse_name is None
    assert record.unit_name is None
    assert record.product_code is None
    assert record.product_name is None
    assert record.category_id is None
    assert record.category_name is None
    # Still eligible because IDs and business values are present!
    assert record.eligibility.eligible_for_analytics is True


def test_duplicate_business_lines_remain_distinct():
    line1 = make_sample_line(id=101, line_number=1, source_row=2)
    line2 = make_sample_line(id=102, line_number=1, source_row=3)
    event = make_sample_event(lines=(line1, line2))

    result = prepare_receiving_events([event])

    assert len(result.records) == 2
    assert result.records[0].line_id == 101
    assert result.records[1].line_id == 102
    assert result.records[0].source_row == 2
    assert result.records[1].source_row == 3


def test_input_order_remains_deterministic():
    event1 = make_sample_event(id=1, receiving_reference="REC-A")
    event2 = make_sample_event(id=2, receiving_reference="REC-B")
    event3 = make_sample_event(id=3, receiving_reference="REC-C")

    result = prepare_receiving_events([event1, event2, event3])

    assert [r.event_id for r in result.records] == [1, 2, 3]
    assert [r.receiving_reference for r in result.records] == ["REC-A", "REC-B", "REC-C"]


def test_dtos_are_immutable():
    event = make_sample_event()
    result = prepare_receiving_events([event])
    record = result.records[0]

    with pytest.raises(FrozenInstanceError):
        record.quantity = Decimal("999")  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        record.eligibility.has_product = False  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.data_quality.total_lines = 100  # type: ignore[misc]


def test_no_input_mutation_occurs():
    line = make_sample_line()
    event = make_sample_event(lines=(line,))
    orig_event_ref = event.receiving_reference
    orig_line_qty = line.quantity

    result = prepare_receiving_events([event])

    assert event.receiving_reference == orig_event_ref
    assert line.quantity == orig_line_qty
    assert len(result.records) == 1


def test_no_database_access_performed():
    # Pure in-memory transformation, passes standalone DTOs without requiring DB session/connection
    event = make_sample_event()
    prep = ReceivingEventAnalyticsPreparation()
    result = prep.prepare([event])
    assert len(result.records) == 1
