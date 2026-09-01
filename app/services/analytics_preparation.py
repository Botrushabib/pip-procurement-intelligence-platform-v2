from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.models.purchase_transaction import PurchaseTransaction


@dataclass(frozen=True)
class AnalyticsEligibility:
    has_transaction_date: bool
    has_product: bool
    has_quantity: bool
    has_unit_price: bool
    has_supplier: bool

    @property
    def eligible_for_purchase_history(self) -> bool:
        return (
            self.has_transaction_date
            and self.has_product
            and self.has_quantity
            and self.has_unit_price
        )


@dataclass(frozen=True)
class PreparedPurchaseTransaction:
    transaction_id: int | None
    transaction_date: date | None
    year: int | None
    month: int | None
    reference: str | None
    supplier_id: int | None
    supplier_name: str | None
    product_id: int | None
    product_code: str | None
    product_name: str | None
    category_id: int | None
    category_name: str | None
    unit_id: int | None
    unit_name: str | None
    company_id: int | None
    company_name: str | None
    branch_id: int | None
    branch_name: str | None
    warehouse_id: int | None
    warehouse_name: str | None
    sub_warehouse_name: str | None
    destination_type: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    subtotal: Decimal | None
    source_file: str | None
    source_sheet: str | None
    source_row: int | None
    eligibility: AnalyticsEligibility


@dataclass(frozen=True)
class AnalyticsDataQualityReport:
    total_transactions: int
    eligible_transactions: int
    ineligible_transactions: int
    missing_product_count: int
    missing_date_count: int
    missing_quantity_count: int
    missing_price_count: int
    missing_supplier_count: int


@dataclass(frozen=True)
class AnalyticsPreparationResult:
    records: tuple[PreparedPurchaseTransaction, ...]
    data_quality: AnalyticsDataQualityReport

    @property
    def eligible_records(self) -> tuple[PreparedPurchaseTransaction, ...]:
        return tuple(
            record
            for record in self.records
            if record.eligibility.eligible_for_purchase_history
        )

    @property
    def ineligible_records(self) -> tuple[PreparedPurchaseTransaction, ...]:
        return tuple(
            record
            for record in self.records
            if not record.eligibility.eligible_for_purchase_history
        )


class AnalyticsPreparation:
    def prepare(
        self,
        transactions: Iterable[PurchaseTransaction],
    ) -> AnalyticsPreparationResult:
        records = tuple(self.prepare_transaction(transaction) for transaction in transactions)
        quality = AnalyticsDataQualityReport(
            total_transactions=len(records),
            eligible_transactions=sum(
                record.eligibility.eligible_for_purchase_history for record in records
            ),
            ineligible_transactions=sum(
                not record.eligibility.eligible_for_purchase_history for record in records
            ),
            missing_product_count=sum(not record.eligibility.has_product for record in records),
            missing_date_count=sum(not record.eligibility.has_transaction_date for record in records),
            missing_quantity_count=sum(not record.eligibility.has_quantity for record in records),
            missing_price_count=sum(not record.eligibility.has_unit_price for record in records),
            missing_supplier_count=sum(not record.eligibility.has_supplier for record in records),
        )
        return AnalyticsPreparationResult(records=records, data_quality=quality)

    @staticmethod
    def prepare_transaction(transaction: PurchaseTransaction) -> PreparedPurchaseTransaction:
        product = transaction.product
        branch = transaction.branch
        warehouse = transaction.warehouse
        transaction_date = transaction.transaction_date
        eligibility = AnalyticsEligibility(
            has_transaction_date=transaction_date is not None,
            has_product=transaction.product_id is not None,
            has_quantity=transaction.quantity is not None,
            has_unit_price=transaction.unit_price is not None,
            has_supplier=transaction.supplier_id is not None,
        )
        return PreparedPurchaseTransaction(
            transaction_id=transaction.id,
            transaction_date=transaction_date,
            year=transaction_date.year if transaction_date else None,
            month=transaction_date.month if transaction_date else None,
            reference=transaction.reference,
            supplier_id=transaction.supplier_id,
            supplier_name=transaction.supplier.name if transaction.supplier else None,
            product_id=transaction.product_id,
            product_code=product.code if product else None,
            product_name=product.name if product else None,
            category_id=product.category_id if product else None,
            category_name=product.category.name if product and product.category else None,
            unit_id=transaction.unit_id,
            unit_name=transaction.unit.name if transaction.unit else None,
            company_id=branch.company_id if branch else None,
            company_name=branch.company.name if branch and branch.company else None,
            branch_id=transaction.branch_id,
            branch_name=branch.name if branch else None,
            warehouse_id=transaction.warehouse_id,
            warehouse_name=warehouse.name if warehouse else None,
            sub_warehouse_name=transaction.sub_warehouse_name,
            destination_type=transaction.destination_type,
            quantity=transaction.quantity,
            unit_price=transaction.unit_price,
            subtotal=transaction.subtotal,
            source_file=transaction.source_file,
            source_sheet=transaction.source_sheet,
            source_row=transaction.source_row,
            eligibility=eligibility,
        )


prepare_purchase_transactions = AnalyticsPreparation().prepare