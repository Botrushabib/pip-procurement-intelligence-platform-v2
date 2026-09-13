from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReceivingEventLine(Base):
    __tablename__ = "receiving_event_lines"

    id: Mapped[int] = mapped_column(primary_key=True)

    receiving_event_id: Mapped[int] = mapped_column(
        ForeignKey("receiving_events.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    raw_product: Mapped[str | None] = mapped_column(String(255))
    raw_item_description: Mapped[str | None] = mapped_column(String(255))
    raw_reference: Mapped[str | None] = mapped_column(String(255))
    raw_quantity: Mapped[str | None] = mapped_column(String(255))
    raw_unit: Mapped[str | None] = mapped_column(String(255))
    raw_unit_price: Mapped[str | None] = mapped_column(String(255))
    raw_subtotal: Mapped[str | None] = mapped_column(String(255))
    raw_destination: Mapped[str | None] = mapped_column(String(255))
    raw_supplier: Mapped[str | None] = mapped_column(String(255))
    raw_date_1: Mapped[str | None] = mapped_column(String(255))
    raw_date_2: Mapped[str | None] = mapped_column(String(255))

    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    receiving_event: Mapped["ReceivingEvent"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()
    unit: Mapped["Unit"] = relationship()