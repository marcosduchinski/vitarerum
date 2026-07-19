"""openpyxl adapter for CollectionObjectParserPort.

Reads the workbook in ``read_only`` (streaming) and ``data_only`` (calculated
values, not formula strings) modes. Per sheet, the first non-empty row is the
header and becomes the keys of each object's ``cells`` mapping; every following
non-empty row becomes one ``ParsedRow`` keeping its Excel coordinates
(sheet title + 1-based row number).
"""

from __future__ import annotations

import io
from datetime import date, datetime, time

from openpyxl import load_workbook

from app.collection_object_index.application.ports import (
    InvalidSpreadsheet,
    ParsedRow,
)


def _normalize(value: object) -> str:
    """Cell value -> consistent text. Dates in ISO form; integral floats
    without the trailing ``.0``; booleans lowercased; None -> empty."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        # A date-only datetime (midnight) reads better as its date.
        if value.time() == time.min:
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _headers(raw: tuple[object, ...]) -> list[str]:
    """Header cells -> unique, non-empty column keys (blank headers fall back
    to the Excel-style position; duplicates get a numeric suffix)."""
    headers: list[str] = []
    seen: dict[str, int] = {}
    for position, value in enumerate(raw, start=1):
        name = _normalize(value) or f"Column {position}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        headers.append(name if count == 0 else f"{name} ({count + 1})")
    return headers


class OpenpyxlCollectionObjectParser:
    def parse(self, content: bytes) -> list[ParsedRow]:
        try:
            workbook = load_workbook(
                io.BytesIO(content), read_only=True, data_only=True
            )
        except Exception as exc:
            raise InvalidSpreadsheet(
                "The file could not be read as an .xlsx spreadsheet."
            ) from exc
        try:
            rows: list[ParsedRow] = []
            for sheet in workbook.worksheets:
                headers: list[str] | None = None
                for row_number, raw in enumerate(
                    sheet.iter_rows(values_only=True), start=1
                ):
                    values = [_normalize(value) for value in raw]
                    if not any(values):
                        continue
                    if headers is None:
                        headers = _headers(raw)
                        continue
                    cells = {
                        header: value
                        for header, value in zip(headers, values, strict=False)
                        if value
                    }
                    rows.append(
                        ParsedRow(
                            sheet=sheet.title,
                            row_number=row_number,
                            content="",
                            cells=cells,
                        )
                    )
            return rows
        finally:
            workbook.close()
