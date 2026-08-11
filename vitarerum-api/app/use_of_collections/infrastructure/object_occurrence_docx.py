"""docxtpl adapter that fills MUHNAC's ROC report with one object occurrence."""

from __future__ import annotations

from typing import Any

from app.use_of_collections.application.documents import ObjectOccurrenceDocument
from app.use_of_collections.infrastructure.docx_rendering import (
    DATE_FORMAT,
    TEMPLATE_DIR,
    render_form,
)

_TEMPLATE_PATH = TEMPLATE_DIR / "roc_object_occurrence.docx"


class DocxObjectOccurrenceRenderer:
    """Renders :class:`ObjectOccurrenceDocument` onto the ROC .docx form."""

    async def render(self, document: ObjectOccurrenceDocument) -> bytes:
        return await render_form(_TEMPLATE_PATH, self._context(document))

    def _context(self, document: ObjectOccurrenceDocument) -> dict[str, Any]:
        issued_on = document.issued_on.strftime(DATE_FORMAT)
        return {
            "reference_number": document.reference_number,
            "issued_on": issued_on,
            "institution": document.institution,
            "collection": document.collection,
            "designation": document.designation,
            "inventory_numbers": self._inventory_numbers(document),
            "occurrence_date": document.occurred_at.strftime(DATE_FORMAT),
            "location": document.location,
            "detailed_description": document.detailed_description,
            "testimonial": document.testimonial,
            "images": self._images(document),
            "reported_by": document.reported_by,
            # The form's "Data do Relatório" is the day the report was produced.
            "reported_on": issued_on,
        }

    def _inventory_numbers(self, document: ObjectOccurrenceDocument) -> str:
        """The form has no quantity field, so the count rides with the number."""
        if document.number_of_objects <= 1:
            return document.inventory_number
        return f"{document.inventory_number} ({document.number_of_objects} objetos)"

    def _images(self, document: ObjectOccurrenceDocument) -> str:
        # The files themselves stay attached to the entry; the report names them
        # so a printed copy still says what should accompany it. docxtpl turns
        # the newlines into line breaks.
        return "\n".join(
            f"{image.file_name} — {image.description}"
            if image.description
            else image.file_name
            for image in document.images
        )
