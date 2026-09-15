from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
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


RECENT_TRANSACTION_COUNT = 3
TREND_PERIOD_OBSERVATION_COUNT = 3
ANOMALY_MINIMUM_OBSERVATION_COUNT = 3
ANOMALY_Z_SCORE_THRESHOLD = Decimal("2.0")
STABLE_PRICE_THRESHOLD = Decimal("0.01")


class ReceivingDataSufficiency(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ReceivingPriceTrend(str, Enum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ReceivingPriceAnomalyStatus(str, Enum):
    ABOVE_EXPECTED_RANGE = "ABOVE_EXPECTED_RANGE"
    BELOW_EXPECTED_RANGE = "BELOW_EXPECTED_RANGE"
    NORMAL = "NORMAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ReceivingPriceChangeStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ReceivingPriceConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class ReceivingPriceIntelligenceRequest:
    product_id: int
    unit_id: int | None = None
    supplier_id: int | None = None
    company_id: int | None = None
    warehouse_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    reference: str | None = None
    current_unit_price: Decimal | None = None


@dataclass(frozen=True)
class ReceivingPriceObservation:
    event_id: int
    line_id: int
    line_number: int
    event_date: date
    unit_price: Decimal
    quantity: Decimal
    subtotal: Decimal
    supplier_id: int
    supplier_name: str | None
    product_id: int
    product_code: str | None
    product_name: str | None
    unit_id: int
    unit_name: str | None
    company_id: int
    company_name: str | None
    warehouse_id: int
    warehouse_name: str | None
    receiving_reference: str
    source_file: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True)
class ReceivingPriceChange:
    status: ReceivingPriceChangeStatus
    previous_price: Decimal | None
    current_price: Decimal | None
    absolute_change: Decimal | None
    percentage_change: Decimal | None
    reason: str


@dataclass(frozen=True)
class ReceivingPriceAnomalyAssessment:
    status: ReceivingPriceAnomalyStatus
    current_price: Decimal | None
    reference_average: Decimal | None
    standard_deviation: Decimal | None
    difference: Decimal | None
    percentage_difference: Decimal | None
    z_score: Decimal | None
    method: str
    reason: str


@dataclass(frozen=True)
class ReceivingPriceDataQuality:
    examined_lines: int
    analytics_eligible_lines: int
    comparable_lines: int
    missing_product_count: int
    missing_date_count: int
    missing_price_count: int
    missing_unit_count: int


@dataclass(frozen=True)
class ReceivingPriceIntelligenceResult:
    request: ReceivingPriceIntelligenceRequest
    sufficiency: ReceivingDataSufficiency
    observations: tuple[ReceivingPriceObservation, ...]
    observation_count: int
    current_price: Decimal | None
    current_price_source: str
    latest_observed_price: Decimal | None
    previous_observed_price: Decimal | None
    weighted_average_price: Decimal | None
    arithmetic_average_price: Decimal | None
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    price_spread: Decimal | None
    standard_deviation: Decimal | None
    recent_average_price: Decimal | None
    trend: ReceivingPriceTrend
    price_change: ReceivingPriceChange
    anomaly: ReceivingPriceAnomalyAssessment
    confidence: ReceivingPriceConfidence
    data_quality: ReceivingPriceDataQuality


class ReceivingPriceIntelligence:
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
        request: ReceivingPriceIntelligenceRequest,
        records: (
            Iterable[PreparedReceivingEventLine]
            | ReceivingAnalyticsPreparationResult
            | None
        ) = None,
    ) -> ReceivingPriceIntelligenceResult:
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

        missing_product_count = sum(
            1 for r in all_records if not r.eligibility.has_product
        )
        missing_date_count = sum(
            1 for r in all_records if not r.eligibility.has_event_date
        )
        missing_price_count = sum(
            1 for r in all_records if not r.eligibility.has_unit_price
        )
        missing_unit_count = sum(
            1 for r in all_records if r.unit_id is None
        )

        comparable_records = [
            r
            for r in all_records
            if r.eligibility.eligible_for_analytics and self._matches(r, request)
        ]

        comparable_records.sort(key=self._observation_order_key)

        observations = tuple(
            self._to_observation(r) for r in comparable_records
        )
        comparable_lines = len(observations)

        quality = ReceivingPriceDataQuality(
            examined_lines=examined_lines,
            analytics_eligible_lines=analytics_eligible_lines,
            comparable_lines=comparable_lines,
            missing_product_count=missing_product_count,
            missing_date_count=missing_date_count,
            missing_price_count=missing_price_count,
            missing_unit_count=missing_unit_count,
        )

        return self._calculate_result(request, observations, quality)

    @staticmethod
    def _matches(
        record: PreparedReceivingEventLine,
        request: ReceivingPriceIntelligenceRequest,
    ) -> bool:
        if record.product_id != request.product_id:
            return False
        if request.unit_id is not None and record.unit_id != request.unit_id:
            return False
        if (
            request.supplier_id is not None
            and record.supplier_id != request.supplier_id
        ):
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
    ) -> ReceivingPriceObservation:
        return ReceivingPriceObservation(
            event_id=record.event_id,
            line_id=record.line_id,
            line_number=record.line_number,
            event_date=record.event_date,  # type: ignore[arg-type]
            unit_price=record.unit_price,
            quantity=record.quantity,
            subtotal=record.subtotal,
            supplier_id=record.supplier_id,
            supplier_name=record.supplier_name,
            product_id=record.product_id,
            product_code=record.product_code,
            product_name=record.product_name,
            unit_id=record.unit_id,
            unit_name=record.unit_name,
            company_id=record.company_id,
            company_name=record.company_name,
            warehouse_id=record.warehouse_id,
            warehouse_name=record.warehouse_name,
            receiving_reference=record.receiving_reference,
            source_file=record.source_file,
            source_sheet=record.source_sheet,
            source_row=record.source_row,
        )

    @classmethod
    def _calculate_result(
        cls,
        request: ReceivingPriceIntelligenceRequest,
        observations: tuple[ReceivingPriceObservation, ...],
        quality: ReceivingPriceDataQuality,
    ) -> ReceivingPriceIntelligenceResult:
        observation_count = len(observations)
        sufficiency = (
            ReceivingDataSufficiency.AVAILABLE
            if observation_count > 0
            else ReceivingDataSufficiency.INSUFFICIENT_DATA
        )

        latest_observed_price = (
            observations[-1].unit_price if observation_count > 0 else None
        )
        previous_observed_price = (
            observations[-2].unit_price if observation_count > 1 else None
        )

        if request.current_unit_price is not None:
            current_price = request.current_unit_price
            current_price_source = "REQUEST"
        elif latest_observed_price is not None:
            current_price = latest_observed_price
            current_price_source = "LATEST_RECEIPT"
        else:
            current_price = None
            current_price_source = "NONE"

        prices = [obs.unit_price for obs in observations]
        total_quantity = sum((obs.quantity for obs in observations), Decimal("0"))
        total_subtotal = sum((obs.subtotal for obs in observations), Decimal("0"))

        weighted_average_price = (
            total_subtotal / total_quantity if total_quantity > 0 else None
        )
        arithmetic_average_price = (
            sum(prices, Decimal("0")) / Decimal(observation_count)
            if observation_count > 0
            else None
        )

        minimum_price = min(prices) if prices else None
        maximum_price = max(prices) if prices else None
        price_spread = (
            maximum_price - minimum_price
            if minimum_price is not None and maximum_price is not None
            else None
        )

        standard_deviation = cls._population_standard_deviation(
            prices, arithmetic_average_price
        )
        recent_average_price = cls._recent_average(prices)
        trend = cls._calculate_trend(prices)
        price_change = cls._calculate_price_change(observations)
        anomaly = cls._calculate_anomaly(
            request=request,
            observations=observations,
            current_price=current_price,
        )
        confidence = cls._calculate_confidence(observations)

        return ReceivingPriceIntelligenceResult(
            request=request,
            sufficiency=sufficiency,
            observations=observations,
            observation_count=observation_count,
            current_price=current_price,
            current_price_source=current_price_source,
            latest_observed_price=latest_observed_price,
            previous_observed_price=previous_observed_price,
            weighted_average_price=weighted_average_price,
            arithmetic_average_price=arithmetic_average_price,
            minimum_price=minimum_price,
            maximum_price=maximum_price,
            price_spread=price_spread,
            standard_deviation=standard_deviation,
            recent_average_price=recent_average_price,
            trend=trend,
            price_change=price_change,
            anomaly=anomaly,
            confidence=confidence,
            data_quality=quality,
        )

    @staticmethod
    def _population_standard_deviation(
        prices: list[Decimal], average: Decimal | None
    ) -> Decimal | None:
        if len(prices) < 2 or average is None:
            return None
        variance = sum(((p - average) ** 2 for p in prices), Decimal("0")) / Decimal(
            len(prices)
        )
        with localcontext() as context:
            context.prec = max(context.prec, 28)
            return variance.sqrt()

    @staticmethod
    def _recent_average(prices: list[Decimal]) -> Decimal | None:
        if len(prices) < RECENT_TRANSACTION_COUNT:
            return None
        recent = prices[-RECENT_TRANSACTION_COUNT:]
        return sum(recent, Decimal("0")) / Decimal(RECENT_TRANSACTION_COUNT)

    @staticmethod
    def _calculate_trend(prices: list[Decimal]) -> ReceivingPriceTrend:
        if len(prices) < TREND_PERIOD_OBSERVATION_COUNT:
            return ReceivingPriceTrend.INSUFFICIENT_DATA
        recent = prices[-TREND_PERIOD_OBSERVATION_COUNT:]
        p1, p2, p3 = recent[0], recent[1], recent[2]

        if p3 > p2 > p1:
            return ReceivingPriceTrend.INCREASING
        if p3 < p2 < p1:
            return ReceivingPriceTrend.DECREASING

        mean_price = sum(recent, Decimal("0")) / Decimal(3)
        if mean_price > 0:
            rel_diff = (max(recent) - min(recent)) / mean_price
            if rel_diff <= STABLE_PRICE_THRESHOLD:
                return ReceivingPriceTrend.STABLE

        return ReceivingPriceTrend.STABLE

    @staticmethod
    def _calculate_price_change(
        observations: tuple[ReceivingPriceObservation, ...],
    ) -> ReceivingPriceChange:
        if len(observations) < 2:
            return ReceivingPriceChange(
                status=ReceivingPriceChangeStatus.UNAVAILABLE,
                previous_price=None,
                current_price=observations[0].unit_price if observations else None,
                absolute_change=None,
                percentage_change=None,
                reason="No previous comparable receipt is available.",
            )

        previous = observations[-2].unit_price
        current = observations[-1].unit_price
        diff = current - previous

        if previous == 0:
            return ReceivingPriceChange(
                status=ReceivingPriceChangeStatus.UNAVAILABLE,
                previous_price=previous,
                current_price=current,
                absolute_change=diff,
                percentage_change=None,
                reason="Percentage change is unavailable because the previous comparable price is zero.",
            )

        pct = (diff / previous) * Decimal("100")
        return ReceivingPriceChange(
            status=ReceivingPriceChangeStatus.AVAILABLE,
            previous_price=previous,
            current_price=current,
            absolute_change=diff,
            percentage_change=pct,
            reason="Change compares the two most recent comparable receipts.",
        )

    @classmethod
    def _calculate_anomaly(
        cls,
        request: ReceivingPriceIntelligenceRequest,
        observations: tuple[ReceivingPriceObservation, ...],
        current_price: Decimal | None,
    ) -> ReceivingPriceAnomalyAssessment:
        method = "Population z-score with a two-standard-deviation threshold"

        if current_price is None:
            return ReceivingPriceAnomalyAssessment(
                status=ReceivingPriceAnomalyStatus.INSUFFICIENT_DATA,
                current_price=None,
                reference_average=None,
                standard_deviation=None,
                difference=None,
                percentage_difference=None,
                z_score=None,
                method=method,
                reason="No current price was supplied or observed for assessment.",
            )

        if request.current_unit_price is not None:
            baseline_obs = observations
        else:
            baseline_obs = observations[:-1] if len(observations) > 0 else ()

        baseline_prices = [obs.unit_price for obs in baseline_obs]
        count = len(baseline_prices)

        if count < ANOMALY_MINIMUM_OBSERVATION_COUNT:
            avg = (
                sum(baseline_prices, Decimal("0")) / Decimal(count)
                if count > 0
                else None
            )
            std = cls._population_standard_deviation(baseline_prices, avg)
            return ReceivingPriceAnomalyAssessment(
                status=ReceivingPriceAnomalyStatus.INSUFFICIENT_DATA,
                current_price=current_price,
                reference_average=avg,
                standard_deviation=std,
                difference=current_price - avg if avg is not None else None,
                percentage_difference=None,
                z_score=None,
                method=method,
                reason="At least three comparable historical baseline receipts are required.",
            )

        ref_average = sum(baseline_prices, Decimal("0")) / Decimal(count)
        std_dev = (
            cls._population_standard_deviation(baseline_prices, ref_average)
            or Decimal("0")
        )

        diff = current_price - ref_average
        pct_diff = (
            (diff / ref_average * Decimal("100")) if ref_average != 0 else None
        )

        if std_dev == 0:
            if diff == 0:
                status = ReceivingPriceAnomalyStatus.NORMAL
                reason = "All comparable historical baseline prices are identical."
            elif diff > 0:
                status = ReceivingPriceAnomalyStatus.ABOVE_EXPECTED_RANGE
                reason = (
                    "Current price is higher than identical comparable baseline prices."
                )
            else:
                status = ReceivingPriceAnomalyStatus.BELOW_EXPECTED_RANGE
                reason = (
                    "Current price is lower than identical comparable baseline prices."
                )

            return ReceivingPriceAnomalyAssessment(
                status=status,
                current_price=current_price,
                reference_average=ref_average,
                standard_deviation=std_dev,
                difference=diff,
                percentage_difference=pct_diff,
                z_score=None,
                method=method,
                reason=reason,
            )

        z_score = diff / std_dev
        if z_score >= ANOMALY_Z_SCORE_THRESHOLD:
            status = ReceivingPriceAnomalyStatus.ABOVE_EXPECTED_RANGE
            reason = "Current price is above the historical z-score threshold."
        elif z_score <= -ANOMALY_Z_SCORE_THRESHOLD:
            status = ReceivingPriceAnomalyStatus.BELOW_EXPECTED_RANGE
            reason = "Current price is below the historical z-score threshold."
        else:
            status = ReceivingPriceAnomalyStatus.NORMAL
            reason = "Current price is within the configured historical z-score range."

        return ReceivingPriceAnomalyAssessment(
            status=status,
            current_price=current_price,
            reference_average=ref_average,
            standard_deviation=std_dev,
            difference=diff,
            percentage_difference=pct_diff,
            z_score=z_score,
            method=method,
            reason=reason,
        )

    @staticmethod
    def _calculate_confidence(
        observations: tuple[ReceivingPriceObservation, ...],
    ) -> ReceivingPriceConfidence:
        count = len(observations)
        if count == 0:
            return ReceivingPriceConfidence.INSUFFICIENT_DATA
        if count in (1, 2):
            return ReceivingPriceConfidence.LOW
        if count in (3, 4):
            return ReceivingPriceConfidence.MEDIUM

        distinct_months = {(obs.event_date.year, obs.event_date.month) for obs in observations}
        if len(distinct_months) >= 2:
            return ReceivingPriceConfidence.HIGH

        return ReceivingPriceConfidence.MEDIUM


analyze_receiving_price = ReceivingPriceIntelligence().analyze
