"""Renderer tests for the ROC report adapter.

The API tests cover the happy path end to end; these pin how the form stretches
to hold what it was not drawn for — a whole log in a form drawn for one
incident, free text that spans lines, and a reference longer than its row.
"""

import io
import zipfile
from datetime import UTC, date, datetime

from docx import Document as DocxDocument
from docx.oxml.ns import qn

from app.use_of_collections.application.documents import (
    ObjectOccurrenceDocument,
    ObjectOccurrenceDocumentEntry,
    ObjectOccurrenceDocumentImage,
)
from app.use_of_collections.infrastructure.object_occurrence_docx import (
    DocxObjectOccurrenceRenderer,
)

_BLOCK_ROWS = 8


def _occurrence(
    *,
    collection: str = "Zoologia",
    designation: str = "Tursiops truncatus",
    inventory_number: str = "INV-001",
    number_of_objects: int = 1,
    occurred_at: datetime = datetime(2026, 6, 2, 14, 30, tzinfo=UTC),
    location: str = "Sala 3, reserva",
    detailed_description: str = "Dano observado na base.",
    testimonial: str = "",
    images: tuple[ObjectOccurrenceDocumentImage, ...] = (),
    reported_by: str = "Nuno Curador",
) -> ObjectOccurrenceDocumentEntry:
    return ObjectOccurrenceDocumentEntry(
        collection=collection,
        designation=designation,
        inventory_number=inventory_number,
        number_of_objects=number_of_objects,
        occurred_at=occurred_at,
        location=location,
        detailed_description=detailed_description,
        testimonial=testimonial,
        images=images,
        reported_by=reported_by,
    )


def _document(
    *occurrences: ObjectOccurrenceDocumentEntry,
    reference_number: str = "OOL-ABCDEFG1",
) -> ObjectOccurrenceDocument:
    return ObjectOccurrenceDocument(
        reference_number=reference_number,
        issued_on=date(2026, 8, 11),
        institution="Ana Silva",
        occurrences=occurrences or (_occurrence(),),
    )


async def _render(document: ObjectOccurrenceDocument) -> bytes:
    return await DocxObjectOccurrenceRenderer().render(document)


def _blocks(content: bytes) -> list[list[str]]:
    """The repeated information tables, as lists of their eight values."""
    rows = DocxDocument(io.BytesIO(content)).tables[1].rows
    values = [row.cells[1].text for row in rows]
    return [values[i : i + _BLOCK_ROWS] for i in range(0, len(values), _BLOCK_ROWS)]


async def test_render_repeats_the_whole_table_once_per_occurrence() -> None:
    content = await _render(
        _document(
            _occurrence(collection="Zoologia", location="Sala 3"),
            _occurrence(collection="Arquivo", location="Sala 1"),
            _occurrence(collection="Botânica", location="Ateliê"),
        )
    )

    blocks = _blocks(content)
    assert len(blocks) == 3
    # Every block names its own collection and object — that is what lets one
    # document carry occurrences of different objects.
    assert [block[0] for block in blocks] == ["Zoologia", "Arquivo", "Botânica"]
    assert [block[4] for block in blocks] == ["Sala 3", "Sala 1", "Ateliê"]


async def test_render_carries_the_quantity_on_each_block() -> None:
    content = await _render(
        _document(_occurrence(number_of_objects=3), _occurrence(number_of_objects=1))
    )

    assert [block[2] for block in _blocks(content)] == [
        "INV-001 (3 objetos)",
        "INV-001",
    ]


async def test_render_names_every_distinct_reporter_once() -> None:
    content = await _render(
        _document(
            _occurrence(reported_by="Nuno Curador"),
            _occurrence(reported_by="Ana Silva"),
            _occurrence(reported_by="Nuno Curador"),
        )
    )

    signature = DocxDocument(io.BytesIO(content)).tables[2].rows[0].cells[1].text
    assert signature == "Nuno Curador; Ana Silva"


async def test_render_breaks_a_multi_line_description_into_line_breaks() -> None:
    content = await _render(
        _document(_occurrence(detailed_description="Linha A.\nLinha B."))
    )

    body = zipfile.ZipFile(io.BytesIO(content)).read("word/document.xml").decode()
    start = body.index("Linha A.")
    end = body.index("Linha B.")
    assert "<w:br/>" in body[start:end]


async def test_render_names_the_attached_images_one_per_line() -> None:
    content = await _render(
        _document(
            _occurrence(
                images=(
                    ObjectOccurrenceDocumentImage("before.jpg", "Antes"),
                    ObjectOccurrenceDocumentImage("after.jpg", ""),
                )
            )
        )
    )

    assert _blocks(content)[0][7] == "before.jpg — Antes\nafter.jpg"


async def test_render_leaves_optional_fields_empty_rather_than_instructional() -> None:
    content = await _render(_document(_occurrence(testimonial="", images=())))

    block = _blocks(content)[0]
    assert block[6] == ""
    assert block[7] == ""


async def test_render_lets_the_header_row_grow_for_a_full_reference() -> None:
    """A reference under the active mask wraps at its hyphen; the row it sits in
    must be free to grow, or Word clips everything after the first line and only
    "OO-" reaches the page."""
    content = await _render(_document(reference_number="OO-MUHNAC/COL/2026/0001"))

    header_row = DocxDocument(io.BytesIO(content)).tables[0].rows[2]
    assert header_row.cells[0].text == "OO-MUHNAC/COL/2026/0001"
    height = header_row._tr.find(qn("w:trPr")).find(qn("w:trHeight"))
    assert height.get(qn("w:hRule")) != "exact"
