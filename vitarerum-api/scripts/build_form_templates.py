"""Annotate MUHNAC's blank forms with the placeholders the DOCX renderers fill.

The museum ships its forms as blank documents: no content controls, no merge
fields, and instruction text where the values belong. This script takes those
untouched forms and writes Jinja placeholders into them, producing the template
assets consumed by ``app.use_of_collections.infrastructure``:

- ``RAIS_formColecoesAcessoInSituRegisto`` → the object access log register;
- ``ROC_formOcorrenciaColecoes`` → one report per object occurrence.

Re-run it whenever MUHNAC revises a form, so the layout stays theirs and only
the placeholders are ours::

    uv run python scripts/build_form_templates.py

Run from the repository root (or pass explicit paths); the defaults resolve
against this file's location. ``--inspect`` prints a form's table coordinates,
which is where to start when a revision moves fields around.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn

_API_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_DIR = _API_ROOT.parent / "docs" / "templates"
_TARGET_DIR = _API_ROOT / "app" / "use_of_collections" / "infrastructure" / "templates"

_RAIS_SOURCE = _SOURCE_DIR / "RAIS_formColecoesAcessoInSituRegisto_MUHNAC_2026.docx"
_RAIS_TARGET = _TARGET_DIR / "rais_object_access_log.docx"
_ROC_SOURCE = _SOURCE_DIR / "ROC_formOcorrenciaColecoes_MUHNAC_2026.docx"
_ROC_TARGET = _TARGET_DIR / "roc_object_occurrence.docx"


def _set_cell_text(cell: Any, text: str) -> None:
    """Replace a cell's content, keeping the paragraph's own run formatting.

    The form's cells carry their font on the paragraph mark (``w:pPr/w:rPr``)
    rather than on a run, so a naive ``add_run`` would render the placeholder —
    and therefore the filled value — in the document default font instead of the
    form's. Any further paragraphs (the ROC's multi-line instruction text) are
    dropped; a cell must keep at least one, so the first is reused.
    """
    paragraph = cell.paragraphs[0]
    for extra in cell.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)
    run = paragraph.add_run(text)
    paragraph_properties = paragraph._p.find(qn("w:pPr"))
    if paragraph_properties is not None:
        mark_properties = paragraph_properties.find(qn("w:rPr"))
        if mark_properties is not None:
            run._element.insert(0, deepcopy(mark_properties))


def _relax_row_height(row: Any) -> None:
    """Let a row grow past the height the blank form printed it at.

    The header rows are laid out with ``w:hRule="exact"``, which is one line
    tall: anything that wraps is silently clipped rather than pushed onto a
    second line. The museum's sample values are short ("MUHNAC/IICT-2026-xxx"),
    but a real reference under the active mask — ``OO-MUHNAC/COL/2026/0001`` —
    wraps at the hyphen and loses everything after it. ``atLeast`` keeps the
    printed height as a minimum while letting the row grow when it must.
    """
    properties = row._tr.find(qn("w:trPr"))
    if properties is None:
        return
    height = properties.find(qn("w:trHeight"))
    if height is not None and height.get(qn("w:hRule")) == "exact":
        height.set(qn("w:hRule"), "atLeast")


def _insert_tag_row(table: Any, index: int, tag: str, *, after: bool = False) -> int:
    """Clone a row to carry a docxtpl ``{%tr %}`` tag, returning its position.

    The blank forms have no spare rows for loop tags, so one is cloned from the
    row being wrapped — it inherits the borders and cell widths, which keeps the
    table well-formed if the tag is ever left unrendered. docxtpl deletes the
    row when it runs the loop.
    """
    anchor = table.rows[index]._tr
    clone = deepcopy(anchor)
    if after:
        anchor.addnext(clone)
        position = index + 1
    else:
        anchor.addprevious(clone)
        position = index
    inserted = table.rows[position]
    _set_cell_text(inserted.cells[0], tag)
    for cell in inserted.cells[1:]:
        _set_cell_text(cell, "")
    return position


def _inspect(document: Any) -> None:
    for table_index, table in enumerate(document.tables):
        print(f"--- table {table_index}: {len(table.rows)}x{len(table.columns)}")
        for row_index, row in enumerate(table.rows):
            cells = [cell.text.replace("\n", "\\n") for cell in row.cells]
            print(f"   r{row_index} {cells!r}")


def annotate_rais(source: Path, target: Path) -> None:
    """The access register: a header, an identification block and a row table."""
    document = Document(str(source))

    _relax_row_height(document.tables[0].rows[2])
    header = document.tables[0].rows[2].cells
    _set_cell_text(header[0], "{{ reference_number }}")
    _set_cell_text(header[2], "{{ issued_on }}")
    _set_cell_text(header[3], "{{ requester }}")

    identification = document.tables[1]
    _set_cell_text(identification.rows[0].cells[1], "{{ researcher_name }}")
    _set_cell_text(identification.rows[1].cells[1], "{{ researcher_email }}")
    _set_cell_text(identification.rows[2].cells[1], "{{ collection }}")
    _set_cell_text(identification.rows[3].cells[1], "{{ curator }}")

    # Row 1 opens the loop, row 2 is the repeated body, row 3 closes it; docxtpl
    # drops the two rows holding `{%tr %}` tags. The remaining blank rows go —
    # the renderer pads the object list back up to the form's fifteen lines.
    objects = document.tables[2]
    _set_cell_text(objects.rows[1].cells[0], "{%tr for object in objects %}")
    body = objects.rows[2].cells
    _set_cell_text(body[0], "{{ object.inventory_number }}")
    _set_cell_text(body[1], "{{ object.designation }}")
    _set_cell_text(body[2], "{{ object.object_type }}")
    _set_cell_text(body[3], "{{ object.number_of_objects }}")
    _set_cell_text(body[4], "{{ object.access_date }}")
    _set_cell_text(body[5], "{{ object.observations }}")
    _set_cell_text(objects.rows[3].cells[0], "{%tr endfor %}")
    for row in list(objects.rows)[4:]:
        objects._tbl.remove(row._tr)

    _set_cell_text(document.tables[3].rows[1].cells[1], "{{ conclusion_date }}")

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(target))


def annotate_roc(source: Path, target: Path) -> None:
    """The occurrence report: one project's whole occurrence log.

    The right-hand column holds instruction text ("Local da ocorrência.") that
    the placeholders replace, so a rendered report reads as a filled-in form
    rather than as the blank one.

    The form describes a single incident, so the whole information table repeats
    once per occurrence — each block naming its own collection and object, which
    is what makes a single document able to carry the entire log.
    """
    document = Document(str(source))

    _relax_row_height(document.tables[0].rows[2])
    header = document.tables[0].rows[2].cells
    _set_cell_text(header[0], "{{ reference_number }}")
    _set_cell_text(header[2], "{{ issued_on }}")
    _set_cell_text(header[3], "{{ institution }}")

    fields = document.tables[1]
    _insert_tag_row(fields, 0, "{%tr for occurrence in occurrences %}")
    for offset, placeholder in enumerate(
        (
            "{{ occurrence.collection }}",
            "{{ occurrence.designation }}",
            "{{ occurrence.inventory_numbers }}",
            "{{ occurrence.occurrence_date }}",
            "{{ occurrence.location }}",
            "{{ occurrence.detailed_description }}",
            "{{ occurrence.testimonial }}",
            "{{ occurrence.images }}",
        )
    ):
        _set_cell_text(fields.rows[1 + offset].cells[1], placeholder)
    _insert_tag_row(fields, 8, "{%tr endfor %}", after=True)

    signature = document.tables[2]
    _set_cell_text(signature.rows[0].cells[1], "{{ reported_by }}")
    _set_cell_text(signature.rows[1].cells[1], "{{ reported_on }}")

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(target))


_FORMS = {
    "rais": (annotate_rais, _RAIS_SOURCE, _RAIS_TARGET),
    "roc": (annotate_roc, _ROC_SOURCE, _ROC_TARGET),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--form", choices=[*_FORMS, "all"], default="all")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--target", type=Path, default=None)
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Print a form's table coordinates and exit.",
    )
    args = parser.parse_args()

    if args.inspect:
        source = args.source or _FORMS[args.form if args.form != "all" else "rais"][1]
        _inspect(Document(str(source)))
        return

    names = list(_FORMS) if args.form == "all" else [args.form]
    if len(names) > 1 and (args.source or args.target):
        parser.error("--source/--target apply to a single --form")
    for name in names:
        annotate, source, target = _FORMS[name]
        annotate(args.source or source, args.target or target)
        print(f"Wrote {args.target or target}")


if __name__ == "__main__":
    main()
