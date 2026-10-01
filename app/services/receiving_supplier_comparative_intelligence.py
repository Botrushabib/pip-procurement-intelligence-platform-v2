from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Iterable

from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
)


class ReceivingSupplierComparativeDataSufficiency(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class SupplierPricePosition(str, Enum):
    LOWEST = "LOWEST"
    ABOVE_LOWEST = "ABOVE_LOWEST"
    HIGHEST = "HIGHEST"


@dataclass(frozen=True)
class ReceivingSupplierComparisonRequest:
    supplier_ids: tuple[int, ...] | None = None
    product_id: int | None = None
    category_id: int | None = None
    unit_id: int | None = None
    company_id: int | None = None
    warehouse_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    reference: str | None = None


@dataclass(frozen=True)
class ReceivingSupplierComparisonObservation:
    event_id: int
    line_id: int
    line_number: int
    event_date: date
    supplier_id: int
    supplier_name: str | None
    product_id: int
    product_code: str | None
    product_name: str | None
    category_id: int | None
    category_name: str | None
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
class ReceivingSupplierComparativeSummary:
    supplier_id: int
    supplier_name: str | None
    observation_count: int
    distinct_event_count: int
    distinct_product_count: int
    distinct_category_count: int
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
class ReceivingSupplierProductComparison:
    product_id: int
    product_code: str | None
    product_name: str | None
    unit_id: int | None
    unit_name: str | None
    supplier_id: int
    supplier_name: str | None
    observation_count: int
    distinct_event_count: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_average_unit_price: Decimal | None
    arithmetic_average_unit_price: Decimal | None
    min_unit_price: Decimal | None
    max_unit_price: Decimal | None
    price_spread: Decimal | None
    latest_price: Decimal | None
    first_receiving_date: date | None
    latest_receiving_date: date | None
    price_position: SupplierPricePosition | None = None
    price_difference_vs_lowest: Decimal | None = None
    price_difference_percentage_vs_lowest: Decimal | None = None


@dataclass(frozen=True)
class ReceivingSupplierPriceComparison:
    product_id: int
    product_code: str | None
    product_name: str | None
    unit_id: int | None
    unit_name: str | None
    supplier_count: int
    lowest_weighted_average_price: Decimal | None
    highest_weighted_average_price: Decimal | None
    price_spread: Decimal | None
    lowest_price_supplier_id: int | None
    lowest_price_supplier_name: str | None
    highest_price_supplier_id: int | None
    highest_price_supplier_name: str | None


@dataclass(frozen=True)
class ReceivingSupplierComparativeDataQuality:
    examined_lines: int
    analytics_eligible_lines: int
    matched_supplier_lines: int
    missing_supplier_count: int
    missing_product_count: int
    missing_category_count: int
    missing_unit_count: int
    missing_date_count: int
    missing_price_count: int
    missing_quantity_count: int


@dataclass(frozen=True)
class ReceivingSupplierComparativeIntelligenceResult:
    request: ReceivingSupplierComparisonRequest
    sufficiency: ReceivingSupplierComparativeDataSufficiency
    observations: tuple[ReceivingSupplierComparisonObservation, ...]
    supplier_summaries: tuple[ReceivingSupplierComparativeSummary, ...]
    supplier_product_comparisons: tuple[ReceivingSupplierProductComparison, ...]
    product_price_comparisons: tuple[ReceivingSupplierPriceComparison, ...]
    data_quality: ReceivingSupplierComparativeDataQuality


class ReceivingSupplierComparativeIntelligence:
    def analyze(
        self,
        request: ReceivingSupplierComparisonRequest,
        records: Iterable[PreparedReceivingEventLine],
    ) -> ReceivingSupplierComparativeIntelligenceResult:
        all_records = tuple(records)

        examined_lines = len(all_records)
        analytics_eligible_lines = sum(
            1 for r in all_records if r.eligibility.eligible_for_analytics
        )

        missing_supplier_count = sum(
            1 for r in all_records if r.supplier_id is None or r.supplier_id <= 0
        )
        missing_product_count = sum(
            1 for r in all_records if r.product_id is None or r.product_id <= 0
        )
        missing_category_count = sum(
            1 for r in all_records if r.category_id is None or r.category_id <= 0
        )
        missing_unit_count = sum(
            1 for r in all_records if r.unit_id is None or r.unit_id <= 0
        )
        missing_date_count = sum(
            1 for r in all_records if r.event_date is None
        )
        missing_price_count = sum(
            1 for r in all_records if not self._is_valid_unit_price(r.unit_price)
        )
        missing_quantity_count = sum(
            1 for r in all_records if not self._is_valid_quantity(r.quantity)
        )

        matched_records = [
            r
            for r in all_records
            if (
                r.eligibility.eligible_for_analytics
                and self._has_valid_comparison_values(r)
                and self._matches(r, request)
            )
        ]

        matched_records.sort(key=self._observation_order_key)

        observations = tuple(
            self._to_observation(r) for r in matched_records
        )
        matched_supplier_lines = len(observations)

        quality = ReceivingSupplierComparativeDataQuality(
            examined_lines=examined_lines,
            analytics_eligible_lines=analytics_eligible_lines,
            matched_supplier_lines=matched_supplier_lines,
            missing_supplier_count=missing_supplier_count,
            missing_product_count=missing_product_count,
            missing_category_count=missing_category_count,
            missing_unit_count=missing_unit_count,
            missing_date_count=missing_date_count,
            missing_price_count=missing_price_count,
            missing_quantity_count=missing_quantity_count,
        )

        sufficiency = (
            ReceivingSupplierComparativeDataSufficiency.AVAILABLE
            if matched_supplier_lines > 0
            else ReceivingSupplierComparativeDataSufficiency.INSUFFICIENT_DATA
        )

        supplier_summaries = self._calculate_supplier_summaries(observations)
        product_price_comparisons, supplier_product_comparisons = (
            self._calculate_product_and_supplier_comparisons(observations)
        )

        return ReceivingSupplierComparativeIntelligenceResult(
            request=request,
            sufficiency=sufficiency,
            observations=observations,
            supplier_summaries=supplier_summaries,
            supplier_product_comparisons=supplier_product_comparisons,
            product_price_comparisons=product_price_comparisons,
            data_quality=quality,
        )

    @staticmethod
    def _matches(
        record: PreparedReceivingEventLine,
        request: ReceivingSupplierComparisonRequest,
    ) -> bool:
        if record.supplier_id is None or record.supplier_id <= 0:
            return False
        if request.supplier_ids == ():
            return False
        if request.supplier_ids is not None:
            if record.supplier_id not in request.supplier_ids:
                return False
        if request.product_id is not None and record.product_id != request.product_id:
            return False
        if (
            request.category_id is not None
            and record.category_id != request.category_id
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
            and ReceivingSupplierComparativeIntelligence._normalize_reference(
                record.receiving_reference
            )
            != ReceivingSupplierComparativeIntelligence._normalize_reference(
                request.reference
            )
        ):
            return False
        return True

    @staticmethod
    def _normalize_reference(value: object) -> str:
        return " ".join(str(value).strip().split()).casefold()

    @staticmethod
    def _is_valid_quantity(value: object) -> bool:
        if value is None:
            return False
        try:
            return value > 0  # type: ignore[operator]
        except TypeError:
            return False

    @staticmethod
    def _is_valid_unit_price(value: object) -> bool:
        if value is None:
            return False
        try:
            return value >= 0  # type: ignore[operator]
        except TypeError:
            return False

    @classmethod
    def _has_valid_comparison_values(
        cls, record: PreparedReceivingEventLine
    ) -> bool:
        return (
            record.supplier_id is not None
            and record.supplier_id > 0
            and record.product_id is not None
            and record.product_id > 0
            and record.category_id is not None
            and record.category_id > 0
            and record.unit_id is not None
            and record.unit_id > 0
            and record.event_date is not None
            and cls._is_valid_quantity(record.quantity)
            and cls._is_valid_unit_price(record.unit_price)
        )

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
    ) -> ReceivingSupplierComparisonObservation:
        return ReceivingSupplierComparisonObservation(
            event_id=record.event_id,
            line_id=record.line_id,
            line_number=record.line_number,
            event_date=record.event_date,  # type: ignore[arg-type]
            supplier_id=record.supplier_id,
            supplier_name=record.supplier_name,
            product_id=record.product_id,
            product_code=record.product_code,
            product_name=record.product_name,
            category_id=record.category_id,
            category_name=record.category_name,
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
    def _calculate_supplier_summaries(
        cls,
        observations: tuple[ReceivingSupplierComparisonObservation, ...],
    ) -> tuple[ReceivingSupplierComparativeSummary, ...]:
        groups: dict[
            int, list[ReceivingSupplierComparisonObservation]
        ] = defaultdict(list)
        for obs in observations:
            groups[obs.supplier_id].append(obs)

        sorted_supplier_ids = sorted(groups.keys())

        results: list[ReceivingSupplierComparativeSummary] = []
        for supp_id in sorted_supplier_ids:
            supp_obs = groups[supp_id]
            obs_count = len(supp_obs)
            sample = supp_obs[0]

            distinct_events = {obs.event_id for obs in supp_obs}
            distinct_products = {obs.product_id for obs in supp_obs}
            distinct_categories = {
                obs.category_id for obs in supp_obs if obs.category_id is not None
            }
            distinct_dates = sorted({obs.event_date for obs in supp_obs})

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
            price_spread = max_price - min_price

            first_date = distinct_dates[0]
            latest_date = distinct_dates[-1]

            if len(distinct_dates) >= 2:
                days_diff = Decimal((latest_date - first_date).days)
                intervals = Decimal(len(distinct_dates) - 1)
                avg_days = days_diff / intervals
            else:
                avg_days = None

            results.append(
                ReceivingSupplierComparativeSummary(
                    supplier_id=supp_id,
                    supplier_name=sample.supplier_name,
                    observation_count=obs_count,
                    distinct_event_count=len(distinct_events),
                    distinct_product_count=len(distinct_products),
                    distinct_category_count=len(distinct_categories),
                    distinct_receiving_date_count=len(distinct_dates),
                    total_quantity=total_qty,
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
            )

        return tuple(results)

    @classmethod
    def _calculate_product_and_supplier_comparisons(
        cls,
        observations: tuple[ReceivingSupplierComparisonObservation, ...],
    ) -> tuple[
        tuple[ReceivingSupplierPriceComparison, ...],
        tuple[ReceivingSupplierProductComparison, ...],
    ]:
        product_unit_groups: dict[
            tuple[int, int | None],
            dict[int, list[ReceivingSupplierComparisonObservation]],
        ] = defaultdict(lambda: defaultdict(list))

        for obs in observations:
            product_unit_groups[(obs.product_id, obs.unit_id)][
                obs.supplier_id
            ].append(obs)

        sorted_pu_keys = sorted(
            product_unit_groups.keys(),
            key=lambda k: (k[0], k[1] if k[1] is not None else -1),
        )

        product_price_comparisons: list[ReceivingSupplierPriceComparison] = []
        supplier_product_comparisons: list[ReceivingSupplierProductComparison] = []

        for pu_key in sorted_pu_keys:
            product_id, unit_id = pu_key
            supp_dict = product_unit_groups[pu_key]

            supplier_data_list: list[dict] = []
            for supp_id in sorted(supp_dict.keys()):
                sp_obs = supp_dict[supp_id]
                obs_count = len(sp_obs)
                sample = sp_obs[0]

                distinct_events = len({obs.event_id for obs in sp_obs})
                total_qty = sum((obs.quantity for obs in sp_obs), Decimal("0"))
                total_spend = sum((obs.subtotal for obs in sp_obs), Decimal("0"))

                weighted_avg = (
                    total_spend / total_qty if total_qty > 0 else None
                )
                arithmetic_avg = (
                    sum((obs.unit_price for obs in sp_obs), Decimal("0"))
                    / Decimal(obs_count)
                    if obs_count > 0
                    else None
                )

                prices = [obs.unit_price for obs in sp_obs]
                min_price = min(prices)
                max_price = max(prices)
                price_spread = max_price - min_price

                sp_obs_sorted = sorted(
                    sp_obs,
                    key=lambda obs: (
                        obs.event_date,
                        obs.event_id,
                        obs.line_number,
                        obs.line_id,
                    ),
                )
                latest_price = sp_obs_sorted[-1].unit_price
                first_date = sp_obs_sorted[0].event_date
                latest_date = sp_obs_sorted[-1].event_date

                supplier_data_list.append(
                    {
                        "product_id": product_id,
                        "product_code": sample.product_code,
                        "product_name": sample.product_name,
                        "unit_id": unit_id,
                        "unit_name": sample.unit_name,
                        "supplier_id": supp_id,
                        "supplier_name": sample.supplier_name,
                        "observation_count": obs_count,
                        "distinct_event_count": distinct_events,
                        "total_quantity": total_qty,
                        "total_spend": total_spend,
                        "weighted_average_unit_price": weighted_avg,
                        "arithmetic_average_unit_price": arithmetic_avg,
                        "min_unit_price": min_price,
                        "max_unit_price": max_price,
                        "price_spread": price_spread,
                        "latest_price": latest_price,
                        "first_receiving_date": first_date,
                        "latest_receiving_date": latest_date,
                    }
                )

            valid_weighted_suppliers = [
                sd
                for sd in supplier_data_list
                if sd["weighted_average_unit_price"] is not None
            ]

            if valid_weighted_suppliers:
                min_w_price = min(
                    sd["weighted_average_unit_price"]
                    for sd in valid_weighted_suppliers
                )
                max_w_price = max(
                    sd["weighted_average_unit_price"]
                    for sd in valid_weighted_suppliers
                )
                price_spread_cross = max_w_price - min_w_price

                lowest_suppliers = [
                    sd
                    for sd in valid_weighted_suppliers
                    if sd["weighted_average_unit_price"] == min_w_price
                ]
                lowest_suppliers.sort(key=lambda sd: sd["supplier_id"])
                lowest_sup = lowest_suppliers[0]

                highest_suppliers = [
                    sd
                    for sd in valid_weighted_suppliers
                    if sd["weighted_average_unit_price"] == max_w_price
                ]
                highest_suppliers.sort(key=lambda sd: sd["supplier_id"])
                highest_sup = highest_suppliers[0]

                lowest_w_price = min_w_price
                highest_w_price = max_w_price
                lowest_id = lowest_sup["supplier_id"]
                lowest_name = lowest_sup["supplier_name"]
                highest_id = highest_sup["supplier_id"]
                highest_name = highest_sup["supplier_name"]
            else:
                lowest_w_price = None
                highest_w_price = None
                price_spread_cross = None
                lowest_id = None
                lowest_name = None
                highest_id = None
                highest_name = None

            sample_first = supplier_data_list[0]
            product_price_comparisons.append(
                ReceivingSupplierPriceComparison(
                    product_id=product_id,
                    product_code=sample_first["product_code"],
                    product_name=sample_first["product_name"],
                    unit_id=unit_id,
                    unit_name=sample_first["unit_name"],
                    supplier_count=len(supplier_data_list),
                    lowest_weighted_average_price=lowest_w_price,
                    highest_weighted_average_price=highest_w_price,
                    price_spread=price_spread_cross,
                    lowest_price_supplier_id=lowest_id,
                    lowest_price_supplier_name=lowest_name,
                    highest_price_supplier_id=highest_id,
                    highest_price_supplier_name=highest_name,
                )
            )

            for sd in supplier_data_list:
                w_price = sd["weighted_average_unit_price"]
                if w_price is not None and lowest_w_price is not None:
                    diff_vs_lowest = w_price - lowest_w_price
                    pct_vs_lowest = (
                        (diff_vs_lowest / lowest_w_price * Decimal("100"))
                        if lowest_w_price != 0
                        else None
                    )

                    if len(supplier_data_list) == 1:
                        position = SupplierPricePosition.LOWEST
                    elif w_price == lowest_w_price and w_price == highest_w_price:
                        position = SupplierPricePosition.LOWEST
                    elif w_price == lowest_w_price:
                        position = SupplierPricePosition.LOWEST
                    elif w_price == highest_w_price:
                        position = SupplierPricePosition.HIGHEST
                    else:
                        position = SupplierPricePosition.ABOVE_LOWEST
                else:
                    diff_vs_lowest = None
                    pct_vs_lowest = None
                    position = None

                supplier_product_comparisons.append(
                    ReceivingSupplierProductComparison(
                        product_id=sd["product_id"],
                        product_code=sd["product_code"],
                        product_name=sd["product_name"],
                        unit_id=sd["unit_id"],
                        unit_name=sd["unit_name"],
                        supplier_id=sd["supplier_id"],
                        supplier_name=sd["supplier_name"],
                        observation_count=sd["observation_count"],
                        distinct_event_count=sd["distinct_event_count"],
                        total_quantity=sd["total_quantity"],
                        total_spend=sd["total_spend"],
                        weighted_average_unit_price=sd["weighted_average_unit_price"],
                        arithmetic_average_unit_price=sd["arithmetic_average_unit_price"],
                        min_unit_price=sd["min_unit_price"],
                        max_unit_price=sd["max_unit_price"],
                        price_spread=sd["price_spread"],
                        latest_price=sd["latest_price"],
                        first_receiving_date=sd["first_receiving_date"],
                        latest_receiving_date=sd["latest_receiving_date"],
                        price_position=position,
                        price_difference_vs_lowest=diff_vs_lowest,
                        price_difference_percentage_vs_lowest=pct_vs_lowest,
                    )
                )

        return tuple(product_price_comparisons), tuple(supplier_product_comparisons)


analyze_receiving_supplier_comparison = (
    ReceivingSupplierComparativeIntelligence().analyze
)
