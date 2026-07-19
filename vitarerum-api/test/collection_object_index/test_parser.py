"""Parser coverage: a real (in-memory) .xlsx exercised through openpyxl."""

import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from app.collection_object_index.application.ports import InvalidSpreadsheet
from app.collection_object_index.infrastructure.parser_openpyxl import (
    OpenpyxlCollectionObjectParser,
)


def _xlsx(build) -> bytes:
    workbook = Workbook()
    build(workbook)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_header_becomes_cell_keys_and_rows_keep_coordinates() -> None:
    def build(wb: Workbook) -> None:
        ws = wb.active
        ws.title = "Specimens"
        ws.append(["Inventory No", "Taxon", "Collected"])
        ws.append(["ZOO-001", "Panthera onca", date(1998, 5, 4)])
        ws.append(["ZOO-002", "Ara ararauna", None])

    rows = OpenpyxlCollectionObjectParser().parse(_xlsx(build))

    assert len(rows) == 2
    first = rows[0]
    assert first.sheet == "Specimens"
    assert first.row_number == 2  # Excel 1-based; header is row 1
    assert first.cells == {
        "Inventory No": "ZOO-001",
        "Taxon": "Panthera onca",
        "Collected": "1998-05-04",
    }
    assert first.content == ""
    # Empty cell is omitted from cells but the row still indexes.
    assert rows[1].cells == {"Inventory No": "ZOO-002", "Taxon": "Ara ararauna"}


def test_fully_empty_rows_are_skipped() -> None:
    def build(wb: Workbook) -> None:
        ws = wb.active
        ws.append(["Code", "Name"])
        ws.append([None, None])
        ws.append(["BOT-1", "Quercus robur"])

    rows = OpenpyxlCollectionObjectParser().parse(_xlsx(build))
    assert [row.row_number for row in rows] == [3]


def test_multiple_sheets_each_have_their_own_header() -> None:
    def build(wb: Workbook) -> None:
        first = wb.active
        first.title = "Birds"
        first.append(["Code"])
        first.append(["AVE-1"])
        second = wb.create_sheet("Minerals")
        second.append(["Sample", "Locality"])
        second.append(["MIN-9", "Ouro Preto"])

    rows = OpenpyxlCollectionObjectParser().parse(_xlsx(build))
    assert {(row.sheet, row.row_number) for row in rows} == {
        ("Birds", 2),
        ("Minerals", 2),
    }
    minerals = next(row for row in rows if row.sheet == "Minerals")
    assert minerals.cells == {"Sample": "MIN-9", "Locality": "Ouro Preto"}


def test_values_are_normalized() -> None:
    def build(wb: Workbook) -> None:
        ws = wb.active
        ws.append(["Count", "Flag", "When", "Weight"])
        ws.append([3.0, True, datetime(2020, 1, 2, 0, 0), 1.25])

    (row,) = OpenpyxlCollectionObjectParser().parse(_xlsx(build))
    assert row.cells == {
        "Count": "3",
        "Flag": "true",
        "When": "2020-01-02",
        "Weight": "1.25",
    }


def test_duplicate_and_blank_headers_get_stable_keys() -> None:
    def build(wb: Workbook) -> None:
        ws = wb.active
        ws.append(["Name", "Name", None])
        ws.append(["a", "b", "c"])

    (row,) = OpenpyxlCollectionObjectParser().parse(_xlsx(build))
    assert row.cells == {"Name": "a", "Name (2)": "b", "Column 3": "c"}


def test_invalid_bytes_raise_invalid_spreadsheet() -> None:
    with pytest.raises(InvalidSpreadsheet):
        OpenpyxlCollectionObjectParser().parse(b"not a spreadsheet")
