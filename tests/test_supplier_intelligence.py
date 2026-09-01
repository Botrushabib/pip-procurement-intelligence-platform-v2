from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.purchase_history_analytics import PurchaseHistoryAnalytics
from app.services.supplier_intelligence import (
    HistoricalDataSufficiency,
    SupplierHistoricalIntelligence,
    SupplierHistoryRequest,
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
    return SupplierHistoricalIntelligence(history), session


def test_empty_and_single_supplier_history_are_explicit():
    empty, _ = engine_for()
    single, _ = engine_for(make_transaction())

    assert empty.analyze().relationships == ()
    relationship = single.analyze(SupplierHistoryRequest(supplier_id=4)).relationships[0]
    assert relationship.transaction_count == 1
    assert relationship.total_quantity == Decimal("2.500")
    assert relationship.total_purchase_value == Decimal("25.3125")
    assert relationship.average_quantity == Decimal("2.500")
    assert relationship.frequency_status is HistoricalDataSufficiency.INSUFFICIENT_DATA


def test_supplier_product_unit_history_has_decimal_metrics_and_traceability():
    first = make_transaction(id=10, transaction_date=date(2026, 7, 1), quantity=Decimal("2.5"), unit_price=Decimal("10"), subtotal=Decimal("25"))
    second = make_transaction(id=11, transaction_date=date(2026, 8, 15), quantity=Decimal("3.5"), unit_price=Decimal("14"), subtotal=Decimal("49"))
    engine, _ = engine_for(first, second)

    relationship = engine.analyze(SupplierHistoryRequest(supplier_id=4)).relationships[0]

    assert relationship.transaction_count == 2
    assert relationship.total_quantity == Decimal("6.0")
    assert relationship.total_purchase_value == Decimal("74")
    assert relationship.average_quantity == Decimal("3.0")
    assert (relationship.average_unit_price, relationship.minimum_unit_price, relationship.maximum_unit_price) == (Decimal("12"), Decimal("10"), Decimal("14"))
    assert (relationship.last_purchase_date, relationship.last_purchase_price, relationship.last_purchase_quantity) == (date(2026, 8, 15), Decimal("14"), Decimal("3.5"))
    assert relationship.active_purchase_months == 2
    assert relationship.average_days_between_purchase_dates == Decimal("45")
    assert relationship.frequency_status is HistoricalDataSufficiency.AVAILABLE
    assert relationship.observations[-1].source_file == "purchases.xlsx"


def test_matrix_groups_product_to_suppliers_and_supplier_to_products_without_recommendation():
    supplier_a_product_a = make_transaction(id=10, supplier_id=4, product_id=7)
    supplier_b_product_a = make_transaction(id=11, supplier_id=5, product_id=7)
    supplier_a_product_b = make_transaction(id=12, supplier_id=4, product_id=8)
    engine, _ = engine_for(supplier_b_product_a, supplier_a_product_b, supplier_a_product_a)

    result = engine.analyze()

    assert [(item.supplier_id, item.product_id) for item in result.relationships] == [(4, 7), (4, 8), (5, 7)]
    assert result.supplier_ids == (4, 5)
    assert result.product_ids == (7, 8)
    assert not hasattr(result, "recommended_supplier")
    assert not hasattr(result, "supplier_score")


def test_different_units_remain_separate_and_are_never_converted():
    kilograms = make_transaction(id=10, unit_id=3, quantity=Decimal("10"), unit_price=Decimal("5"))
    boxes = make_transaction(id=11, unit_id=99, quantity=Decimal("2"), unit_price=Decimal("50"))
    engine, _ = engine_for(kilograms, boxes)

    result = engine.analyze(SupplierHistoryRequest(supplier_id=4))

    assert [(item.unit_id, item.total_quantity, item.average_unit_price) for item in result.relationships] == [
        (3, Decimal("10"), Decimal("5")),
        (99, Decimal("2"), Decimal("50")),
    ]


def test_normalized_category_supplier_location_and_date_filters_are_applied():
    matching = make_transaction(transaction_date=date(2026, 8, 15), destination_type="WAREHOUSE")
    excluded = make_transaction(id=9, supplier_id=5, category_id=20, branch_id=99, warehouse_id=99, transaction_date=date(2026, 7, 15), destination_type="BRANCH")
    engine, _ = engine_for(matching, excluded)

    result = engine.analyze(
        SupplierHistoryRequest(
            supplier_id=4,
            product_id=7,
            category_id=2,
            unit_id=3,
            company_id=1,
            branch_id=5,
            warehouse_id=6,
            destination_type="WAREHOUSE",
            sub_warehouse_name="Cold Storage",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
        )
    )

    assert len(result.observations) == 1
    assert result.observations[0].transaction_id == 8
    assert result.category_ids == (2,)
    assert result.branch_ids == (5,)
    assert result.warehouse_ids == (6,)


def test_missing_supplier_and_other_missing_data_are_reported_without_mutation():
    valid = make_transaction(id=10)
    missing_supplier = make_transaction(id=11, supplier_id=None)
    missing_price = make_transaction(id=12, unit_price=None)
    raw_values = (valid.supplier_raw, valid.product_raw, valid.destination_raw, valid.unit_raw)
    engine, _ = engine_for(valid, missing_supplier, missing_price)

    result = engine.analyze()

    assert result.data_quality.missing_supplier_count == 1
    assert result.data_quality.missing_price_count == 1
    assert result.data_quality.supplier_eligible_transactions == 1
    assert raw_values == (valid.supplier_raw, valid.product_raw, valid.destination_raw, valid.unit_raw)


def test_same_date_order_is_stable_and_database_access_is_select_only():
    later_id = make_transaction(id=11, transaction_date=date(2026, 8, 15), unit_price=Decimal("12"))
    earlier_id = make_transaction(id=10, transaction_date=date(2026, 8, 15), unit_price=Decimal("10"))
    engine, session = engine_for(later_id, earlier_id)

    first = engine.analyze()
    second = engine.analyze()

    assert first == second
    assert [item.transaction_id for item in first.observations] == [10, 11]
    assert session.closed is True
    statement = str(session.statements[0]).upper()
    assert statement.startswith("SELECT")
    assert all(keyword not in statement for keyword in ("INSERT", "UPDATE", "DELETE"))