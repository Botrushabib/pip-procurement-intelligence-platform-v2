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


class ObservedPattern(str, Enum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    VARIABLE = "VARIABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class SeasonalEvidence(str, Enum):
    NO_EVIDENCE = "NO_EVIDENCE"
    LIMITED_EVIDENCE = "LIMITED_EVIDENCE"
    REPEATED_PATTERN = "REPEATED_PATTERN"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class ComparisonStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class SeasonalityRequest:
    product_id: int | None = None
    category_id: int | None = None
    supplier_id: int | None = None
    unit_id: int | None = None
    company_id: int | None = None
    branch_id: int | None = None
    warehouse_id: int | None = None
    destination_type: str | None = None
    sub_warehouse_name: str | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class MonthOverMonthChange:
    status: ComparisonStatus
    previous_year: int | None
    previous_month: int | None
    absolute_quantity_change: Decimal | None
    percentage_quantity_change: Decimal | None
    reason: str


@dataclass(frozen=True)
class MonthlyPurchasePattern:
    year: int
    month: int
    year_month: str
    unit_id: int | None
    unit_name: str | None
    transaction_count: int
    total_quantity: Decimal
    total_purchase_value: Decimal
    average_quantity: Decimal
    average_unit_price: Decimal
    minimum_unit_price: Decimal
    maximum_unit_price: Decimal
    distinct_product_count: int
    distinct_supplier_count: int
    month_over_month: MonthOverMonthChange


@dataclass(frozen=True)
class YearOverYearComparison:
    month: int
    earlier_year: int
    later_year: int
    quantity_change: Decimal
    purchase_value_change: Decimal
    average_price_change: Decimal


@dataclass(frozen=True)
class SeasonalityCoverage:
    first_transaction_date: date | None
    last_transaction_date: date | None
    years_available: tuple[int, ...]
    observed_year_months: tuple[str, ...]
    inactive_year_months: tuple[str, ...]


@dataclass(frozen=True)
class SeasonalityDataQuality:
    examined_transactions: int
    eligible_transactions: int
    missing_product_count: int
    missing_date_count: int
    missing_quantity_count: int
    missing_price_count: int
    missing_subtotal_count: int
    missing_unit_count: int
    incomplete_location_count: int


@dataclass(frozen=True)
class SeasonalityResult:
    request: SeasonalityRequest
    monthly_patterns: tuple[MonthlyPurchasePattern, ...]
    year_over_year_comparisons: tuple[YearOverYearComparison, ...]
    coverage: SeasonalityCoverage
    data_quality: SeasonalityDataQuality
    observed_pattern: ObservedPattern
    seasonal_evidence: SeasonalEvidence
    mixed_units: bool


class SeasonalityEngine:
    """Read-only observed purchase patterns, not demand or forecasts.

    Quantities and prices are aggregated only within an exact unit. A monthly
    change is available only when the prior calendar month was observed. A
    repeated pattern requires at least two years with the same observed month;
    one year yields insufficient history rather than a seasonal conclusion.
    """

    def __init__(self, purchase_history: PurchaseHistoryAnalytics | None = None) -> None:
        self.purchase_history = purchase_history or PurchaseHistoryAnalytics()

    def analyze(self, request: SeasonalityRequest | None = None) -> SeasonalityResult:
        selected_request = request or SeasonalityRequest()
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
        patterns = self._patterns(history.records)
        coverage = self._coverage(history.records, selected_request)
        units = {record.unit_id for record in history.records if record.unit_id is not None}
        return SeasonalityResult(
            request=selected_request,
            monthly_patterns=patterns,
            year_over_year_comparisons=self._year_over_year(patterns),
            coverage=coverage,
            data_quality=SeasonalityDataQuality(
                examined_transactions=history.examined_count,
                eligible_transactions=history.data_quality.eligible_transactions,
                missing_product_count=history.data_quality.missing_product_count,
                missing_date_count=history.data_quality.missing_date_count,
                missing_quantity_count=history.data_quality.missing_quantity_count,
                missing_price_count=history.data_quality.missing_price_count,
                missing_subtotal_count=sum(record.subtotal is None for record in history.records),
                missing_unit_count=sum(record.unit_id is None for record in history.records),
                incomplete_location_count=sum(
                    record.branch_id is None
                    and record.warehouse_id is None
                    and record.destination_type is None
                    and record.sub_warehouse_name is None
                    for record in history.records
                ),
            ),
            observed_pattern=self._observed_pattern(patterns),
            seasonal_evidence=self._seasonal_evidence(patterns, coverage),
            mixed_units=len(units) > 1,
        )

    @classmethod
    def _patterns(
        cls, records: tuple[PreparedPurchaseTransaction, ...]
    ) -> tuple[MonthlyPurchasePattern, ...]:
        groups: dict[tuple[int, int, int | None], list[PreparedPurchaseTransaction]] = {}
        for record in records:
            groups.setdefault((record.year, record.month, record.unit_id), []).append(record)
        raw_patterns = []
        for (year, month, unit_id), group in groups.items():
            first = group[0]
            quantity = sum((record.quantity for record in group), Decimal("0"))
            prices = tuple(record.unit_price for record in group)
            raw_patterns.append(
                MonthlyPurchasePattern(
                    year=year,
                    month=month,
                    year_month=f"{year:04d}-{month:02d}",
                    unit_id=unit_id,
                    unit_name=first.unit_name,
                    transaction_count=len(group),
                    total_quantity=quantity,
                    total_purchase_value=sum(
                        (record.subtotal for record in group if record.subtotal is not None),
                        Decimal("0"),
                    ),
                    average_quantity=quantity / len(group),
                    average_unit_price=sum(prices, Decimal("0")) / len(prices),
                    minimum_unit_price=min(prices),
                    maximum_unit_price=max(prices),
                    distinct_product_count=len({record.product_id for record in group}),
                    distinct_supplier_count=len({record.supplier_id for record in group if record.supplier_id is not None}),
                    month_over_month=MonthOverMonthChange(ComparisonStatus.UNAVAILABLE, None, None, None, None, "Month comparison has not been calculated."),
                )
            )
        ordered = tuple(sorted(raw_patterns, key=lambda item: (item.unit_id is None, item.unit_id or -1, item.year, item.month)))
        return tuple(cls._with_month_change(item, ordered) for item in ordered)

    @staticmethod
    def _with_month_change(
        pattern: MonthlyPurchasePattern,
        all_patterns: tuple[MonthlyPurchasePattern, ...],
    ) -> MonthlyPurchasePattern:
        previous_year, previous_month = (
            (pattern.year - 1, 12) if pattern.month == 1 else (pattern.year, pattern.month - 1)
        )
        previous = next(
            (
                candidate
                for candidate in all_patterns
                if candidate.unit_id == pattern.unit_id
                and candidate.year == previous_year
                and candidate.month == previous_month
            ),
            None,
        )
        if previous is None:
            change = MonthOverMonthChange(ComparisonStatus.UNAVAILABLE, None, None, None, None, "The previous calendar month has no observed purchase data.")
        elif previous.total_quantity == 0:
            change = MonthOverMonthChange(ComparisonStatus.UNAVAILABLE, previous.year, previous.month, pattern.total_quantity, None, "Percentage change is unavailable because the previous observed quantity is zero.")
        else:
            absolute = pattern.total_quantity - previous.total_quantity
            change = MonthOverMonthChange(ComparisonStatus.AVAILABLE, previous.year, previous.month, absolute, absolute / previous.total_quantity * Decimal("100"), "Change compares consecutive observed calendar months for the same unit.")
        return MonthlyPurchasePattern(**{**pattern.__dict__, "month_over_month": change})

    @staticmethod
    def _coverage(
        records: tuple[PreparedPurchaseTransaction, ...], request: SeasonalityRequest
    ) -> SeasonalityCoverage:
        dates = tuple(record.transaction_date for record in records)
        observed = tuple(sorted({(item.year, item.month) for item in records}))
        first = min(dates) if dates else None
        last = max(dates) if dates else None
        start = request.date_from or first
        end = request.date_to or last
        inactive = () if start is None or end is None else tuple(
            f"{year:04d}-{month:02d}"
            for year, month in SeasonalityEngine._months_between(start, end)
            if (year, month) not in set(observed)
        )
        return SeasonalityCoverage(
            first_transaction_date=first,
            last_transaction_date=last,
            years_available=tuple(sorted({item.year for item in records})),
            observed_year_months=tuple(f"{year:04d}-{month:02d}" for year, month in observed),
            inactive_year_months=inactive,
        )

    @staticmethod
    def _months_between(start: date, end: date) -> tuple[tuple[int, int], ...]:
        months = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            months.append((year, month))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return tuple(months)

    @staticmethod
    def _observed_pattern(patterns: tuple[MonthlyPurchasePattern, ...]) -> ObservedPattern:
        if len(patterns) < 2:
            return ObservedPattern.INSUFFICIENT_DATA
        quantities = tuple(pattern.total_quantity for pattern in patterns)
        changes = tuple(later - earlier for earlier, later in zip(quantities, quantities[1:]))
        if all(change > 0 for change in changes):
            return ObservedPattern.INCREASING
        if all(change < 0 for change in changes):
            return ObservedPattern.DECREASING
        if all(change == 0 for change in changes):
            return ObservedPattern.STABLE
        return ObservedPattern.VARIABLE

    @staticmethod
    def _seasonal_evidence(
        patterns: tuple[MonthlyPurchasePattern, ...], coverage: SeasonalityCoverage
    ) -> SeasonalEvidence:
        if len(patterns) < 2 or len(coverage.years_available) < 2:
            return SeasonalEvidence.INSUFFICIENT_HISTORY
        month_years: dict[tuple[int | None, int], set[int]] = {}
        for pattern in patterns:
            month_years.setdefault((pattern.unit_id, pattern.month), set()).add(pattern.year)
        if any(len(years) >= 2 for years in month_years.values()):
            return SeasonalEvidence.REPEATED_PATTERN
        return SeasonalEvidence.LIMITED_EVIDENCE

    @staticmethod
    def _year_over_year(
        patterns: tuple[MonthlyPurchasePattern, ...]
    ) -> tuple[YearOverYearComparison, ...]:
        grouped: dict[tuple[int | None, int], list[MonthlyPurchasePattern]] = {}
        for pattern in patterns:
            grouped.setdefault((pattern.unit_id, pattern.month), []).append(pattern)
        comparisons = []
        for (_, month), group in grouped.items():
            ordered = sorted(group, key=lambda item: item.year)
            for earlier, later in zip(ordered, ordered[1:]):
                comparisons.append(YearOverYearComparison(month, earlier.year, later.year, later.total_quantity - earlier.total_quantity, later.total_purchase_value - earlier.total_purchase_value, later.average_unit_price - earlier.average_unit_price))
        return tuple(sorted(comparisons, key=lambda item: (item.month, item.earlier_year, item.later_year)))