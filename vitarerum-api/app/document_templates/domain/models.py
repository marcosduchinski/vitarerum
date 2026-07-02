"""Document Templates domain model.

A ``DocumentTemplate`` is a curated blank form (``.docx``) that staff associate
with a ``UseType`` so external citizens can download, fill in and submit it with
a collection-use request. Pure domain: standard library plus the Shared Kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NewType

from app.shared.kernel import PermissionId, UseType

DocumentTemplateId = NewType("DocumentTemplateId", str)


class DocumentTemplateNotFound(Exception):
    """Raised when a document template id does not resolve."""


@dataclass(slots=True)
class DocumentTemplate:
    """A downloadable template offered for a given use type."""

    id: DocumentTemplateId
    use_type: UseType
    title: str
    description: str
    mandatory: bool
    active: bool
    display_order: int
    file_name: str
    file_reference: str
    uploaded_by: PermissionId
    uploaded_at: datetime

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Document template title is required.")

    def update_metadata(
        self,
        *,
        title: str,
        description: str,
        mandatory: bool,
        active: bool,
        display_order: int,
    ) -> None:
        if not title.strip():
            raise ValueError("Document template title is required.")
        self.title = title
        self.description = description
        self.mandatory = mandatory
        self.active = active
        self.display_order = display_order

    def replace_file(self, *, file_name: str, file_reference: str) -> None:
        self.file_name = file_name
        self.file_reference = file_reference
