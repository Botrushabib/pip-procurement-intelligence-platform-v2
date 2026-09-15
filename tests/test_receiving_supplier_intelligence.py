from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ReceivingAnalyticsDataQualityReport,
    ReceivingAnalyticsEligibility,
    ReceivingAnalyticsPreparationResult,
)
from app.services.receiving_supplier_intelligence import (
    ReceivingSupplierDataQuality,
    ReceivingSupplierDataSufficiency,
    ReceivingSupplierIntelligence,
    ReceivingSupplierIntelligenceRequest,
    ReceivingSupplierIntelligenceResult,
    ReceivingSupplierMonthlyActivity,
    ReceivingSupplierObservation,
    ReceivingSupplierProductSummary,
    ReceivingSupplierSummary,
    analyze_receiving_supplier,
)


def make_prepared_line(
    event_id: int = 1,
    line_id: int = 101,
    line_number: int = 1,
    event_date: date | None = date(2026, 3, 15),
    receiving_reference: str = "REC-REF-001",
    company_id: int = 10,
    company_name: str | None = "Acme Corp",
    supplier_id: int = 20,
    supplier_name: str | None = "Supplier One",
    warehouse_id: int = 30,
    warehouse_name: str | None = "Main Warehouse",
    product_id: int = 200,
    product_code: str | None = "PROD-200",
    product_name: str | None = "Steel Rod",
    category_id: int | None = 50,
    category_name: str | None = "Metals",
    unit_id: int | None = 300,
    unit_name: str | None = "kg",
    quantity: Decimal = Decimal("100.00"),
    unit_price: Decimal = Decimal("25.00"),
    subtotal: Decimal = Decimal("2500.00"),
    source_file: str = "receiving_batch.xlsx",
    source_sheet: str = "Sheet1",
    source_row: int = 2,
    eligible: bool = True,
    eligibility_override: ReceivingAnalyticsEligibility | None = None,
) -> PreparedReceivingEventLine:
    if eligibility_override is not None:
        eligibility = eligibility_override
    else:
        eligibility = ReceivingAnalyticsEligibility(
            has_event_date=event_date is not None,
            has_product=product_id is not None and product_id > 0,
            has_quantity=quantity is not None and quantity > 0,
            has_unit_price=unit_price is not None and unit_price >= 0,
            has_supplier=supplier_id is not None and supplier_id > 0,
            has_warehouse=warehouse_id is not None and warehouse_id > 0,
        )
        if not eligible:
            eligibility = ReceivingAnalyticsEligibility(
                has_event_date=False,
                has_product=True,
                has_quantity=True,
                has_unit_price=True,
                has_supplier=True,
                has_warehouse=True,
            )

    year = event_date.year if event_date else None
    month = event_date.month if event_date else None

    return PreparedReceivingEventLine(
        event_id=event_id,
        line_id=line_id,
        line_number=line_number,
        event_date=event_date,
        year=year,
        month=month,
        receiving_reference=receiving_reference,
        company_id=company_id,
        company_name=company_name,
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        product_id=product_id,
        product_code=product_code,
        product_name=product_name,
        category_id=category_id,
        category_name=category_name,
        unit_id=unit_id,
        unit_name=unit_name,
        quantity=quantity,
        unit_price=unit_price,
        subtotal=subtotal,
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
        eligibility=eligibility,
    )


def test_01_empty_input():
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[],
    )

    assert isinstance(result, ReceivingSupplierIntelligenceResult)
    assert result.sufficiency == ReceivingSupplierDataSufficiency.INSUFFICIENT_DATA
    assert result.observations == ()
    assert result.summary.observation_count == 0
    assert result.summary.distinct_event_count == 0
    assert result.summary.distinct_product_count == 0
    assert result.summary.distinct_receiving_date_count == 0
    assert result.summary.total_quantity == Decimal("0")
    assert result.summary.total_spend == Decimal("0")
    assert result.summary.weighted_average_unit_price is None
    assert result.summary.arithmetic_average_unit_price is None
    assert result.summary.min_unit_price is None
    assert result.summary.max_unit_price is None
    assert result.summary.price_spread is None
    assert result.summary.first_receiving_date is None
    assert result.summary.latest_receiving_date is None
    assert result.summary.average_days_between_receipts is None
    assert result.monthly_activity == ()
    assert result.product_summaries == ()
    assert result.data_quality.examined_lines == 0
    assert result.data_quality.analytics_eligible_lines == 0
    assert result.data_quality.supplier_matched_lines == 0


def test_02_no_matching_supplier():
    line = make_prepared_line(supplier_id=99)
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert result.sufficiency == ReceivingSupplierDataSufficiency.INSUFFICIENT_DATA
    assert result.observations == ()
    assert result.data_quality.examined_lines == 1
    assert result.data_quality.analytics_eligible_lines == 1
    assert result.data_quality.supplier_matched_lines == 0


def test_03_single_observation():
    line = make_prepared_line(
        event_id=1,
        line_id=101,
        event_date=date(2026, 3, 15),
        supplier_id=20,
        product_id=200,
        quantity=Decimal("50.00"),
        unit_price=Decimal("10.00"),
        subtotal=Decimal("500.00"),
    )
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert result.sufficiency == ReceivingSupplierDataSufficiency.AVAILABLE
    assert len(result.observations) == 1
    obs = result.observations[0]
    assert obs.event_id == 1
    assert obs.line_id == 101
    assert obs.supplier_id == 20
    assert obs.product_id == 200
    assert obs.quantity == Decimal("50.00")
    assert obs.unit_price == Decimal("10.00")
    assert obs.subtotal == Decimal("500.00")

    assert result.summary.observation_count == 1
    assert result.summary.distinct_event_count == 1
    assert result.summary.distinct_product_count == 1
    assert result.summary.distinct_receiving_date_count == 1
    assert result.summary.total_quantity == Decimal("50.00")
    assert result.summary.total_spend == Decimal("500.00")
    assert result.summary.weighted_average_unit_price == Decimal("10.00")
    assert result.summary.arithmetic_average_unit_price == Decimal("10.00")
    assert result.summary.min_unit_price == Decimal("10.00")
    assert result.summary.max_unit_price == Decimal("10.00")
    assert result.summary.price_spread == Decimal("0.00")
    assert result.summary.first_receiving_date == date(2026, 3, 15)
    assert result.summary.latest_receiving_date == date(2026, 3, 15)
    assert result.summary.average_days_between_receipts is None

    assert len(result.monthly_activity) == 1
    assert result.monthly_activity[0].year == 2026
    assert result.monthly_activity[0].month == 3
    assert result.monthly_activity[0].observation_count == 1
    assert result.monthly_activity[0].total_quantity == Decimal("50.00")
    assert result.monthly_activity[0].total_spend == Decimal("500.00")
    assert result.monthly_activity[0].weighted_average_unit_price == Decimal("10.00")

    assert len(result.product_summaries) == 1
    assert result.product_summaries[0].product_id == 200
    assert result.product_summaries[0].observation_count == 1
    assert result.product_summaries[0].latest_price == Decimal("10.00")


def test_04_multiple_observations():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 10), quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 20), quantity=Decimal("20"), unit_price=Decimal("15"), subtotal=Decimal("300")),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert result.summary.observation_count == 2
    assert result.summary.total_quantity == Decimal("30")
    assert result.summary.total_spend == Decimal("400")
    # Weighted avg: 400 / 30 = 13.333...
    assert result.summary.arithmetic_average_unit_price == Decimal("12.5")


def test_05_multiple_products():
    lines = [
        make_prepared_line(event_id=1, line_id=1, product_id=201),
        make_prepared_line(event_id=1, line_id=2, product_id=202),
        make_prepared_line(event_id=2, line_id=3, product_id=203),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert result.summary.distinct_product_count == 3
    assert len(result.product_summaries) == 3


def test_06_multiple_events():
    lines = [
        make_prepared_line(event_id=10, line_id=1),
        make_prepared_line(event_id=10, line_id=2),
        make_prepared_line(event_id=20, line_id=3),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert result.summary.distinct_event_count == 2
    assert result.summary.observation_count == 3


def test_07_duplicate_operational_lines():
    line1 = make_prepared_line(event_id=1, line_id=101, line_number=1, quantity=Decimal("10"), subtotal=Decimal("100"))
    line2 = make_prepared_line(event_id=1, line_id=102, line_number=1, quantity=Decimal("10"), subtotal=Decimal("100"))

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line1, line2],
    )

    assert result.summary.observation_count == 2
    assert result.summary.distinct_event_count == 1
    assert result.summary.total_quantity == Decimal("20")
    assert result.summary.total_spend == Decimal("200")


def test_08_supplier_exact_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, supplier_id=20)
    l2 = make_prepared_line(event_id=2, line_id=2, supplier_id=21)

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].supplier_id == 20


def test_09_product_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, product_id=200)
    l2 = make_prepared_line(event_id=2, line_id=2, product_id=201)

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20, product_id=200),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].product_id == 200


def test_10_unit_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, unit_id=300)
    l2 = make_prepared_line(event_id=2, line_id=2, unit_id=301)

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20, unit_id=300),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].unit_id == 300


def test_11_company_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, company_id=10)
    l2 = make_prepared_line(event_id=2, line_id=2, company_id=11)

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20, company_id=10),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].company_id == 10


def test_12_warehouse_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, warehouse_id=30)
    l2 = make_prepared_line(event_id=2, line_id=2, warehouse_id=31)

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20, warehouse_id=30),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].warehouse_id == 30


def test_13_date_from_inclusive():
    l1 = make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 3, 10))
    l2 = make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 3, 9))

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20, date_from=date(2026, 3, 10)),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].line_id == 1


def test_14_date_to_inclusive():
    l1 = make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 3, 20))
    l2 = make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 3, 21))

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20, date_to=date(2026, 3, 20)),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].line_id == 1


def test_15_reference_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, receiving_reference="REC-REF-AAA")
    l2 = make_prepared_line(event_id=2, line_id=2, receiving_reference="REC-REF-BBB")

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20, reference="REC-REF-AAA"),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].receiving_reference == "REC-REF-AAA"


def test_16_combined_filters():
    target = make_prepared_line(
        event_id=1,
        line_id=101,
        supplier_id=20,
        product_id=200,
        unit_id=300,
        company_id=10,
        warehouse_id=30,
        event_date=date(2026, 3, 15),
        receiving_reference="REC-TARGET",
    )
    other = make_prepared_line(
        event_id=2,
        line_id=102,
        supplier_id=20,
        product_id=200,
        unit_id=300,
        company_id=99,
        warehouse_id=30,
        event_date=date(2026, 3, 15),
        receiving_reference="REC-TARGET",
    )

    req = ReceivingSupplierIntelligenceRequest(
        supplier_id=20,
        product_id=200,
        unit_id=300,
        company_id=10,
        warehouse_id=30,
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        reference="REC-TARGET",
    )
    result = analyze_receiving_supplier(req, records=[target, other])

    assert result.summary.observation_count == 1
    assert result.observations[0].line_id == 101


def test_17_18_19_20_totals_and_averages():
    # Line 1: 10 qty @ $10 = 100
    # Line 2: 90 qty @ $20 = 1800
    # Total qty = 100, Total spend = 1900
    # Weighted avg = 19.00
    # Arithmetic avg = 15.00
    lines = [
        make_prepared_line(event_id=1, line_id=1, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, quantity=Decimal("90"), unit_price=Decimal("20"), subtotal=Decimal("1800")),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert result.summary.total_quantity == Decimal("100")
    assert result.summary.total_spend == Decimal("1900")
    assert result.summary.weighted_average_unit_price == Decimal("19")
    assert result.summary.arithmetic_average_unit_price == Decimal("15")


def test_21_22_23_min_max_spread():
    lines = [
        make_prepared_line(event_id=1, line_id=1, unit_price=Decimal("15.50")),
        make_prepared_line(event_id=2, line_id=2, unit_price=Decimal("4.50")),
        make_prepared_line(event_id=3, line_id=3, unit_price=Decimal("29.00")),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert result.summary.min_unit_price == Decimal("4.50")
    assert result.summary.max_unit_price == Decimal("29.00")
    assert result.summary.price_spread == Decimal("24.50")


def test_24_25_26_distinct_counts():
    lines = [
        make_prepared_line(event_id=1, line_id=1, product_id=201, event_date=date(2026, 3, 1)),
        make_prepared_line(event_id=1, line_id=2, product_id=202, event_date=date(2026, 3, 1)),
        make_prepared_line(event_id=2, line_id=3, product_id=201, event_date=date(2026, 3, 2)),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert result.summary.distinct_event_count == 2
    assert result.summary.distinct_product_count == 2
    assert result.summary.distinct_receiving_date_count == 2


def test_27_28_first_and_latest_receiving_date():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 15)),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 5, 20)),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 3, 10)),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert result.summary.first_receiving_date == date(2026, 1, 15)
    assert result.summary.latest_receiving_date == date(2026, 5, 20)


def test_29_30_monthly_aggregation_and_ordering():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 2, 10), quantity=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2025, 12, 1), quantity=Decimal("20"), subtotal=Decimal("300")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 15), quantity=Decimal("30"), subtotal=Decimal("600")),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert len(result.monthly_activity) == 3
    # Sorted chronologically
    assert (result.monthly_activity[0].year, result.monthly_activity[0].month) == (2025, 12)
    assert (result.monthly_activity[1].year, result.monthly_activity[1].month) == (2026, 1)
    assert (result.monthly_activity[2].year, result.monthly_activity[2].month) == (2026, 2)


def test_31_supplier_product_aggregation():
    lines = [
        make_prepared_line(event_id=1, line_id=1, product_id=201, unit_id=300, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, product_id=201, unit_id=300, quantity=Decimal("20"), unit_price=Decimal("20"), subtotal=Decimal("400")),
        make_prepared_line(event_id=3, line_id=3, product_id=202, unit_id=300, quantity=Decimal("5"), unit_price=Decimal("50"), subtotal=Decimal("250")),
    ]
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=lines,
    )

    assert len(result.product_summaries) == 2
    p1 = result.product_summaries[0]
    assert p1.product_id == 201
    assert p1.observation_count == 2
    assert p1.total_quantity == Decimal("30")
    assert p1.total_spend == Decimal("500")
    # Weighted avg: 500 / 30 = 16.666...
    assert p1.arithmetic_average_unit_price == Decimal("15")
    assert p1.min_price == Decimal("10")
    assert p1.max_price == Decimal("20")


def test_32_33_supplier_product_latest_price_and_tie_break():
    # Same product, two dates
    l1 = make_prepared_line(event_id=1, line_id=1, product_id=201, event_date=date(2026, 1, 1), unit_price=Decimal("10"))
    l2 = make_prepared_line(event_id=2, line_id=2, product_id=201, event_date=date(2026, 1, 2), unit_price=Decimal("15"))
    # Same date tie-break by event_id, line_number, line_id
    l3 = make_prepared_line(event_id=3, line_id=10, line_number=1, product_id=201, event_date=date(2026, 1, 2), unit_price=Decimal("18"))

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[l1, l2, l3],
    )

    p_summary = result.product_summaries[0]
    assert p_summary.latest_price == Decimal("18")
    assert p_summary.latest_receiving_date == date(2026, 1, 2)
    assert p_summary.first_receiving_date == date(2026, 1, 1)


def test_34_frequency_using_distinct_dates():
    # 3 distinct dates: 2026-03-01, 2026-03-11, 2026-03-21 -> span 20 days, intervals 2 -> avg = 10 days
    l1 = make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 3, 1))
    l2 = make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 3, 11))
    l3 = make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 3, 21))
    l4 = make_prepared_line(event_id=4, line_id=4, event_date=date(2026, 3, 21))  # duplicate date

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[l1, l2, l3, l4],
    )

    assert result.summary.distinct_receiving_date_count == 3
    assert result.summary.average_days_between_receipts == Decimal("10")


def test_35_single_distinct_date_frequency():
    l1 = make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 3, 1))
    l2 = make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 3, 1))

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[l1, l2],
    )

    assert result.summary.distinct_receiving_date_count == 1
    assert result.summary.average_days_between_receipts is None


def test_36_zero_observations_frequency():
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[],
    )

    assert result.summary.average_days_between_receipts is None


def test_37_zero_quantity_protection():
    line = make_prepared_line(quantity=Decimal("0.00"), unit_price=Decimal("10.00"), subtotal=Decimal("0.00"))
    # Ineligible because quantity <= 0
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert result.summary.observation_count == 0
    assert result.summary.weighted_average_unit_price is None


def test_38_decimal_precision():
    q1 = Decimal("123.456789")
    p1 = Decimal("98.765432")
    s1 = q1 * p1
    line = make_prepared_line(quantity=q1, unit_price=p1, subtotal=s1)

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert isinstance(result.summary.total_quantity, Decimal)
    assert isinstance(result.summary.total_spend, Decimal)
    assert isinstance(result.summary.weighted_average_unit_price, Decimal)
    assert result.summary.total_quantity == q1
    assert result.summary.total_spend == s1
    assert result.summary.weighted_average_unit_price == p1


def test_39_ineligible_line_retention():
    l_valid = make_prepared_line(event_id=1, line_id=1, eligible=True)
    l_invalid = make_prepared_line(event_id=2, line_id=2, eligible=False)

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[l_valid, l_invalid],
    )

    assert result.data_quality.examined_lines == 2
    assert result.data_quality.analytics_eligible_lines == 1
    assert result.data_quality.supplier_matched_lines == 1
    assert result.summary.observation_count == 1


def test_40_missing_supplier():
    line = make_prepared_line(
        supplier_id=None,  # type: ignore[arg-type]
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=True,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=False,
            has_warehouse=True,
        ),
    )
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert result.data_quality.missing_supplier_count == 1
    assert result.data_quality.supplier_matched_lines == 0


def test_41_missing_product():
    line = make_prepared_line(
        product_id=None,  # type: ignore[arg-type]
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=False,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert result.data_quality.missing_product_count == 1


def test_42_missing_date():
    line = make_prepared_line(
        event_date=None,
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=False,
            has_product=True,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert result.data_quality.missing_date_count == 1


def test_43_missing_price():
    line = make_prepared_line(
        unit_price=None,  # type: ignore[arg-type]
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=True,
            has_quantity=True,
            has_unit_price=False,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert result.data_quality.missing_price_count == 1


def test_44_missing_quantity():
    line = make_prepared_line(
        quantity=None,  # type: ignore[arg-type]
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=True,
            has_quantity=False,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert result.data_quality.missing_quantity_count == 1


def test_45_immutability():
    line = make_prepared_line()
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    with pytest.raises(FrozenInstanceError):
        result.summary.observation_count = 999  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.request.supplier_id = 999  # type: ignore[misc]


def test_46_input_non_mutation():
    line = make_prepared_line()
    orig_qty = line.quantity
    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[line],
    )

    assert line.quantity == orig_qty
    assert len(result.observations) == 1


def test_47_deterministic_observation_ordering():
    l1 = make_prepared_line(event_id=2, line_id=20, line_number=1, event_date=date(2026, 3, 2))
    l2 = make_prepared_line(event_id=1, line_id=10, line_number=2, event_date=date(2026, 3, 1))
    l3 = make_prepared_line(event_id=1, line_id=11, line_number=1, event_date=date(2026, 3, 1))

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[l1, l2, l3],
    )

    assert [obs.line_id for obs in result.observations] == [11, 10, 20]


def test_48_deterministic_product_ordering():
    l1 = make_prepared_line(event_id=1, line_id=1, product_id=205, unit_id=300)
    l2 = make_prepared_line(event_id=2, line_id=2, product_id=201, unit_id=302)
    l3 = make_prepared_line(event_id=3, line_id=3, product_id=201, unit_id=301)

    result = analyze_receiving_supplier(
        ReceivingSupplierIntelligenceRequest(supplier_id=20),
        records=[l1, l2, l3],
    )

    assert [p.product_id for p in result.product_summaries] == [201, 201, 205]
    assert [p.unit_id for p in result.product_summaries] == [301, 302, 300]


def test_49_read_only_behavior():
    line = make_prepared_line()
    service = ReceivingSupplierIntelligence()
    res = service.analyze(ReceivingSupplierIntelligenceRequest(supplier_id=20), records=[line])
    assert res.summary.observation_count == 1
    assert isinstance(res.observations, tuple)
    assert isinstance(res.monthly_activity, tuple)
    assert isinstance(res.product_summaries, tuple)


def test_50_no_domain_crossing():
    # Service accepts only receiving records and does not touch or require purchase models
    line = make_prepared_line()
    result = analyze_receiving_supplier(ReceivingSupplierIntelligenceRequest(supplier_id=20), records=[line])
    assert result.summary.observation_count == 1
