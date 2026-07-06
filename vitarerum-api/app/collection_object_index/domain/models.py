"""Collection Object Index domain model.

A ``Collection`` is a curated scientific collection (Zoology, Botany, ...);
each collection has one or more staff-managed source documents (``.xlsx``
files) whose rows are indexed as searchable collection objects.
``CollectionArea`` is an administrative/scientific classification one level
above ``Collection`` (catalogue organisation only — permissions and ingestion
stay at the ``Collection`` level). Pure domain: standard library plus the
Shared Kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NewType

from app.collection_object_index.domain.enums import (
    SourceDocumentStatus,
    SourceKind,
)
from app.shared.kernel import PermissionId

CollectionAreaId = NewType("CollectionAreaId", str)
CollectionId = NewType("CollectionId", str)
SourceDocumentId = NewType("SourceDocumentId", str)


class CollectionNotFound(Exception):
    """Raised when a collection id does not resolve."""


class CollectionAreaNotFound(Exception):
    """Raised when a collection area id does not resolve."""


class CollectionAreaInUse(Exception):
    """Raised when removing a collection area that still has collections
    assigned to it."""


class SourceDocumentNotFound(Exception):
    """Raised when a source document id does not resolve (or is deleted)."""


@dataclass(slots=True)
class CollectionArea:
    """Administrative/scientific classification above `Collection` (e.g.
    Botany groups the Fungi, Algae, Xylotheque collections). Administered by
    SYS_ADMIN; a classification only — curator assignment and ingestion stay
    at the `Collection` level. Removal is blocked while collections are still
    assigned to the area (see `CollectionAreaInUse`): unlike `Collection`,
    cascading the removal would take out every collection under it."""

    id: CollectionAreaId
    name: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("Collection area name is required.")
        self.name = name

    def rename(self, name: str, *, updated_at: datetime) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Collection area name is required.")
        self.name = name
        self.updated_at = updated_at


@dataclass(slots=True)
class Collection:
    """A curated scientific collection. Administered by SYS_ADMIN (create,
    rename, remove); seeded with a starting catalogue of 14. There is no
    "inactive" state — removal is permanent and takes everything under the
    collection (curators, source documents, indexed rows, files) with it."""

    id: CollectionId
    area_id: CollectionAreaId
    name: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("Collection name is required.")
        self.name = name

    def rename(self, name: str, *, updated_at: datetime) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Collection name is required.")
        self.name = name
        self.updated_at = updated_at

    def move_to_area(self, area_id: CollectionAreaId, *, updated_at: datetime) -> None:
        self.area_id = area_id
        self.updated_at = updated_at


@dataclass(frozen=True, slots=True)
class CuratorAssignment:
    """A curator (identity permission) in charge of a collection.
    ``assigned_by`` records who granted the assignment, for audit."""

    collection_id: CollectionId
    permission_id: PermissionId
    assigned_at: datetime
    assigned_by: PermissionId


@dataclass(slots=True)
class SourceDocument:
    """A managed spreadsheet whose rows feed the object index.

    ``deleted_at`` soft-deletes the record (its index rows are removed on
    delete/replace); ``status``/``error_message``/``row_count`` back the
    management UI's status badge."""

    id: SourceDocumentId
    collection_id: CollectionId
    file_name: str
    file_reference: str
    source_kind: SourceKind
    content_hash: str
    status: SourceDocumentStatus
    uploaded_by: PermissionId
    uploaded_at: datetime
    error_message: str | None = None
    row_count: int | None = None
    indexed_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def mark_indexed(self, *, indexed_at: datetime, row_count: int) -> None:
        self.status = SourceDocumentStatus.INDEXED
        self.indexed_at = indexed_at
        self.row_count = row_count
        self.error_message = None

    def mark_error(self, message: str) -> None:
        self.status = SourceDocumentStatus.ERROR
        self.error_message = message
        self.row_count = None
        self.indexed_at = None

    def mark_deleted(self, deleted_at: datetime) -> None:
        self.deleted_at = deleted_at
