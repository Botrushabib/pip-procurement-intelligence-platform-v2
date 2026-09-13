from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReceivingEvent(Base):
    __tablename__ = "receiving_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"), nullable=False, index=True
    )
    receiving_reference: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    raw_reference: Mapped[str | None] = mapped_column(String(255))
    raw_supplier: Mapped[str | None] = mapped_column(String(255))
    raw_destination: Mapped[str | None] = mapped_column(String(255))
    raw_date_1: Mapped[str | None] = mapped_column(String(255))
    raw_date_2: Mapped[str | None] = mapped_column(String(255))

    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row: Mapped[int | None] = mapped_column(Integer)

    company: Mapped["Company"] = relationship()
    supplier: Mapped["Supplier"] = relationship()
    warehouse: Mapped["Warehouse"] = relationship()
    lines: Mapped[list["ReceivingEventLine"]] = relationship(
        back_populates="receiving_event", cascade="all, delete-orphan"
    )