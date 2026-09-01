from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.purchase_history_analytics import (
    PurchaseHistoryAnalytics,
    PurchaseHistoryFilter,
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


def analytics_for(*transactions):
    session = ReadOnlySession(list(transactions))
    return PurchaseHistoryAnalytics(session_factory=lambda: session), session


def test_empty_dataset_returns_missing_metrics_and_no_months():
    analytics, _ = analytics_for()

    result = analytics.analyze()

    assert result.transaction_count == 0
    assert result.total_quantity == Decimal("0")
    assert result.total_subtotal == Decimal("0")
    assert result.average_quantity is None
    assert result.average_unit_price is None
    assert result.last_purchase is None
    assert result.monthly_totals == ()


def test_metrics_monthly_totals_and_supplier_relationships_are_decimal_safe():
    first = make_transaction(id=10, transaction_date=date(2026, 7, 2), quantity=Decimal("2.500"), unit_price=Decimal("10.125"), subtotal=Decimal("25.3125"))
    second = make_transaction(id=11, transaction_date=date(2026, 8, 15), quantity=Decimal("3.500"), unit_price=Decimal("12.375"), subtotal=Decimal("43.3125"))
    analytics, _ = analytics_for(first, second)

    result = analytics.analyze()

    assert result.transaction_count == 2
    assert result.total_quantity == Decimal("6.000")
    assert result.total_subtotal == Decimal("68.6250")
    assert result.average_quantity == Decimal("3.000")
    assert result.average_unit_price == Decimal("11.250")
    assert (result.minimum_unit_price, result.maximum_unit_price) == (Decimal("10.125"), Decimal("12.375"))
    assert (result.last_purchase_date, result.last_purchase_price, result.last_supplier_name) == (date(2026, 8, 15), Decimal("12.375"), "Supplier A")
    assert [(month.year, month.month, month.total_quantity, month.average_unit_price) for month in result.monthly_totals] == [
        (2026, 7, Decimal("2.500"), Decimal("10.125")),
        (2026, 8, Decimal("3.500"), Decimal("12.375")),
    ]
    assert result.purchase_frequency.average_days_between_purchase_dates == Decimal("44")


def test_filters_support_product_category_supplier_unit_location_destination_and_month():
    matching = make_transaction(transaction_date=date(2026, 8, 15))
    other = make_transaction(id=9, transaction_date=date(2026, 7, 15), warehouse_id=99)
    analytics, _ = analytics_for(matching, other)

    result = analytics.analyze(
        PurchaseHistoryFilter(
            product_id=7,
            category_id=2,
            supplier_id=4,
            unit_id=3,
            company_id=1,
            branch_id=5,
            warehouse_id=6,
            destination_type="WAREHOUSE",
            sub_warehouse_name="Cold Storage",
            start_month=date(2026, 8, 1),
            end_month=date(2026, 8, 31),
        )
    )

    assert result.transaction_count == 1
    assert result.records[0].transaction_id == 8


def test_same_date_last_purchase_tie_breaks_by_transaction_id_then_traceability():
    lower_id = make_transaction(id=10, unit_price=Decimal("15"), source_row=20)
    higher_id = make_transaction(id=11, unit_price=Decimal("18"), source_row=2)
    analytics, _ = analytics_for(higher_id, lower_id)

    result = analytics.analyze()

    assert result.last_purchase.transaction_id == 11
    assert result.last_purchase_price == Decimal("18")
    assert [record.transaction_id for record in result.records] == [10, 11]


def test_ineligible_records_are_excluded_but_quality_is_retained_and_queries_repeat():
    eligible = make_transaction()
    ineligible = make_transaction(id=9, quantity=None)
    analytics, _ = analytics_for(ineligible, eligible)

    first = analytics.analyze()
    second = analytics.analyze()

    assert first == second
    assert first.examined_count == 2
    assert first.transaction_count == 1
    assert first.data_quality.ineligible_transactions == 1


def test_database_interaction_is_select_only_and_session_is_closed():
    analytics, session = analytics_for(make_transaction())

    analytics.analyze()

    assert session.closed is True
    assert len(session.statements) == 1
    statement = str(session.statements[0]).upper()
    assert statement.startswith("SELECT")
    assert all(keyword not in statement for keyword in ("INSERT", "UPDATE", "DELETE"))