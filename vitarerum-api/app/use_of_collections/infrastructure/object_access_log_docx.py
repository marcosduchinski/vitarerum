"""docxtpl adapter that fills MUHNAC's RAIS register with an object access log."""

from __future__ import annotations

from typing import Any

from app.use_of_collections.application.documents import (
    ObjectAccessLogDocument,
    ObjectAccessLogDocumentObject,
)
from app.use_of_collections.infrastructure.docx_rendering import (
    DATE_FORMAT,
    TEMPLATE_DIR,
    render_form,
)

_TEMPLATE_PATH = TEMPLATE_DIR / "rais_object_access_log.docx"
# The blank form prints fifteen object lines; keep that shape when fewer objects
# were logged so the rendered register still reads as the museum's form.
_FORM_OBJECT_LINES = 15


class DocxObjectAccessLogRenderer:
    """Renders :class:`ObjectAccessLogDocument` onto the RAIS .docx form."""

    async def render(self, document: ObjectAccessLogDocument) -> bytes:
        return await render_form(_TEMPLATE_PATH, self._context(document))

    def _context(self, document: ObjectAccessLogDocument) -> dict[str, Any]:
        lines = [self._object_line(obj) for obj in document.objects]
        lines.extend([self._blank_line()] * (_FORM_OBJECT_LINES - len(lines)))
        return {
            "reference_number": document.reference_number,
            "issued_on": document.issued_on.strftime(DATE_FORMAT),
            "requester": document.requester,
            "researcher_name": document.researcher_name,
            "researcher_email": document.researcher_email,
            "collection": document.collection,
            "curator": document.curator,
            "conclusion_date": (
                document.conclusion_date.strftime(DATE_FORMAT)
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
            "access_date": obj.accessed_at.strftime(DATE_FORMAT),
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
