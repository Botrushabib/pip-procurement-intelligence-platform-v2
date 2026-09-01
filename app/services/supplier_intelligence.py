from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from app.services.analytics_preparation import PreparedPurchaseTransaction
from app.services.purchase_history_analytics import (
    PurchaseHistoryAnalytics,
    PurchaseHistoryFilter,
)


class HistoricalDataSufficiency(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class SupplierHistoryRequest:
    supplier_id: int | None = None
    product_id: int | None = None
    category_id: int | None = None
    unit_id: int | None = None
    company_id: int | None = None
    branch_id: int | None = None
    warehouse_id: int | None = None
    destination_type: str | None = None
    sub_warehouse_name: str | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class SupplierPurchaseObservation:
    transaction_id: int | None
    transaction_date: date
    supplier_id: int
    supplier_name: str | None
    product_id: int
    product_name: str | None
    category_id: int | None
    category_name: str | None
    unit_id: int | None
    unit_name: str | None
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal | None
    branch_id: int | None
    warehouse_id: int | None
    destination_type: str | None
    sub_warehouse_name: str | None
    source_file: str | None
    source_sheet: str | None
    source_row: int | None


@dataclass(frozen=True)
class SupplierProductHistory:
    supplier_id: int
    supplier_name: str | None
    product_id: int
    product_name: str | None
    category_id: int | None
    category_name: str | None
    unit_id: int | None
    unit_name: str | None
    observations: tuple[SupplierPurchaseObservation, ...]
    transaction_count: int
    total_quantity: Decimal
    total_purchase_value: Decimal
    average_quantity: Decimal | None
    average_unit_price: Decimal | None
    minimum_unit_price: Decimal | None
    maximum_unit_price: Decimal | None
    last_purchase_date: date | None
    last_purchase_price: Decimal | None
    last_purchase_quantity: Decimal | None
    active_purchase_months: int
    average_days_between_purchase_dates: Decimal | None
    frequency_status: HistoricalDataSufficiency


@dataclass(frozen=True)
class SupplierHistoryDataQuality:
    examined_transactions: int
    purchase_history_eligible_transactions: int
    supplier_eligible_transactions: int
    missing_supplier_count: int
    missing_product_count: int
    missing_unit_count: int
    missing_date_count: int
    missing_quantity_count: int
    missing_price_count: int
    incomplete_location_count: int


@dataclass(frozen=True)
class SupplierHistoricalResult:
    request: SupplierHistoryRequest
    observations: tuple[SupplierPurchaseObservation, ...]
    relationships: tuple[SupplierProductHistory, ...]
    data_quality: SupplierHistoryDataQuality
    supplier_ids: tuple[int, ...]
    product_ids: tuple[int, ...]
    category_ids: tuple[int, ...]
    unit_ids: tuple[int, ...]
    branch_ids: tuple[int, ...]
    warehouse_ids: tuple[int, ...]


class SupplierHistoricalIntelligence:
    """Read-only historical supplier facts grouped by supplier, product, and unit.

    Each relationship keeps one exact unit. Frequency is the average number of
    days between distinct purchase dates and is unavailable with fewer than two
    dates. Last purchase uses the stable Phase 9A chronological order.
    """

    def __init__(self, purchase_history: PurchaseHistoryAnalytics | None = None) -> None:
        self.purchase_history = purchase_history or PurchaseHistoryAnalytics()

    def analyze(self, request: SupplierHistoryRequest | None = None) -> SupplierHistoricalResult:
        selected_request = request or SupplierHistoryRequest()
        history = self.purchase_history.analyze(
            PurchaseHistoryFilter(
                product_id=selected_request.product_id,
                category_id=selected_request.category_id,
                supplier_id=selected_request.supplier_id,
                unit_id=selected_request.unit_id,
                company_id=selected_request.company_id,
                branch_id=selected_request.branch_id,
                warehouse_id=selected_request.warehouse_id,
                destination_type=selected_request.destination_type,
                sub_warehouse_name=selected_request.sub_warehouse_name,
                start_month=selected_request.date_from,
                end_month=selected_request.date_to,
            )
        )
        records = tuple(record for record in history.records if record.supplier_id is not None)
        observations = tuple(self._observation(record) for record in records)
        return SupplierHistoricalResult(
            request=selected_request,
            observations=observations,
            relationships=self._relationships(observations),
            data_quality=SupplierHistoryDataQuality(
                examined_transactions=history.examined_count,
                purchase_history_eligible_transactions=history.data_quality.eligible_transactions,
                supplier_eligible_transactions=len(observations),
                missing_supplier_count=history.data_quality.missing_supplier_count,
                missing_product_count=history.data_quality.missing_product_count,
                missing_unit_count=sum(record.unit_id is None for record in history.records),
                missing_date_count=history.data_quality.missing_date_count,
                missing_quantity_count=history.data_quality.missing_quantity_count,
                missing_price_count=history.data_quality.missing_price_count,
                incomplete_location_count=sum(
                    record.branch_id is None
                    and record.warehouse_id is None
                    and record.destination_type is None
                    and record.sub_warehouse_name is None
                    for record in history.records
                ),
            ),
            supplier_ids=tuple(sorted({record.supplier_id for record in observations})),
            product_ids=tuple(sorted({record.product_id for record in observations})),
            category_ids=tuple(sorted({record.category_id for record in observations if record.category_id is not None})),
            unit_ids=tuple(sorted({record.unit_id for record in observations if record.unit_id is not None})),
            branch_ids=tuple(sorted({record.branch_id for record in observations if record.branch_id is not None})),
            warehouse_ids=tuple(sorted({record.warehouse_id for record in observations if record.warehouse_id is not None})),
        )

    @staticmethod
    def _observation(record: PreparedPurchaseTransaction) -> SupplierPurchaseObservation:
        return SupplierPurchaseObservation(
            transaction_id=record.transaction_id,
            transaction_date=record.transaction_date,
            supplier_id=record.supplier_id,
            supplier_name=record.supplier_name,
            product_id=record.product_id,
            product_name=record.product_name,
            category_id=record.category_id,
            category_name=record.category_name,
            unit_id=record.unit_id,
            unit_name=record.unit_name,
            quantity=record.quantity,
            unit_price=record.unit_price,
            subtotal=record.subtotal,
            branch_id=record.branch_id,
            warehouse_id=record.warehouse_id,
            destination_type=record.destination_type,
            sub_warehouse_name=record.sub_warehouse_name,
            source_file=record.source_file,
            source_sheet=record.source_sheet,
            source_row=record.source_row,
        )

    @classmethod
    def _relationships(
        cls, observations: tuple[SupplierPurchaseObservation, ...]
    ) -> tuple[SupplierProductHistory, ...]:
        groups: dict[tuple[int, int, int | None], list[SupplierPurchaseObservation]] = {}
        for observation in observations:
            groups.setdefault(
                (observation.supplier_id, observation.product_id, observation.unit_id), []
            ).append(observation)
        return tuple(
            cls._relationship(tuple(group))
            for _, group in sorted(groups.items())
        )

    @staticmethod
    def _relationship(
        observations: tuple[SupplierPurchaseObservation, ...]
    ) -> SupplierProductHistory:
        first = observations[0]
        prices = tuple(observation.unit_price for observation in observations)
        total_quantity = sum((observation.quantity for observation in observations), Decimal("0"))
        dates = tuple(sorted({observation.transaction_date for observation in observations}))
        average_days = None
        if len(dates) > 1:
            average_days = Decimal((dates[-1] - dates[0]).days) / Decimal(len(dates) - 1)
        last = observations[-1]
        return SupplierProductHistory(
            supplier_id=first.supplier_id,
            supplier_name=first.supplier_name,
            product_id=first.product_id,
            product_name=first.product_name,
            category_id=first.category_id,
            category_name=first.category_name,
            unit_id=first.unit_id,
            unit_name=first.unit_name,
            observations=observations,
            transaction_count=len(observations),
            total_quantity=total_quantity,
            total_purchase_value=sum(
                (observation.subtotal for observation in observations if observation.subtotal is not None),
                Decimal("0"),
            ),
            average_quantity=total_quantity / len(observations) if observations else None,
            average_unit_price=sum(prices, Decimal("0")) / len(prices) if prices else None,
            minimum_unit_price=min(prices) if prices else None,
            maximum_unit_price=max(prices) if prices else None,
            last_purchase_date=last.transaction_date,
            last_purchase_price=last.unit_price,
            last_purchase_quantity=last.quantity,
            active_purchase_months=len({(item.transaction_date.year, item.transaction_date.month) for item in observations}),
            average_days_between_purchase_dates=average_days,
            frequency_status=HistoricalDataSufficiency.AVAILABLE if average_days is not None else HistoricalDataSufficiency.INSUFFICIENT_DATA,
        )