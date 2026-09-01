from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.purchase_request import PurchaseRequestStatus


class PurchaseRequestLine(Base):
    __tablename__ = "purchase_request_lines"

    id: Mapped[int] = mapped_column(primary_key=True)

    request_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_requests.id"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), index=True
    )
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))

    requested_quantity: Mapped[Decimal | None] = mapped_column(Numeric)
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PurchaseRequestStatus.DRAFT.value
    )
    notes: Mapped[str | None] = mapped_column(String(1000))

    # Raw source values are preserved verbatim; they are not parsed or normalized here.
    raw_product: Mapped[str | None] = mapped_column(String(255))
    raw_unit: Mapped[str | None] = mapped_column(String(255))
    raw_quantity: Mapped[str | None] = mapped_column(String(255))
    raw_packaging: Mapped[str | None] = mapped_column(String(255))

    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str | None] = mapped_column(String(255))
    source_row: Mapped[int | None] = mapped_column(Integer)

    request: Mapped["PurchaseRequest"] = relationship(back_populates="lines")
    product: Mapped["Product | None"] = relationship()
    unit: Mapped["Unit | None"] = relationship()
