from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PurchaseTransaction(Base):
    __tablename__ = "purchase_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_date: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(255))

    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))

    quantity: Mapped[Decimal | None] = mapped_column(Numeric)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric)

    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"))
    sub_warehouse_name: Mapped[str | None] = mapped_column(String(255))
    destination_type: Mapped[str | None] = mapped_column(String(50))

    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str | None] = mapped_column(String(255))
    source_row: Mapped[int | None] = mapped_column(Integer)

    supplier_raw: Mapped[str | None] = mapped_column(String(255))
    product_raw: Mapped[str | None] = mapped_column(String(255))
    destination_raw: Mapped[str | None] = mapped_column(String(255))
    unit_raw: Mapped[str | None] = mapped_column(String(255))

    supplier: Mapped["Supplier | None"] = relationship()
    product: Mapped["Product | None"] = relationship()
    unit: Mapped["Unit | None"] = relationship()
    branch: Mapped["Branch | None"] = relationship()
    warehouse: Mapped["Warehouse | None"] = relationship()