from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ReceivingAnalyticsPreparationResult,
    ReceivingEventAnalyticsPreparation,
)
from app.services.receiving_event_query_service import (
    ReceivingEventQueryService,
)


class ReceivingCategoryDataSufficiency(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class ReceivingCategoryIntelligenceRequest:
    category_id: int
    product_id: int | None = None
    supplier_id: int | None = None
    unit_id: int | None = None
    company_id: int | None = None
    warehouse_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    reference: str | None = None


@dataclass(frozen=True)
class ReceivingCategoryObservation:
    event_id: int
    line_id: int
    line_number: int
    event_date: date
    category_id: int
    category_name: str | None
    product_id: int
    product_code: str | None
    product_name: str | None
    supplier_id: int
    supplier_name: str | None
    unit_id: int
    unit_name: str | None
    company_id: int
    company_name: str | None
    warehouse_id: int
    warehouse_name: str | None
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal
    receiving_reference: str
    source_file: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True)
class ReceivingCategorySummary:
    category_id: int
    category_name: str | None
    observation_count: int
    distinct_event_count: int
    distinct_product_count: int
    distinct_supplier_count: int
    distinct_receiving_date_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_unit_price: Decimal | None
    arithmetic_average_unit_price: Decimal | None
    min_unit_price: Decimal | None
    max_unit_price: Decimal | None
    price_spread: Decimal | None
    first_receiving_date: date | None
    latest_receiving_date: date | None
    average_days_between_receipts: Decimal | None


@dataclass(frozen=True)
class ReceivingCategoryMonthlyActivity:
    year: int
    month: int
    observation_count: int
    distinct_event_count: int
    distinct_product_count: int
    distinct_supplier_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_unit_price: Decimal | None


@dataclass(frozen=True)
class ReceivingCategoryProductSummary:
    product_id: int
    product_code: str | None
    product_name: str | None
    unit_id: int | None
    unit_name: str | None
    observation_count: int
    distinct_supplier_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_unit_price: Decimal | None
    arithmetic_average_unit_price: Decimal | None
    min_price: Decimal | None
    max_price: Decimal | None
    latest_price: Decimal | None
    first_receiving_date: date | None
    latest_receiving_date: date | None


@dataclass(frozen=True)
class ReceivingCategorySupplierSummary:
    supplier_id: int
    supplier_name: str | None
    observation_count: int
    distinct_event_count: int
    distinct_product_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_unit_price: Decimal | None
    arithmetic_average_unit_price: Decimal | None
    min_price: Decimal | None
    max_price: Decimal | None
    first_receiving_date: date | None
    latest_receiving_date: date | None


@dataclass(frozen=True)
class ReceivingCategoryDataQuality:
    examined_lines: int
    analytics_eligible_lines: int
    category_matched_lines: int
    missing_category_count: int
    missing_product_count: int
    missing_supplier_count: int
    missing_date_count: int
    missing_price_count: int
    missing_quantity_count: int
    missing_unit_count: int


@dataclass(frozen=True)
class ReceivingCategoryIntelligenceResult:
    request: ReceivingCategoryIntelligenceRequest
    sufficiency: ReceivingCategoryDataSufficiency
    observations: tuple[ReceivingCategoryObservation, ...]
    summary: ReceivingCategorySummary
    monthly_activity: tuple[ReceivingCategoryMonthlyActivity, ...]
    product_summaries: tuple[ReceivingCategoryProductSummary, ...]
    supplier_summaries: tuple[ReceivingCategorySupplierSummary, ...]
    data_quality: ReceivingCategoryDataQuality


class ReceivingCategoryIntelligence:
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
        request: ReceivingCategoryIntelligenceRequest,
        records: (
            Iterable[PreparedReceivingEventLine]
            | ReceivingAnalyticsPreparationResult
            | None
        ) = None,
    ) -> ReceivingCategoryIntelligenceResult:
        if records is None:
            raw_events = self.query_service.query()
            prep_result = self.preparation.prepare(raw_events)
            all_records = prep_result.records
        elif isinstance(records, ReceivingAnalyticsPreparationResult):
            all_records = records.records
        else:
            all_records = tuple(records)

        examined_lines = len(all_records)
        analytics_eligible_lines = sum(
            1 for r in all_records if r.eligibility.eligible_for_analytics
        )

        missing_category_count = sum(
            1 for r in all_records if r.category_id is None or r.category_id <= 0
        )
        missing_product_count = sum(
            1 for r in all_records if not r.eligibility.has_product
        )
        missing_supplier_count = sum(
            1 for r in all_records if not r.eligibility.has_supplier
        )
        missing_date_count = sum(
            1 for r in all_records if not r.eligibility.has_event_date
        )
        missing_price_count = sum(
            1 for r in all_records if not r.eligibility.has_unit_price
        )
        missing_quantity_count = sum(
            1 for r in all_records if not r.eligibility.has_quantity
        )
        missing_unit_count = sum(
            1 for r in all_records if r.unit_id is None
        )

        matched_records = [
            r
            for r in all_records
            if r.eligibility.eligible_for_analytics and self._matches(r, request)
        ]

        matched_records.sort(key=self._observation_order_key)

        observations = tuple(
            self._to_observation(r) for r in matched_records
        )
        category_matched_lines = len(observations)

        quality = ReceivingCategoryDataQuality(
            examined_lines=examined_lines,
            analytics_eligible_lines=analytics_eligible_lines,
            category_matched_lines=category_matched_lines,
            missing_category_count=missing_category_count,
            missing_product_count=missing_product_count,
            missing_supplier_count=missing_supplier_count,
            missing_date_count=missing_date_count,
            missing_price_count=missing_price_count,
            missing_quantity_count=missing_quantity_count,
            missing_unit_count=missing_unit_count,
        )

        sufficiency = (
            ReceivingCategoryDataSufficiency.AVAILABLE
            if category_matched_lines > 0
            else ReceivingCategoryDataSufficiency.INSUFFICIENT_DATA
        )

        summary = self._calculate_summary(request, observations)
        monthly_activity = self._calculate_monthly_activity(observations)
        product_summaries = self._calculate_product_summaries(observations)
        supplier_summaries = self._calculate_supplier_summaries(observations)

        return ReceivingCategoryIntelligenceResult(
            request=request,
            sufficiency=sufficiency,
            observations=observations,
            summary=summary,
            monthly_activity=monthly_activity,
            product_summaries=product_summaries,
            supplier_summaries=supplier_summaries,
            data_quality=quality,
        )

    @staticmethod
    def _matches(
        record: PreparedReceivingEventLine,
        request: ReceivingCategoryIntelligenceRequest,
    ) -> bool:
        if record.category_id is None or record.category_id != request.category_id:
            return False
        if request.product_id is not None and record.product_id != request.product_id:
            return False
        if (
            request.supplier_id is not None
            and record.supplier_id != request.supplier_id
        ):
            return False
        if request.unit_id is not None and record.unit_id != request.unit_id:
            return False
        if request.company_id is not None and record.company_id != request.company_id:
            return False
        if (
            request.warehouse_id is not None
            and record.warehouse_id != request.warehouse_id
        ):
            return False
        if request.date_from is not None and (
            record.event_date is None or record.event_date < request.date_from
        ):
            return False
        if request.date_to is not None and (
            record.event_date is None or record.event_date > request.date_to
        ):
            return False
        if (
            request.reference is not None
            and record.receiving_reference != request.reference
        ):
            return False
        return True

    @staticmethod
    def _observation_order_key(record: PreparedReceivingEventLine) -> tuple:
        return (
            record.event_date or date.min,
            record.event_id if record.event_id is not None else -1,
            record.line_number if record.line_number is not None else -1,
            record.line_id if record.line_id is not None else -1,
        )

    @staticmethod
    def _to_observation(
        record: PreparedReceivingEventLine,
    ) -> ReceivingCategoryObservation:
        return ReceivingCategoryObservation(
            event_id=record.event_id,
            line_id=record.line_id,
            line_number=record.line_number,
            event_date=record.event_date,  # type: ignore[arg-type]
            category_id=record.category_id,  # type: ignore[arg-type]
            category_name=record.category_name,
            product_id=record.product_id,
            product_code=record.product_code,
            product_name=record.product_name,
            supplier_id=record.supplier_id,
            supplier_name=record.supplier_name,
            unit_id=record.unit_id,
            unit_name=record.unit_name,
            company_id=record.company_id,
            company_name=record.company_name,
            warehouse_id=record.warehouse_id,
            warehouse_name=record.warehouse_name,
            quantity=record.quantity,
            unit_price=record.unit_price,
            subtotal=record.subtotal,
            receiving_reference=record.receiving_reference,
            source_file=record.source_file,
            source_sheet=record.source_sheet,
            source_row=record.source_row,
        )

    @classmethod
    def _calculate_summary(
        cls,
        request: ReceivingCategoryIntelligenceRequest,
        observations: tuple[ReceivingCategoryObservation, ...],
    ) -> ReceivingCategorySummary:
        observation_count = len(observations)
        if observation_count == 0:
            return ReceivingCategorySummary(
                category_id=request.category_id,
                category_name=None,
                observation_count=0,
                distinct_event_count=0,
                distinct_product_count=0,
                distinct_supplier_count=0,
                distinct_receiving_date_count=0,
                total_quantity=Decimal("0"),
                total_spend=Decimal("0"),
                weighted_average_unit_price=None,
                arithmetic_average_unit_price=None,
                min_unit_price=None,
                max_unit_price=None,
                price_spread=None,
                first_receiving_date=None,
                latest_receiving_date=None,
                average_days_between_receipts=None,
            )

        category_name = observations[0].category_name
        distinct_events = {obs.event_id for obs in observations}
        distinct_products = {obs.product_id for obs in observations}
        distinct_suppliers = {obs.supplier_id for obs in observations}
        distinct_dates = sorted({obs.event_date for obs in observations})

        total_quantity = sum((obs.quantity for obs in observations), Decimal("0"))
        total_spend = sum((obs.subtotal for obs in observations), Decimal("0"))

        weighted_avg = (
            total_spend / total_quantity if total_quantity > 0 else None
        )
        arithmetic_avg = (
            sum((obs.unit_price for obs in observations), Decimal("0"))
            / Decimal(observation_count)
            if observation_count > 0
            else None
        )

        prices = [obs.unit_price for obs in observations]
        min_price = min(prices)
        max_price = max(prices)
        price_spread = max_price - min_price

        first_date = distinct_dates[0]
        latest_date = distinct_dates[-1]

        if len(distinct_dates) >= 2:
            days_diff = Decimal((latest_date - first_date).days)
            intervals = Decimal(len(distinct_dates) - 1)
            avg_days = days_diff / intervals
        else:
            avg_days = None

        return ReceivingCategorySummary(
            category_id=request.category_id,
            category_name=category_name,
            observation_count=observation_count,
            distinct_event_count=len(distinct_events),
            distinct_product_count=len(distinct_products),
            distinct_supplier_count=len(distinct_suppliers),
            distinct_receiving_date_count=len(distinct_dates),
            total_quantity=total_quantity,
            total_spend=total_spend,
            weighted_average_unit_price=weighted_avg,
            arithmetic_average_unit_price=arithmetic_avg,
            min_unit_price=min_price,
            max_unit_price=max_price,
            price_spread=price_spread,
            first_receiving_date=first_date,
            latest_receiving_date=latest_date,
            average_days_between_receipts=avg_days,
        )

    @staticmethod
    def _calculate_monthly_activity(
        observations: tuple[ReceivingCategoryObservation, ...],
    ) -> tuple[ReceivingCategoryMonthlyActivity, ...]:
        groups: dict[tuple[int, int], list[ReceivingCategoryObservation]] = (
            defaultdict(list)
        )
        for obs in observations:
            groups[(obs.event_date.year, obs.event_date.month)].append(obs)

        results: list[ReceivingCategoryMonthlyActivity] = []
        for (year, month) in sorted(groups.keys()):
            month_obs = groups[(year, month)]
            obs_count = len(month_obs)
            event_count = len({obs.event_id for obs in month_obs})
            product_count = len({obs.product_id for obs in month_obs})
            supplier_count = len({obs.supplier_id for obs in month_obs})
            total_qty = sum((obs.quantity for obs in month_obs), Decimal("0"))
            total_spend = sum((obs.subtotal for obs in month_obs), Decimal("0"))
            weighted_avg = (
                total_spend / total_qty if total_qty > 0 else None
            )

            results.append(
                ReceivingCategoryMonthlyActivity(
                    year=year,
                    month=month,
                    observation_count=obs_count,
                    distinct_event_count=event_count,
                    distinct_product_count=product_count,
                    distinct_supplier_count=supplier_count,
                    total_quantity=total_qty,
                    total_spend=total_spend,
                    weighted_average_unit_price=weighted_avg,
                )
            )

        return tuple(results)

    @classmethod
    def _calculate_product_summaries(
        cls,
        observations: tuple[ReceivingCategoryObservation, ...],
    ) -> tuple[ReceivingCategoryProductSummary, ...]:
        groups: dict[
            tuple[int, int | None], list[ReceivingCategoryObservation]
        ] = defaultdict(list)
        for obs in observations:
            groups[(obs.product_id, obs.unit_id)].append(obs)

        sorted_keys = sorted(
            groups.keys(),
            key=lambda k: (k[0], k[1] if k[1] is not None else -1),
        )

        results: list[ReceivingCategoryProductSummary] = []
        for key in sorted_keys:
            prod_obs = groups[key]
            obs_count = len(prod_obs)
            sample = prod_obs[0]
            supplier_count = len({obs.supplier_id for obs in prod_obs})

            total_qty = sum((obs.quantity for obs in prod_obs), Decimal("0"))
            total_spend = sum((obs.subtotal for obs in prod_obs), Decimal("0"))

            weighted_avg = (
                total_spend / total_qty if total_qty > 0 else None
            )
            arithmetic_avg = (
                sum((obs.unit_price for obs in prod_obs), Decimal("0"))
                / Decimal(obs_count)
                if obs_count > 0
                else None
            )

            prices = [obs.unit_price for obs in prod_obs]
            min_price = min(prices)
            max_price = max(prices)

            prod_obs_sorted = sorted(
                prod_obs,
                key=lambda obs: (
                    obs.event_date,
                    obs.event_id,
                    obs.line_number,
                    obs.line_id,
                ),
            )
            latest_price = prod_obs_sorted[-1].unit_price
            first_date = prod_obs_sorted[0].event_date
            latest_date = prod_obs_sorted[-1].event_date

            results.append(
                ReceivingCategoryProductSummary(
                    product_id=key[0],
                    product_code=sample.product_code,
                    product_name=sample.product_name,
                    unit_id=key[1],
                    unit_name=sample.unit_name,
                    observation_count=obs_count,
                    distinct_supplier_count=supplier_count,
                    total_quantity=total_qty,
                    total_spend=total_spend,
                    weighted_average_unit_price=weighted_avg,
                    arithmetic_average_unit_price=arithmetic_avg,
                    min_price=min_price,
                    max_price=max_price,
                    latest_price=latest_price,
                    first_receiving_date=first_date,
                    latest_receiving_date=latest_date,
                )
            )

        return tuple(results)

    @classmethod
    def _calculate_supplier_summaries(
        cls,
        observations: tuple[ReceivingCategoryObservation, ...],
    ) -> tuple[ReceivingCategorySupplierSummary, ...]:
        groups: dict[int, list[ReceivingCategoryObservation]] = defaultdict(list)
        for obs in observations:
            groups[obs.supplier_id].append(obs)

        sorted_supplier_ids = sorted(groups.keys())

        results: list[ReceivingCategorySupplierSummary] = []
        for supp_id in sorted_supplier_ids:
            supp_obs = groups[supp_id]
            obs_count = len(supp_obs)
            sample = supp_obs[0]

            event_count = len({obs.event_id for obs in supp_obs})
            product_count = len({obs.product_id for obs in supp_obs})

            total_qty = sum((obs.quantity for obs in supp_obs), Decimal("0"))
            total_spend = sum((obs.subtotal for obs in supp_obs), Decimal("0"))

            weighted_avg = (
                total_spend / total_qty if total_qty > 0 else None
            )
            arithmetic_avg = (
                sum((obs.unit_price for obs in supp_obs), Decimal("0"))
                / Decimal(obs_count)
                if obs_count > 0
                else None
            )

            prices = [obs.unit_price for obs in supp_obs]
            min_price = min(prices)
            max_price = max(prices)

            supp_obs_sorted = sorted(
                supp_obs,
                key=lambda obs: (
                    obs.event_date,
                    obs.event_id,
                    obs.line_number,
                    obs.line_id,
                ),
            )
            first_date = supp_obs_sorted[0].event_date
            latest_date = supp_obs_sorted[-1].event_date

            results.append(
                ReceivingCategorySupplierSummary(
                    supplier_id=supp_id,
                    supplier_name=sample.supplier_name,
                    observation_count=obs_count,
                    distinct_event_count=event_count,
                    distinct_product_count=product_count,
                    total_quantity=total_qty,
                    total_spend=total_spend,
                    weighted_average_unit_price=weighted_avg,
                    arithmetic_average_unit_price=arithmetic_avg,
                    min_price=min_price,
                    max_price=max_price,
                    first_receiving_date=first_date,
                    latest_receiving_date=latest_date,
                )
            )

        return tuple(results)


analyze_receiving_category = ReceivingCategoryIntelligence().analyze
