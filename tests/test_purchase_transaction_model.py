from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric
from sqlalchemy.orm import DeclarativeBase

import app.models
from app.core.database import Base
from app.models.purchase_transaction import PurchaseTransaction


def test_model_imports_and_uses_existing_base():
    assert app.models.PurchaseTransaction is PurchaseTransaction
    assert issubclass(PurchaseTransaction, DeclarativeBase)
    assert PurchaseTransaction.__bases__[0] is Base


def test_table_name_and_primary_key():
    table = PurchaseTransaction.__table__

    assert table.name == "purchase_transactions"
    assert table.primary_key.columns.keys() == ["id"]


def test_master_data_relationships_and_foreign_keys():
    table = PurchaseTransaction.__table__
    expected_foreign_keys = {
        "supplier_id": "suppliers.id",
        "product_id": "products.id",
        "unit_id": "units.id",
        "branch_id": "branches.id",
        "warehouse_id": "warehouses.id",
    }

    assert set(PurchaseTransaction.__mapper__.relationships.keys()) == {
        "supplier",
        "product",
        "unit",
        "branch",
        "warehouse",
    }
    for column_name, target in expected_foreign_keys.items():
        foreign_key = next(
            foreign_key
            for foreign_key in table.foreign_keys
            if foreign_key.parent.name == column_name
        )
        assert foreign_key.target_fullname == target


def test_transaction_fields_and_destination_columns():
    columns = PurchaseTransaction.__table__.columns

    assert isinstance(columns["transaction_date"].type, Date)
    assert columns["reference"].type.length == 255
    assert isinstance(columns["quantity"].type, Numeric)
    assert isinstance(columns["unit_price"].type, Numeric)
    assert isinstance(columns["subtotal"].type, Numeric)
    assert columns["branch_id"].nullable is True
    assert columns["warehouse_id"].nullable is True
    assert columns["sub_warehouse_name"].nullable is True
    assert columns["destination_type"].nullable is True
    assert "destination_id" not in columns


def test_source_traceability_and_raw_source_fields():
    columns = PurchaseTransaction.__table__.columns

    assert {
        "source_file",
        "source_sheet",
        "source_row",
        "supplier_raw",
        "product_raw",
        "destination_raw",
        "unit_raw",
    } <= set(columns.keys())


def test_model_can_hold_transaction_and_raw_values():
    transaction = PurchaseTransaction(
        transaction_date=date(2026, 1, 15),
        reference="PO-001",
        quantity=Decimal("2.5"),
        unit_price=Decimal("10.00"),
        subtotal=Decimal("25.00"),
        destination_type="SUB_WAREHOUSE",
        sub_warehouse_name="Cold Storage",
        source_file="purchases.xlsx",
        source_sheet="January",
        source_row=4,
        supplier_raw="Supplier A",
        product_raw="Product A",
        destination_raw="Warehouse 1 / Cold Storage",
        unit_raw="Each",
    )

    assert transaction.transaction_date == date(2026, 1, 15)
    assert transaction.reference == "PO-001"
    assert transaction.quantity == Decimal("2.5")
    assert transaction.unit_price == Decimal("10.00")
    assert transaction.subtotal == Decimal("25.00")
    assert transaction.sub_warehouse_name == "Cold Storage"
    assert transaction.source_row == 4