from datetime import date
from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import DeclarativeBase

import app.models
from app.core.database import Base
from app.models.purchase_request import PurchaseRequest, PurchaseRequestStatus
from app.models.purchase_request_line import PurchaseRequestLine


def test_purchase_request_model_imports_and_uses_existing_base():
    assert app.models.PurchaseRequest is PurchaseRequest
    assert issubclass(PurchaseRequest, DeclarativeBase)
    assert PurchaseRequest.__bases__[0] is Base


def test_purchase_request_line_model_imports_and_uses_existing_base():
    assert app.models.PurchaseRequestLine is PurchaseRequestLine
    assert issubclass(PurchaseRequestLine, DeclarativeBase)
    assert PurchaseRequestLine.__bases__[0] is Base


def test_purchase_request_can_be_constructed():
    request = PurchaseRequest(
        company_id=1,
        destination_type="BRANCH",
        request_date=date(2026, 8, 20),
        status=PurchaseRequestStatus.DRAFT.value,
    )

    assert request.company_id == 1
    assert request.destination_type == "BRANCH"
    assert request.request_date == date(2026, 8, 20)
    assert request.status == "DRAFT"


def test_purchase_request_line_can_be_constructed():
    line = PurchaseRequestLine(
        requested_quantity=Decimal("100"),
        status=PurchaseRequestStatus.DRAFT.value,
    )

    assert line.requested_quantity == Decimal("100")
    assert line.status == "DRAFT"


def test_header_to_lines_relationship():
    request = PurchaseRequest(
        company_id=1,
        destination_type="BRANCH",
        request_date=date(2026, 8, 20),
        status=PurchaseRequestStatus.DRAFT.value,
    )
    line_one = PurchaseRequestLine(status=PurchaseRequestStatus.DRAFT.value)
    line_two = PurchaseRequestLine(status=PurchaseRequestStatus.DRAFT.value)
    request.lines.append(line_one)
    request.lines.append(line_two)

    assert list(request.lines) == [line_one, line_two]
    assert line_one.request is request
    assert line_two.request is request


def test_product_foreign_key_is_wired_correctly():
    table = PurchaseRequestLine.__table__
    foreign_key = next(fk for fk in table.foreign_keys if fk.parent.name == "product_id")

    assert foreign_key.target_fullname == "products.id"
    assert "product" in PurchaseRequestLine.__mapper__.relationships.keys()


def test_unit_foreign_key_is_wired_correctly():
    table = PurchaseRequestLine.__table__
    foreign_key = next(fk for fk in table.foreign_keys if fk.parent.name == "unit_id")

    assert foreign_key.target_fullname == "units.id"
    assert "unit" in PurchaseRequestLine.__mapper__.relationships.keys()


def test_company_branch_warehouse_foreign_keys_follow_existing_architecture():
    table = PurchaseRequest.__table__
    expected_foreign_keys = {
        "company_id": "companies.id",
        "branch_id": "branches.id",
        "warehouse_id": "warehouses.id",
    }

    for column_name, target in expected_foreign_keys.items():
        foreign_key = next(fk for fk in table.foreign_keys if fk.parent.name == column_name)
        assert foreign_key.target_fullname == target

    assert set(PurchaseRequest.__mapper__.relationships.keys()) >= {
        "company",
        "branch",
        "warehouse",
        "lines",
    }


def test_requested_quantity_accepts_decimal():
    columns = PurchaseRequestLine.__table__.columns

    assert isinstance(columns["requested_quantity"].type, Numeric)

    line = PurchaseRequestLine(requested_quantity=Decimal("450.5"))
    assert line.requested_quantity == Decimal("450.5")


def test_approved_quantity_is_nullable():
    columns = PurchaseRequestLine.__table__.columns

    assert columns["approved_quantity"].nullable is True

    line = PurchaseRequestLine(requested_quantity=Decimal("500"))
    assert line.approved_quantity is None


def test_raw_quantity_preserves_text_representations():
    columns = PurchaseRequestLine.__table__.columns
    assert isinstance(columns["raw_quantity"].type, String)

    for raw_value in ("5 box", "50 بالتة", "مطلوب", "0"):
        line = PurchaseRequestLine(raw_quantity=raw_value)
        assert line.raw_quantity == raw_value


def test_raw_packaging_is_nullable():
    columns = PurchaseRequestLine.__table__.columns

    assert columns["raw_packaging"].nullable is True

    line = PurchaseRequestLine(raw_product="Cheese Emmental")
    assert line.raw_packaging is None


def test_reference_is_nullable():
    columns = PurchaseRequest.__table__.columns

    assert columns["reference"].nullable is True


def test_provenance_fields_are_nullable_for_manual_records():
    request_columns = PurchaseRequest.__table__.columns
    line_columns = PurchaseRequestLine.__table__.columns

    for column_name in ("source_file", "source_sheet", "source_row"):
        assert request_columns[column_name].nullable is True
        assert line_columns[column_name].nullable is True


def test_status_uses_only_approved_phase_10a_statuses():
    approved_statuses = {"DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "CANCELLED"}

    assert {status.value for status in PurchaseRequestStatus} == approved_statuses
