from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from app.services.receiving_category_intelligence import (
    ReceivingCategoryDataQuality,
    ReceivingCategoryDataSufficiency,
    ReceivingCategoryIntelligence,
    ReceivingCategoryIntelligenceRequest,
    ReceivingCategoryIntelligenceResult,
    ReceivingCategoryMonthlyActivity,
    ReceivingCategoryObservation,
    ReceivingCategoryProductSummary,
    ReceivingCategorySummary,
    ReceivingCategorySupplierSummary,
    analyze_receiving_category,
)
from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ReceivingAnalyticsEligibility,
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
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[],
    )

    assert isinstance(result, ReceivingCategoryIntelligenceResult)
    assert result.sufficiency == ReceivingCategoryDataSufficiency.INSUFFICIENT_DATA
    assert result.observations == ()
    assert result.summary.category_id == 50
    assert result.summary.category_name is None
    assert result.summary.observation_count == 0
    assert result.summary.distinct_event_count == 0
    assert result.summary.distinct_product_count == 0
    assert result.summary.distinct_supplier_count == 0
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
    assert result.supplier_summaries == ()
    assert result.data_quality.examined_lines == 0
    assert result.data_quality.analytics_eligible_lines == 0
    assert result.data_quality.category_matched_lines == 0


def test_02_no_matching_category():
    line = make_prepared_line(category_id=99)
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[line],
    )

    assert result.sufficiency == ReceivingCategoryDataSufficiency.INSUFFICIENT_DATA
    assert result.observations == ()
    assert result.data_quality.examined_lines == 1
    assert result.data_quality.analytics_eligible_lines == 1
    assert result.data_quality.category_matched_lines == 0


def test_03_single_observation():
    line = make_prepared_line(
        event_id=1,
        line_id=101,
        event_date=date(2026, 3, 15),
        category_id=50,
        category_name="Metals",
        supplier_id=20,
        supplier_name="Supplier One",
        product_id=200,
        product_code="PROD-200",
        product_name="Steel Rod",
        unit_id=300,
        unit_name="kg",
        quantity=Decimal("50.00"),
        unit_price=Decimal("10.00"),
        subtotal=Decimal("500.00"),
    )
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[line],
    )

    assert result.sufficiency == ReceivingCategoryDataSufficiency.AVAILABLE
    assert len(result.observations) == 1
    obs = result.observations[0]
    assert obs.event_id == 1
    assert obs.line_id == 101
    assert obs.category_id == 50
    assert obs.category_name == "Metals"
    assert obs.product_id == 200
    assert obs.supplier_id == 20
    assert obs.quantity == Decimal("50.00")
    assert obs.unit_price == Decimal("10.00")
    assert obs.subtotal == Decimal("500.00")

    assert result.summary.category_id == 50
    assert result.summary.category_name == "Metals"
    assert result.summary.observation_count == 1
    assert result.summary.distinct_event_count == 1
    assert result.summary.distinct_product_count == 1
    assert result.summary.distinct_supplier_count == 1
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
    assert result.monthly_activity[0].distinct_event_count == 1
    assert result.monthly_activity[0].distinct_product_count == 1
    assert result.monthly_activity[0].distinct_supplier_count == 1
    assert result.monthly_activity[0].total_quantity == Decimal("50.00")
    assert result.monthly_activity[0].total_spend == Decimal("500.00")

    assert len(result.product_summaries) == 1
    prod = result.product_summaries[0]
    assert prod.product_id == 200
    assert prod.unit_id == 300
    assert prod.observation_count == 1
    assert prod.distinct_supplier_count == 1
    assert prod.latest_price == Decimal("10.00")

    assert len(result.supplier_summaries) == 1
    supp = result.supplier_summaries[0]
    assert supp.supplier_id == 20
    assert supp.supplier_name == "Supplier One"
    assert supp.observation_count == 1
    assert supp.distinct_event_count == 1
    assert supp.distinct_product_count == 1


def test_04_multiple_products():
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, product_id=201),
        make_prepared_line(event_id=1, line_id=2, category_id=50, product_id=202),
        make_prepared_line(event_id=2, line_id=3, category_id=50, product_id=203),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert result.summary.distinct_product_count == 3
    assert len(result.product_summaries) == 3


def test_05_multiple_suppliers():
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, supplier_id=21),
        make_prepared_line(event_id=2, line_id=2, category_id=50, supplier_id=22),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert result.summary.distinct_supplier_count == 2
    assert len(result.supplier_summaries) == 2


def test_06_multiple_events():
    lines = [
        make_prepared_line(event_id=10, line_id=1, category_id=50),
        make_prepared_line(event_id=10, line_id=2, category_id=50),
        make_prepared_line(event_id=20, line_id=3, category_id=50),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert result.summary.distinct_event_count == 2
    assert result.summary.observation_count == 3


def test_07_duplicate_operational_lines():
    line1 = make_prepared_line(event_id=1, line_id=101, line_number=1, category_id=50, quantity=Decimal("10"), subtotal=Decimal("100"))
    line2 = make_prepared_line(event_id=1, line_id=102, line_number=1, category_id=50, quantity=Decimal("10"), subtotal=Decimal("100"))

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[line1, line2],
    )

    assert result.summary.observation_count == 2
    assert result.summary.distinct_event_count == 1
    assert result.summary.total_quantity == Decimal("20")
    assert result.summary.total_spend == Decimal("200")


def test_08_exact_category_matching():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50)
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=51)

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].category_id == 50


def test_09_product_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, product_id=200)
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, product_id=201)

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50, product_id=200),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].product_id == 200


def test_10_supplier_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, supplier_id=20)
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, supplier_id=21)

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50, supplier_id=20),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].supplier_id == 20


def test_11_unit_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, unit_id=300)
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, unit_id=301)

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50, unit_id=300),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].unit_id == 300


def test_12_company_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, company_id=10)
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, company_id=11)

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50, company_id=10),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].company_id == 10


def test_13_warehouse_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, warehouse_id=30)
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, warehouse_id=31)

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50, warehouse_id=30),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].warehouse_id == 30


def test_14_date_from_inclusive():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, event_date=date(2026, 3, 10))
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, event_date=date(2026, 3, 9))

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50, date_from=date(2026, 3, 10)),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].line_id == 1


def test_15_date_to_inclusive():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, event_date=date(2026, 3, 20))
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, event_date=date(2026, 3, 21))

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50, date_to=date(2026, 3, 20)),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].line_id == 1


def test_16_reference_filter():
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, receiving_reference="REC-REF-AAA")
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, receiving_reference="REC-REF-BBB")

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50, reference="REC-REF-AAA"),
        records=[l1, l2],
    )

    assert result.summary.observation_count == 1
    assert result.observations[0].receiving_reference == "REC-REF-AAA"


def test_17_combined_filters():
    target = make_prepared_line(
        event_id=1,
        line_id=101,
        category_id=50,
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
        category_id=50,
        supplier_id=20,
        product_id=200,
        unit_id=300,
        company_id=99,
        warehouse_id=30,
        event_date=date(2026, 3, 15),
        receiving_reference="REC-TARGET",
    )

    req = ReceivingCategoryIntelligenceRequest(
        category_id=50,
        supplier_id=20,
        product_id=200,
        unit_id=300,
        company_id=10,
        warehouse_id=30,
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        reference="REC-TARGET",
    )
    result = analyze_receiving_category(req, records=[target, other])

    assert result.summary.observation_count == 1
    assert result.observations[0].line_id == 101


def test_18_to_21_totals_and_averages():
    # Line 1: 10 qty @ $10 = 100
    # Line 2: 90 qty @ $20 = 1800
    # Total qty = 100, Total spend = 1900
    # Weighted avg = 19.00
    # Arithmetic avg = 15.00
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, category_id=50, quantity=Decimal("90"), unit_price=Decimal("20"), subtotal=Decimal("1800")),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert result.summary.total_quantity == Decimal("100")
    assert result.summary.total_spend == Decimal("1900")
    assert result.summary.weighted_average_unit_price == Decimal("19")
    assert result.summary.arithmetic_average_unit_price == Decimal("15")


def test_22_to_24_min_max_spread():
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, unit_price=Decimal("15.50")),
        make_prepared_line(event_id=2, line_id=2, category_id=50, unit_price=Decimal("4.50")),
        make_prepared_line(event_id=3, line_id=3, category_id=50, unit_price=Decimal("29.00")),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert result.summary.min_unit_price == Decimal("4.50")
    assert result.summary.max_unit_price == Decimal("29.00")
    assert result.summary.price_spread == Decimal("24.50")


def test_25_to_28_distinct_counts():
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, product_id=201, supplier_id=21, event_date=date(2026, 3, 1)),
        make_prepared_line(event_id=1, line_id=2, category_id=50, product_id=202, supplier_id=22, event_date=date(2026, 3, 1)),
        make_prepared_line(event_id=2, line_id=3, category_id=50, product_id=201, supplier_id=21, event_date=date(2026, 3, 2)),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert result.summary.distinct_event_count == 2
    assert result.summary.distinct_product_count == 2
    assert result.summary.distinct_supplier_count == 2
    assert result.summary.distinct_receiving_date_count == 2


def test_29_30_first_and_latest_receiving_date():
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, event_date=date(2026, 1, 15)),
        make_prepared_line(event_id=2, line_id=2, category_id=50, event_date=date(2026, 5, 20)),
        make_prepared_line(event_id=3, line_id=3, category_id=50, event_date=date(2026, 3, 10)),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert result.summary.first_receiving_date == date(2026, 1, 15)
    assert result.summary.latest_receiving_date == date(2026, 5, 20)


def test_31_to_33_category_frequency():
    # 3 distinct dates: 2026-03-01, 2026-03-11, 2026-03-21 -> span 20 days, intervals 2 -> avg = 10 days
    l1 = make_prepared_line(event_id=1, line_id=1, category_id=50, event_date=date(2026, 3, 1))
    l2 = make_prepared_line(event_id=2, line_id=2, category_id=50, event_date=date(2026, 3, 11))
    l3 = make_prepared_line(event_id=3, line_id=3, category_id=50, event_date=date(2026, 3, 21))
    l4 = make_prepared_line(event_id=4, line_id=4, category_id=50, event_date=date(2026, 3, 21))  # duplicate date

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[l1, l2, l3, l4],
    )

    assert result.summary.distinct_receiving_date_count == 3
    assert result.summary.average_days_between_receipts == Decimal("10")

    # Single date
    res_single = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[l1],
    )
    assert res_single.summary.average_days_between_receipts is None

    # Zero observations
    res_zero = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[],
    )
    assert res_zero.summary.average_days_between_receipts is None


def test_34_to_37_monthly_aggregation_and_counts():
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, product_id=201, supplier_id=21, event_date=date(2026, 2, 10), quantity=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, category_id=50, product_id=202, supplier_id=22, event_date=date(2025, 12, 1), quantity=Decimal("20"), subtotal=Decimal("300")),
        make_prepared_line(event_id=3, line_id=3, category_id=50, product_id=201, supplier_id=21, event_date=date(2026, 1, 15), quantity=Decimal("30"), subtotal=Decimal("600")),
        make_prepared_line(event_id=4, line_id=4, category_id=50, product_id=202, supplier_id=21, event_date=date(2026, 1, 16), quantity=Decimal("40"), subtotal=Decimal("800")),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert len(result.monthly_activity) == 3
    # Sorted chronologically
    assert (result.monthly_activity[0].year, result.monthly_activity[0].month) == (2025, 12)
    assert (result.monthly_activity[1].year, result.monthly_activity[1].month) == (2026, 1)
    assert (result.monthly_activity[2].year, result.monthly_activity[2].month) == (2026, 2)

    # Jan 2026 has 2 distinct products (201, 202) and 1 supplier (21)
    jan = result.monthly_activity[1]
    assert jan.observation_count == 2
    assert jan.distinct_product_count == 2
    assert jan.distinct_supplier_count == 1
    assert jan.total_quantity == Decimal("70")
    assert jan.total_spend == Decimal("1400")


def test_38_to_40_category_product_aggregation_and_latest_price():
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, product_id=201, unit_id=300, supplier_id=21, event_date=date(2026, 1, 1), unit_price=Decimal("10"), quantity=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, category_id=50, product_id=201, unit_id=300, supplier_id=22, event_date=date(2026, 1, 2), unit_price=Decimal("15"), quantity=Decimal("20"), subtotal=Decimal("300")),
        make_prepared_line(event_id=3, line_id=10, line_number=1, category_id=50, product_id=201, unit_id=300, supplier_id=22, event_date=date(2026, 1, 2), unit_price=Decimal("18"), quantity=Decimal("5"), subtotal=Decimal("90")),
        make_prepared_line(event_id=4, line_id=4, category_id=50, product_id=202, unit_id=300, supplier_id=21, event_date=date(2026, 1, 3), unit_price=Decimal("50"), quantity=Decimal("2"), subtotal=Decimal("100")),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert len(result.product_summaries) == 2
    p1 = result.product_summaries[0]
    assert p1.product_id == 201
    assert p1.unit_id == 300
    assert p1.observation_count == 3
    assert p1.distinct_supplier_count == 2
    assert p1.total_quantity == Decimal("35")
    assert p1.total_spend == Decimal("490")
    assert p1.min_price == Decimal("10")
    assert p1.max_price == Decimal("18")
    assert p1.latest_price == Decimal("18")
    assert p1.first_receiving_date == date(2026, 1, 1)
    assert p1.latest_receiving_date == date(2026, 1, 2)


def test_41_42_category_supplier_aggregation():
    lines = [
        make_prepared_line(event_id=1, line_id=1, category_id=50, supplier_id=21, product_id=201, event_date=date(2026, 1, 1), quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, category_id=50, supplier_id=21, product_id=202, event_date=date(2026, 1, 2), quantity=Decimal("20"), unit_price=Decimal("20"), subtotal=Decimal("400")),
        make_prepared_line(event_id=3, line_id=3, category_id=50, supplier_id=22, product_id=201, event_date=date(2026, 1, 3), quantity=Decimal("5"), unit_price=Decimal("50"), subtotal=Decimal("250")),
    ]
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=lines,
    )

    assert len(result.supplier_summaries) == 2
    s1 = result.supplier_summaries[0]
    assert s1.supplier_id == 21
    assert s1.observation_count == 2
    assert s1.distinct_event_count == 2
    assert s1.distinct_product_count == 2
    assert s1.total_quantity == Decimal("30")
    assert s1.total_spend == Decimal("500")
    assert s1.first_receiving_date == date(2026, 1, 1)
    assert s1.latest_receiving_date == date(2026, 1, 2)


def test_43_44_zero_quantity_and_decimal_precision():
    q1 = Decimal("123.456789")
    p1 = Decimal("98.765432")
    s1 = q1 * p1
    line = make_prepared_line(category_id=50, quantity=q1, unit_price=p1, subtotal=s1)

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[line],
    )

    assert isinstance(result.summary.total_quantity, Decimal)
    assert isinstance(result.summary.total_spend, Decimal)
    assert isinstance(result.summary.weighted_average_unit_price, Decimal)
    assert result.summary.total_quantity == q1
    assert result.summary.total_spend == s1
    assert result.summary.weighted_average_unit_price == p1


def test_45_to_52_data_quality_and_missing_counters():
    l_valid = make_prepared_line(event_id=1, line_id=1, category_id=50, eligible=True)
    l_ineligible = make_prepared_line(event_id=2, line_id=2, category_id=50, eligible=False)
    l_missing_cat = make_prepared_line(
        event_id=3,
        line_id=3,
        category_id=None,
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=True,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    l_missing_prod = make_prepared_line(
        event_id=4,
        line_id=4,
        category_id=50,
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
    l_missing_supp = make_prepared_line(
        event_id=5,
        line_id=5,
        category_id=50,
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
    l_missing_unit = make_prepared_line(
        event_id=6,
        line_id=6,
        category_id=50,
        unit_id=None,
    )

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[l_valid, l_ineligible, l_missing_cat, l_missing_prod, l_missing_supp, l_missing_unit],
    )

    assert result.data_quality.examined_lines == 6
    assert result.data_quality.category_matched_lines == 2  # l_valid + l_missing_unit
    assert result.data_quality.missing_category_count == 1
    assert result.data_quality.missing_product_count == 1
    assert result.data_quality.missing_supplier_count == 1
    assert result.data_quality.missing_unit_count == 1


def test_53_54_immutability_and_non_mutation():
    line = make_prepared_line(category_id=50)
    orig_qty = line.quantity
    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[line],
    )

    assert line.quantity == orig_qty
    with pytest.raises(FrozenInstanceError):
        result.summary.observation_count = 999  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.request.category_id = 999  # type: ignore[misc]


def test_55_to_57_deterministic_orderings():
    l1 = make_prepared_line(event_id=2, line_id=20, line_number=1, category_id=50, product_id=205, unit_id=300, supplier_id=22, event_date=date(2026, 3, 2))
    l2 = make_prepared_line(event_id=1, line_id=10, line_number=2, category_id=50, product_id=201, unit_id=302, supplier_id=21, event_date=date(2026, 3, 1))
    l3 = make_prepared_line(event_id=1, line_id=11, line_number=1, category_id=50, product_id=201, unit_id=301, supplier_id=21, event_date=date(2026, 3, 1))

    result = analyze_receiving_category(
        ReceivingCategoryIntelligenceRequest(category_id=50),
        records=[l1, l2, l3],
    )

    # Observations sorted by (event_date, event_id, line_number, line_id)
    assert [obs.line_id for obs in result.observations] == [11, 10, 20]

    # Product summaries sorted by (product_id ASC, unit_id ASC)
    assert [(p.product_id, p.unit_id) for p in result.product_summaries] == [(201, 301), (201, 302), (205, 300)]

    # Supplier summaries sorted by supplier_id ASC
    assert [s.supplier_id for s in result.supplier_summaries] == [21, 22]


def test_58_59_read_only_and_no_domain_crossing():
    line = make_prepared_line(category_id=50)
    service = ReceivingCategoryIntelligence()
    res = service.analyze(ReceivingCategoryIntelligenceRequest(category_id=50), records=[line])
    assert res.summary.observation_count == 1
    assert isinstance(res.observations, tuple)
    assert isinstance(res.monthly_activity, tuple)
    assert isinstance(res.product_summaries, tuple)
    assert isinstance(res.supplier_summaries, tuple)
