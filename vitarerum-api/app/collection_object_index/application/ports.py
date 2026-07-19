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
    CollectionArea,
    CollectionAreaId,
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
    sheet's header row; ``content`` is populated by the indexing use case from
    the document's searchable-column mapping."""

    sheet: str
    row_number: int
    content: str
    cells: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CollectionObjectSearchQuery:
    q: str
    collection_id: CollectionId | None
    page: int
    size: int


@dataclass(frozen=True, slots=True)
class ObjectSnapshot:
    inventory_number: str
    display_title: str
    object_name: str
    brief_description_snapshot: str | None
    category: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    collection_id: CollectionId
    collection_name: str
    source_document_id: SourceDocumentId
    file_name: str
    sheet: str
    row_number: int
    cells: Mapping[str, str]
    highlight: str
    object_snapshot: ObjectSnapshot | None = None


@dataclass(frozen=True, slots=True)
class CollectionObjectSearchResult:
    total: int
    items: list[SearchHit]


class CollectionRepository(Protocol):
    async def add(self, collection: Collection) -> None: ...

    async def save(self, collection: Collection) -> None: ...

    async def delete(self, collection_id: CollectionId) -> None:
        """Hard-delete the collection row. Caller must have already removed
        its curators, source documents and indexed rows."""
        ...

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

    async def remove_all_curators(self, collection_id: CollectionId) -> None: ...

    async def count_live_documents(self) -> dict[CollectionId, int]: ...

    # ── Collection areas (catalogue classification above Collection) ───────

    async def add_area(self, area: CollectionArea) -> None: ...

    async def save_area(self, area: CollectionArea) -> None: ...

    async def delete_area(self, area_id: CollectionAreaId) -> None: ...

    async def list_areas(self) -> list[CollectionArea]: ...

    async def get_area_by_id(
        self, area_id: CollectionAreaId
    ) -> CollectionArea | None: ...

    async def count_collections_by_area(self) -> dict[CollectionAreaId, int]: ...


class SourceDocumentRepository(Protocol):
    async def add(self, document: SourceDocument) -> None: ...

    async def get_by_id(
        self, document_id: SourceDocumentId
    ) -> SourceDocument | None: ...

    async def list_live_by_collection(
        self, collection_id: CollectionId
    ) -> list[SourceDocument]: ...

    async def list_all_by_collection(
        self, collection_id: CollectionId
    ) -> list[SourceDocument]:
        """Every document of the collection, live or already soft-deleted —
        used to reclaim files when the collection itself is removed."""
        ...

    async def find_live_by_hash(
        self, collection_id: CollectionId, content_hash: str
    ) -> SourceDocument | None: ...

    async def find_live_by_file_name(
        self, collection_id: CollectionId, file_name: str
    ) -> SourceDocument | None: ...

    async def save(self, document: SourceDocument) -> None: ...

    async def delete_all_by_collection(self, collection_id: CollectionId) -> None: ...


class CollectionObjectIndexPort(Protocol):
    """The searchable object index: write side (index/remove) feeds the
    Collection Data Sources admin flow; ``search`` is the read side consumed by
    Objects -> Search."""

    async def index(
        self,
        source_document_id: SourceDocumentId,
        collection_id: CollectionId,
        rows: Sequence[ParsedRow],
    ) -> int:
        """Replace the document's indexed rows; returns the row count."""
        ...

    async def remove_document(self, source_document_id: SourceDocumentId) -> None: ...

    async def remove_collection(self, collection_id: CollectionId) -> None:
        """Bulk-remove every indexed row of the collection (its source
        documents are being removed too)."""
        ...

    async def list_columns(self, source_document_id: SourceDocumentId) -> list[str]:
        """Return the union of indexed cell keys for one source document."""
        ...

    async def search(
        self, query: CollectionObjectSearchQuery
    ) -> CollectionObjectSearchResult:
        """Full-text + trigram search over live (non-deleted-source) objects,
        optionally scoped to one collection."""
        ...


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
