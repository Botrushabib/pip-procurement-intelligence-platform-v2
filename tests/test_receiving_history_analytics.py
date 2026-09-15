from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ReceivingAnalyticsDataQualityReport,
    ReceivingAnalyticsEligibility,
    ReceivingAnalyticsPreparationResult,
    ReceivingEventAnalyticsPreparation,
)
from app.services.receiving_history_analytics import (
    LastReceiving,
    MonthlyReceivingTotal,
    ReceivingFrequency,
    ReceivingHistoryAnalytics,
    ReceivingHistoryFilter,
    ReceivingHistoryResult,
    analyze_receiving_history,
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
    unit_id: int = 300,
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


def test_empty_result():
    analytics = ReceivingHistoryAnalytics()
    result = analytics.analyze(records=[])

    assert isinstance(result, ReceivingHistoryResult)
    assert result.examined_count == 0
    assert result.records == ()
    assert result.line_count == 0
    assert result.distinct_event_count == 0
    assert result.total_quantity == Decimal("0")
    assert result.total_subtotal == Decimal("0")
    assert result.average_quantity_per_line is None
    assert result.average_unit_price is None
    assert result.minimum_unit_price is None
    assert result.maximum_unit_price is None
    assert result.last_receiving is None
    assert result.receiving_frequency == ReceivingFrequency(
        event_count=0,
        line_count=0,
        first_receiving_date=None,
        last_receiving_date=None,
        average_days_between_receipts=None,
    )
    assert result.monthly_totals == ()
    assert result.data_quality.total_lines == 0
    assert result.data_quality.eligible_lines == 0
    assert result.data_quality.ineligible_lines == 0


def test_single_eligible_line():
    line = make_prepared_line(
        event_id=1,
        line_id=101,
        event_date=date(2026, 3, 10),
        quantity=Decimal("100"),
        unit_price=Decimal("20"),
        subtotal=Decimal("2000"),
    )
    result = analyze_receiving_history(records=[line])

    assert result.examined_count == 1
    assert result.line_count == 1
    assert result.distinct_event_count == 1
    assert result.total_quantity == Decimal("100")
    assert result.total_subtotal == Decimal("2000")
    assert result.average_quantity_per_line == Decimal("100")
    assert result.average_unit_price == Decimal("20")
    assert result.minimum_unit_price == Decimal("20")
    assert result.maximum_unit_price == Decimal("20")
    assert result.last_receiving == LastReceiving(
        event_date=date(2026, 3, 10),
        unit_price=Decimal("20"),
        quantity=Decimal("100"),
        supplier_id=20,
        supplier_name="Supplier One",
        warehouse_id=30,
        warehouse_name="Main Warehouse",
        receiving_reference="REC-REF-001",
        event_id=1,
        line_id=101,
    )
    assert result.receiving_frequency.event_count == 1
    assert result.receiving_frequency.line_count == 1
    assert result.receiving_frequency.first_receiving_date == date(2026, 3, 10)
    assert result.receiving_frequency.last_receiving_date == date(2026, 3, 10)
    assert result.receiving_frequency.average_days_between_receipts is None

    assert len(result.monthly_totals) == 1
    assert result.monthly_totals[0] == MonthlyReceivingTotal(
        year=2026,
        month=3,
        event_count=1,
        line_count=1,
        total_quantity=Decimal("100"),
        total_subtotal=Decimal("2000"),
        average_unit_price=Decimal("20"),
    )


def test_multiple_eligible_lines():
    line1 = make_prepared_line(
        event_id=1,
        line_id=101,
        quantity=Decimal("50"),
        unit_price=Decimal("10"),
        subtotal=Decimal("500"),
    )
    line2 = make_prepared_line(
        event_id=2,
        line_id=102,
        quantity=Decimal("150"),
        unit_price=Decimal("30"),
        subtotal=Decimal("4500"),
    )
    result = analyze_receiving_history([line1, line2])

    assert result.examined_count == 2
    assert result.line_count == 2
    assert result.distinct_event_count == 2
    assert result.total_quantity == Decimal("200")
    assert result.total_subtotal == Decimal("5000")
    # Weighted avg price: 5000 / 200 = 25
    assert result.average_unit_price == Decimal("25")
    assert result.minimum_unit_price == Decimal("10")
    assert result.maximum_unit_price == Decimal("30")


def test_multiple_lines_belonging_to_one_event():
    line1 = make_prepared_line(
        event_id=1,
        line_id=101,
        line_number=1,
        quantity=Decimal("10"),
        unit_price=Decimal("5"),
        subtotal=Decimal("50"),
    )
    line2 = make_prepared_line(
        event_id=1,
        line_id=102,
        line_number=2,
        quantity=Decimal("20"),
        unit_price=Decimal("10"),
        subtotal=Decimal("200"),
    )
    result = analyze_receiving_history([line1, line2])

    assert result.line_count == 2
    assert result.distinct_event_count == 1
    assert result.total_quantity == Decimal("30")
    assert result.total_subtotal == Decimal("250")
    assert result.receiving_frequency.event_count == 1
    assert result.receiving_frequency.line_count == 2


def test_multiple_events():
    line1 = make_prepared_line(event_id=1, line_id=101, event_date=date(2026, 1, 5))
    line2 = make_prepared_line(event_id=2, line_id=102, event_date=date(2026, 1, 15))
    line3 = make_prepared_line(event_id=3, line_id=103, event_date=date(2026, 1, 25))

    result = analyze_receiving_history([line1, line2, line3])

    assert result.distinct_event_count == 3
    assert result.line_count == 3
    assert result.receiving_frequency.event_count == 3


def test_multiple_months_and_years():
    line1 = make_prepared_line(event_id=1, line_id=1, event_date=date(2025, 11, 1), quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100"))
    line2 = make_prepared_line(event_id=2, line_id=2, event_date=date(2025, 12, 1), quantity=Decimal("20"), unit_price=Decimal("15"), subtotal=Decimal("300"))
    line3 = make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 1), quantity=Decimal("30"), unit_price=Decimal("20"), subtotal=Decimal("600"))

    result = analyze_receiving_history([line3, line1, line2])  # pass out of order to verify sorting

    assert len(result.monthly_totals) == 3
    # Sorted year ASC, month ASC
    assert (result.monthly_totals[0].year, result.monthly_totals[0].month) == (2025, 11)
    assert (result.monthly_totals[1].year, result.monthly_totals[1].month) == (2025, 12)
    assert (result.monthly_totals[2].year, result.monthly_totals[2].month) == (2026, 1)

    assert result.monthly_totals[0].total_quantity == Decimal("10")
    assert result.monthly_totals[1].total_quantity == Decimal("20")
    assert result.monthly_totals[2].total_quantity == Decimal("30")


def test_weighted_average_unit_price():
    # 10 units at $10 = $100
    # 90 units at $20 = $1800
    # Total qty = 100, Total subtotal = 1900
    # Arithmetic avg would be 15, Weighted avg is 19.00
    line1 = make_prepared_line(event_id=1, line_id=1, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100"))
    line2 = make_prepared_line(event_id=2, line_id=2, quantity=Decimal("90"), unit_price=Decimal("20"), subtotal=Decimal("1800"))

    result = analyze_receiving_history([line1, line2])

    assert result.average_unit_price == Decimal("19")
    assert result.average_quantity_per_line == Decimal("50")


def test_min_and_max_price():
    line1 = make_prepared_line(event_id=1, line_id=1, unit_price=Decimal("12.50"))
    line2 = make_prepared_line(event_id=2, line_id=2, unit_price=Decimal("5.00"))
    line3 = make_prepared_line(event_id=3, line_id=3, unit_price=Decimal("45.00"))

    result = analyze_receiving_history([line1, line2, line3])

    assert result.minimum_unit_price == Decimal("5.00")
    assert result.maximum_unit_price == Decimal("45.00")


def test_receiving_frequency_with_multiple_distinct_dates():
    # Dates: 2026-03-01, 2026-03-11, 2026-03-21 (3 distinct dates, span = 20 days, intervals = 2 -> avg = 10 days)
    line1 = make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 3, 1))
    line2 = make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 3, 11))
    line3 = make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 3, 21))
    line4 = make_prepared_line(event_id=4, line_id=4, event_date=date(2026, 3, 21))  # duplicate date

    result = analyze_receiving_history([line1, line2, line3, line4])

    assert result.receiving_frequency.event_count == 4
    assert result.receiving_frequency.line_count == 4
    assert result.receiving_frequency.first_receiving_date == date(2026, 3, 1)
    assert result.receiving_frequency.last_receiving_date == date(2026, 3, 21)
    assert result.receiving_frequency.average_days_between_receipts == Decimal("10")


def test_receiving_frequency_with_only_one_distinct_date():
    line1 = make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 3, 1))
    line2 = make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 3, 1))

    result = analyze_receiving_history([line1, line2])

    assert result.receiving_frequency.first_receiving_date == date(2026, 3, 1)
    assert result.receiving_frequency.last_receiving_date == date(2026, 3, 1)
    assert result.receiving_frequency.average_days_between_receipts is None


def test_receiving_frequency_with_no_eligible_records():
    line_ineligible = make_prepared_line(event_id=1, line_id=1, eligible=False)

    result = analyze_receiving_history([line_ineligible])

    assert result.receiving_frequency.event_count == 0
    assert result.receiving_frequency.line_count == 0
    assert result.receiving_frequency.first_receiving_date is None
    assert result.receiving_frequency.last_receiving_date is None
    assert result.receiving_frequency.average_days_between_receipts is None


def test_last_receiving_selection():
    line_early = make_prepared_line(
        event_id=1,
        line_id=101,
        event_date=date(2026, 1, 10),
        receiving_reference="REC-01",
    )
    line_latest = make_prepared_line(
        event_id=2,
        line_id=102,
        event_date=date(2026, 5, 20),
        receiving_reference="REC-02",
        quantity=Decimal("88"),
        unit_price=Decimal("12"),
    )

    result = analyze_receiving_history([line_early, line_latest])

    assert result.last_receiving is not None
    assert result.last_receiving.event_date == date(2026, 5, 20)
    assert result.last_receiving.event_id == 2
    assert result.last_receiving.line_id == 102
    assert result.last_receiving.receiving_reference == "REC-02"
    assert result.last_receiving.quantity == Decimal("88")
    assert result.last_receiving.unit_price == Decimal("12")


def test_deterministic_last_receiving_tie_break():
    # Same date: tie break by (event_date, event_id, line_number, line_id)
    line1 = make_prepared_line(event_id=10, line_id=1, line_number=1, event_date=date(2026, 4, 1))
    line2 = make_prepared_line(event_id=10, line_id=2, line_number=2, event_date=date(2026, 4, 1))
    line3 = make_prepared_line(event_id=11, line_id=3, line_number=1, event_date=date(2026, 4, 1))

    result = analyze_receiving_history([line1, line2, line3])

    assert result.last_receiving is not None
    assert result.last_receiving.event_id == 11
    assert result.last_receiving.line_id == 3


def test_product_filter():
    line1 = make_prepared_line(event_id=1, line_id=1, product_id=201)
    line2 = make_prepared_line(event_id=2, line_id=2, product_id=202)

    result = analyze_receiving_history([line1, line2], filters=ReceivingHistoryFilter(product_id=201))

    assert result.examined_count == 1
    assert result.line_count == 1
    assert result.records[0].product_id == 201


def test_category_filter():
    line1 = make_prepared_line(event_id=1, line_id=1, category_id=51)
    line2 = make_prepared_line(event_id=2, line_id=2, category_id=52)

    result = analyze_receiving_history([line1, line2], filters=ReceivingHistoryFilter(category_id=51))

    assert result.examined_count == 1
    assert result.line_count == 1
    assert result.records[0].category_id == 51


def test_supplier_filter():
    line1 = make_prepared_line(event_id=1, line_id=1, supplier_id=21)
    line2 = make_prepared_line(event_id=2, line_id=2, supplier_id=22)

    result = analyze_receiving_history([line1, line2], filters=ReceivingHistoryFilter(supplier_id=21))

    assert result.examined_count == 1
    assert result.line_count == 1
    assert result.records[0].supplier_id == 21


def test_unit_filter():
    line1 = make_prepared_line(event_id=1, line_id=1, unit_id=301)
    line2 = make_prepared_line(event_id=2, line_id=2, unit_id=302)

    result = analyze_receiving_history([line1, line2], filters=ReceivingHistoryFilter(unit_id=301))

    assert result.examined_count == 1
    assert result.line_count == 1
    assert result.records[0].unit_id == 301


def test_company_filter():
    line1 = make_prepared_line(event_id=1, line_id=1, company_id=11)
    line2 = make_prepared_line(event_id=2, line_id=2, company_id=12)

    result = analyze_receiving_history([line1, line2], filters=ReceivingHistoryFilter(company_id=11))

    assert result.examined_count == 1
    assert result.line_count == 1
    assert result.records[0].company_id == 11


def test_warehouse_filter():
    line1 = make_prepared_line(event_id=1, line_id=1, warehouse_id=31)
    line2 = make_prepared_line(event_id=2, line_id=2, warehouse_id=32)

    result = analyze_receiving_history([line1, line2], filters=ReceivingHistoryFilter(warehouse_id=31))

    assert result.examined_count == 1
    assert result.line_count == 1
    assert result.records[0].warehouse_id == 31


def test_start_and_end_date_inclusive():
    line1 = make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 3, 1))
    line2 = make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 3, 15))
    line3 = make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 3, 31))
    line4 = make_prepared_line(event_id=4, line_id=4, event_date=date(2026, 4, 1))

    result = analyze_receiving_history(
        [line1, line2, line3, line4],
        filters=ReceivingHistoryFilter(start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)),
    )

    assert result.examined_count == 3
    assert [r.line_id for r in result.records] == [1, 2, 3]


def test_combined_filters():
    target = make_prepared_line(
        event_id=1,
        line_id=101,
        company_id=10,
        supplier_id=20,
        warehouse_id=30,
        product_id=200,
        category_id=50,
        unit_id=300,
        event_date=date(2026, 3, 15),
    )
    other = make_prepared_line(
        event_id=2,
        line_id=102,
        company_id=10,
        supplier_id=99,
        warehouse_id=30,
        product_id=200,
        category_id=50,
        unit_id=300,
        event_date=date(2026, 3, 15),
    )

    result = analyze_receiving_history(
        [target, other],
        filters=ReceivingHistoryFilter(
            company_id=10,
            supplier_id=20,
            warehouse_id=30,
            product_id=200,
            category_id=50,
            unit_id=300,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        ),
    )

    assert result.examined_count == 1
    assert result.records[0].line_id == 101


def test_ineligible_lines_excluded_from_metrics_but_retained_in_records():
    line_eligible = make_prepared_line(
        event_id=1,
        line_id=1,
        quantity=Decimal("50"),
        unit_price=Decimal("10"),
        subtotal=Decimal("500"),
        eligible=True,
    )
    line_ineligible = make_prepared_line(
        event_id=2,
        line_id=2,
        quantity=Decimal("100"),
        unit_price=Decimal("20"),
        subtotal=Decimal("2000"),
        eligible=False,
    )

    result = analyze_receiving_history([line_eligible, line_ineligible])

    # Examined records contains both
    assert result.examined_count == 2
    assert len(result.records) == 2
    assert result.data_quality.total_lines == 2
    assert result.data_quality.eligible_lines == 1
    assert result.data_quality.ineligible_lines == 1

    # Metrics only count the eligible line!
    assert result.line_count == 1
    assert result.distinct_event_count == 1
    assert result.total_quantity == Decimal("50")
    assert result.total_subtotal == Decimal("500")
    assert result.average_unit_price == Decimal("10")


def test_data_quality_counts_preserved():
    line1 = make_prepared_line(
        event_id=1,
        line_id=1,
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=False,
            has_product=True,
            has_quantity=True,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )
    line2 = make_prepared_line(
        event_id=2,
        line_id=2,
        eligibility_override=ReceivingAnalyticsEligibility(
            has_event_date=True,
            has_product=False,
            has_quantity=False,
            has_unit_price=True,
            has_supplier=True,
            has_warehouse=True,
        ),
    )

    result = analyze_receiving_history([line1, line2])

    assert result.data_quality.missing_date_count == 1
    assert result.data_quality.missing_product_count == 1
    assert result.data_quality.missing_quantity_count == 1
    assert result.data_quality.missing_price_count == 0
    assert result.data_quality.eligible_lines == 0
    assert result.data_quality.ineligible_lines == 2


def test_duplicate_operational_lines_not_deduplicated():
    line1 = make_prepared_line(event_id=1, line_id=101, line_number=1, quantity=Decimal("10"), subtotal=Decimal("100"))
    line2 = make_prepared_line(event_id=1, line_id=102, line_number=1, quantity=Decimal("10"), subtotal=Decimal("100"))

    result = analyze_receiving_history([line1, line2])

    assert result.line_count == 2
    assert result.distinct_event_count == 1
    assert result.total_quantity == Decimal("20")
    assert result.total_subtotal == Decimal("200")


def test_decimal_precision():
    q1 = Decimal("123.456789")
    p1 = Decimal("98.765432")
    s1 = q1 * p1
    line1 = make_prepared_line(event_id=1, line_id=1, quantity=q1, unit_price=p1, subtotal=s1)

    result = analyze_receiving_history([line1])

    assert isinstance(result.total_quantity, Decimal)
    assert isinstance(result.total_subtotal, Decimal)
    assert isinstance(result.average_unit_price, Decimal)
    assert result.total_quantity == q1
    assert result.total_subtotal == s1
    assert result.average_unit_price == p1


def test_input_and_output_immutability():
    line = make_prepared_line()
    result = analyze_receiving_history([line])

    with pytest.raises(FrozenInstanceError):
        result.total_quantity = Decimal("999")  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.filters.company_id = 999  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.receiving_frequency.event_count = 999  # type: ignore[misc]


def test_deterministic_ordering_of_records():
    line1 = make_prepared_line(event_id=2, line_id=20, event_date=date(2026, 3, 2), receiving_reference="REC-B")
    line2 = make_prepared_line(event_id=1, line_id=10, event_date=date(2026, 3, 1), receiving_reference="REC-A")
    line3 = make_prepared_line(event_id=1, line_id=11, event_date=date(2026, 3, 1), receiving_reference="REC-A")

    result = analyze_receiving_history([line1, line2, line3])

    # Expected order: (event_date, receiving_reference, event_id, line_number, line_id)
    assert [r.line_id for r in result.records] == [10, 11, 20]


def test_no_database_writes_or_session_requirement():
    # Pure in-memory invocation without database dependencies
    line = make_prepared_line()
    analytics = ReceivingHistoryAnalytics()
    res = analytics.analyze(records=[line])
    assert res.line_count == 1
