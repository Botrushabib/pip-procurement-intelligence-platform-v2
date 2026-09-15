from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ReceivingAnalyticsDataQualityReport,
    ReceivingAnalyticsPreparationResult,
    ReceivingEventAnalyticsPreparation,
)
from app.services.receiving_event_query_service import (
    ReceivingEventQueryService,
)


@dataclass(frozen=True)
class ReceivingHistoryFilter:
    product_id: int | None = None
    category_id: int | None = None
    supplier_id: int | None = None
    unit_id: int | None = None
    company_id: int | None = None
    warehouse_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class MonthlyReceivingTotal:
    year: int
    month: int
    event_count: int
    line_count: int
    total_quantity: Decimal
    total_subtotal: Decimal
    average_unit_price: Decimal | None


@dataclass(frozen=True)
class ReceivingFrequency:
    event_count: int
    line_count: int
    first_receiving_date: date | None
    last_receiving_date: date | None
    average_days_between_receipts: Decimal | None


@dataclass(frozen=True)
class LastReceiving:
    event_date: date
    unit_price: Decimal
    quantity: Decimal
    supplier_id: int
    supplier_name: str | None
    warehouse_id: int
    warehouse_name: str | None
    receiving_reference: str
    event_id: int
    line_id: int


@dataclass(frozen=True)
class ReceivingHistoryResult:
    filters: ReceivingHistoryFilter
    examined_count: int
    records: tuple[PreparedReceivingEventLine, ...]
    data_quality: ReceivingAnalyticsDataQualityReport
    line_count: int
    distinct_event_count: int
    total_quantity: Decimal
    total_subtotal: Decimal
    average_quantity_per_line: Decimal | None
    average_unit_price: Decimal | None
    minimum_unit_price: Decimal | None
    maximum_unit_price: Decimal | None
    last_receiving: LastReceiving | None
    receiving_frequency: ReceivingFrequency
    monthly_totals: tuple[MonthlyReceivingTotal, ...]


class ReceivingHistoryAnalytics:
    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        preparation: ReceivingEventAnalyticsPreparation | None = None,
        query_service: ReceivingEventQueryService | None = None,
    ) -> None:
        self.session_factory = session_factory or SessionLocal
        self.preparation = preparation or ReceivingEventAnalyticsPreparation()
        self.query_service = query_service or ReceivingEventQueryService(
            session_factory=self.session_factory
        )

    def analyze(
        self,
        records_or_filters: (
            Iterable[PreparedReceivingEventLine]
            | ReceivingAnalyticsPreparationResult
            | ReceivingHistoryFilter
            | None
        ) = None,
        filters: ReceivingHistoryFilter | None = None,
        *,
        records: (
            Iterable[PreparedReceivingEventLine]
            | ReceivingAnalyticsPreparationResult
            | None
        ) = None,
    ) -> ReceivingHistoryResult:
        if isinstance(records_or_filters, ReceivingHistoryFilter):
            selected_filters = records_or_filters
            target_records = records
        else:
            target_records = (
                records_or_filters if records_or_filters is not None else records
            )
            selected_filters = filters or ReceivingHistoryFilter()

        if target_records is None:
            raw_events = self.query_service.query()
            prep_result = self.preparation.prepare(raw_events)
            all_records = prep_result.records
        elif isinstance(target_records, ReceivingAnalyticsPreparationResult):
            all_records = target_records.records
        else:
            all_records = tuple(target_records)

        filtered_records = tuple(
            r for r in all_records if self._matches(r, selected_filters)
        )

        ordered_records = tuple(
            sorted(filtered_records, key=self._record_order_key)
        )
        examined_count = len(ordered_records)
        data_quality = self.preparation._calculate_data_quality(ordered_records)

        eligible_records = tuple(
            r for r in ordered_records if r.eligibility.eligible_for_analytics
        )

        return self._build_result(
            filters=selected_filters,
            examined_count=examined_count,
            records=ordered_records,
            data_quality=data_quality,
            eligible_records=eligible_records,
        )

    @staticmethod
    def _matches(
        record: PreparedReceivingEventLine, filters: ReceivingHistoryFilter
    ) -> bool:
        if filters.product_id is not None and record.product_id != filters.product_id:
            return False
        if (
            filters.category_id is not None
            and record.category_id != filters.category_id
        ):
            return False
        if (
            filters.supplier_id is not None
            and record.supplier_id != filters.supplier_id
        ):
            return False
        if filters.unit_id is not None and record.unit_id != filters.unit_id:
            return False
        if filters.company_id is not None and record.company_id != filters.company_id:
            return False
        if (
            filters.warehouse_id is not None
            and record.warehouse_id != filters.warehouse_id
        ):
            return False
        if filters.start_date is not None and (
            record.event_date is None or record.event_date < filters.start_date
        ):
            return False
        if filters.end_date is not None and (
            record.event_date is None or record.event_date > filters.end_date
        ):
            return False
        return True

    @staticmethod
    def _record_order_key(record: PreparedReceivingEventLine) -> tuple:
        return (
            record.event_date or date.min,
            record.receiving_reference or "",
            record.event_id if record.event_id is not None else -1,
            record.line_number if record.line_number is not None else -1,
            record.line_id if record.line_id is not None else -1,
        )

    @staticmethod
    def _last_receiving_order_key(record: PreparedReceivingEventLine) -> tuple:
        return (
            record.event_date or date.min,
            record.event_id if record.event_id is not None else -1,
            record.line_number if record.line_number is not None else -1,
            record.line_id if record.line_id is not None else -1,
        )

    def _build_result(
        self,
        filters: ReceivingHistoryFilter,
        examined_count: int,
        records: tuple[PreparedReceivingEventLine, ...],
        data_quality: ReceivingAnalyticsDataQualityReport,
        eligible_records: tuple[PreparedReceivingEventLine, ...],
    ) -> ReceivingHistoryResult:
        line_count = len(eligible_records)
        distinct_events = {
            r.event_id for r in eligible_records if r.event_id is not None
        }
        distinct_event_count = len(distinct_events)

        if line_count == 0:
            return ReceivingHistoryResult(
                filters=filters,
                examined_count=examined_count,
                records=records,
                data_quality=data_quality,
                line_count=0,
                distinct_event_count=0,
                total_quantity=Decimal("0"),
                total_subtotal=Decimal("0"),
                average_quantity_per_line=None,
                average_unit_price=None,
                minimum_unit_price=None,
                maximum_unit_price=None,
                last_receiving=None,
                receiving_frequency=ReceivingFrequency(
                    event_count=0,
                    line_count=0,
                    first_receiving_date=None,
                    last_receiving_date=None,
                    average_days_between_receipts=None,
                ),
                monthly_totals=(),
            )

        total_quantity = sum(
            (r.quantity for r in eligible_records), Decimal("0")
        )
        total_subtotal = sum(
            (r.subtotal for r in eligible_records), Decimal("0")
        )

        average_quantity_per_line = (
            total_quantity / Decimal(line_count) if line_count > 0 else None
        )
        average_unit_price = (
            total_subtotal / total_quantity if total_quantity > 0 else None
        )

        prices = [r.unit_price for r in eligible_records]
        minimum_unit_price = min(prices) if prices else None
        maximum_unit_price = max(prices) if prices else None

        last_record = max(eligible_records, key=self._last_receiving_order_key)
        last_receiving = LastReceiving(
            event_date=last_record.event_date,  # type: ignore[arg-type]
            unit_price=last_record.unit_price,
            quantity=last_record.quantity,
            supplier_id=last_record.supplier_id,
            supplier_name=last_record.supplier_name,
            warehouse_id=last_record.warehouse_id,
            warehouse_name=last_record.warehouse_name,
            receiving_reference=last_record.receiving_reference,
            event_id=last_record.event_id,
            line_id=last_record.line_id,
        )

        receiving_frequency = self._calculate_frequency(eligible_records)
        monthly_totals = self._calculate_monthly_totals(eligible_records)

        return ReceivingHistoryResult(
            filters=filters,
            examined_count=examined_count,
            records=records,
            data_quality=data_quality,
            line_count=line_count,
            distinct_event_count=distinct_event_count,
            total_quantity=total_quantity,
            total_subtotal=total_subtotal,
            average_quantity_per_line=average_quantity_per_line,
            average_unit_price=average_unit_price,
            minimum_unit_price=minimum_unit_price,
            maximum_unit_price=maximum_unit_price,
            last_receiving=last_receiving,
            receiving_frequency=receiving_frequency,
            monthly_totals=monthly_totals,
        )

    @staticmethod
    def _calculate_frequency(
        eligible_records: tuple[PreparedReceivingEventLine, ...],
    ) -> ReceivingFrequency:
        distinct_events = {
            r.event_id for r in eligible_records if r.event_id is not None
        }
        event_count = len(distinct_events)
        line_count = len(eligible_records)

        distinct_dates = sorted(
            {r.event_date for r in eligible_records if r.event_date is not None}
        )
        first_date = distinct_dates[0] if distinct_dates else None
        last_date = distinct_dates[-1] if distinct_dates else None

        if len(distinct_dates) < 2 or first_date is None or last_date is None:
            average_days = None
        else:
            days_diff = Decimal((last_date - first_date).days)
            intervals = Decimal(len(distinct_dates) - 1)
            average_days = days_diff / intervals

        return ReceivingFrequency(
            event_count=event_count,
            line_count=line_count,
            first_receiving_date=first_date,
            last_receiving_date=last_date,
            average_days_between_receipts=average_days,
        )

    @staticmethod
    def _calculate_monthly_totals(
        eligible_records: tuple[PreparedReceivingEventLine, ...],
    ) -> tuple[MonthlyReceivingTotal, ...]:
        groups: dict[tuple[int, int], list[PreparedReceivingEventLine]] = (
            defaultdict(list)
        )
        for r in eligible_records:
            if r.year is not None and r.month is not None:
                groups[(r.year, r.month)].append(r)

        results: list[MonthlyReceivingTotal] = []
        for (year, month) in sorted(groups.keys()):
            month_lines = groups[(year, month)]
            event_count = len(
                {r.event_id for r in month_lines if r.event_id is not None}
            )
            line_count = len(month_lines)
            total_qty = sum((r.quantity for r in month_lines), Decimal("0"))
            total_sub = sum((r.subtotal for r in month_lines), Decimal("0"))
            avg_price = total_sub / total_qty if total_qty > 0 else None

            results.append(
                MonthlyReceivingTotal(
                    year=year,
                    month=month,
                    event_count=event_count,
                    line_count=line_count,
                    total_quantity=total_qty,
                    total_subtotal=total_sub,
                    average_unit_price=avg_price,
                )
            )

        return tuple(results)


analyze_receiving_history = ReceivingHistoryAnalytics().analyze
