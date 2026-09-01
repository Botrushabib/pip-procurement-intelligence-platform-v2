from sqlalchemy.orm import DeclarativeBase

from app.core.database import Base
import app.models


def test_master_data_models_import_successfully():
    expected_models = {
        "Company",
        "Branch",
        "Warehouse",
        "Supplier",
        "Category",
        "Unit",
        "Product",
    }

    imported_names = {name for name in dir(app.models) if not name.startswith("_")}
    for model_name in expected_models:
        assert model_name in imported_names


def test_all_master_data_models_use_the_same_base():
    model_classes = [
        getattr(app.models, name)
        for name in [
            "Company",
            "Branch",
            "Warehouse",
            "Supplier",
            "Category",
            "Unit",
            "Product",
        ]
    ]

    for model_class in model_classes:
        assert issubclass(model_class, DeclarativeBase)
        assert model_class.__bases__[0] is Base


def test_metadata_registers_exactly_seven_application_tables():
    expected_tables = {
        "companies",
        "branches",
        "warehouses",
        "suppliers",
        "categories",
        "units",
        "products",
    }

    assert set(Base.metadata.tables.keys()) == expected_tables | {
        "purchase_transactions",
        "purchase_requests",
        "purchase_request_lines",
    }
    assert len(Base.metadata.tables) == 10


def test_primary_keys_and_required_foreign_keys_exist():
    company_table = Base.metadata.tables["companies"]
    branch_table = Base.metadata.tables["branches"]
    warehouse_table = Base.metadata.tables["warehouses"]
    product_table = Base.metadata.tables["products"]

    assert company_table.primary_key.columns.keys() == ["id"]
    assert branch_table.primary_key.columns.keys() == ["id"]
    assert warehouse_table.primary_key.columns.keys() == ["id"]
    assert product_table.primary_key.columns.keys() == ["id"]

    branch_fk = next(
        fk for fk in branch_table.foreign_keys if fk.parent.name == "company_id"
    )
    warehouse_fk = next(
        fk for fk in warehouse_table.foreign_keys if fk.parent.name == "branch_id"
    )
    product_category_fk = next(
        fk for fk in product_table.foreign_keys if fk.parent.name == "category_id"
    )
    product_unit_fk = next(
        fk for fk in product_table.foreign_keys if fk.parent.name == "unit_id"
    )

    assert branch_fk.parent.name == "company_id"
    assert warehouse_fk.parent.name == "branch_id"
    assert product_category_fk.parent.name == "category_id"
    assert product_unit_fk.parent.name == "unit_id"
    assert branch_fk.target_fullname == "companies.id"
    assert warehouse_fk.target_fullname == "branches.id"
    assert product_category_fk.target_fullname == "categories.id"
    assert product_unit_fk.target_fullname == "units.id"


def test_required_unique_constraints_and_indexes_exist():
    from sqlalchemy import Index, UniqueConstraint

    company_table = Base.metadata.tables["companies"]
    branch_table = Base.metadata.tables["branches"]
    warehouse_table = Base.metadata.tables["warehouses"]
    supplier_table = Base.metadata.tables["suppliers"]
    category_table = Base.metadata.tables["categories"]
    unit_table = Base.metadata.tables["units"]
    product_table = Base.metadata.tables["products"]

    assert any(isinstance(constraint, UniqueConstraint) for constraint in company_table.constraints)
    assert any(isinstance(constraint, UniqueConstraint) for constraint in supplier_table.constraints)
    assert any(isinstance(constraint, UniqueConstraint) for constraint in category_table.constraints)
    assert any(isinstance(constraint, UniqueConstraint) for constraint in unit_table.constraints)
    assert any(isinstance(constraint, UniqueConstraint) for constraint in product_table.constraints)

    assert any(constraint.name == "uq_branches_company_code" for constraint in branch_table.constraints)
    assert any(constraint.name == "uq_warehouses_branch_code" for constraint in warehouse_table.constraints)

    assert any(index.name == "ix_companies_name" for index in company_table.indexes)
    assert any(index.name == "ix_branches_company_id" for index in branch_table.indexes)
    assert any(index.name == "ix_warehouses_branch_id" for index in warehouse_table.indexes)
    assert any(index.name == "ix_suppliers_name" for index in supplier_table.indexes)
    assert any(index.name == "ix_categories_name" for index in category_table.indexes)
    assert any(index.name == "ix_units_name" for index in unit_table.indexes)
    assert any(index.name == "ix_products_name" for index in product_table.indexes)
    assert any(index.name == "ix_products_category_id" for index in product_table.indexes)
    assert any(index.name == "ix_products_unit_id" for index in product_table.indexes)


def test_product_does_not_have_supplier_or_price_fields():
    product_table = Base.metadata.tables["products"]

    assert "supplier_id" not in product_table.columns
    assert "price" not in product_table.columns
    assert "current_price" not in product_table.columns
    assert "purchase_price" not in product_table.columns


def test_purchase_transaction_model_is_registered():
    assert "PurchaseTransaction" in dir(app.models)
    assert "Import" not in dir(app.models)


def test_health_endpoint_still_passes():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
