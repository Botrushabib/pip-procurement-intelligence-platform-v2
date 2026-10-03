from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.receiving_analytics_api import (
    get_receiving_event_analytics_preparation,
    get_receiving_event_query_service,
)
from app.core.database import Base
from app.main import app
from app.services.receiving_event_analytics_preparation import (
    ReceivingEventAnalyticsPreparation,
)


class FakeReceivingEventQueryService:
    def __init__(self, events):
        self.events = tuple(events)
        self.filters = []

    def query(self, filters=None):
        self.filters.append(filters)
        return self.events


class EnrichedPreparation(ReceivingEventAnalyticsPreparation):
    def prepare(self, events, *args, **kwargs):
        kwargs["product_categories"] = {40: 50, 41: 51}
        return super().prepare(events, *args, **kwargs)


def event(
    *,
    event_id,
    company_id,
    warehouse_id,
    supplier_id,
    product_id,
    unit_id,
    reference,
    event_date,
):
    receiving_line = SimpleNamespace(
        id=event_id * 10,
        line_number=1,
        product_id=product_id,
        unit_id=unit_id,
        quantity=Decimal("10"),
        unit_price=Decimal("5"),
        subtotal=Decimal("50"),
        source_file="receipts.xlsx",
        source_sheet="Sheet1",
        source_row=event_id + 1,
    )
    return SimpleNamespace(
        id=event_id,
        company_id=company_id,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        receiving_reference=reference,
        event_date=event_date,
        source_file="receipts.xlsx",
        source_sheet="Sheet1",
        source_row=event_id + 1,
        lines=(receiving_line,),
    )


@pytest.fixture
def api_services():
    service = FakeReceivingEventQueryService(
        [
            event(
                event_id=1,
                company_id=10,
                warehouse_id=20,
                supplier_id=30,
                product_id=40,
                unit_id=60,
                reference="  rec   alpha ",
                event_date=date(2026, 1, 15),
            ),
            event(
                event_id=2,
                company_id=11,
                warehouse_id=21,
                supplier_id=31,
                product_id=41,
                unit_id=61,
                reference="REC-BETA",
                event_date=date(2026, 1, 16),
            ),
        ]
    )
    app.dependency_overrides[get_receiving_event_query_service] = lambda: service
    app.dependency_overrides[
        get_receiving_event_analytics_preparation
    ] = EnrichedPreparation
    yield service
    app.dependency_overrides.clear()


def test_analytics_endpoint_is_registered_and_read_only():
    assert "get" in app.openapi()["paths"]["/api/receiving/analytics"]
    response_schema = app.openapi()["components"]["schemas"][
        "ReceivingAnalyticsResponse"
    ]["properties"]
    assert set(response_schema) == {
        "summary",
        "history",
        "price",
        "supplier",
        "category",
        "trend",
        "supplier_comparison",
    }
    response = TestClient(app).post("/api/receiving/analytics")
    assert response.status_code == 405


def test_analytics_returns_existing_results_and_is_read_only(api_services):
    response = TestClient(app).get(
        "/api/receiving/analytics",
        params={
            "company_id": 10,
            "warehouse_id": 20,
            "supplier_id": 30,
            "product_id": 40,
            "category_id": 50,
            "unit_id": 60,
            "date_from": "2026-01-15",
            "date_to": "2026-01-15",
            "reference": "REC ALPHA",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "summary",
        "history",
        "price",
        "supplier",
        "category",
        "trend",
        "supplier_comparison",
    }
    assert body["summary"]["eligible_lines"] == 1
    assert body["summary"]["total_spend"] == 50
    assert len(body["price"]["observations"]) == 1
    assert len(body["supplier"]["observations"]) == 1
    assert len(body["category"]["observations"]) == 1
    assert len(body["trend"]["observations"]) == 1
    assert len(body["supplier_comparison"]["observations"]) == 1
    assert len(api_services.filters) == 1


@pytest.mark.parametrize(
    ("filter_name", "filter_value", "expected_event_id"),
    [
        ("company_id", 10, 1),
        ("warehouse_id", 20, 1),
        ("supplier_id", 30, 1),
        ("product_id", 40, 1),
        ("category_id", 50, 1),
        ("unit_id", 60, 1),
        ("date_from", "2026-01-16", 2),
        ("date_to", "2026-01-15", 1),
        ("reference", "REC ALPHA", 1),
    ],
)
def test_analytics_filters_are_applied_independently(
    api_services, filter_name, filter_value, expected_event_id
):
    response = TestClient(app).get(
        "/api/receiving/analytics", params={filter_name: filter_value}
    )

    assert response.status_code == 200
    assert [item["event_id"] for item in response.json()["trend"]["observations"]] == [
        expected_event_id
    ]


def test_empty_analytics_response_contains_no_data_results(api_services):
    api_services.events = ()

    response = TestClient(app).get("/api/receiving/analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["examined_lines"] == 0
    assert body["summary"]["eligible_lines"] == 0
    assert body["history"]["monthly_totals"] == []
    assert body["history"]["last_receiving"] is None
    assert body["price"] is None
    assert body["supplier"] is None
    assert body["category"] is None
    assert body["trend"]["observations"] == []
    assert body["trend"]["monthly_trends"] == []
    assert body["trend"]["product_monthly_trends"] == []
    assert body["trend"]["supplier_monthly_trends"] == []
    assert body["trend"]["category_monthly_trends"] == []
    assert body["trend"]["quality"]["examined_lines"] == 0
    assert body["supplier_comparison"]["observations"] == []
    assert body["supplier_comparison"]["supplier_summaries"] == []
    assert body["supplier_comparison"]["supplier_product_comparisons"] == []
    assert body["supplier_comparison"]["product_price_comparisons"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"company_id": "0"},
        {"product_id": "-1"},
        {"date_from": "not-a-date"},
        {"date_from": "2026-02-01", "date_to": "2026-01-01"},
        {"reference": "   "},
    ],
)
def test_invalid_filters_return_safe_validation_errors(api_services, params):
    response = TestClient(app).get("/api/receiving/analytics", params=params)

    assert response.status_code == 422
    assert "detail" in response.json()
    assert "ReceivingEventQueryService" not in response.text
    assert "Traceback" not in response.text


def test_no_matching_records_keep_the_response_contract(api_services):
    response = TestClient(app).get(
        "/api/receiving/analytics", params={"product_id": 999}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "summary",
        "history",
        "price",
        "supplier",
        "category",
        "trend",
        "supplier_comparison",
    }
    assert body["summary"]["eligible_lines"] == 0
    assert body["price"]["observations"] == []
    assert body["price"]["observation_count"] == 0
    assert body["trend"]["observations"] == []


def test_api_adds_no_database_models_or_tables():
    assert set(Base.metadata.tables) == {
        "branches",
        "categories",
        "companies",
        "products",
        "purchase_request_lines",
        "purchase_requests",
        "purchase_transactions",
        "receiving_event_lines",
        "receiving_events",
        "suppliers",
        "units",
        "warehouses",
    }