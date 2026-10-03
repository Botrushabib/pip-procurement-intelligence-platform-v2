from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
import inspect

import pytest

from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ReceivingAnalyticsEligibility,
)
from app.services.receiving_trend_intelligence import (
    ReceivingTrendIntelligence,
    ReceivingTrendRequest,
)


def line(
    *,
    event_id=1,
    line_id=1,
    line_number=1,
    event_date=date(2026, 1, 15),
    company_id=10,
    warehouse_id=20,
    supplier_id=30,
    product_id=40,
    category_id=50,
    unit_id=60,
    quantity=Decimal("10"),
    unit_price=Decimal("5"),
    subtotal=Decimal("50"),
    reference="REC-001",
    eligible=True,
):
    eligibility = ReceivingAnalyticsEligibility(
        has_event_date=event_date is not None,
        has_product=product_id is not None and product_id > 0,
        has_quantity=quantity is not None and quantity > 0,
        has_unit_price=unit_price is not None and unit_price >= 0,
        has_supplier=supplier_id is not None and supplier_id > 0,
        has_warehouse=warehouse_id is not None and warehouse_id > 0,
    )
    if not eligible:
        eligibility = ReceivingAnalyticsEligibility(False, True, True, True, True, True)
    return PreparedReceivingEventLine(
        event_id=event_id,
        line_id=line_id,
        line_number=line_number,
        event_date=event_date,
        year=event_date.year if event_date else None,
        month=event_date.month if event_date else None,
        receiving_reference=reference,
        company_id=company_id,
        company_name=None,
        supplier_id=supplier_id,
        supplier_name=None,
        warehouse_id=warehouse_id,
        warehouse_name=None,
        product_id=product_id,
        product_code=None,
        product_name=None,
        category_id=category_id,
        category_name=None,
        unit_id=unit_id,
        unit_name=None,
        quantity=quantity,
        unit_price=unit_price,
        subtotal=subtotal,
        source_file="source.xlsx",
        source_sheet="Sheet1",
        source_row=2,
        eligibility=eligibility,
    )


def analyze(records, request=None):
    return ReceivingTrendIntelligence().analyze(
        request or ReceivingTrendRequest(), records
    )


def test_empty_input_and_direct_architecture():
    result = analyze([])
    assert result.observations == ()
    assert result.monthly_trends == ()
    assert result.product_monthly_trends == ()
    assert result.supplier_monthly_trends == ()
    assert result.category_monthly_trends == ()
    assert result.quality.examined_lines == 0
    assert result.quality.analytics_eligible_lines == 0
    source = inspect.getsource(__import__(
        "app.services.receiving_trend_intelligence", fromlist=["x"]
    ))
    assert "Session" not in source
    assert "SessionLocal" not in source
    assert "ReceivingEventQueryService" not in source
    assert "ReceivingEventAnalyticsPreparation" not in source


def test_filters_and_normalized_reference_are_applied_inclusively():
    target = line(reference="  rec   alpha ", event_date=date(2026, 2, 1))
    other = line(event_id=2, line_id=2, company_id=99)
    request = ReceivingTrendRequest(
        company_id=10, warehouse_id=20, supplier_id=30, product_id=40,
        category_id=50, unit_id=60, date_from=date(2026, 2, 1),
        date_to=date(2026, 2, 1), reference="REC ALPHA",
    )
    result = analyze([target, other], request)
    assert len(result.observations) == 1
    assert result.observations[0].event_id == 1


@pytest.mark.parametrize(
    ("request_kwargs", "nonmatching_kwargs"),
    [
        pytest.param({"company_id": 10}, {"company_id": 99}, id="company_id"),
        pytest.param({"warehouse_id": 20}, {"warehouse_id": 99}, id="warehouse_id"),
        pytest.param({"supplier_id": 30}, {"supplier_id": 99}, id="supplier_id"),
        pytest.param({"product_id": 40}, {"product_id": 99}, id="product_id"),
        pytest.param({"category_id": 50}, {"category_id": 99}, id="category_id"),
        pytest.param({"unit_id": 60}, {"unit_id": 99}, id="unit_id"),
        pytest.param(
            {"date_from": date(2026, 1, 15)},
            {"event_date": date(2026, 1, 14)},
            id="date_from",
        ),
        pytest.param(
            {"date_to": date(2026, 1, 15)},
            {"event_date": date(2026, 1, 16)},
            id="date_to",
        ),
        pytest.param(
            {"reference": "REC-001"}, {"reference": "REC-OTHER"}, id="reference"
        ),
    ],
)
def test_each_filter_independently_excludes_nonmatching_records(
    request_kwargs, nonmatching_kwargs
):
    target = line(event_id=1, line_id=1)
    nonmatching = line(event_id=2, line_id=2, **nonmatching_kwargs)

    result = analyze([target, nonmatching], ReceivingTrendRequest(**request_kwargs))

    assert [observation.event_id for observation in result.observations] == [1]


def test_eligibility_and_independent_quality_counters():
    invalid = line(
        event_id=2, supplier_id=0, product_id=0, category_id=0, unit_id=0,
        warehouse_id=0, quantity=Decimal("0"), unit_price=Decimal("-1"),
    )
    missing_date = line(event_id=3, event_date=None)
    ineligible = line(event_id=4, eligible=False)
    result = analyze([invalid, missing_date, ineligible])
    assert result.observations == ()
    assert result.quality.examined_lines == 3
    assert result.quality.analytics_eligible_lines == 0
    assert result.quality.missing_supplier == 1
    assert result.quality.missing_product == 1
    assert result.quality.missing_category == 1
    assert result.quality.missing_unit == 1
    assert result.quality.missing_event_date == 1
    assert result.quality.missing_quantity == 1
    assert result.quality.missing_unit_price == 1


def test_monthly_aggregation_and_period_changes_use_decimal():
    records = [
        line(event_id=1, line_id=1, event_date=date(2026, 1, 1), quantity=Decimal("10"), unit_price=Decimal("5"), subtotal=Decimal("50")),
        line(event_id=2, line_id=2, event_date=date(2026, 1, 20), quantity=Decimal("20"), unit_price=Decimal("7"), subtotal=Decimal("140")),
        line(event_id=3, line_id=3, event_date=date(2026, 2, 1), quantity=Decimal("60"), unit_price=Decimal("10"), subtotal=Decimal("600")),
    ]
    result = analyze(records)
    january, february = result.monthly_trends
    assert january.observation_count == 2
    assert january.total_quantity == Decimal("30")
    assert january.total_spend == Decimal("190")
    assert january.weighted_average_price == Decimal("19") / Decimal("3")
    assert january.arithmetic_average_price == Decimal("6")
    assert january.minimum_price == Decimal("5")
    assert january.maximum_price == Decimal("7")
    assert january.price_spread == Decimal("2")
    assert january.distinct_receiving_dates == 2
    assert february.quantity_change == Decimal("30")
    assert february.quantity_change_pct == Decimal("100")
    assert february.spend_change == Decimal("410")
    assert february.spend_change_pct == Decimal("215.7894736842105263157894737")
    assert february.price_change == Decimal("10") - Decimal("19") / Decimal("3")
    assert isinstance(february.price_change, Decimal)


def test_product_units_supplier_category_grouping_and_duplicates():
    records = [
        line(event_id=1, line_id=1, product_id=40, unit_id=60, supplier_id=30, category_id=50),
        line(event_id=1, line_id=2, product_id=40, unit_id=60, supplier_id=30, category_id=50),
        line(event_id=2, line_id=3, product_id=40, unit_id=61, supplier_id=31, category_id=51),
    ]
    result = analyze(records)
    assert len(result.observations) == 3
    assert [(x.product_id, x.unit_id) for x in result.product_monthly_trends] == [(40, 60), (40, 61)]
    assert result.product_monthly_trends[0].observation_count == 2
    assert result.supplier_monthly_trends[0].distinct_products == 1
    assert result.supplier_monthly_trends[0].distinct_receiving_dates == 1
    assert result.category_monthly_trends[0].distinct_products == 1
    assert result.category_monthly_trends[0].distinct_suppliers == 1


def test_period_first_month_and_previous_zero_percentages_are_none():
    records = [
        line(event_id=1, event_date=date(2026, 1, 1), quantity=Decimal("1"), unit_price=Decimal("0"), subtotal=Decimal("0")),
        line(event_id=2, event_date=date(2026, 2, 1), quantity=Decimal("2"), unit_price=Decimal("1"), subtotal=Decimal("2")),
    ]
    january, february = analyze(records).monthly_trends
    assert january.quantity_change is None
    assert february.spend_change_pct is None
    assert february.price_change_pct is None


def test_ordering_immutability_and_input_preservation():
    records = [
        line(event_id=2, line_id=20, event_date=date(2026, 2, 1)),
        line(event_id=1, line_id=10, event_date=date(2026, 1, 1)),
    ]
    original = tuple(records)
    result = analyze(records)
    assert records == list(original)
    assert [item.event_id for item in result.observations] == [1, 2]
    assert isinstance(result.observations, tuple)
    assert isinstance(result.monthly_trends, tuple)
    with pytest.raises(FrozenInstanceError):
        result.observations[0].event_id = 99  # type: ignore[misc]
