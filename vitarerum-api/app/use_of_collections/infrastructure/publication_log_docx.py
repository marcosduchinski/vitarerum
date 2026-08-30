"""docxtpl adapter that fills the RRP publication/output register."""

from __future__ import annotations

from typing import Any

from app.use_of_collections.application.documents import (
    PublicationLogDocument,
    PublicationLogDocumentAttachment,
    PublicationLogDocumentEntry,
)
from app.use_of_collections.infrastructure.docx_rendering import (
    DATE_FORMAT,
    TEMPLATE_DIR,
    render_form,
)

_TEMPLATE_PATH = TEMPLATE_DIR / "publication_log_register.docx"


class DocxPublicationLogRenderer:
    """Renders :class:`PublicationLogDocument` onto the RRP .docx register."""

    async def render(self, document: PublicationLogDocument) -> bytes:
        return await render_form(_TEMPLATE_PATH, self._context(document))

    def _context(self, document: PublicationLogDocument) -> dict[str, Any]:
        return {
            "reference_number": document.reference_number,
            "issued_on": document.issued_on.strftime(DATE_FORMAT),
            "project_reference": document.project_reference,
            "project_title": document.project_title,
            "requester": document.requester,
            "curator": document.curator,
            "entry_count": len(document.entries),
            "publications": [
                self._publication_line(entry) for entry in document.entries
            ],
        }

    def _publication_line(
        self, entry: PublicationLogDocumentEntry
    ) -> dict[str, str]:
        return {
            "sequence": str(entry.sequence),
            "date": entry.added_at.strftime(DATE_FORMAT),
            "added_by": entry.added_by,
            "note": entry.note,
            "object_reference": entry.object_reference,
            "attachments": self._attachments(entry.attachments),
        }

    def _attachments(
        self, attachments: tuple[PublicationLogDocumentAttachment, ...]
    ) -> str:
        if not attachments:
            return "—"
        return "\n".join(
            f"{attachment.file_name} — {attachment.description}"
            if attachment.description
            else attachment.file_name
            for attachment in attachments
        )
