"""Ports for the Collection Object Index context.

``FileStorage`` is a structural twin of the shared local-disk adapter's port
(same shape as in the Document Templates context): the adapter is reused at the
composition root only, keeping this context free of cross-context imports.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.collection_object_index.domain.models import (
    Collection,
    CollectionId,
    CuratorAssignment,
    SourceDocument,
    SourceDocumentId,
)
from app.shared.kernel import PermissionId


class InvalidSpreadsheet(ValueError):
    """The uploaded bytes are not a parseable spreadsheet (or exceed limits)."""


@dataclass(frozen=True, slots=True)
class ParsedRow:
    """One spreadsheet row normalised for indexing: ``cells`` is keyed by the
    sheet's header row; ``content`` is the row's cells concatenated for
    full-text matching."""

    sheet: str
    row_number: int
    content: str
    cells: Mapping[str, str]


class CollectionRepository(Protocol):
    async def list_all(self) -> list[Collection]: ...

    async def get_by_id(self, collection_id: CollectionId) -> Collection | None: ...

    async def list_curators(
        self, collection_id: CollectionId | None = None
    ) -> list[CuratorAssignment]: ...

    async def list_curated_collection_ids(
        self, permission_id: PermissionId
    ) -> set[CollectionId]: ...

    async def add_curator(self, assignment: CuratorAssignment) -> None: ...

    async def remove_curator(
        self, collection_id: CollectionId, permission_id: PermissionId
    ) -> None: ...

    async def count_live_documents(self) -> dict[CollectionId, int]: ...


class SourceDocumentRepository(Protocol):
    async def add(self, document: SourceDocument) -> None: ...

    async def get_by_id(
        self, document_id: SourceDocumentId
    ) -> SourceDocument | None: ...

    async def list_live_by_collection(
        self, collection_id: CollectionId
    ) -> list[SourceDocument]: ...

    async def find_live_by_hash(
        self, collection_id: CollectionId, content_hash: str
    ) -> SourceDocument | None: ...

    async def find_live_by_file_name(
        self, collection_id: CollectionId, file_name: str
    ) -> SourceDocument | None: ...

    async def save(self, document: SourceDocument) -> None: ...


class CollectionObjectIndexPort(Protocol):
    """Write side of the searchable object index. The read side (``search``)
    is added by the Objects -> Search plan on the same port."""

    async def index(
        self,
        source_document_id: SourceDocumentId,
        collection_id: CollectionId,
        rows: Sequence[ParsedRow],
    ) -> int:
        """Replace the document's indexed rows; returns the row count."""
        ...

    async def remove_document(self, source_document_id: SourceDocumentId) -> None: ...


class CollectionObjectParserPort(Protocol):
    def parse(self, content: bytes) -> list[ParsedRow]:
        """Extract indexable rows; raises InvalidSpreadsheet on bad content."""
        ...


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
