from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.price_intelligence import (
    DataSufficiency,
    PriceAnomalyStatus,
    PriceChangeStatus,
    PriceConfidence,
    PriceIntelligenceEngine,
    PriceIntelligenceRequest,
    PriceTrend,
)
from app.services.purchase_history_analytics import PurchaseHistoryAnalytics
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
    return PriceIntelligenceEngine(history), session


def request(**changes):
    values = {"product_id": 7}
    values.update(changes)
    return PriceIntelligenceRequest(**values)


def transactions_for_prices(*prices):
    return tuple(
        make_transaction(
            id=index + 10,
            transaction_date=date(2026, 1, index + 1),
            unit_price=Decimal(str(price)),
            subtotal=Decimal(str(price)) * Decimal("2.5"),
        )
        for index, price in enumerate(prices)
    )


def test_empty_and_single_history_return_explicit_insufficient_states():
    empty, _ = engine_for()
    single, _ = engine_for(*transactions_for_prices("10"))

    empty_result = empty.analyze(request())
    single_result = single.analyze(request())

    assert empty_result.comparable_transaction_count == 0
    assert empty_result.average_price is None
    assert empty_result.confidence is PriceConfidence.INSUFFICIENT_DATA
    assert single_result.last_purchase_price == Decimal("10")
    assert single_result.recent_average_status is DataSufficiency.INSUFFICIENT_DATA
    assert single_result.volatility_status is DataSufficiency.INSUFFICIENT_DATA
    assert single_result.trend is PriceTrend.INSUFFICIENT_DATA
    assert single_result.price_change.status is PriceChangeStatus.UNAVAILABLE


def test_price_metrics_history_context_and_recent_average_are_decimal_safe():
    engine, _ = engine_for(*transactions_for_prices("10.125", "12.375", "14.625"))

    result = engine.analyze(request())

    assert [observation.unit_price for observation in result.observations] == [Decimal("10.125"), Decimal("12.375"), Decimal("14.625")]
    assert (result.minimum_price, result.maximum_price, result.price_range) == (Decimal("10.125"), Decimal("14.625"), Decimal("4.500"))
    assert (result.average_price, result.median_price, result.recent_average_price) == (Decimal("12.375"), Decimal("12.375"), Decimal("12.375"))
    assert result.last_purchase_date == date(2026, 1, 3)
    assert result.last_purchase_price == Decimal("14.625")
    assert result.last_supplier_name == "Supplier A"
    assert result.observations[-1].source_file == "purchases.xlsx"
    assert result.price_change == result.price_change.__class__(PriceChangeStatus.AVAILABLE, Decimal("12.375"), Decimal("14.625"), Decimal("2.250"), Decimal("18.18181818181818181818181818"), "Change compares the two most recent comparable purchases.")
    assert result.recent_average_status is DataSufficiency.AVAILABLE
    assert result.volatility_status is DataSufficiency.AVAILABLE


def test_trends_and_confidence_use_documented_deterministic_thresholds():
    increasing, _ = engine_for(*transactions_for_prices(1, 2, 3, 4, 5, 6, 7, 8))
    decreasing, _ = engine_for(*transactions_for_prices(8, 7, 6, 5, 4, 3))
    stable, _ = engine_for(*transactions_for_prices(5, 5, 5, 5, 5, 5))

    assert increasing.analyze(request()).trend is PriceTrend.INCREASING
    assert increasing.analyze(request()).confidence is PriceConfidence.MEDIUM
    assert decreasing.analyze(request()).trend is PriceTrend.DECREASING
    assert stable.analyze(request()).trend is PriceTrend.STABLE


def test_anomaly_assessment_is_explainable_and_requires_history():
    engine, _ = engine_for(*transactions_for_prices(110, 112, 114, 116, 118))

    anomalous = engine.analyze(request(current_unit_price=Decimal("150"))).anomaly
    normal = engine.analyze(request(current_unit_price=Decimal("114"))).anomaly
    insufficient, _ = engine_for(*transactions_for_prices(110, 112))

    assert anomalous.status is PriceAnomalyStatus.ABOVE_EXPECTED_RANGE
    assert anomalous.current_price == Decimal("150")
    assert anomalous.reference_average == Decimal("114")
    assert anomalous.difference == Decimal("36")
    assert anomalous.z_score is not None
    assert "z-score" in anomalous.method
    assert normal.status is PriceAnomalyStatus.NORMAL
    assert insufficient.analyze(request(current_unit_price=Decimal("150"))).anomaly.status is PriceAnomalyStatus.INSUFFICIENT_DATA


def test_same_product_with_different_units_is_not_compared_without_a_unit_filter():
    kilograms = make_transaction(id=10, unit_id=3, unit_price=Decimal("10"))
    boxes = make_transaction(id=11, unit_id=99, unit_price=Decimal("100"))
    engine, _ = engine_for(kilograms, boxes)

    unresolved = engine.analyze(request())
    kilograms_only = engine.analyze(request(unit_id=3))

    assert unresolved.comparable_transaction_count == 0
    assert unresolved.data_quality.different_unit_excluded_count == 2
    assert kilograms_only.comparable_transaction_count == 1
    assert kilograms_only.average_price == Decimal("10")
    assert kilograms_only.data_quality.different_unit_excluded_count == 1


def test_different_product_and_reference_are_not_used_as_price_identity():
    expected = make_transaction(id=10, reference="PO-A", unit_price=Decimal("10"))
    different_product = make_transaction(id=11, product_id=8, reference="PO-A", unit_price=Decimal("100"))
    different_reference = make_transaction(id=12, reference="PO-B", unit_price=Decimal("200"))
    engine, _ = engine_for(expected, different_product, different_reference)

    result = engine.analyze(request(reference="PO-A"))

    assert result.comparable_transaction_count == 1
    assert result.average_price == Decimal("10")
    assert result.data_quality.reference_excluded_count == 1


def test_supplier_location_and_date_filters_use_existing_history_dimensions():
    matching = make_transaction(transaction_date=date(2026, 8, 15), destination_type="WAREHOUSE")
    other = make_transaction(id=9, transaction_date=date(2026, 7, 15), supplier_id=90, warehouse_id=99, destination_type="BRANCH")
    engine, _ = engine_for(matching, other)

    result = engine.analyze(
        request(
            supplier_id=4,
            branch_id=5,
            warehouse_id=6,
            destination_type="WAREHOUSE",
            sub_warehouse_name="Cold Storage",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
        )
    )

    assert result.comparable_transaction_count == 1
    assert result.observations[0].transaction_id == 8


def test_same_date_tie_breaking_is_stable_and_previous_zero_has_no_percentage_change():
    first = make_transaction(id=10, transaction_date=date(2026, 8, 15), unit_price=Decimal("0"), source_row=50)
    second = make_transaction(id=11, transaction_date=date(2026, 8, 15), unit_price=Decimal("12"), source_row=1)
    engine, _ = engine_for(second, first)

    first_result = engine.analyze(request())
    second_result = engine.analyze(request())

    assert first_result == second_result
    assert [observation.transaction_id for observation in first_result.observations] == [10, 11]
    assert first_result.last_purchase_price == Decimal("12")
    assert first_result.price_change.status is PriceChangeStatus.UNAVAILABLE
    assert first_result.price_change.percentage_change is None


def test_missing_price_is_reported_and_raw_transaction_values_are_unchanged():
    valid = make_transaction(id=10, unit_price=Decimal("10"))
    missing_price = make_transaction(id=11, unit_price=None)
    raw_values = (valid.supplier_raw, valid.product_raw, valid.destination_raw, valid.unit_raw)
    engine, session = engine_for(valid, missing_price)

    result = engine.analyze(request())

    assert result.comparable_transaction_count == 1
    assert result.data_quality.missing_price_count == 1
    assert raw_values == (valid.supplier_raw, valid.product_raw, valid.destination_raw, valid.unit_raw)
    assert session.closed is True
    statement = str(session.statements[0]).upper()
    assert statement.startswith("SELECT")
    assert all(keyword not in statement for keyword in ("INSERT", "UPDATE", "DELETE"))