from datetime import date
from decimal import Decimal

from app.models.branch import Branch
from app.models.category import Category
from app.models.company import Company
from app.models.product import Product
from app.models.purchase_transaction import PurchaseTransaction
from app.models.supplier import Supplier
from app.models.unit import Unit
from app.models.warehouse import Warehouse
from app.services.analytics_preparation import AnalyticsPreparation


def make_transaction(**changes):
    company = Company(id=1, name="Company A", code="COMPANY_A")
    category = Category(id=2, name="Category A", code="CATEGORY_A")
    unit = Unit(id=3, name="Kilogram", code="KG")
    supplier = Supplier(id=4, name="Supplier A", code="SUPPLIER_A")
    branch = Branch(id=5, company_id=company.id, name="Branch A", code="BRANCH_A")
    warehouse = Warehouse(id=6, branch_id=branch.id, name="Warehouse A", code="WAREHOUSE_A")
    product = Product(id=7, code="PRODUCT_A", name="Product A", category_id=category.id, unit_id=unit.id)
    product.category = category
    product.unit = unit
    branch.company = company
    warehouse.branch = branch
    transaction = PurchaseTransaction(
        id=8,
        transaction_date=date(2026, 8, 15),
        reference="PO-001",
        supplier_id=supplier.id,
        product_id=product.id,
        unit_id=unit.id,
        quantity=Decimal("2.500"),
        unit_price=Decimal("10.125"),
        subtotal=Decimal("25.3125"),
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        sub_warehouse_name="Cold Storage",
        destination_type="WAREHOUSE",
        source_file="purchases.xlsx",
        source_sheet="August",
        source_row=9,
        supplier_raw="Supplier Raw",
        product_raw="Product Raw",
        destination_raw="Destination Raw",
        unit_raw="Unit Raw",
    )
    transaction.supplier = supplier
    transaction.product = product
    transaction.unit = unit
    transaction.branch = branch
    transaction.warehouse = warehouse
    for field, value in changes.items():
        setattr(transaction, field, value)
    return transaction


def test_preparation_derives_normalized_dimensions_and_traceability():
    result = AnalyticsPreparation().prepare([make_transaction()])

    record = result.records[0]
    assert (record.year, record.month) == (2026, 8)
    assert (record.product_code, record.product_name, record.category_name) == ("PRODUCT_A", "Product A", "Category A")
    assert (record.supplier_name, record.unit_name, record.company_name) == ("Supplier A", "Kilogram", "Company A")
    assert (record.branch_name, record.warehouse_name, record.sub_warehouse_name) == ("Branch A", "Warehouse A", "Cold Storage")
    assert (record.source_file, record.source_sheet, record.source_row) == ("purchases.xlsx", "August", 9)
    assert record.eligibility.eligible_for_purchase_history is True


def test_preparation_reports_missing_fields_without_discarding_transactions():
    missing = make_transaction(
        transaction_date=None,
        product_id=None,
        quantity=None,
        unit_price=None,
        supplier_id=None,
    )

    result = AnalyticsPreparation().prepare([missing])

    assert len(result.records) == 1
    assert result.eligible_records == ()
    assert result.ineligible_records == result.records
    assert result.data_quality == result.data_quality.__class__(1, 0, 1, 1, 1, 1, 1, 1)


def test_preparation_preserves_raw_and_transaction_values():
    transaction = make_transaction()
    before = (
        transaction.product_raw,
        transaction.supplier_raw,
        transaction.destination_raw,
        transaction.unit_raw,
        transaction.quantity,
        transaction.unit_price,
        transaction.subtotal,
    )

    record = AnalyticsPreparation().prepare([transaction]).records[0]

    assert record.quantity == Decimal("2.500")
    assert before == (
        transaction.product_raw,
        transaction.supplier_raw,
        transaction.destination_raw,
        transaction.unit_raw,
        transaction.quantity,
        transaction.unit_price,
        transaction.subtotal,
    )