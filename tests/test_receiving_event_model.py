from datetime import date
from decimal import Decimal

import app.models
from app.core.database import Base
from app.models.receiving_event import ReceivingEvent
from app.models.receiving_event_line import ReceivingEventLine


def test_receiving_models_are_registered_on_existing_base():
    assert app.models.ReceivingEvent is ReceivingEvent
    assert app.models.ReceivingEventLine is ReceivingEventLine
    assert ReceivingEvent.__bases__[0] is Base
    assert ReceivingEventLine.__bases__[0] is Base


def test_receiving_tables_and_foreign_keys():
    assert ReceivingEvent.__table__.name == "receiving_events"
    assert ReceivingEventLine.__table__.name == "receiving_event_lines"
    assert ReceivingEvent.__table__.primary_key.columns.keys() == ["id"]
    assert ReceivingEventLine.__table__.primary_key.columns.keys() == ["id"]

    event_targets = {
        foreign_key.parent.name: foreign_key.target_fullname
        for foreign_key in ReceivingEvent.__table__.foreign_keys
    }
    line_targets = {
        foreign_key.parent.name: foreign_key.target_fullname
        for foreign_key in ReceivingEventLine.__table__.foreign_keys
    }
    assert event_targets == {
        "company_id": "companies.id",
        "supplier_id": "suppliers.id",
        "warehouse_id": "warehouses.id",
    }
    assert line_targets == {
        "receiving_event_id": "receiving_events.id",
        "product_id": "products.id",
        "unit_id": "units.id",
    }


def test_receiving_event_and_line_hold_normalized_and_raw_values():
    event = ReceivingEvent(
        company_id=1,
        supplier_id=2,
        warehouse_id=3,
        receiving_reference="10560",
        event_date=date(2026, 8, 12),
        raw_reference="10560",
        raw_supplier="Supplier A",
        raw_destination="Main Stores/Stock",
        raw_date_1="2026-08-12",
        raw_date_2="2026-09-01",
        source_file="receiving.xlsx",
        source_sheet="Report",
        source_row=2,
    )
    line = ReceivingEventLine(
        receiving_event=event,
        line_number=1,
        product_id=4,
        unit_id=5,
        quantity=Decimal("2.5"),
        unit_price=Decimal("10.00"),
        subtotal=Decimal("25.00"),
        raw_product="[162017] Sugar Brown Portion TLT",
        raw_quantity="2.5",
        raw_unit="kg",
        raw_unit_price="10.00",
        raw_subtotal="25.00",
        raw_supplier="Supplier A",
        source_file="receiving.xlsx",
        source_sheet="Report",
        source_row=5,
    )
    event.lines.append(line)

    assert event.receiving_reference == "10560"
    assert event.event_date == date(2026, 8, 12)
    assert line.receiving_event is event
    assert line.line_number == 1
    assert line.raw_product == "[162017] Sugar Brown Portion TLT"