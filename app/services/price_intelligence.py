from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum

from app.services.analytics_preparation import PreparedPurchaseTransaction
from app.services.purchase_history_analytics import (
    PurchaseHistoryAnalytics,
    PurchaseHistoryFilter,
)


RECENT_TRANSACTION_COUNT = 3
TREND_PERIOD_TRANSACTION_COUNT = 3
ANOMALY_MINIMUM_TRANSACTION_COUNT = 3
ANOMALY_Z_SCORE_THRESHOLD = Decimal("2")


class DataSufficiency(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PriceTrend(str, Enum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PriceAnomalyStatus(str, Enum):
    ABOVE_EXPECTED_RANGE = "ABOVE_EXPECTED_RANGE"
    BELOW_EXPECTED_RANGE = "BELOW_EXPECTED_RANGE"
    NORMAL = "NORMAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PriceChangeStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class PriceConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class PriceIntelligenceRequest:
    product_id: int | None
    unit_id: int | None = None
    supplier_id: int | None = None
    company_id: int | None = None
    branch_id: int | None = None
    warehouse_id: int | None = None
    destination_type: str | None = None
    sub_warehouse_name: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    reference: str | None = None
    current_unit_price: Decimal | None = None


@dataclass(frozen=True)
class PriceObservation:
    transaction_id: int | None
    transaction_date: date
    unit_price: Decimal
    quantity: Decimal | None
    supplier_id: int | None
    supplier_name: str | None
    product_id: int
    product_name: str | None
    unit_id: int
    unit_name: str | None
    branch_id: int | None
    warehouse_id: int | None
    destination_type: str | None
    sub_warehouse_name: str | None
    source_file: str | None
    source_sheet: str | None
    source_row: int | None


@dataclass(frozen=True)
class PriceChange:
    status: PriceChangeStatus
    previous_price: Decimal | None
    current_price: Decimal | None
    absolute_change: Decimal | None
    percentage_change: Decimal | None
    reason: str


@dataclass(frozen=True)
class PriceAnomalyAssessment:
    status: PriceAnomalyStatus
    current_price: Decimal | None
    reference_average: Decimal | None
    standard_deviation: Decimal | None
    difference: Decimal | None
    percentage_difference: Decimal | None
    z_score: Decimal | None
    method: str
    reason: str


@dataclass(frozen=True)
class PriceDataQuality:
    examined_transactions: int
    purchase_history_eligible_transactions: int
    comparable_transactions: int
    missing_product_count: int
    missing_date_count: int
    missing_price_count: int
    missing_unit_count: int
    different_unit_excluded_count: int
    reference_excluded_count: int


@dataclass(frozen=True)
class PriceIntelligenceResult:
    request: PriceIntelligenceRequest
    observations: tuple[PriceObservation, ...]
    data_quality: PriceDataQuality
    comparable_transaction_count: int
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    average_price: Decimal | None
    median_price: Decimal | None
    price_range: Decimal | None
    recent_average_price: Decimal | None
    recent_average_status: DataSufficiency
    population_standard_deviation: Decimal | None
    volatility_status: DataSufficiency
    last_purchase_date: date | None
    last_purchase_price: Decimal | None
    last_supplier_id: int | None
    last_supplier_name: str | None
    price_change: PriceChange
    trend: PriceTrend
    anomaly: PriceAnomalyAssessment
    confidence: PriceConfidence


class PriceIntelligenceEngine:
    """Read-only price facts for one normalized product and exact unit.

    Comparable records share product_id and unit_id. The default recent average
    uses the three most recent comparable observations. Trend compares the mean
    of the latest three observations with the immediately previous three.
    Volatility is population standard deviation. Anomaly assessment uses a
    two-standard-deviation population z-score and requires three observations.
    """

    def __init__(self, purchase_history: PurchaseHistoryAnalytics | None = None) -> None:
        self.purchase_history = purchase_history or PurchaseHistoryAnalytics()

    def analyze(self, request: PriceIntelligenceRequest) -> PriceIntelligenceResult:
        history = self.purchase_history.analyze(
            PurchaseHistoryFilter(
                product_id=request.product_id,
                supplier_id=request.supplier_id,
                company_id=request.company_id,
                branch_id=request.branch_id,
                warehouse_id=request.warehouse_id,
                destination_type=request.destination_type,
                sub_warehouse_name=request.sub_warehouse_name,
                start_month=request.date_from,
                end_month=request.date_to,
            )
        )
        candidates = tuple(
            record for record in history.records if request.reference is None or record.reference == request.reference
        )
        selected_unit_id = request.unit_id or self._single_unit_id(candidates)
        comparable = tuple(
            record for record in candidates if selected_unit_id is not None and record.unit_id == selected_unit_id
        )
        observations = tuple(self._observation(record) for record in comparable)
        quality = PriceDataQuality(
            examined_transactions=history.examined_count,
            purchase_history_eligible_transactions=history.data_quality.eligible_transactions,
            comparable_transactions=len(observations),
            missing_product_count=history.data_quality.missing_product_count,
            missing_date_count=history.data_quality.missing_date_count,
            missing_price_count=history.data_quality.missing_price_count,
            missing_unit_count=sum(record.unit_id is None for record in candidates),
            different_unit_excluded_count=sum(
                record.unit_id is not None and record.unit_id != selected_unit_id for record in candidates
            ) if selected_unit_id is not None else sum(record.unit_id is not None for record in candidates),
            reference_excluded_count=len(history.records) - len(candidates),
        )
        return self._result(request, observations, quality)

    @staticmethod
    def _single_unit_id(records: tuple[PreparedPurchaseTransaction, ...]) -> int | None:
        unit_ids = {record.unit_id for record in records if record.unit_id is not None}
        return next(iter(unit_ids)) if len(unit_ids) == 1 else None

    @staticmethod
    def _observation(record: PreparedPurchaseTransaction) -> PriceObservation:
        return PriceObservation(
            transaction_id=record.transaction_id,
            transaction_date=record.transaction_date,
            unit_price=record.unit_price,
            quantity=record.quantity,
            supplier_id=record.supplier_id,
            supplier_name=record.supplier_name,
            product_id=record.product_id,
            product_name=record.product_name,
            unit_id=record.unit_id,
            unit_name=record.unit_name,
            branch_id=record.branch_id,
            warehouse_id=record.warehouse_id,
            destination_type=record.destination_type,
            sub_warehouse_name=record.sub_warehouse_name,
            source_file=record.source_file,
            source_sheet=record.source_sheet,
            source_row=record.source_row,
        )

    @classmethod
    def _result(
        cls,
        request: PriceIntelligenceRequest,
        observations: tuple[PriceObservation, ...],
        quality: PriceDataQuality,
    ) -> PriceIntelligenceResult:
        prices = tuple(observation.unit_price for observation in observations)
        count = len(prices)
        average = sum(prices, Decimal("0")) / count if count else None
        standard_deviation = cls._population_standard_deviation(prices, average)
        last = observations[-1] if observations else None
        recent_average = cls._recent_average(prices)
        return PriceIntelligenceResult(
            request=request,
            observations=observations,
            data_quality=quality,
            comparable_transaction_count=count,
            minimum_price=min(prices) if prices else None,
            maximum_price=max(prices) if prices else None,
            average_price=average,
            median_price=cls._median(prices),
            price_range=max(prices) - min(prices) if prices else None,
            recent_average_price=recent_average,
            recent_average_status=DataSufficiency.AVAILABLE if recent_average is not None else DataSufficiency.INSUFFICIENT_DATA,
            population_standard_deviation=standard_deviation,
            volatility_status=DataSufficiency.AVAILABLE if standard_deviation is not None else DataSufficiency.INSUFFICIENT_DATA,
            last_purchase_date=last.transaction_date if last else None,
            last_purchase_price=last.unit_price if last else None,
            last_supplier_id=last.supplier_id if last else None,
            last_supplier_name=last.supplier_name if last else None,
            price_change=cls._price_change(observations),
            trend=cls._trend(prices),
            anomaly=cls._anomaly(request.current_unit_price, average, standard_deviation, count),
            confidence=cls._confidence(observations),
        )

    @staticmethod
    def _median(prices: tuple[Decimal, ...]) -> Decimal | None:
        if not prices:
            return None
        ordered = tuple(sorted(prices))
        midpoint = len(ordered) // 2
        return ordered[midpoint] if len(ordered) % 2 else (ordered[midpoint - 1] + ordered[midpoint]) / 2

    @staticmethod
    def _recent_average(prices: tuple[Decimal, ...]) -> Decimal | None:
        if len(prices) < RECENT_TRANSACTION_COUNT:
            return None
        recent = prices[-RECENT_TRANSACTION_COUNT:]
        return sum(recent, Decimal("0")) / RECENT_TRANSACTION_COUNT

    @staticmethod
    def _population_standard_deviation(
        prices: tuple[Decimal, ...], average: Decimal | None
    ) -> Decimal | None:
        if len(prices) < 2 or average is None:
            return None
        variance = sum(((price - average) ** 2 for price in prices), Decimal("0")) / len(prices)
        with localcontext() as context:
            context.prec = max(context.prec, 28)
            return variance.sqrt()

    @staticmethod
    def _price_change(observations: tuple[PriceObservation, ...]) -> PriceChange:
        if len(observations) < 2:
            return PriceChange(PriceChangeStatus.UNAVAILABLE, None, None, None, None, "No previous comparable purchase is available.")
        previous = observations[-2].unit_price
        current = observations[-1].unit_price
        if previous == 0:
            return PriceChange(PriceChangeStatus.UNAVAILABLE, previous, current, current - previous, None, "Percentage change is unavailable because the previous comparable price is zero.")
        return PriceChange(PriceChangeStatus.AVAILABLE, previous, current, current - previous, (current - previous) / previous * Decimal("100"), "Change compares the two most recent comparable purchases.")

    @staticmethod
    def _trend(prices: tuple[Decimal, ...]) -> PriceTrend:
        period_size = TREND_PERIOD_TRANSACTION_COUNT
        if len(prices) < period_size * 2:
            return PriceTrend.INSUFFICIENT_DATA
        recent = sum(prices[-period_size:], Decimal("0")) / period_size
        previous = sum(prices[-period_size * 2:-period_size], Decimal("0")) / period_size
        if recent > previous:
            return PriceTrend.INCREASING
        if recent < previous:
            return PriceTrend.DECREASING
        return PriceTrend.STABLE

    @staticmethod
    def _anomaly(
        current_price: Decimal | None,
        average: Decimal | None,
        standard_deviation: Decimal | None,
        count: int,
    ) -> PriceAnomalyAssessment:
        method = "Population z-score with a two-standard-deviation threshold"
        if current_price is None:
            return PriceAnomalyAssessment(PriceAnomalyStatus.INSUFFICIENT_DATA, None, average, standard_deviation, None, None, None, method, "No current price was supplied for assessment.")
        if count < ANOMALY_MINIMUM_TRANSACTION_COUNT or average is None or standard_deviation is None:
            return PriceAnomalyAssessment(PriceAnomalyStatus.INSUFFICIENT_DATA, current_price, average, standard_deviation, None, None, None, method, "At least three comparable historical prices are required.")
        difference = current_price - average
        percentage = None if average == 0 else difference / average * Decimal("100")
        if standard_deviation == 0:
            status = PriceAnomalyStatus.NORMAL if difference == 0 else (PriceAnomalyStatus.ABOVE_EXPECTED_RANGE if difference > 0 else PriceAnomalyStatus.BELOW_EXPECTED_RANGE)
            return PriceAnomalyAssessment(status, current_price, average, standard_deviation, difference, percentage, None, method, "All comparable historical prices are identical." if status is PriceAnomalyStatus.NORMAL else "Current price differs from identical comparable historical prices.")
        z_score = difference / standard_deviation
        status = PriceAnomalyStatus.NORMAL
        if z_score >= ANOMALY_Z_SCORE_THRESHOLD:
            status = PriceAnomalyStatus.ABOVE_EXPECTED_RANGE
        elif z_score <= -ANOMALY_Z_SCORE_THRESHOLD:
            status = PriceAnomalyStatus.BELOW_EXPECTED_RANGE
        return PriceAnomalyAssessment(status, current_price, average, standard_deviation, difference, percentage, z_score, method, "Current price is within the configured historical z-score range." if status is PriceAnomalyStatus.NORMAL else "Current price is outside the configured historical z-score range.")

    @staticmethod
    def _confidence(observations: tuple[PriceObservation, ...]) -> PriceConfidence:
        count = len(observations)
        if count < 2:
            return PriceConfidence.INSUFFICIENT_DATA
        coverage_days = (observations[-1].transaction_date - observations[0].transaction_date).days
        if count >= 8 and coverage_days >= 90:
            return PriceConfidence.HIGH
        if count >= 5:
            return PriceConfidence.MEDIUM
        return PriceConfidence.LOW