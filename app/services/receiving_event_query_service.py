from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal
from app.models.receiving_event import ReceivingEvent
from app.models.receiving_event_line import ReceivingEventLine


@dataclass(frozen=True)
class ReceivingEventQueryFilter:
    event_id: int | None = None
    company_id: int | None = None
    supplier_id: int | None = None
    warehouse_id: int | None = None
    receiving_reference: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None


# Backwards-compatible / ergonomic alias
ReceivingEventFilter = ReceivingEventQueryFilter


@dataclass(frozen=True)
class ReceivingEventLineReadDTO:
    id: int
    receiving_event_id: int
    line_number: int
    product_id: int
    unit_id: int
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal
    raw_product: str | None
    raw_item_description: str | None
    raw_reference: str | None
    raw_quantity: str | None
    raw_unit: str | None
    raw_unit_price: str | None
    raw_subtotal: str | None
    raw_destination: str | None
    raw_supplier: str | None
    raw_date_1: str | None
    raw_date_2: str | None
    source_file: str
    source_sheet: str
    source_row: int


# Backwards-compatible / ergonomic alias
ReceivingEventLineRead = ReceivingEventLineReadDTO


@dataclass(frozen=True)
class ReceivingEventReadDTO:
    id: int
    company_id: int
    supplier_id: int
    warehouse_id: int
    receiving_reference: str
    event_date: date
    raw_reference: str | None
    raw_supplier: str | None
    raw_destination: str | None
    raw_date_1: str | None
    raw_date_2: str | None
    source_file: str
    source_sheet: str
    source_row: int | None
    lines: tuple[ReceivingEventLineReadDTO, ...] = ()


# Backwards-compatible / ergonomic alias
ReceivingEventRead = ReceivingEventReadDTO


class ReceivingEventQueryService:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.session_factory = session_factory

    def query(
        self,
        filters: ReceivingEventQueryFilter | None = None,
    ) -> tuple[ReceivingEventReadDTO, ...]:
        stmt = (
            select(ReceivingEvent)
            .options(selectinload(ReceivingEvent.lines))
            .order_by(
                ReceivingEvent.event_date.asc(),
                ReceivingEvent.receiving_reference.asc(),
                ReceivingEvent.id.asc(),
            )
        )

        if filters is not None:
            if filters.event_id is not None:
                stmt = stmt.where(ReceivingEvent.id == filters.event_id)
            if filters.company_id is not None:
                stmt = stmt.where(ReceivingEvent.company_id == filters.company_id)
            if filters.supplier_id is not None:
                stmt = stmt.where(ReceivingEvent.supplier_id == filters.supplier_id)
            if filters.warehouse_id is not None:
                stmt = stmt.where(ReceivingEvent.warehouse_id == filters.warehouse_id)
            if filters.receiving_reference is not None:
                stmt = stmt.where(
                    ReceivingEvent.receiving_reference == filters.receiving_reference
                )
            if filters.date_from is not None:
                stmt = stmt.where(ReceivingEvent.event_date >= filters.date_from)
            if filters.date_to is not None:
                stmt = stmt.where(ReceivingEvent.event_date <= filters.date_to)
            if filters.source_file is not None:
                stmt = stmt.where(ReceivingEvent.source_file == filters.source_file)
            if filters.source_sheet is not None:
                stmt = stmt.where(ReceivingEvent.source_sheet == filters.source_sheet)
            if filters.source_row is not None:
                stmt = stmt.where(ReceivingEvent.source_row == filters.source_row)

        session = self.session_factory()
        try:
            events = session.scalars(stmt).all()
            return tuple(self._to_dto(event) for event in events)
        finally:
            session.close()

    def get_by_id(self, event_id: int) -> ReceivingEventReadDTO | None:
        results = self.query(ReceivingEventQueryFilter(event_id=event_id))
        return results[0] if results else None

    def _to_line_dto(self, line: ReceivingEventLine) -> ReceivingEventLineReadDTO:
        return ReceivingEventLineReadDTO(
            id=line.id,
            receiving_event_id=line.receiving_event_id,
            line_number=line.line_number,
            product_id=line.product_id,
            unit_id=line.unit_id,
            quantity=line.quantity,
            unit_price=line.unit_price,
            subtotal=line.subtotal,
            raw_product=line.raw_product,
            raw_item_description=line.raw_item_description,
            raw_reference=line.raw_reference,
            raw_quantity=line.raw_quantity,
            raw_unit=line.raw_unit,
            raw_unit_price=line.raw_unit_price,
            raw_subtotal=line.raw_subtotal,
            raw_destination=line.raw_destination,
            raw_supplier=line.raw_supplier,
            raw_date_1=line.raw_date_1,
            raw_date_2=line.raw_date_2,
            source_file=line.source_file,
            source_sheet=line.source_sheet,
            source_row=line.source_row,
        )

    def _to_dto(self, event: ReceivingEvent) -> ReceivingEventReadDTO:
        sorted_lines = sorted(
            event.lines,
            key=lambda line: (line.line_number, line.id),
        )
        return ReceivingEventReadDTO(
            id=event.id,
            company_id=event.company_id,
            supplier_id=event.supplier_id,
            warehouse_id=event.warehouse_id,
            receiving_reference=event.receiving_reference,
            event_date=event.event_date,
            raw_reference=event.raw_reference,
            raw_supplier=event.raw_supplier,
            raw_destination=event.raw_destination,
            raw_date_1=event.raw_date_1,
            raw_date_2=event.raw_date_2,
            source_file=event.source_file,
            source_sheet=event.source_sheet,
            source_row=event.source_row,
            lines=tuple(self._to_line_dto(line) for line in sorted_lines),
        )
