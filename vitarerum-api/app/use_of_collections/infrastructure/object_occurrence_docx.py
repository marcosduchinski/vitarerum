"""docxtpl adapter that fills MUHNAC's ROC report with one object's occurrences."""

from __future__ import annotations

from typing import Any

from app.use_of_collections.application.documents import (
    ObjectOccurrenceDocument,
    ObjectOccurrenceDocumentEntry,
)
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
            "occurrences": [
                self._occurrence_block(occurrence)
                for occurrence in document.occurrences
            ],
            "reported_by": self._reporters(document),
            # The form's "Data do Relatório" is the day the report was produced.
            "reported_on": issued_on,
        }

    def _occurrence_block(
        self, occurrence: ObjectOccurrenceDocumentEntry
    ) -> dict[str, str]:
        return {
            "collection": occurrence.collection,
            "designation": occurrence.designation,
            "inventory_numbers": self._inventory_numbers(occurrence),
            "occurrence_date": occurrence.occurred_at.strftime(DATE_FORMAT),
            "location": occurrence.location,
            "detailed_description": occurrence.detailed_description,
            "testimonial": occurrence.testimonial,
            "images": self._images(occurrence),
        }

    def _inventory_numbers(self, occurrence: ObjectOccurrenceDocumentEntry) -> str:
        """The form has no quantity field, so the count rides with the number."""
        if occurrence.number_of_objects <= 1:
            return occurrence.inventory_number
        return f"{occurrence.inventory_number} ({occurrence.number_of_objects} objetos)"

    def _images(self, occurrence: ObjectOccurrenceDocumentEntry) -> str:
        # The files themselves stay attached to the entry; the report names them
        # so a printed copy still says what should accompany it. docxtpl turns
        # the newlines into line breaks.
        return "\n".join(
            f"{image.file_name} — {image.description}"
            if image.description
            else image.file_name
            for image in occurrence.images
        )

    def _reporters(self, document: ObjectOccurrenceDocument) -> str:
        """The form signs off once, but occurrences may have different reporters."""
        names: dict[str, None] = {}
        for occurrence in document.occurrences:
            if occurrence.reported_by:
                names.setdefault(occurrence.reported_by, None)
        return "; ".join(names)
