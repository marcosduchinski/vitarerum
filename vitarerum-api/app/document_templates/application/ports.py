"""Ports for the Document Templates context."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.document_templates.domain.models import (
    DocumentTemplate,
    DocumentTemplateId,
)
from app.shared.kernel import UseType


class DocumentTemplateRepository(Protocol):
    async def add(self, template: DocumentTemplate) -> None: ...

    async def get_by_id(
        self, template_id: DocumentTemplateId
    ) -> DocumentTemplate | None: ...

    async def list_by_use_type(
        self, use_type: UseType, active_only: bool
    ) -> list[DocumentTemplate]: ...

    async def list_all(self, use_type: UseType | None) -> list[DocumentTemplate]: ...

    async def save(self, template: DocumentTemplate) -> None: ...

    async def delete(self, template_id: DocumentTemplateId) -> None: ...


class FileStorage(Protocol):
    async def save(self, content: bytes, file_reference: str) -> str:
        """Persist bytes and return the durable file reference."""
        ...

    async def read(self, file_reference: str) -> bytes:
        """Read persisted bytes by file reference."""
        ...

    async def delete(self, file_reference: str) -> None:
        """Delete a stored file (no error if already gone)."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...
