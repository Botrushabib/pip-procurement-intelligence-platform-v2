from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.purchase_history_analytics import PurchaseHistoryAnalytics
from app.services.seasonality_engine import (
    ComparisonStatus,
    ObservedPattern,
    SeasonalEvidence,
    SeasonalityEngine,
    SeasonalityRequest,
)
from tests.test_analytics_preparation import make_transaction


class ReadOnlySession:
    def __init__(self, transactions):
        self.transactions = transactions
        self.statements = []
        self.closed = False

    def scalars(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: self.transactions)

    def close(self):
        self.closed = True


def engine_for(*transactions):
    session = ReadOnlySession(list(transactions))
    history = PurchaseHistoryAnalytics(session_factory=lambda: session)
    return SeasonalityEngine(history), session


def transaction(transaction_id, year, month, quantity, price, **changes):
    return make_transaction(
        id=transaction_id,
        transaction_date=date(year, month, 15),
        quantity=Decimal(str(quantity)),
        unit_price=Decimal(str(price)),
        subtotal=Decimal(str(quantity)) * Decimal(str(price)),
        **changes,
    )


def test_empty_and_single_month_history_expose_coverage_without_seasonal_claims():
    empty, _ = engine_for()
    single, _ = engine_for(transaction(10, 2026, 8, 10, 5))

    assert empty.analyze().monthly_patterns == ()
    assert empty.analyze().seasonal_evidence is SeasonalEvidence.INSUFFICIENT_HISTORY
    result = single.analyze()
    assert result.coverage.observed_year_months == ("2026-08",)
    assert result.observed_pattern is ObservedPattern.INSUFFICIENT_DATA
    assert result.seasonal_evidence is SeasonalEvidence.INSUFFICIENT_HISTORY


def test_monthly_metrics_and_observed_product_pattern_are_decimal_safe():
    july_one = transaction(10, 2026, 7, "2.5", "10")
    july_two = transaction(11, 2026, 7, "3.5", "14")
    august = transaction(12, 2026, 8, "8", "15")
    engine, _ = engine_for(august, july_two, july_one)

    result = engine.analyze(SeasonalityRequest(product_id=7))

    july, august_pattern = result.monthly_patterns
    assert (july.year_month, july.transaction_count, july.total_quantity, july.total_purchase_value) == ("2026-07", 2, Decimal("6.0"), Decimal("74.0"))
    assert (july.average_quantity, july.average_unit_price, july.minimum_unit_price, july.maximum_unit_price) == (Decimal("3.0"), Decimal("12"), Decimal("10"), Decimal("14"))
    assert (august_pattern.total_quantity, august_pattern.month_over_month.absolute_quantity_change) == (Decimal("8"), Decimal("2.0"))
    assert august_pattern.month_over_month.percentage_quantity_change == Decimal("33.33333333333333333333333333")
    assert result.observed_pattern is ObservedPattern.INCREASING


def test_mixed_units_are_separate_and_never_converted():
    kilograms = transaction(10, 2026, 7, 100, 5, unit_id=3)
    boxes = transaction(11, 2026, 7, 10, 50, unit_id=99)
    engine, _ = engine_for(kilograms, boxes)

    result = engine.analyze()

    assert result.mixed_units is True
    assert [(pattern.unit_id, pattern.total_quantity) for pattern in result.monthly_patterns] == [(3, Decimal("100")), (99, Decimal("10"))]


def test_missing_month_is_not_zero_and_zero_previous_quantity_has_no_percentage():
    june = transaction(10, 2026, 6, 10, 5)
    august = transaction(11, 2026, 8, 20, 5)
    zero_july = transaction(12, 2026, 7, 0, 5)
    engine, _ = engine_for(june, august)
    zero_engine, _ = engine_for(zero_july, august)

    result = engine.analyze(SeasonalityRequest(date_from=date(2026, 6, 1), date_to=date(2026, 8, 31)))
    zero_result = zero_engine.analyze()

    assert result.monthly_patterns[-1].month_over_month.status is ComparisonStatus.UNAVAILABLE
    assert result.coverage.inactive_year_months == ("2026-07",)
    assert zero_result.monthly_patterns[-1].month_over_month.status is ComparisonStatus.UNAVAILABLE
    assert zero_result.monthly_patterns[-1].month_over_month.percentage_quantity_change is None


def test_pattern_classification_and_year_over_year_evidence_are_conservative():
    decreasing, _ = engine_for(transaction(10, 2026, 6, 8, 5), transaction(11, 2026, 7, 4, 5))
    stable, _ = engine_for(transaction(10, 2026, 6, 5, 5), transaction(11, 2026, 7, 5, 5))
    variable, _ = engine_for(transaction(10, 2026, 6, 5, 5), transaction(11, 2026, 7, 8, 5), transaction(12, 2026, 8, 6, 5))
    years, _ = engine_for(transaction(10, 2025, 8, 10, 5), transaction(11, 2026, 8, 15, 6))

    assert decreasing.analyze().observed_pattern is ObservedPattern.DECREASING
    assert stable.analyze().observed_pattern is ObservedPattern.STABLE
    assert variable.analyze().observed_pattern is ObservedPattern.VARIABLE
    result = years.analyze()
    assert result.seasonal_evidence is SeasonalEvidence.REPEATED_PATTERN
    assert result.year_over_year_comparisons[0].quantity_change == Decimal("5")
    assert result.year_over_year_comparisons[0].average_price_change == Decimal("1")


def test_normalized_category_supplier_and_location_filters_apply_to_monthly_patterns():
    matching = transaction(10, 2026, 8, 10, 5, destination_type="WAREHOUSE")
    other = transaction(11, 2026, 7, 100, 50, supplier_id=5, category_id=99, warehouse_id=99, destination_type="BRANCH")
    engine, _ = engine_for(matching, other)

    result = engine.analyze(SeasonalityRequest(product_id=7, category_id=2, supplier_id=4, unit_id=3, company_id=1, branch_id=5, warehouse_id=6, destination_type="WAREHOUSE", sub_warehouse_name="Cold Storage", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)))

    assert len(result.monthly_patterns) == 1
    assert result.monthly_patterns[0].year_month == "2026-08"


def test_data_quality_raw_preservation_determinism_and_select_only_behavior():
    valid = transaction(10, 2026, 8, 10, 5)
    missing_price = make_transaction(id=11, transaction_date=date(2026, 8, 15), unit_price=None)
    raw_values = (valid.supplier_raw, valid.product_raw, valid.destination_raw, valid.unit_raw)
    engine, session = engine_for(valid, missing_price)

    first = engine.analyze()
    second = engine.analyze()

    assert first == second
    assert first.data_quality.missing_price_count == 1
    assert raw_values == (valid.supplier_raw, valid.product_raw, valid.destination_raw, valid.unit_raw)
    assert session.closed is True
    statement = str(session.statements[0]).upper()
    assert statement.startswith("SELECT")
    assert all(keyword not in statement for keyword in ("INSERT", "UPDATE", "DELETE"))