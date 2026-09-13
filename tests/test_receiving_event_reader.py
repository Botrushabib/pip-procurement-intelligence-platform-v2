from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.receiving_event_reader import (
    ReceivingExcelReader,
    ReceivingRowClassification,
    RequiredHeadersNotFoundError,
    extract_product_code,
)


HEADERS = [
    "Suppliers",
    "Date",
    "Receipt Date",
    "Reference",
    "Product",
    "To",
    "Qty",
    "Unit",
    "Unit Price",
    "Subtotal",
    "Item description",
]


def create_workbook(path: Path, rows: list[list], sheet_name: str = "Report") -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append(HEADERS)
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def detail(
    supplier, event_date, second_date, reference, product, destination, quantity, unit_price, subtotal
):
    return [
        supplier,
        event_date,
        second_date,
        reference,
        product,
        destination,
        quantity,
        "kg",
        unit_price,
        subtotal,
        "Brown sugar",
    ]


def test_reader_preserves_hierarchy_and_inherits_supplier_context(tmp_path):
    path = tmp_path / "receiving.xlsx"
    create_workbook(
        path,
        [
            ["Supplier A", datetime(2026, 8, 1), datetime(2026, 9, 1), None, None, None, None, None, None, None, None],
            [None, datetime(2026, 8, 1), datetime(2026, 9, 1), None, "Food / Sugar", None, None, None, None, None, None],
            detail(None, datetime(2026, 8, 1), datetime(2026, 9, 1), "10560", "[162017] Sugar Brown Portion TLT", "Main Stores/Stock", 2, 10, 20),
            detail(None, datetime(2026, 8, 1), datetime(2026, 9, 1), "10560", "[162018] Sugar White Portion TLT", "Main Stores/Stock", 3, 5, 15),
            ["Supplier B", datetime(2026, 8, 2), datetime(2026, 9, 2), None, None, None, None, None, None, None, None],
            detail(None, datetime(2026, 8, 2), datetime(2026, 9, 2), "10561", "[162019] Salt", "Main Store Sahel/Stock", 1, 4, 4),
            [None, None, None, None, None, None, "not numeric", None, None, None, None],
        ],
    )

    result = ReceivingExcelReader().read(path)

    assert result.detail_row_count == 3
    assert result.non_detail_row_count == 4
    assert [row.source_row for row in result.detail_rows] == [4, 5, 7]
    assert [row.raw_supplier for row in result.detail_rows] == ["Supplier A", "Supplier A", "Supplier B"]
    assert result.rows[0].row_classification is ReceivingRowClassification.SUPPLIER_HEADER
    assert result.rows[1].row_classification is ReceivingRowClassification.PRODUCT_SUMMARY
    assert result.rows[6].row_classification is ReceivingRowClassification.OTHER


def test_detail_rows_can_share_reference_without_being_collapsed(tmp_path):
    path = tmp_path / "receiving.xlsx"
    create_workbook(
        path,
        [
            detail("Supplier A", datetime(2026, 8, 1), datetime(2026, 9, 1), "10560", "[1] Product A", "Main Stores/Stock", 2, 10, 20),
            detail("Supplier A", datetime(2026, 8, 1), datetime(2026, 9, 1), "10560", "[2] Product B", "Main Stores/Stock", 3, 5, 15),
        ],
    )

    result = ReceivingExcelReader().read(path)

    assert len(result.detail_rows) == 2
    assert [row.raw_reference for row in result.detail_rows] == ["10560", "10560"]
    assert [row.source_row for row in result.detail_rows] == [2, 3]


def test_reader_preserves_both_dates_and_approved_event_date_candidate(tmp_path):
    path = tmp_path / "receiving.xlsx"
    create_workbook(
        path,
        [detail("Supplier A", datetime(2026, 8, 12), datetime(2026, 9, 3), "10560", "[1] Product A", "Main Stores/Stock", Decimal("2.5"), Decimal("10"), Decimal("25") )],
    )

    row = ReceivingExcelReader().read(path).detail_rows[0]

    assert row.raw_date_1 == datetime(2026, 8, 12)
    assert row.raw_date_2 == datetime(2026, 9, 3)
    assert row.event_date_candidate == datetime(2026, 8, 12)
    assert row.raw_product == "[1] Product A"
    assert row.product_code == "1"
    assert row.raw_item_description == "Brown sugar"
    assert row.source_row == 2


def test_extract_product_code_accepts_approved_bracketed_format():
    assert extract_product_code("[162017] Sugar Brown Portion TLT") == "162017"


@pytest.mark.parametrize(
    "raw_product",
    [
        "Sugar Brown Portion TLT",
        "[] Sugar Brown Portion TLT",
        "[162017A] Sugar Brown Portion TLT",
        "[162017 Sugar Brown Portion TLT",
        "162017] Sugar Brown Portion TLT",
    ],
)
def test_extract_product_code_does_not_fallback_or_invent_codes(raw_product):
    assert extract_product_code(raw_product) is None


def test_missing_code_preserves_raw_product_and_description_without_identity_fallback(tmp_path):
    path = tmp_path / "receiving.xlsx"
    create_workbook(
        path,
        [detail("Supplier A", datetime(2026, 8, 12), datetime(2026, 9, 3), "10560", "Sugar Brown Portion TLT", "Main Stores/Stock", 2, 10, 20)],
    )

    row = ReceivingExcelReader().read(path).detail_rows[0]

    assert row.raw_product == "Sugar Brown Portion TLT"
    assert row.product_code is None
    assert row.raw_item_description == "Brown sugar"
    assert row.source_file == str(path)
    assert row.source_sheet == "Report"
    assert row.source_row == 2
    assert row.row_classification is ReceivingRowClassification.DETAIL


def test_missing_required_header_raises_error(tmp_path):
    path = tmp_path / "receiving.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Report"
    worksheet.append(["Date", "Reference", "Product"])
    workbook.save(path)

    with pytest.raises(RequiredHeadersNotFoundError):
        ReceivingExcelReader().read(path)