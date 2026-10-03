from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from app.services.receiving_category_intelligence import (
    ReceivingCategoryIntelligence,
    ReceivingCategoryIntelligenceRequest,
)
from app.services.receiving_event_analytics_preparation import (
    PreparedReceivingEventLine,
    ReceivingEventAnalyticsPreparation,
)
from app.services.receiving_event_query_service import (
    ReceivingEventQueryFilter,
    ReceivingEventQueryService,
)
from app.services.receiving_history_analytics import (
    ReceivingHistoryAnalytics,
    ReceivingHistoryFilter,
)
from app.services.receiving_price_intelligence import (
    ReceivingPriceIntelligence,
    ReceivingPriceIntelligenceRequest,
)
from app.services.receiving_supplier_comparative_intelligence import (
    ReceivingSupplierComparativeIntelligence,
    ReceivingSupplierComparisonRequest,
)
from app.services.receiving_supplier_intelligence import (
    ReceivingSupplierIntelligence,
    ReceivingSupplierIntelligenceRequest,
)
from app.services.receiving_trend_intelligence import (
    ReceivingTrendIntelligence,
    ReceivingTrendRequest,
)


router = APIRouter(prefix="/api/receiving", tags=["receiving analytics"])


def get_receiving_event_query_service() -> ReceivingEventQueryService:
    return ReceivingEventQueryService()


def get_receiving_event_analytics_preparation() -> ReceivingEventAnalyticsPreparation:
    return ReceivingEventAnalyticsPreparation()


def _matches_request(
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
    if request.date_from is not None and (
        record.event_date is None or record.event_date < request.date_from
    ):
        return False
    if request.date_to is not None and (
        record.event_date is None or record.event_date > request.date_to
    ):
        return False
    if request.reference is not None:
        reference = " ".join(request.reference.strip().split()).casefold()
        record_reference = " ".join(
            record.receiving_reference.strip().split()
        ).casefold()
        if record_reference != reference:
            return False
    return True


@router.get("/analytics")
def get_receiving_analytics(
    company_id: int | None = None,
    warehouse_id: int | None = None,
    supplier_id: int | None = None,
    product_id: int | None = None,
    category_id: int | None = None,
    unit_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    reference: str | None = None,
    query_service: ReceivingEventQueryService = Depends(
        get_receiving_event_query_service
    ),
    preparation: ReceivingEventAnalyticsPreparation = Depends(
        get_receiving_event_analytics_preparation
    ),
) -> dict[str, object]:
    request = ReceivingTrendRequest(
        company_id=company_id,
        warehouse_id=warehouse_id,
        supplier_id=supplier_id,
        product_id=product_id,
        category_id=category_id,
        unit_id=unit_id,
        date_from=date_from,
        date_to=date_to,
        reference=reference,
    )
    events = query_service.query(
        ReceivingEventQueryFilter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            supplier_id=supplier_id,
            date_from=date_from,
            date_to=date_to,
        )
    )
    all_records = preparation.prepare(events).records
    records = tuple(
        record for record in all_records if _matches_request(record, request)
    )

    history_result = ReceivingHistoryAnalytics(
        preparation=preparation,
        query_service=query_service,
    ).analyze(
        records=records,
        filters=ReceivingHistoryFilter(
            product_id=product_id,
            category_id=category_id,
            supplier_id=supplier_id,
            unit_id=unit_id,
            company_id=company_id,
            warehouse_id=warehouse_id,
            start_date=date_from,
            end_date=date_to,
        ),
    )
    trend_result = ReceivingTrendIntelligence().analyze(request, all_records)
    supplier_comparison = ReceivingSupplierComparativeIntelligence().analyze(
        ReceivingSupplierComparisonRequest(
            supplier_ids=(supplier_id,) if supplier_id is not None else None,
            product_id=product_id,
            category_id=category_id,
            unit_id=unit_id,
            company_id=company_id,
            warehouse_id=warehouse_id,
            date_from=date_from,
            date_to=date_to,
            reference=None,
        ),
        records,
    )

    price_result = None
    if product_id is not None:
        price_result = ReceivingPriceIntelligence(
            preparation=preparation,
            query_service=query_service,
        ).analyze(
            ReceivingPriceIntelligenceRequest(
                product_id=product_id,
                unit_id=unit_id,
                supplier_id=supplier_id,
                company_id=company_id,
                warehouse_id=warehouse_id,
                date_from=date_from,
                date_to=date_to,
                reference=None,
            ),
            records,
        )

    supplier_result = None
    if supplier_id is not None:
        supplier_result = ReceivingSupplierIntelligence(
            preparation=preparation,
            query_service=query_service,
        ).analyze(
            ReceivingSupplierIntelligenceRequest(
                supplier_id=supplier_id,
                product_id=product_id,
                unit_id=unit_id,
                company_id=company_id,
                warehouse_id=warehouse_id,
                date_from=date_from,
                date_to=date_to,
                reference=None,
            ),
            records,
        )

    category_result = None
    if category_id is not None:
        category_result = ReceivingCategoryIntelligence(
            preparation=preparation,
            query_service=query_service,
        ).analyze(
            ReceivingCategoryIntelligenceRequest(
                category_id=category_id,
                product_id=product_id,
                supplier_id=supplier_id,
                unit_id=unit_id,
                company_id=company_id,
                warehouse_id=warehouse_id,
                date_from=date_from,
                date_to=date_to,
                reference=None,
            ),
            records,
        )

    return {
        "summary": jsonable_encoder(
            {
                "examined_lines": history_result.examined_count,
                "eligible_lines": history_result.line_count,
                "distinct_event_count": history_result.distinct_event_count,
                "total_quantity": history_result.total_quantity,
                "total_spend": history_result.total_subtotal,
                "average_unit_price": history_result.average_unit_price,
                "minimum_unit_price": history_result.minimum_unit_price,
                "maximum_unit_price": history_result.maximum_unit_price,
            }
        ),
        "history": jsonable_encoder(
            {
                "last_receiving": history_result.last_receiving,
                "receiving_frequency": history_result.receiving_frequency,
                "monthly_totals": history_result.monthly_totals,
                "data_quality": history_result.data_quality,
            }
        ),
        "price": jsonable_encoder(price_result),
        "supplier": jsonable_encoder(supplier_result),
        "category": jsonable_encoder(category_result),
        "trend": jsonable_encoder(trend_result),
        "supplier_comparison": jsonable_encoder(supplier_comparison),
    }