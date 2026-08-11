"""docxtpl adapter that fills MUHNAC's RAIS register with an object access log.

The template under ``templates/`` is the museum's own blank form with Jinja
placeholders written into its cells by
``scripts/build_object_access_log_template.py``; nothing about its layout is
reproduced here, so a revised form only needs that script re-run.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from anyio.to_thread import run_sync
from docxtpl import DocxTemplate

from app.use_of_collections.application.documents import (
    ObjectAccessLogDocument,
    ObjectAccessLogDocumentObject,
)

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "rais_object_access_log.docx"
_DATE_FORMAT = "%d-%m-%Y"
# The blank form prints fifteen object lines; keep that shape when fewer objects
# were logged so the rendered register still reads as the museum's form.
_FORM_OBJECT_LINES = 15


@lru_cache(maxsize=1)
def _template_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


class DocxObjectAccessLogRenderer:
    """Renders :class:`ObjectAccessLogDocument` onto the RAIS .docx form."""

    def __init__(self, template_path: Path = _TEMPLATE_PATH) -> None:
        self._template_path = template_path

    async def render(self, document: ObjectAccessLogDocument) -> bytes:
        # python-docx parses the whole package (~2 MB, mostly embedded fonts);
        # keep that off the event loop.
        return await run_sync(self._render, document)

    def _render(self, document: ObjectAccessLogDocument) -> bytes:
        template = DocxTemplate(BytesIO(_template_bytes(str(self._template_path))))
        template.render(self._context(document))
        rendered = BytesIO()
        template.save(rendered)
        return rendered.getvalue()

    def _context(self, document: ObjectAccessLogDocument) -> dict[str, Any]:
        lines = [self._object_line(obj) for obj in document.objects]
        lines.extend([self._blank_line()] * (_FORM_OBJECT_LINES - len(lines)))
        return {
            "reference_number": document.reference_number,
            "issued_on": document.issued_on.strftime(_DATE_FORMAT),
            "requester": document.requester,
            "researcher_name": document.researcher_name,
            "researcher_email": document.researcher_email,
            "collection": document.collection,
            "curator": document.curator,
            "conclusion_date": (
                document.conclusion_date.strftime(_DATE_FORMAT)
                if document.conclusion_date
                else ""
            ),
            "objects": lines,
        }

    def _object_line(self, obj: ObjectAccessLogDocumentObject) -> dict[str, str]:
        return {
            "inventory_number": obj.inventory_number,
            "designation": obj.designation,
            "object_type": obj.object_type,
            "number_of_objects": str(obj.number_of_objects),
            "access_date": obj.accessed_at.strftime(_DATE_FORMAT),
            "observations": obj.observations,
        }

    def _blank_line(self) -> dict[str, str]:
        return {
            "inventory_number": "",
            "designation": "",
            "object_type": "",
            "number_of_objects": "",
            "access_date": "",
            "observations": "",
        }
