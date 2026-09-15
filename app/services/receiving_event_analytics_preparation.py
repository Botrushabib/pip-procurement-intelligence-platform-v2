from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Mapping

from app.services.receiving_event_query_service import (
    ReceivingEventLineReadDTO,
    ReceivingEventReadDTO,
)


@dataclass(frozen=True)
class ReceivingAnalyticsEligibility:
    has_event_date: bool
    has_product: bool
    has_quantity: bool
    has_unit_price: bool
    has_supplier: bool
    has_warehouse: bool

    @property
    def eligible_for_analytics(self) -> bool:
        return (
            self.has_event_date
            and self.has_product
            and self.has_quantity
            and self.has_unit_price
            and self.has_supplier
            and self.has_warehouse
        )


@dataclass(frozen=True)
class PreparedReceivingEventLine:
    event_id: int
    line_id: int
    line_number: int
    event_date: date | None
    year: int | None
    month: int | None
    receiving_reference: str
    company_id: int
    company_name: str | None
    supplier_id: int
    supplier_name: str | None
    warehouse_id: int
    warehouse_name: str | None
    product_id: int
    product_code: str | None
    product_name: str | None
    category_id: int | None
    category_name: str | None
    unit_id: int
    unit_name: str | None
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal
    source_file: str
    source_sheet: str
    source_row: int
    eligibility: ReceivingAnalyticsEligibility


@dataclass(frozen=True)
class ReceivingAnalyticsDataQualityReport:
    total_lines: int
    eligible_lines: int
    ineligible_lines: int
    missing_date_count: int
    missing_product_count: int
    missing_quantity_count: int
    missing_price_count: int
    missing_supplier_count: int
    missing_warehouse_count: int


@dataclass(frozen=True)
class ReceivingAnalyticsPreparationResult:
    records: tuple[PreparedReceivingEventLine, ...]
    data_quality: ReceivingAnalyticsDataQualityReport

    @property
    def eligible_records(self) -> tuple[PreparedReceivingEventLine, ...]:
        return tuple(
            record
            for record in self.records
            if record.eligibility.eligible_for_analytics
        )

    @property
    def ineligible_records(self) -> tuple[PreparedReceivingEventLine, ...]:
        return tuple(
            record
            for record in self.records
            if not record.eligibility.eligible_for_analytics
        )


@dataclass(frozen=True)
class ProductMasterData:
    code: str | None = None
    name: str | None = None
    category_id: int | None = None
    category_name: str | None = None


@dataclass(frozen=True)
class ReceivingMasterDataEnrichment:
    company_names: Mapping[int, str] = field(default_factory=dict)
    supplier_names: Mapping[int, str] = field(default_factory=dict)
    warehouse_names: Mapping[int, str] = field(default_factory=dict)
    unit_names: Mapping[int, str] = field(default_factory=dict)
    category_names: Mapping[int, str] = field(default_factory=dict)
    products: Mapping[int, ProductMasterData] = field(default_factory=dict)
    product_codes: Mapping[int, str] = field(default_factory=dict)
    product_names: Mapping[int, str] = field(default_factory=dict)
    product_categories: Mapping[int, int] = field(default_factory=dict)


class ReceivingEventAnalyticsPreparation:
    def prepare(
        self,
        events: Iterable[ReceivingEventReadDTO | Any],
        enrichment: ReceivingMasterDataEnrichment | None = None,
        *,
        company_names: Mapping[int, str] | None = None,
        supplier_names: Mapping[int, str] | None = None,
        warehouse_names: Mapping[int, str] | None = None,
        unit_names: Mapping[int, str] | None = None,
        category_names: Mapping[int, str] | None = None,
        products: Mapping[int, ProductMasterData] | None = None,
        product_codes: Mapping[int, str] | None = None,
        product_names: Mapping[int, str] | None = None,
        product_categories: Mapping[int, int] | None = None,
    ) -> ReceivingAnalyticsPreparationResult:
        resolved_enrichment = self._build_enrichment(
            enrichment=enrichment,
            company_names=company_names,
            supplier_names=supplier_names,
            warehouse_names=warehouse_names,
            unit_names=unit_names,
            category_names=category_names,
            products=products,
            product_codes=product_codes,
            product_names=product_names,
            product_categories=product_categories,
        )

        records_list: list[PreparedReceivingEventLine] = []
        for event in events:
            lines = getattr(event, "lines", ())
            for line in lines:
                record = self.prepare_line(event, line, resolved_enrichment)
                records_list.append(record)

        records = tuple(records_list)
        quality = self._calculate_data_quality(records)
        return ReceivingAnalyticsPreparationResult(
            records=records,
            data_quality=quality,
        )

    def prepare_line(
        self,
        event: ReceivingEventReadDTO | Any,
        line: ReceivingEventLineReadDTO | Any,
        enrichment: ReceivingMasterDataEnrichment | None = None,
    ) -> PreparedReceivingEventLine:
        resolved_enrichment = enrichment or ReceivingMasterDataEnrichment()

        event_date = getattr(event, "event_date", None)
        product_id = getattr(line, "product_id", None)
        quantity = getattr(line, "quantity", None)
        unit_price = getattr(line, "unit_price", None)
        supplier_id = getattr(event, "supplier_id", None)
        warehouse_id = getattr(event, "warehouse_id", None)
        company_id = getattr(event, "company_id", None)
        unit_id = getattr(line, "unit_id", None)

        has_event_date = isinstance(event_date, date)
        has_product = product_id is not None and product_id > 0
        has_quantity = quantity is not None and quantity > 0
        has_unit_price = unit_price is not None and unit_price >= 0
        has_supplier = supplier_id is not None and supplier_id > 0
        has_warehouse = warehouse_id is not None and warehouse_id > 0

        eligibility = ReceivingAnalyticsEligibility(
            has_event_date=has_event_date,
            has_product=has_product,
            has_quantity=has_quantity,
            has_unit_price=has_unit_price,
            has_supplier=has_supplier,
            has_warehouse=has_warehouse,
        )

        year = event_date.year if isinstance(event_date, date) else None
        month = event_date.month if isinstance(event_date, date) else None

        company_name = resolved_enrichment.company_names.get(company_id) if company_id is not None else None
        supplier_name = resolved_enrichment.supplier_names.get(supplier_id) if supplier_id is not None else None
        warehouse_name = resolved_enrichment.warehouse_names.get(warehouse_id) if warehouse_id is not None else None
        unit_name = resolved_enrichment.unit_names.get(unit_id) if unit_id is not None else None

        prod_master = resolved_enrichment.products.get(product_id) if product_id is not None else None
        product_code = (
            prod_master.code
            if prod_master and prod_master.code is not None
            else resolved_enrichment.product_codes.get(product_id) if product_id is not None else None
        )
        product_name = (
            prod_master.name
            if prod_master and prod_master.name is not None
            else resolved_enrichment.product_names.get(product_id) if product_id is not None else None
        )
        category_id = (
            prod_master.category_id
            if prod_master and prod_master.category_id is not None
            else resolved_enrichment.product_categories.get(product_id) if product_id is not None else None
        )
        category_name = (
            prod_master.category_name
            if prod_master and prod_master.category_name is not None
            else resolved_enrichment.category_names.get(category_id) if category_id is not None else None
        )

        return PreparedReceivingEventLine(
            event_id=getattr(event, "id", None),
            line_id=getattr(line, "id", None),
            line_number=getattr(line, "line_number", None),
            event_date=event_date if isinstance(event_date, date) else None,
            year=year,
            month=month,
            receiving_reference=getattr(event, "receiving_reference", ""),
            company_id=company_id,
            company_name=company_name,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            warehouse_id=warehouse_id,
            warehouse_name=warehouse_name,
            product_id=product_id,
            product_code=product_code,
            product_name=product_name,
            category_id=category_id,
            category_name=category_name,
            unit_id=unit_id,
            unit_name=unit_name,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=getattr(line, "subtotal", Decimal("0")),
            source_file=getattr(line, "source_file", ""),
            source_sheet=getattr(line, "source_sheet", ""),
            source_row=getattr(line, "source_row", 0),
            eligibility=eligibility,
        )

    @staticmethod
    def _calculate_data_quality(
        records: tuple[PreparedReceivingEventLine, ...],
    ) -> ReceivingAnalyticsDataQualityReport:
        total = len(records)
        eligible = sum(1 for r in records if r.eligibility.eligible_for_analytics)
        ineligible = total - eligible

        missing_date = sum(1 for r in records if not r.eligibility.has_event_date)
        missing_product = sum(1 for r in records if not r.eligibility.has_product)
        missing_quantity = sum(1 for r in records if not r.eligibility.has_quantity)
        missing_price = sum(1 for r in records if not r.eligibility.has_unit_price)
        missing_supplier = sum(1 for r in records if not r.eligibility.has_supplier)
        missing_warehouse = sum(1 for r in records if not r.eligibility.has_warehouse)

        return ReceivingAnalyticsDataQualityReport(
            total_lines=total,
            eligible_lines=eligible,
            ineligible_lines=ineligible,
            missing_date_count=missing_date,
            missing_product_count=missing_product,
            missing_quantity_count=missing_quantity,
            missing_price_count=missing_price,
            missing_supplier_count=missing_supplier,
            missing_warehouse_count=missing_warehouse,
        )

    @staticmethod
    def _build_enrichment(
        enrichment: ReceivingMasterDataEnrichment | None = None,
        *,
        company_names: Mapping[int, str] | None = None,
        supplier_names: Mapping[int, str] | None = None,
        warehouse_names: Mapping[int, str] | None = None,
        unit_names: Mapping[int, str] | None = None,
        category_names: Mapping[int, str] | None = None,
        products: Mapping[int, ProductMasterData] | None = None,
        product_codes: Mapping[int, str] | None = None,
        product_names: Mapping[int, str] | None = None,
        product_categories: Mapping[int, int] | None = None,
    ) -> ReceivingMasterDataEnrichment:
        base = enrichment or ReceivingMasterDataEnrichment()

        c_names = dict(base.company_names)
        if company_names:
            c_names.update(company_names)

        s_names = dict(base.supplier_names)
        if supplier_names:
            s_names.update(supplier_names)

        w_names = dict(base.warehouse_names)
        if warehouse_names:
            w_names.update(warehouse_names)

        u_names = dict(base.unit_names)
        if unit_names:
            u_names.update(unit_names)

        cat_names = dict(base.category_names)
        if category_names:
            cat_names.update(category_names)

        p_dict = dict(base.products)
        if products:
            p_dict.update(products)

        p_codes = dict(base.product_codes)
        if product_codes:
            p_codes.update(product_codes)

        p_names = dict(base.product_names)
        if product_names:
            p_names.update(product_names)

        p_cats = dict(base.product_categories)
        if product_categories:
            p_cats.update(product_categories)

        return ReceivingMasterDataEnrichment(
            company_names=c_names,
            supplier_names=s_names,
            warehouse_names=w_names,
            unit_names=u_names,
            category_names=cat_names,
            products=p_dict,
            product_codes=p_codes,
            product_names=p_names,
            product_categories=p_cats,
        )


prepare_receiving_events = ReceivingEventAnalyticsPreparation().prepare
