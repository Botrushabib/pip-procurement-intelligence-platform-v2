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
from app.services.receiving_price_intelligence import (
    ReceivingDataSufficiency,
    ReceivingPriceAnomalyAssessment,
    ReceivingPriceAnomalyStatus,
    ReceivingPriceChange,
    ReceivingPriceChangeStatus,
    ReceivingPriceConfidence,
    ReceivingPriceDataQuality,
    ReceivingPriceIntelligence,
    ReceivingPriceIntelligenceRequest,
    ReceivingPriceIntelligenceResult,
    ReceivingPriceObservation,
    ReceivingPriceTrend,
    analyze_receiving_price,
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


def test_01_empty_input():
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=[],
    )

    assert isinstance(result, ReceivingPriceIntelligenceResult)
    assert result.sufficiency == ReceivingDataSufficiency.INSUFFICIENT_DATA
    assert result.observations == ()
    assert result.observation_count == 0
    assert result.current_price is None
    assert result.current_price_source == "NONE"
    assert result.latest_observed_price is None
    assert result.previous_observed_price is None
    assert result.weighted_average_price is None
    assert result.arithmetic_average_price is None
    assert result.minimum_price is None
    assert result.maximum_price is None
    assert result.price_spread is None
    assert result.standard_deviation is None
    assert result.recent_average_price is None
    assert result.trend == ReceivingPriceTrend.INSUFFICIENT_DATA
    assert result.price_change.status == ReceivingPriceChangeStatus.UNAVAILABLE
    assert result.anomaly.status == ReceivingPriceAnomalyStatus.INSUFFICIENT_DATA
    assert result.confidence == ReceivingPriceConfidence.INSUFFICIENT_DATA
    assert result.data_quality.examined_lines == 0
    assert result.data_quality.analytics_eligible_lines == 0
    assert result.data_quality.comparable_lines == 0


def test_02_no_matching_product():
    line = make_prepared_line(product_id=201)
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=[line],
    )

    assert result.sufficiency == ReceivingDataSufficiency.INSUFFICIENT_DATA
    assert result.observation_count == 0
    assert result.data_quality.examined_lines == 1
    assert result.data_quality.analytics_eligible_lines == 1
    assert result.data_quality.comparable_lines == 0


def test_03_single_observation():
    line = make_prepared_line(
        event_id=1,
        line_id=101,
        product_id=200,
        unit_price=Decimal("50.00"),
        quantity=Decimal("10.00"),
        subtotal=Decimal("500.00"),
    )
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=[line],
    )

    assert result.sufficiency == ReceivingDataSufficiency.AVAILABLE
    assert result.observation_count == 1
    assert result.current_price == Decimal("50.00")
    assert result.current_price_source == "LATEST_RECEIPT"
    assert result.latest_observed_price == Decimal("50.00")
    assert result.previous_observed_price is None
    assert result.weighted_average_price == Decimal("50.00")
    assert result.arithmetic_average_price == Decimal("50.00")
    assert result.minimum_price == Decimal("50.00")
    assert result.maximum_price == Decimal("50.00")
    assert result.price_spread == Decimal("0.00")
    assert result.standard_deviation is None
    assert result.recent_average_price is None
    assert result.trend == ReceivingPriceTrend.INSUFFICIENT_DATA
    assert result.price_change.status == ReceivingPriceChangeStatus.UNAVAILABLE
    assert result.anomaly.status == ReceivingPriceAnomalyStatus.INSUFFICIENT_DATA
    assert result.confidence == ReceivingPriceConfidence.LOW


def test_04_multiple_observations():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 10), unit_price=Decimal("10"), quantity=Decimal("100"), subtotal=Decimal("1000")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 2, 10), unit_price=Decimal("20"), quantity=Decimal("100"), subtotal=Decimal("2000")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )

    assert result.observation_count == 2
    assert result.latest_observed_price == Decimal("20")
    assert result.previous_observed_price == Decimal("10")
    assert result.minimum_price == Decimal("10")
    assert result.maximum_price == Decimal("20")
    assert result.price_spread == Decimal("10")


def test_05_current_price_from_request():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 10), unit_price=Decimal("10")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 2, 10), unit_price=Decimal("12")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200, current_unit_price=Decimal("15.50")),
        records=lines,
    )

    assert result.current_price == Decimal("15.50")
    assert result.current_price_source == "REQUEST"
    assert result.latest_observed_price == Decimal("12")


def test_06_current_price_fallback_to_latest_receipt():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 10), unit_price=Decimal("10")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 2, 10), unit_price=Decimal("14")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )

    assert result.current_price == Decimal("14")
    assert result.current_price_source == "LATEST_RECEIPT"


def test_07_08_latest_receipt_baseline_exclusion_and_contamination_prevention():
    # 4 lines: 3 historical + 1 latest.
    # Historical baseline prices: 10, 10, 10 -> mean = 10, std = 0
    # Latest price: 100 (which is an extreme anomaly).
    # If the latest price is NOT excluded from baseline, mean = 32.5, std != 0 (contaminating baseline).
    # When excluded, baseline has exactly 3 obs (10, 10, 10), mean = 10, std = 0 -> anomaly ABOVE_EXPECTED_RANGE.
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("10")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("10")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 3), unit_price=Decimal("10")),
        make_prepared_line(event_id=4, line_id=4, event_date=date(2026, 1, 4), unit_price=Decimal("100")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )

    assert result.current_price == Decimal("100")
    assert result.current_price_source == "LATEST_RECEIPT"
    assert result.anomaly.reference_average == Decimal("10")
    assert result.anomaly.standard_deviation == Decimal("0")
    assert result.anomaly.status == ReceivingPriceAnomalyStatus.ABOVE_EXPECTED_RANGE


def test_09_normal_anomaly_with_request_price():
    # Baseline: 10, 20, 30 -> mean = 20, variance = (100 + 0 + 100)/3 = 66.666..., std = 8.1649...
    # Request price: 25 -> diff = 5 -> z = 5 / 8.1649 = 0.612 -> NORMAL
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("10")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("20")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 3), unit_price=Decimal("30")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200, current_unit_price=Decimal("25")),
        records=lines,
    )

    assert result.anomaly.status == ReceivingPriceAnomalyStatus.NORMAL
    assert result.anomaly.z_score is not None
    assert Decimal("0.60") < result.anomaly.z_score < Decimal("0.63")


def test_10_above_range_anomaly():
    # Baseline: 10, 10, 12, 10 -> mean = 10.5, std ~ 0.866
    # Request price: 50 -> z >> 2 -> ABOVE_EXPECTED_RANGE
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("10")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("10")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 3), unit_price=Decimal("12")),
        make_prepared_line(event_id=4, line_id=4, event_date=date(2026, 1, 4), unit_price=Decimal("10")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200, current_unit_price=Decimal("50")),
        records=lines,
    )

    assert result.anomaly.status == ReceivingPriceAnomalyStatus.ABOVE_EXPECTED_RANGE
    assert result.anomaly.z_score is not None
    assert result.anomaly.z_score >= Decimal("2.0")


def test_11_below_range_anomaly():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("105")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 3), unit_price=Decimal("95")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200, current_unit_price=Decimal("10")),
        records=lines,
    )

    assert result.anomaly.status == ReceivingPriceAnomalyStatus.BELOW_EXPECTED_RANGE
    assert result.anomaly.z_score is not None
    assert result.anomaly.z_score <= Decimal("-2.0")


def test_12_zero_variance_baseline():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("50")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("50")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 3), unit_price=Decimal("50")),
    ]
    # Current price identical
    res_same = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200, current_unit_price=Decimal("50")),
        records=lines,
    )
    assert res_same.anomaly.status == ReceivingPriceAnomalyStatus.NORMAL
    assert res_same.anomaly.standard_deviation == Decimal("0")
    assert res_same.anomaly.z_score is None

    # Current price below identical baseline
    res_below = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200, current_unit_price=Decimal("40")),
        records=lines,
    )
    assert res_below.anomaly.status == ReceivingPriceAnomalyStatus.BELOW_EXPECTED_RANGE
    assert res_below.anomaly.z_score is None


def test_13_trend_increasing():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("10")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("12")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 3), unit_price=Decimal("15")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )
    assert result.trend == ReceivingPriceTrend.INCREASING


def test_14_trend_decreasing():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("30")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("25")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 3), unit_price=Decimal("20")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )
    assert result.trend == ReceivingPriceTrend.DECREASING


def test_15_trend_stable_within_1_percent():
    # Mean = 100. Diff = 100.5 - 99.8 = 0.7 <= 1% of 100 -> STABLE
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("99.8")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("100.5")),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 3), unit_price=Decimal("100.2")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )
    assert result.trend == ReceivingPriceTrend.STABLE


def test_16_trend_insufficient_data():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("10")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("12")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )
    assert result.trend == ReceivingPriceTrend.INSUFFICIENT_DATA


def test_17_18_weighted_and_arithmetic_average():
    # Line 1: 10 qty at 10.00 = 100
    # Line 2: 90 qty at 20.00 = 1800
    # Weighted avg = 1900 / 100 = 19.00
    # Arithmetic avg = (10 + 20) / 2 = 15.00
    lines = [
        make_prepared_line(event_id=1, line_id=1, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, quantity=Decimal("90"), unit_price=Decimal("20"), subtotal=Decimal("1800")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )

    assert result.weighted_average_price == Decimal("19")
    assert result.arithmetic_average_price == Decimal("15")


def test_19_20_21_price_extremes_and_spread():
    lines = [
        make_prepared_line(event_id=1, line_id=1, unit_price=Decimal("15.50")),
        make_prepared_line(event_id=2, line_id=2, unit_price=Decimal("4.50")),
        make_prepared_line(event_id=3, line_id=3, unit_price=Decimal("29.00")),
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=lines,
    )

    assert result.minimum_price == Decimal("4.50")
    assert result.maximum_price == Decimal("29.00")
    assert result.price_spread == Decimal("24.50")


def test_22_23_population_standard_deviation_and_zscore_precision():
    # Prices: 2, 4, 4, 4, 5, 5, 7, 9
    # Count = 8, Mean = 40 / 8 = 5.0
    # Diff sq: 9 + 1 + 1 + 1 + 0 + 0 + 4 + 16 = 32
    # Variance = 32 / 8 = 4.0
    # Pop Std Dev = 2.0
    prices = [Decimal("2"), Decimal("4"), Decimal("4"), Decimal("4"), Decimal("5"), Decimal("5"), Decimal("7"), Decimal("9")]
    lines = [
        make_prepared_line(event_id=i, line_id=i, event_date=date(2026, 1, i), unit_price=p)
        for i, p in enumerate(prices, start=1)
    ]
    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200, current_unit_price=Decimal("9")),
        records=lines,
    )

    assert result.standard_deviation == Decimal("2")
    # z_score = (9 - 5) / 2 = 2.0
    assert result.anomaly.z_score == Decimal("2")
    assert result.anomaly.status == ReceivingPriceAnomalyStatus.ABOVE_EXPECTED_RANGE


def test_24_25_price_change_positive_and_negative():
    lines_pos = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("125")),
    ]
    res_pos = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=lines_pos)
    assert res_pos.price_change.status == ReceivingPriceChangeStatus.AVAILABLE
    assert res_pos.price_change.previous_price == Decimal("100")
    assert res_pos.price_change.current_price == Decimal("125")
    assert res_pos.price_change.absolute_change == Decimal("25")
    assert res_pos.price_change.percentage_change == Decimal("25")

    lines_neg = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("100")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("80")),
    ]
    res_neg = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=lines_neg)
    assert res_neg.price_change.status == ReceivingPriceChangeStatus.AVAILABLE
    assert res_neg.price_change.absolute_change == Decimal("-20")
    assert res_neg.price_change.percentage_change == Decimal("-20")


def test_26_previous_price_zero():
    lines = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1), unit_price=Decimal("0")),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 2), unit_price=Decimal("10")),
    ]
    result = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=lines)

    assert result.price_change.status == ReceivingPriceChangeStatus.UNAVAILABLE
    assert result.price_change.previous_price == Decimal("0")
    assert result.price_change.current_price == Decimal("10")
    assert result.price_change.absolute_change == Decimal("10")
    assert result.price_change.percentage_change is None


def test_27_no_previous_price():
    lines = [make_prepared_line(event_id=1, line_id=1, unit_price=Decimal("10"))]
    result = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=lines)

    assert result.price_change.status == ReceivingPriceChangeStatus.UNAVAILABLE
    assert result.price_change.previous_price is None


def test_28_29_30_31_confidence_levels():
    # INSUFFICIENT_DATA (0 obs)
    r0 = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=[])
    assert r0.confidence == ReceivingPriceConfidence.INSUFFICIENT_DATA

    # LOW (1-2 obs)
    r1 = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=[make_prepared_line()])
    assert r1.confidence == ReceivingPriceConfidence.LOW

    # MEDIUM (3-4 obs)
    lines_med = [make_prepared_line(event_id=i, line_id=i, event_date=date(2026, 1, i)) for i in range(1, 4)]
    r_med = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=lines_med)
    assert r_med.confidence == ReceivingPriceConfidence.MEDIUM

    # HIGH (>=5 obs and >=2 distinct calendar months)
    lines_high = [
        make_prepared_line(event_id=1, line_id=1, event_date=date(2026, 1, 1)),
        make_prepared_line(event_id=2, line_id=2, event_date=date(2026, 1, 15)),
        make_prepared_line(event_id=3, line_id=3, event_date=date(2026, 1, 20)),
        make_prepared_line(event_id=4, line_id=4, event_date=date(2026, 2, 1)),
        make_prepared_line(event_id=5, line_id=5, event_date=date(2026, 2, 10)),
    ]
    r_high = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=lines_high)
    assert r_high.confidence == ReceivingPriceConfidence.HIGH

    # 5 obs in single month -> MEDIUM
    lines_single_month = [
        make_prepared_line(event_id=i, line_id=i, event_date=date(2026, 1, i))
        for i in range(1, 6)
    ]
    r_single_month = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=lines_single_month)
    assert r_single_month.confidence == ReceivingPriceConfidence.MEDIUM


def test_32_33_multi_line_and_duplicate_preservation():
    # Multiple lines in same event & duplicate lines
    line1 = make_prepared_line(event_id=1, line_id=101, line_number=1, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100"))
    line2 = make_prepared_line(event_id=1, line_id=102, line_number=2, quantity=Decimal("10"), unit_price=Decimal("10"), subtotal=Decimal("100"))

    result = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=[line1, line2])

    assert result.observation_count == 2
    assert result.weighted_average_price == Decimal("10")
    assert result.arithmetic_average_price == Decimal("10")


def test_34_to_42_filters():
    line_target = make_prepared_line(
        event_id=1,
        line_id=101,
        product_id=200,
        unit_id=300,
        supplier_id=20,
        company_id=10,
        warehouse_id=30,
        event_date=date(2026, 3, 15),
        receiving_reference="REC-TARGET",
    )
    line_other = make_prepared_line(
        event_id=2,
        line_id=102,
        product_id=200,
        unit_id=301,
        supplier_id=99,
        company_id=99,
        warehouse_id=99,
        event_date=date(2026, 5, 1),
        receiving_reference="REC-OTHER",
    )

    # Combined filter
    req = ReceivingPriceIntelligenceRequest(
        product_id=200,
        unit_id=300,
        supplier_id=20,
        company_id=10,
        warehouse_id=30,
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        reference="REC-TARGET",
    )
    result = analyze_receiving_price(req, records=[line_target, line_other])

    assert result.observation_count == 1
    assert result.observations[0].line_id == 101


def test_43_44_45_ineligible_lines_retention_and_exclusion():
    line_valid = make_prepared_line(event_id=1, line_id=1, unit_price=Decimal("20"), eligible=True)
    line_invalid = make_prepared_line(event_id=2, line_id=2, unit_price=Decimal("100"), eligible=False)

    result = analyze_receiving_price(
        ReceivingPriceIntelligenceRequest(product_id=200),
        records=[line_valid, line_invalid],
    )

    assert result.data_quality.examined_lines == 2
    assert result.data_quality.analytics_eligible_lines == 1
    assert result.data_quality.comparable_lines == 1
    assert result.observation_count == 1
    assert result.current_price == Decimal("20")


def test_46_decimal_precision():
    p1 = Decimal("123.456789")
    q1 = Decimal("98.765432")
    s1 = p1 * q1
    line = make_prepared_line(unit_price=p1, quantity=q1, subtotal=s1)

    result = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=[line])

    assert isinstance(result.current_price, Decimal)
    assert isinstance(result.weighted_average_price, Decimal)
    assert isinstance(result.arithmetic_average_price, Decimal)
    assert result.current_price == p1
    assert result.weighted_average_price == p1


def test_47_48_immutability_and_input_non_mutation():
    line = make_prepared_line()
    orig_price = line.unit_price
    result = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=[line])

    assert line.unit_price == orig_price
    with pytest.raises(FrozenInstanceError):
        result.current_price = Decimal("999")  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.trend = ReceivingPriceTrend.INCREASING  # type: ignore[misc]


def test_49_deterministic_ordering():
    l1 = make_prepared_line(event_id=2, line_id=20, line_number=1, event_date=date(2026, 3, 2))
    l2 = make_prepared_line(event_id=1, line_id=10, line_number=2, event_date=date(2026, 3, 1))
    l3 = make_prepared_line(event_id=1, line_id=11, line_number=1, event_date=date(2026, 3, 1))

    result = analyze_receiving_price(ReceivingPriceIntelligenceRequest(product_id=200), records=[l1, l2, l3])

    # Sorted by (event_date, event_id, line_number, line_id)
    assert [obs.line_id for obs in result.observations] == [11, 10, 20]


def test_50_read_only_behavior():
    line = make_prepared_line()
    service = ReceivingPriceIntelligence()
    res = service.analyze(ReceivingPriceIntelligenceRequest(product_id=200), records=[line])
    assert res.observation_count == 1
    assert isinstance(res.observations, tuple)
