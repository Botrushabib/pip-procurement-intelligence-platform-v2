from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
)


@dataclass(frozen=True)
class ReceivingTrendRequest:
    company_id: int | None = None
    warehouse_id: int | None = None
    supplier_id: int | None = None
    product_id: int | None = None
    category_id: int | None = None
    unit_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    reference: str | None = None


@dataclass(frozen=True)
class ReceivingTrendObservation:
    event_date: date
    event_id: int
    line_id: int
    line_number: int
    company_id: int
    warehouse_id: int
    supplier_id: int
    product_id: int
    category_id: int
    unit_id: int
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal
    reference: str


@dataclass(frozen=True)
class ReceivingMonthlyTrend:
    year: int
    month: int
    observation_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_price: Decimal | None
    arithmetic_average_price: Decimal | None
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    price_spread: Decimal | None
    distinct_receiving_dates: int
    quantity_change: Decimal | None = None
    quantity_change_pct: Decimal | None = None
    spend_change: Decimal | None = None
    spend_change_pct: Decimal | None = None
    price_change: Decimal | None = None
    price_change_pct: Decimal | None = None


@dataclass(frozen=True)
class ReceivingProductMonthlyTrend:
    product_id: int
    unit_id: int
    year: int
    month: int
    observation_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_price: Decimal | None
    arithmetic_average_price: Decimal | None
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    price_spread: Decimal | None
    distinct_receiving_dates: int
    quantity_change: Decimal | None = None
    quantity_change_pct: Decimal | None = None
    spend_change: Decimal | None = None
    spend_change_pct: Decimal | None = None
    price_change: Decimal | None = None
    price_change_pct: Decimal | None = None


@dataclass(frozen=True)
class ReceivingSupplierMonthlyTrend:
    supplier_id: int
    year: int
    month: int
    observation_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_price: Decimal | None
    arithmetic_average_price: Decimal | None
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    price_spread: Decimal | None
    distinct_products: int
    distinct_receiving_dates: int
    quantity_change: Decimal | None = None
    quantity_change_pct: Decimal | None = None
    spend_change: Decimal | None = None
    spend_change_pct: Decimal | None = None
    price_change: Decimal | None = None
    price_change_pct: Decimal | None = None


@dataclass(frozen=True)
class ReceivingCategoryMonthlyTrend:
    category_id: int
    year: int
    month: int
    observation_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_price: Decimal | None
    arithmetic_average_price: Decimal | None
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    price_spread: Decimal | None
    distinct_products: int
    distinct_suppliers: int
    distinct_receiving_dates: int
    quantity_change: Decimal | None = None
    quantity_change_pct: Decimal | None = None
    spend_change: Decimal | None = None
    spend_change_pct: Decimal | None = None
    price_change: Decimal | None = None
    price_change_pct: Decimal | None = None


@dataclass(frozen=True)
class ReceivingTrendQuality:
    examined_lines: int
    analytics_eligible_lines: int
    missing_supplier: int
    missing_product: int
    missing_category: int
    missing_unit: int
    missing_event_date: int
    missing_quantity: int
    missing_unit_price: int


@dataclass(frozen=True)
class ReceivingTrendResult:
    observations: tuple[ReceivingTrendObservation, ...]
    monthly_trends: tuple[ReceivingMonthlyTrend, ...]
    product_monthly_trends: tuple[ReceivingProductMonthlyTrend, ...]
    supplier_monthly_trends: tuple[ReceivingSupplierMonthlyTrend, ...]
    category_monthly_trends: tuple[ReceivingCategoryMonthlyTrend, ...]
    quality: ReceivingTrendQuality


@dataclass(frozen=True)
class _TrendValues:
    observation_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_price: Decimal | None
    arithmetic_average_price: Decimal | None
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    price_spread: Decimal | None
    distinct_receiving_dates: int
    distinct_products: int = 0
    distinct_suppliers: int = 0


class ReceivingTrendIntelligence:
    def analyze(
        self,
        request: ReceivingTrendRequest,
        records: Iterable[PreparedReceivingEventLine],
    ) -> ReceivingTrendResult:
        all_records = tuple(records)
        eligible_records = tuple(
            record
            for record in all_records
            if self._is_eligible(record) and self._matches(record, request)
        )
        eligible_records = tuple(sorted(eligible_records, key=self._record_key))
        observations = tuple(self._to_observation(record) for record in eligible_records)

        quality = ReceivingTrendQuality(
            examined_lines=len(all_records),
            analytics_eligible_lines=sum(
                1 for record in all_records if self._is_eligible(record)
            ),
            missing_supplier=sum(
                1 for record in all_records
                if record.supplier_id is None or record.supplier_id <= 0
            ),
            missing_product=sum(
                1 for record in all_records
                if record.product_id is None or record.product_id <= 0
            ),
            missing_category=sum(
                1 for record in all_records
                if record.category_id is None or record.category_id <= 0
            ),
            missing_unit=sum(
                1 for record in all_records
                if record.unit_id is None or record.unit_id <= 0
            ),
            missing_event_date=sum(
                1 for record in all_records if record.event_date is None
            ),
            missing_quantity=sum(
                1 for record in all_records
                if not self._valid_quantity(record.quantity)
            ),
            missing_unit_price=sum(
                1 for record in all_records
                if not self._valid_price(record.unit_price)
            ),
        )

        return ReceivingTrendResult(
            observations=observations,
            monthly_trends=self._monthly_trends(observations),
            product_monthly_trends=self._product_trends(observations),
            supplier_monthly_trends=self._supplier_trends(observations),
            category_monthly_trends=self._category_trends(observations),
            quality=quality,
        )

    @staticmethod
    def _valid_quantity(value: object) -> bool:
        if value is None:
            return False
        try:
            return value > 0  # type: ignore[operator]
        except TypeError:
            return False

    @staticmethod
    def _valid_price(value: object) -> bool:
        if value is None:
            return False
        try:
            return value >= 0  # type: ignore[operator]
        except TypeError:
            return False

    @classmethod
    def _is_eligible(cls, record: PreparedReceivingEventLine) -> bool:
        return (
            record.eligibility.eligible_for_analytics
            and record.event_date is not None
            and record.product_id is not None
            and record.product_id > 0
            and record.supplier_id is not None
            and record.supplier_id > 0
            and record.category_id is not None
            and record.category_id > 0
            and record.unit_id is not None
            and record.unit_id > 0
            and record.warehouse_id is not None
            and record.warehouse_id > 0
            and cls._valid_quantity(record.quantity)
            and cls._valid_price(record.unit_price)
        )

    @staticmethod
    def _normalize_reference(value: object) -> str:
        return " ".join(str(value).strip().split()).casefold()

    @classmethod
    def _matches(
        cls,
        record: PreparedReceivingEventLine,
        request: ReceivingTrendRequest,
    ) -> bool:
        if request.company_id is not None and record.company_id != request.company_id:
            return False
        if request.warehouse_id is not None and record.warehouse_id != request.warehouse_id:
            return False
        if request.supplier_id is not None and record.supplier_id != request.supplier_id:
            return False
        if request.product_id is not None and record.product_id != request.product_id:
            return False
        if request.category_id is not None and record.category_id != request.category_id:
            return False
        if request.unit_id is not None and record.unit_id != request.unit_id:
            return False
        if request.date_from is not None and record.event_date < request.date_from:
            return False
        if request.date_to is not None and record.event_date > request.date_to:
            return False
        if request.reference is not None and cls._normalize_reference(record.receiving_reference) != cls._normalize_reference(request.reference):
            return False
        return True

    @staticmethod
    def _record_key(record: PreparedReceivingEventLine) -> tuple:
        return (
            record.event_date or date.min,
            record.event_id,
            record.line_number,
            record.line_id,
        )

    @staticmethod
    def _to_observation(record: PreparedReceivingEventLine) -> ReceivingTrendObservation:
        return ReceivingTrendObservation(
            event_date=record.event_date,  # type: ignore[arg-type]
            event_id=record.event_id,
            line_id=record.line_id,
            line_number=record.line_number,
            company_id=record.company_id,
            warehouse_id=record.warehouse_id,
            supplier_id=record.supplier_id,
            product_id=record.product_id,
            category_id=record.category_id,  # type: ignore[arg-type]
            unit_id=record.unit_id,
            quantity=record.quantity,
            unit_price=record.unit_price,
            subtotal=record.subtotal,
            reference=record.receiving_reference,
        )

    @staticmethod
    def _values(observations: Iterable[ReceivingTrendObservation]) -> _TrendValues:
        items = tuple(observations)
        quantities = sum((item.quantity for item in items), Decimal("0"))
        spend = sum((item.subtotal for item in items), Decimal("0"))
        prices = tuple(item.unit_price for item in items)
        weighted = spend / quantities if quantities > 0 else None
        arithmetic = sum(prices, Decimal("0")) / Decimal(len(prices)) if prices else None
        minimum = min(prices) if prices else None
        maximum = max(prices) if prices else None
        return _TrendValues(
            observation_count=len(items),
            total_quantity=quantities,
            total_spend=spend,
            weighted_average_price=weighted,
            arithmetic_average_price=arithmetic,
            minimum_price=minimum,
            maximum_price=maximum,
            price_spread=maximum - minimum if minimum is not None and maximum is not None else None,
            distinct_receiving_dates=len({item.event_date for item in items}),
        )

    @staticmethod
    def _period_changes(
        current: _TrendValues,
        previous: _TrendValues | None,
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
        if previous is None:
            return (None, None, None, None, None, None)
        quantity_change = current.total_quantity - previous.total_quantity
        quantity_pct = quantity_change / previous.total_quantity * Decimal("100") if previous.total_quantity != 0 else None
        spend_change = current.total_spend - previous.total_spend
        spend_pct = spend_change / previous.total_spend * Decimal("100") if previous.total_spend != 0 else None
        if current.weighted_average_price is None or previous.weighted_average_price is None:
            price_change = None
            price_pct = None
        else:
            price_change = current.weighted_average_price - previous.weighted_average_price
            price_pct = price_change / previous.weighted_average_price * Decimal("100") if previous.weighted_average_price != 0 else None
        return quantity_change, quantity_pct, spend_change, spend_pct, price_change, price_pct

    @staticmethod
    def _trend_kwargs(values: _TrendValues) -> dict[str, object]:
        return {
            "observation_count": values.observation_count,
            "total_quantity": values.total_quantity,
            "total_spend": values.total_spend,
            "weighted_average_price": values.weighted_average_price,
            "arithmetic_average_price": values.arithmetic_average_price,
            "minimum_price": values.minimum_price,
            "maximum_price": values.maximum_price,
            "price_spread": values.price_spread,
            "distinct_receiving_dates": values.distinct_receiving_dates,
        }

    @classmethod
    def _monthly_trends(cls, observations: tuple[ReceivingTrendObservation, ...]) -> tuple[ReceivingMonthlyTrend, ...]:
        groups: dict[tuple[int, int], list[ReceivingTrendObservation]] = defaultdict(list)
        for item in observations:
            groups[(item.event_date.year, item.event_date.month)].append(item)
        previous = None
        result = []
        for key in sorted(groups):
            values = cls._values(groups[key])
            changes = cls._period_changes(values, previous)
            result.append(ReceivingMonthlyTrend(year=key[0], month=key[1], **cls._trend_kwargs(values), quantity_change=changes[0], quantity_change_pct=changes[1], spend_change=changes[2], spend_change_pct=changes[3], price_change=changes[4], price_change_pct=changes[5]))
            previous = values
        return tuple(result)

    @classmethod
    def _product_trends(cls, observations: tuple[ReceivingTrendObservation, ...]) -> tuple[ReceivingProductMonthlyTrend, ...]:
        groups: dict[tuple[int, int, int, int], list[ReceivingTrendObservation]] = defaultdict(list)
        for item in observations:
            groups[(item.product_id, item.unit_id, item.event_date.year, item.event_date.month)].append(item)
        result = []
        for product_unit in sorted({(key[0], key[1]) for key in groups}):
            previous = None
            keys = sorted(key for key in groups if key[:2] == product_unit)
            for key in keys:
                values = cls._values(groups[key])
                changes = cls._period_changes(values, previous)
                result.append(ReceivingProductMonthlyTrend(product_id=key[0], unit_id=key[1], year=key[2], month=key[3], **cls._trend_kwargs(values), quantity_change=changes[0], quantity_change_pct=changes[1], spend_change=changes[2], spend_change_pct=changes[3], price_change=changes[4], price_change_pct=changes[5]))
                previous = values
        return tuple(result)

    @classmethod
    def _supplier_trends(cls, observations: tuple[ReceivingTrendObservation, ...]) -> tuple[ReceivingSupplierMonthlyTrend, ...]:
        groups: dict[tuple[int, int, int], list[ReceivingTrendObservation]] = defaultdict(list)
        for item in observations:
            groups[(item.supplier_id, item.event_date.year, item.event_date.month)].append(item)
        result = []
        for supplier in sorted({key[0] for key in groups}):
            previous = None
            for key in sorted(key for key in groups if key[0] == supplier):
                values = cls._values(groups[key])
                values = _TrendValues(**{**values.__dict__, "distinct_products": len({item.product_id for item in groups[key]})})
                changes = cls._period_changes(values, previous)
                result.append(ReceivingSupplierMonthlyTrend(supplier_id=key[0], year=key[1], month=key[2], **cls._trend_kwargs(values), distinct_products=values.distinct_products, quantity_change=changes[0], quantity_change_pct=changes[1], spend_change=changes[2], spend_change_pct=changes[3], price_change=changes[4], price_change_pct=changes[5]))
                previous = values
        return tuple(result)

    @classmethod
    def _category_trends(cls, observations: tuple[ReceivingTrendObservation, ...]) -> tuple[ReceivingCategoryMonthlyTrend, ...]:
        groups: dict[tuple[int, int, int], list[ReceivingTrendObservation]] = defaultdict(list)
        for item in observations:
            groups[(item.category_id, item.event_date.year, item.event_date.month)].append(item)
        result = []
        for category in sorted({key[0] for key in groups}):
            previous = None
            for key in sorted(key for key in groups if key[0] == category):
                values = cls._values(groups[key])
                values = _TrendValues(
                    **{
                        **values.__dict__,
                        "distinct_products": len(
                            {item.product_id for item in groups[key]}
                        ),
                        "distinct_suppliers": len(
                            {item.supplier_id for item in groups[key]}
                        ),
                    }
                )
                changes = cls._period_changes(values, previous)
                result.append(ReceivingCategoryMonthlyTrend(category_id=key[0], year=key[1], month=key[2], **cls._trend_kwargs(values), distinct_products=values.distinct_products, distinct_suppliers=values.distinct_suppliers, quantity_change=changes[0], quantity_change_pct=changes[1], spend_change=changes[2], spend_change_pct=changes[3], price_change=changes[4], price_change_pct=changes[5]))
                previous = values
        return tuple(result)


analyze_receiving_trends = ReceivingTrendIntelligence().analyze
