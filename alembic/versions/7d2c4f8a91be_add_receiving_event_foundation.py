"""add receiving event foundation

Revision ID: 7d2c4f8a91be
Revises: 1b49bdbac57f
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d2c4f8a91be"
down_revision: Union[str, Sequence[str], None] = "1b49bdbac57f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "receiving_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("receiving_reference", sa.String(length=255), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("raw_reference", sa.String(length=255), nullable=True),
        sa.Column("raw_supplier", sa.String(length=255), nullable=True),
        sa.Column("raw_destination", sa.String(length=255), nullable=True),
        sa.Column("raw_date_1", sa.String(length=255), nullable=True),
        sa.Column("raw_date_2", sa.String(length=255), nullable=True),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_sheet", sa.String(length=255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receiving_events_company_id"), "receiving_events", ["company_id"], unique=False)
    op.create_index(op.f("ix_receiving_events_supplier_id"), "receiving_events", ["supplier_id"], unique=False)
    op.create_index(op.f("ix_receiving_events_warehouse_id"), "receiving_events", ["warehouse_id"], unique=False)
    op.create_index(op.f("ix_receiving_events_receiving_reference"), "receiving_events", ["receiving_reference"], unique=False)
    op.create_index(op.f("ix_receiving_events_event_date"), "receiving_events", ["event_date"], unique=False)

    op.create_table(
        "receiving_event_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receiving_event_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("unit_price", sa.Numeric(), nullable=False),
        sa.Column("subtotal", sa.Numeric(), nullable=False),
        sa.Column("raw_product", sa.String(length=255), nullable=True),
        sa.Column("raw_item_description", sa.String(length=255), nullable=True),
        sa.Column("raw_reference", sa.String(length=255), nullable=True),
        sa.Column("raw_quantity", sa.String(length=255), nullable=True),
        sa.Column("raw_unit", sa.String(length=255), nullable=True),
        sa.Column("raw_unit_price", sa.String(length=255), nullable=True),
        sa.Column("raw_subtotal", sa.String(length=255), nullable=True),
        sa.Column("raw_destination", sa.String(length=255), nullable=True),
        sa.Column("raw_supplier", sa.String(length=255), nullable=True),
        sa.Column("raw_date_1", sa.String(length=255), nullable=True),
        sa.Column("raw_date_2", sa.String(length=255), nullable=True),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_sheet", sa.String(length=255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["receiving_event_id"], ["receiving_events.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receiving_event_lines_receiving_event_id"), "receiving_event_lines", ["receiving_event_id"], unique=False)
    op.create_index(op.f("ix_receiving_event_lines_product_id"), "receiving_event_lines", ["product_id"], unique=False)
    op.create_index(op.f("ix_receiving_event_lines_unit_id"), "receiving_event_lines", ["unit_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_receiving_event_lines_unit_id"), table_name="receiving_event_lines")
    op.drop_index(op.f("ix_receiving_event_lines_product_id"), table_name="receiving_event_lines")
    op.drop_index(op.f("ix_receiving_event_lines_receiving_event_id"), table_name="receiving_event_lines")
    op.drop_table("receiving_event_lines")
    op.drop_index(op.f("ix_receiving_events_event_date"), table_name="receiving_events")
    op.drop_index(op.f("ix_receiving_events_receiving_reference"), table_name="receiving_events")
    op.drop_index(op.f("ix_receiving_events_warehouse_id"), table_name="receiving_events")
    op.drop_index(op.f("ix_receiving_events_supplier_id"), table_name="receiving_events")
    op.drop_index(op.f("ix_receiving_events_company_id"), table_name="receiving_events")
    op.drop_table("receiving_events")