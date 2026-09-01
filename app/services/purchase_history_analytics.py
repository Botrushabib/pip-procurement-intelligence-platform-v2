from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal
from app.models.branch import Branch
from app.models.product import Product
from app.models.purchase_transaction import PurchaseTransaction
from app.services.analytics_preparation import (
    AnalyticsDataQualityReport,
    AnalyticsPreparation,
    PreparedPurchaseTransaction,
)


@dataclass(frozen=True)
class PurchaseHistoryFilter:
    product_id: int | None = None
    category_id: int | None = None
    supplier_id: int | None = None
    unit_id: int | None = None
    company_id: int | None = None
    branch_id: int | None = None
    warehouse_id: int | None = None
    destination_type: str | None = None
    sub_warehouse_name: str | None = None
    start_month: date | None = None
    end_month: date | None = None


@dataclass(frozen=True)
class MonthlyPurchaseTotal:
    year: int
    month: int
    transaction_count: int
    total_quantity: Decimal
    total_subtotal: Decimal
    average_unit_price: Decimal | None


@dataclass(frozen=True)
class PurchaseFrequency:
    transaction_count: int
    first_purchase_date: date | None
    last_purchase_date: date | None
    average_days_between_purchase_dates: Decimal | None


@dataclass(frozen=True)
class LastPurchase:
    transaction_date: date
    unit_price: Decimal
    supplier_id: int | None
    supplier_name: str | None
    transaction_id: int | None


@dataclass(frozen=True)
class PurchaseHistoryResult:
    filters: PurchaseHistoryFilter
    examined_count: int
    records: tuple[PreparedPurchaseTransaction, ...]
    data_quality: AnalyticsDataQualityReport
    transaction_count: int
    total_quantity: Decimal
    total_subtotal: Decimal
    average_quantity: Decimal | None
    average_unit_price: Decimal | None
    minimum_unit_price: Decimal | None
    maximum_unit_price: Decimal | None
    last_purchase: LastPurchase | None
    purchase_frequency: PurchaseFrequency
    monthly_totals: tuple[MonthlyPurchaseTotal, ...]

    @property
    def last_purchase_date(self) -> date | None:
        return self.last_purchase.transaction_date if self.last_purchase else None

    @property
    def last_purchase_price(self) -> Decimal | None:
        return self.last_purchase.unit_price if self.last_purchase else None

    @property
    def last_supplier_id(self) -> int | None:
        return self.last_purchase.supplier_id if self.last_purchase else None

    @property
    def last_supplier_name(self) -> str | None:
        return self.last_purchase.supplier_name if self.last_purchase else None


class PurchaseHistoryAnalytics:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        preparation: AnalyticsPreparation | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.preparation = preparation or AnalyticsPreparation()

    def analyze(self, filters: PurchaseHistoryFilter | None = None) -> PurchaseHistoryResult:
        selected_filters = filters or PurchaseHistoryFilter()
        session = self.session_factory()
        try:
            transactions = session.scalars(
                select(PurchaseTransaction)
                .options(
                    joinedload(PurchaseTransaction.supplier),
                    joinedload(PurchaseTransaction.product).joinedload(Product.category),
                    joinedload(PurchaseTransaction.unit),
                    joinedload(PurchaseTransaction.branch).joinedload(Branch.company),
                    joinedload(PurchaseTransaction.warehouse),
                )
                .order_by(PurchaseTransaction.id)
            ).all()
        finally:
            session.close()
        prepared = self.preparation.prepare(transactions)
        records = tuple(
            record for record in prepared.eligible_records if self._matches(record, selected_filters)
        )
        return self._result(selected_filters, len(prepared.records), records, prepared.data_quality)

    @staticmethod
    def _matches(record: PreparedPurchaseTransaction, filters: PurchaseHistoryFilter) -> bool:
        if filters.product_id is not None and record.product_id != filters.product_id:
            return False
        if filters.category_id is not None and record.category_id != filters.category_id:
            return False
        if filters.supplier_id is not None and record.supplier_id != filters.supplier_id:
            return False
        if filters.unit_id is not None and record.unit_id != filters.unit_id:
            return False
        if filters.company_id is not None and record.company_id != filters.company_id:
            return False
        if filters.branch_id is not None and record.branch_id != filters.branch_id:
            return False
        if filters.warehouse_id is not None and record.warehouse_id != filters.warehouse_id:
            return False
        if filters.destination_type is not None and record.destination_type != filters.destination_type:
            return False
        if filters.sub_warehouse_name is not None and record.sub_warehouse_name != filters.sub_warehouse_name:
            return False
        if filters.start_month is not None and (
            record.transaction_date is None or record.transaction_date < filters.start_month
        ):
            return False
        if filters.end_month is not None and (
            record.transaction_date is None or record.transaction_date > filters.end_month
        ):
            return False
        return True

    @staticmethod
    def _result(
        filters: PurchaseHistoryFilter,
        examined_count: int,
        records: tuple[PreparedPurchaseTransaction, ...],
        data_quality: AnalyticsDataQualityReport,
    ) -> PurchaseHistoryResult:
        ordered_records = tuple(sorted(records, key=PurchaseHistoryAnalytics._record_order))
        transaction_count = len(ordered_records)
        total_quantity = sum((record.quantity for record in ordered_records), Decimal("0"))
        total_subtotal = sum(
            (record.subtotal for record in ordered_records if record.subtotal is not None),
            Decimal("0"),
        )
        prices = tuple(record.unit_price for record in ordered_records)
        last_record = max(ordered_records, key=PurchaseHistoryAnalytics._last_purchase_order, default=None)
        return PurchaseHistoryResult(
            filters=filters,
            examined_count=examined_count,
            records=ordered_records,
            data_quality=data_quality,
            transaction_count=transaction_count,
            total_quantity=total_quantity,
            total_subtotal=total_subtotal,
            average_quantity=total_quantity / transaction_count if transaction_count else None,
            average_unit_price=sum(prices, Decimal("0")) / transaction_count if transaction_count else None,
            minimum_unit_price=min(prices) if prices else None,
            maximum_unit_price=max(prices) if prices else None,
            last_purchase=PurchaseHistoryAnalytics._last_purchase(last_record),
            purchase_frequency=PurchaseHistoryAnalytics._frequency(ordered_records),
            monthly_totals=PurchaseHistoryAnalytics._monthly_totals(ordered_records),
        )

    @staticmethod
    def _record_order(record: PreparedPurchaseTransaction) -> tuple:
        return (
            record.transaction_date or date.min,
            record.transaction_id if record.transaction_id is not None else -1,
            record.source_file or "",
            record.source_sheet or "",
            record.source_row if record.source_row is not None else -1,
        )

    @staticmethod
    def _last_purchase_order(record: PreparedPurchaseTransaction) -> tuple:
        """Order by date, transaction ID, then source traceability and business values."""
        return (
            record.transaction_date,
            record.transaction_id if record.transaction_id is not None else -1,
            record.source_file or "",
            record.source_sheet or "",
            record.source_row if record.source_row is not None else -1,
            record.reference or "",
            record.supplier_id if record.supplier_id is not None else -1,
            record.quantity,
            record.unit_price,
            record.subtotal if record.subtotal is not None else Decimal("0"),
        )

    @staticmethod
    def _last_purchase(record: PreparedPurchaseTransaction | None) -> LastPurchase | None:
        if record is None:
            return None
        return LastPurchase(
            transaction_date=record.transaction_date,
            unit_price=record.unit_price,
            supplier_id=record.supplier_id,
            supplier_name=record.supplier_name,
            transaction_id=record.transaction_id,
        )

    @staticmethod
    def _frequency(records: tuple[PreparedPurchaseTransaction, ...]) -> PurchaseFrequency:
        dates = tuple(sorted({record.transaction_date for record in records}))
        average = None
        if len(dates) > 1:
            average = Decimal((dates[-1] - dates[0]).days) / Decimal(len(dates) - 1)
        return PurchaseFrequency(
            transaction_count=len(records),
            first_purchase_date=dates[0] if dates else None,
            last_purchase_date=dates[-1] if dates else None,
            average_days_between_purchase_dates=average,
        )

    @staticmethod
    def _monthly_totals(
        records: tuple[PreparedPurchaseTransaction, ...],
    ) -> tuple[MonthlyPurchaseTotal, ...]:
        grouped: dict[tuple[int, int], list[PreparedPurchaseTransaction]] = {}
        for record in records:
            grouped.setdefault((record.year, record.month), []).append(record)
        return tuple(
            MonthlyPurchaseTotal(
                year=year,
                month=month,
                transaction_count=len(month_records),
                total_quantity=sum((record.quantity for record in month_records), Decimal("0")),
                total_subtotal=sum(
                    (record.subtotal for record in month_records if record.subtotal is not None),
                    Decimal("0"),
                ),
                average_unit_price=sum(
                    (record.unit_price for record in month_records), Decimal("0")
                ) / len(month_records),
            )
            for (year, month), month_records in sorted(grouped.items())
        )