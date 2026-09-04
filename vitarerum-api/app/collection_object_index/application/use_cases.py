"""Use cases for the Collection Object Index context.

Commands manage the collection catalog itself (create/rename/remove,
SYS_ADMIN only — removal is permanent, taking curators/documents/index/files
with it), a collection's source documents (upload / delete / reindex), and
curator assignments; queries back the management UI. Indexing is synchronous
in the MVP: the upload request parses the spreadsheet and writes the object
rows before returning.

File-cleanup protocol (mirrors Document Templates): commands never delete
stored files themselves — they return the affected file references so the
caller can reclaim them only *after* its transaction commits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.collection_object_index.application.authorization import (
    can_manage_all_collections,
    require_catalog_admin,
    require_collection_scope,
)
from app.collection_object_index.application.ports import (
    Clock,
    CollectionObjectIndexPort,
    CollectionObjectParserPort,
    CollectionObjectSearchQuery,
    CollectionObjectSearchResult,
    CollectionRepository,
    FileStorage,
    InvalidSpreadsheet,
    ParsedRow,
    SearchableColumnScope,
    SourceDocumentRepository,
)
from app.collection_object_index.application.read_models import (
    CollectionAreaView,
    CollectionView,
)
from app.collection_object_index.domain.enums import SourceDocumentStatus, SourceKind
from app.collection_object_index.domain.models import (
    Collection,
    CollectionArea,
    CollectionAreaId,
    CollectionAreaInUse,
    CollectionAreaNotFound,
    CollectionId,
    CollectionNotFound,
    CuratorAssignment,
    ObjectSnapshotMapping,
    SourceDocument,
    SourceDocumentId,
    SourceDocumentMappingInvalid,
    SourceDocumentNotFound,
    SourceDocumentSearchableColumnsEmpty,
)
from app.identity.public import Actor, GroupName, PermissionReader, PermissionView
from app.shared.authorization import require_staff
from app.shared.kernel import PermissionId

# Synchronous indexing happens inside the upload request; cap the row count so
# a huge spreadsheet cannot stall the request. Async ingestion arrives with the
# remote sources.
MAX_INDEXED_ROWS = 20_000


def _new_id() -> str:
    return str(uuid4())


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_reference(document_id: str, file_name: str) -> str:
    return f"collection_object_index/{document_id}/{file_name}"


async def _curated_ids(
    caller: Actor, collections: CollectionRepository
) -> set[CollectionId]:
    """The collections the caller curates — only relevant for CURATORIAL."""
    if caller.group != GroupName.CURATORIAL:
        return set()
    return await collections.list_curated_collection_ids(caller.id)


# ── Queries ───────────────────────────────────────────────────────────────────


class ListManageableCollections:
    """Every collection in the catalogue, flagged with whether the caller may
    manage it.

    Staff outside the management groups and without assignments (e.g.
    DIRECTION) still see the catalogue, with nothing manageable."""

    def __init__(self, collections: CollectionRepository) -> None:
        self._collections = collections

    async def execute(self, caller: Actor) -> list[CollectionView]:
        manage_all = can_manage_all_collections(caller)
        curated = await _curated_ids(caller, self._collections)
        curators = await self._collections.list_curators()
        counts = await self._collections.count_live_documents()
        area_names = {a.id: a.name for a in await self._collections.list_areas()}
        by_collection: dict[CollectionId, list[CuratorAssignment]] = {}
        for assignment in curators:
            by_collection.setdefault(assignment.collection_id, []).append(assignment)
        return [
            CollectionView(
                collection=collection,
                area_name=area_names.get(collection.area_id, ""),
                curators=by_collection.get(collection.id, []),
                document_count=counts.get(collection.id, 0),
                manageable=manage_all or collection.id in curated,
            )
            for collection in await self._collections.list_all()
        ]


class ListCollectionSourceDocuments:
    def __init__(
        self,
        collections: CollectionRepository,
        documents: SourceDocumentRepository,
    ) -> None:
        self._collections = collections
        self._documents = documents

    async def execute(
        self, caller: Actor, collection_id: CollectionId
    ) -> list[SourceDocument]:
        if await self._collections.get_by_id(collection_id) is None:
            raise CollectionNotFound(collection_id)
        require_collection_scope(
            caller, collection_id, await _curated_ids(caller, self._collections)
        )
        return await self._documents.list_live_by_collection(collection_id)


# ── Commands ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class UploadSourceDocumentInput:
    caller: Actor
    collection_id: CollectionId
    file_name: str
    content: bytes
    object_mapping: ObjectSnapshotMapping


@dataclass(frozen=True, slots=True)
class UploadSourceDocumentResult:
    document: SourceDocument
    created: bool
    # File reference of a replaced previous version, reclaimed by the caller
    # after commit; None when nothing was replaced.
    replaced_file_reference: str | None


class PreviewSourceDocumentColumns:
    def __init__(
        self,
        collections: CollectionRepository,
        parser: CollectionObjectParserPort,
    ) -> None:
        self._collections = collections
        self._parser = parser

    async def execute(
        self, caller: Actor, collection_id: CollectionId, content: bytes
    ) -> list[str]:
        if await self._collections.get_by_id(collection_id) is None:
            raise CollectionNotFound(collection_id)
        require_collection_scope(
            caller,
            collection_id,
            await _curated_ids(caller, self._collections),
        )
        rows = self._parser.parse(content)
        if len(rows) > MAX_INDEXED_ROWS:
            raise InvalidSpreadsheet(
                f"Spreadsheet has {len(rows)} rows; the limit is {MAX_INDEXED_ROWS}."
            )
        return _columns_from_rows(rows)


class UploadSourceDocument:
    """Upload + synchronous indexing, with hash-based idempotency.

    - identical live file (same ``content_hash``) -> dedupe: no-op, returns the
      existing document with ``created=False``;
    - same ``file_name``, different hash -> new version: the previous source is
      soft-deleted and its index rows removed before the new one is indexed;
    - parse failures are persisted as ``status=ERROR`` (with the file kept) so
      the management UI can surface the failure."""

    def __init__(
        self,
        collections: CollectionRepository,
        documents: SourceDocumentRepository,
        storage: FileStorage,
        parser: CollectionObjectParserPort,
        index: CollectionObjectIndexPort,
        clock: Clock,
    ) -> None:
        self._collections = collections
        self._documents = documents
        self._storage = storage
        self._parser = parser
        self._index = index
        self._clock = clock

    async def execute(
        self, data: UploadSourceDocumentInput
    ) -> UploadSourceDocumentResult:
        if await self._collections.get_by_id(data.collection_id) is None:
            raise CollectionNotFound(data.collection_id)
        require_collection_scope(
            data.caller,
            data.collection_id,
            await _curated_ids(data.caller, self._collections),
        )

        content_hash = _content_hash(data.content)
        existing = await self._documents.find_live_by_hash(
            data.collection_id, content_hash
        )
        if existing is not None:
            rows = self._parser.parse(data.content)
            if len(rows) > MAX_INDEXED_ROWS:
                raise InvalidSpreadsheet(
                    f"Spreadsheet has {len(rows)} rows; "
                    f"the limit is {MAX_INDEXED_ROWS}."
                )
            _validate_mapping_columns(
                data.object_mapping, set(_columns_from_rows(rows))
            )
            existing.configure_object_snapshot(data.object_mapping)
            await _reindex_rows(
                document=existing,
                rows=rows,
                index=self._index,
                indexed_at=self._clock.now(),
            )
            await self._documents.save(existing)
            return UploadSourceDocumentResult(
                document=existing, created=False, replaced_file_reference=None
            )

        now = self._clock.now()
        replaced_reference: str | None = None
        previous = await self._documents.find_live_by_file_name(
            data.collection_id, data.file_name
        )
        if previous is not None:
            await self._index.remove_document(previous.id)
            previous.mark_deleted(now)
            await self._documents.save(previous)
            replaced_reference = previous.file_reference

        document_id = SourceDocumentId(_new_id())
        reference = await self._storage.save(
            data.content, _file_reference(document_id, data.file_name)
        )
        document = SourceDocument(
            id=document_id,
            collection_id=data.collection_id,
            file_name=data.file_name,
            file_reference=reference,
            source_kind=SourceKind.UPLOAD,
            content_hash=content_hash,
            status=SourceDocumentStatus.UPLOADED,
            uploaded_by=data.caller.id,
            uploaded_at=now,
            object_snapshot_mapping=data.object_mapping,
        )
        try:
            await self._documents.add(document)
            await self._index_rows(document, data.content)
            await self._documents.save(document)
        except Exception:
            # Persistence failed: the just-written file would be orphaned.
            await self._storage.delete(reference)
            raise
        return UploadSourceDocumentResult(
            document=document, created=True, replaced_file_reference=replaced_reference
        )

    async def _index_rows(self, document: SourceDocument, content: bytes) -> None:
        try:
            rows = self._parser.parse(content)
            if len(rows) > MAX_INDEXED_ROWS:
                raise InvalidSpreadsheet(
                    f"Spreadsheet has {len(rows)} rows; "
                    f"the limit is {MAX_INDEXED_ROWS}."
                )
            if document.object_snapshot_mapping is None:
                raise SourceDocumentMappingInvalid("Object mapping is required.")
            _validate_mapping_columns(
                document.object_snapshot_mapping, set(_columns_from_rows(rows))
            )
            await _reindex_rows(
                document=document,
                rows=rows,
                index=self._index,
                indexed_at=self._clock.now(),
            )
        except InvalidSpreadsheet as exc:
            document.mark_error(str(exc))


def _columns_from_rows(rows: list[ParsedRow]) -> list[str]:
    columns: set[str] = set()
    for row in rows:
        columns.update(str(key) for key in row.cells.keys())
    return sorted(columns, key=str.casefold)


class DeleteSourceDocument:
    """Soft-deletes the record and removes its index rows; returns the file
    reference for the caller to reclaim after commit."""

    def __init__(
        self,
        collections: CollectionRepository,
        documents: SourceDocumentRepository,
        index: CollectionObjectIndexPort,
        clock: Clock,
    ) -> None:
        self._collections = collections
        self._documents = documents
        self._index = index
        self._clock = clock

    async def execute(self, caller: Actor, document_id: SourceDocumentId) -> str:
        document = await self._documents.get_by_id(document_id)
        if document is None or document.is_deleted:
            raise SourceDocumentNotFound(document_id)
        require_collection_scope(
            caller,
            document.collection_id,
            await _curated_ids(caller, self._collections),
        )
        await self._index.remove_document(document.id)
        document.mark_deleted(self._clock.now())
        await self._documents.save(document)
        return document.file_reference


class ReindexSourceDocument:
    """Re-reads the stored file and rebuilds the document's index rows."""

    def __init__(
        self,
        collections: CollectionRepository,
        documents: SourceDocumentRepository,
        storage: FileStorage,
        parser: CollectionObjectParserPort,
        index: CollectionObjectIndexPort,
        clock: Clock,
    ) -> None:
        self._collections = collections
        self._documents = documents
        self._storage = storage
        self._parser = parser
        self._index = index
        self._clock = clock

    async def execute(
        self, caller: Actor, document_id: SourceDocumentId
    ) -> SourceDocument:
        document = await self._documents.get_by_id(document_id)
        if document is None or document.is_deleted:
            raise SourceDocumentNotFound(document_id)
        require_collection_scope(
            caller,
            document.collection_id,
            await _curated_ids(caller, self._collections),
        )
        content = await self._storage.read(document.file_reference)
        try:
            rows = self._parser.parse(content)
            if len(rows) > MAX_INDEXED_ROWS:
                raise InvalidSpreadsheet(
                    f"Spreadsheet has {len(rows)} rows; "
                    f"the limit is {MAX_INDEXED_ROWS}."
                )
            if document.object_snapshot_mapping is None:
                raise SourceDocumentMappingInvalid("Object mapping is required.")
            _validate_mapping_columns(
                document.object_snapshot_mapping,
                set(_columns_from_rows(rows)),
                require_searchable_columns=False,
            )
            await _reindex_rows(
                document=document,
                rows=rows,
                index=self._index,
                indexed_at=self._clock.now(),
            )
        except InvalidSpreadsheet as exc:
            document.mark_error(str(exc))
        await self._documents.save(document)
        return document


@dataclass(frozen=True, slots=True)
class UpdateSourceDocumentObjectMappingInput:
    caller: Actor
    document_id: SourceDocumentId
    inventory_number_column: str
    display_title_columns: tuple[str, ...]
    object_name_column: str | None
    description_columns: tuple[str, ...]
    searchable_columns: tuple[str, ...]


class ListSourceDocumentColumns:
    def __init__(
        self,
        collections: CollectionRepository,
        documents: SourceDocumentRepository,
        index: CollectionObjectIndexPort,
    ) -> None:
        self._collections = collections
        self._documents = documents
        self._index = index

    async def execute(self, caller: Actor, document_id: SourceDocumentId) -> list[str]:
        document = await self._documents.get_by_id(document_id)
        if document is None or document.is_deleted:
            raise SourceDocumentNotFound(document_id)
        require_collection_scope(
            caller,
            document.collection_id,
            await _curated_ids(caller, self._collections),
        )
        return await self._index.list_columns(document_id)


class UpdateSourceDocumentObjectMapping:
    def __init__(
        self,
        collections: CollectionRepository,
        documents: SourceDocumentRepository,
        storage: FileStorage,
        parser: CollectionObjectParserPort,
        index: CollectionObjectIndexPort,
        clock: Clock,
    ) -> None:
        self._collections = collections
        self._documents = documents
        self._storage = storage
        self._parser = parser
        self._index = index
        self._clock = clock

    async def execute(
        self, data: UpdateSourceDocumentObjectMappingInput
    ) -> SourceDocument:
        document = await self._documents.get_by_id(data.document_id)
        if document is None or document.is_deleted:
            raise SourceDocumentNotFound(data.document_id)
        require_collection_scope(
            data.caller,
            document.collection_id,
            await _curated_ids(data.caller, self._collections),
        )
        mapping = ObjectSnapshotMapping(
            inventory_number_column=data.inventory_number_column,
            display_title_columns=data.display_title_columns,
            object_name_column=data.object_name_column,
            description_columns=data.description_columns,
            searchable_columns=data.searchable_columns,
        )
        content = await self._storage.read(document.file_reference)
        rows = self._parser.parse(content)
        if len(rows) > MAX_INDEXED_ROWS:
            raise InvalidSpreadsheet(
                f"Spreadsheet has {len(rows)} rows; the limit is {MAX_INDEXED_ROWS}."
            )
        columns = set(_columns_from_rows(rows))
        _validate_mapping_columns(mapping, columns)
        document.configure_object_snapshot(mapping)
        await _reindex_rows(
            document=document,
            rows=rows,
            index=self._index,
            indexed_at=self._clock.now(),
        )
        await self._documents.save(document)
        return document


def _validate_mapping_columns(
    mapping: ObjectSnapshotMapping,
    columns: set[str],
    *,
    require_searchable_columns: bool = True,
) -> None:
    if require_searchable_columns and not mapping.searchable_columns:
        raise SourceDocumentSearchableColumnsEmpty(
            "searchableColumns must include at least one column."
        )
    required = [
        mapping.inventory_number_column,
        *mapping.display_title_columns,
        *(column for column in [mapping.object_name_column] if column is not None),
        *mapping.description_columns,
        *mapping.searchable_columns,
    ]
    missing = [column for column in required if column not in columns]
    if missing:
        raise SourceDocumentMappingInvalid(
            "Unknown source document columns: " + ", ".join(missing)
        )


def _rows_with_searchable_content(
    rows: list[ParsedRow], mapping: ObjectSnapshotMapping
) -> list[ParsedRow]:
    searchable_columns = mapping.searchable_columns or tuple(_columns_from_rows(rows))
    return [
        ParsedRow(
            sheet=row.sheet,
            row_number=row.row_number,
            content=" ".join(
                row.cells[column]
                for column in searchable_columns
                if row.cells.get(column)
            ),
            cells=row.cells,
        )
        for row in rows
    ]


async def _reindex_rows(
    *,
    document: SourceDocument,
    rows: list[ParsedRow],
    index: CollectionObjectIndexPort,
    indexed_at: datetime,
) -> None:
    if document.object_snapshot_mapping is None:
        raise SourceDocumentMappingInvalid("Object mapping is required.")
    indexed_rows = _rows_with_searchable_content(rows, document.object_snapshot_mapping)
    count = await index.index(document.id, document.collection_id, indexed_rows)
    document.mark_indexed(indexed_at=indexed_at, row_count=count)


class AssignCollectionCurator:
    def __init__(self, collections: CollectionRepository, clock: Clock) -> None:
        self._collections = collections
        self._clock = clock

    async def execute(
        self, caller: Actor, collection_id: CollectionId, permission_id: PermissionId
    ) -> CuratorAssignment:
        require_catalog_admin(caller)
        if await self._collections.get_by_id(collection_id) is None:
            raise CollectionNotFound(collection_id)
        current = await self._collections.list_curators(collection_id)
        for assignment in current:
            if assignment.permission_id == permission_id:
                return assignment  # idempotent
        assignment = CuratorAssignment(
            collection_id=collection_id,
            permission_id=permission_id,
            assigned_at=self._clock.now(),
            assigned_by=caller.id,
        )
        await self._collections.add_curator(assignment)
        return assignment


class RemoveCollectionCurator:
    def __init__(self, collections: CollectionRepository) -> None:
        self._collections = collections

    async def execute(
        self, caller: Actor, collection_id: CollectionId, permission_id: PermissionId
    ) -> None:
        require_catalog_admin(caller)
        if await self._collections.get_by_id(collection_id) is None:
            raise CollectionNotFound(collection_id)
        await self._collections.remove_curator(collection_id, permission_id)


# ── Collection catalog admin (SYS_ADMIN only) ───────────────────────────────


@dataclass(frozen=True, slots=True)
class CreateCollectionInput:
    caller: Actor
    name: str
    area_id: CollectionAreaId


class CreateCollection:
    def __init__(self, collections: CollectionRepository, clock: Clock) -> None:
        self._collections = collections
        self._clock = clock

    async def execute(self, data: CreateCollectionInput) -> Collection:
        require_catalog_admin(data.caller)
        if await self._collections.get_area_by_id(data.area_id) is None:
            raise CollectionAreaNotFound(data.area_id)
        now = self._clock.now()
        collection = Collection(
            id=CollectionId(_new_id()),
            area_id=data.area_id,
            name=data.name,
            created_at=now,
            updated_at=now,
        )
        await self._collections.add(collection)
        return collection


class GetCollection:
    """A single collection, enriched like the management list (curators,
    live-document count, whether the caller may manage it)."""

    def __init__(self, collections: CollectionRepository) -> None:
        self._collections = collections

    async def execute(
        self, caller: Actor, collection_id: CollectionId
    ) -> CollectionView:
        collection = await self._collections.get_by_id(collection_id)
        if collection is None:
            raise CollectionNotFound(collection_id)
        manage_all = can_manage_all_collections(caller)
        curated = await _curated_ids(caller, self._collections)
        curators = await self._collections.list_curators(collection_id)
        counts = await self._collections.count_live_documents()
        area = await self._collections.get_area_by_id(collection.area_id)
        return CollectionView(
            collection=collection,
            area_name=area.name if area is not None else "",
            curators=curators,
            document_count=counts.get(collection_id, 0),
            manageable=manage_all or collection_id in curated,
        )


@dataclass(frozen=True, slots=True)
class UpdateCollectionInput:
    caller: Actor
    collection_id: CollectionId
    name: str


class UpdateCollection:
    """Renames a collection."""

    def __init__(self, collections: CollectionRepository, clock: Clock) -> None:
        self._collections = collections
        self._clock = clock

    async def execute(self, data: UpdateCollectionInput) -> Collection:
        require_catalog_admin(data.caller)
        collection = await self._collections.get_by_id(data.collection_id)
        if collection is None:
            raise CollectionNotFound(data.collection_id)
        collection.rename(data.name, updated_at=self._clock.now())
        await self._collections.save(collection)
        return collection


@dataclass(frozen=True, slots=True)
class MoveCollectionToAreaInput:
    caller: Actor
    collection_id: CollectionId
    area_id: CollectionAreaId


class MoveCollectionToArea:
    """Moves a collection to a different area — a dedicated command (like
    curator assign/remove) rather than a side effect of the generic rename,
    since it has its own validation (target area must exist)."""

    def __init__(self, collections: CollectionRepository, clock: Clock) -> None:
        self._collections = collections
        self._clock = clock

    async def execute(self, data: MoveCollectionToAreaInput) -> Collection:
        require_catalog_admin(data.caller)
        collection = await self._collections.get_by_id(data.collection_id)
        if collection is None:
            raise CollectionNotFound(data.collection_id)
        if await self._collections.get_area_by_id(data.area_id) is None:
            raise CollectionAreaNotFound(data.area_id)
        collection.move_to_area(data.area_id, updated_at=self._clock.now())
        await self._collections.save(collection)
        return collection


class ListCuratorCandidates:
    """Permissions in the CURATORIAL group, for the collection admin's
    curator picker — decouples it from the generic identity users API."""

    def __init__(self, permission_reader: PermissionReader) -> None:
        self._permission_reader = permission_reader

    async def execute(self, caller: Actor) -> list[PermissionView]:
        require_catalog_admin(caller)
        return await self._permission_reader.list_by_group(GroupName.CURATORIAL)


class RemoveCollection:
    """Permanently removes a collection and everything under it: indexed
    rows, source documents (live or already soft-deleted), curator
    assignments, and the collection row itself. Irreversible.

    Deletion order respects FKs: indexed rows -> source documents ->
    curators -> collection. Returns every source document's file reference
    (live or already soft-deleted) for the caller to reclaim from storage
    only *after* its transaction commits — ``FileStorage.delete`` is
    idempotent, so attempting all of them (not just the still-live ones) is
    safe and covers any document whose file wasn't already cleaned up."""

    def __init__(
        self,
        collections: CollectionRepository,
        documents: SourceDocumentRepository,
        index: CollectionObjectIndexPort,
    ) -> None:
        self._collections = collections
        self._documents = documents
        self._index = index

    async def execute(self, caller: Actor, collection_id: CollectionId) -> list[str]:
        require_catalog_admin(caller)
        if await self._collections.get_by_id(collection_id) is None:
            raise CollectionNotFound(collection_id)

        documents = await self._documents.list_all_by_collection(collection_id)
        file_references = [document.file_reference for document in documents]

        await self._index.remove_collection(collection_id)
        await self._documents.delete_all_by_collection(collection_id)
        await self._collections.remove_all_curators(collection_id)
        await self._collections.delete(collection_id)
        return file_references


# ── Collection areas (catalogue classification, SYS_ADMIN only) ────────────


class ListCollectionAreas:
    """Every collection area with its live collection count — backs the area
    management screen and the create-collection area picker (both SYS_ADMIN
    only; other staff see area info denormalised on the collection itself)."""

    def __init__(self, collections: CollectionRepository) -> None:
        self._collections = collections

    async def execute(self, caller: Actor) -> list[CollectionAreaView]:
        require_catalog_admin(caller)
        counts = await self._collections.count_collections_by_area()
        return [
            CollectionAreaView(area=area, collection_count=counts.get(area.id, 0))
            for area in await self._collections.list_areas()
        ]


@dataclass(frozen=True, slots=True)
class CreateCollectionAreaInput:
    caller: Actor
    name: str


class CreateCollectionArea:
    def __init__(self, collections: CollectionRepository, clock: Clock) -> None:
        self._collections = collections
        self._clock = clock

    async def execute(self, data: CreateCollectionAreaInput) -> CollectionArea:
        require_catalog_admin(data.caller)
        now = self._clock.now()
        area = CollectionArea(
            id=CollectionAreaId(_new_id()),
            name=data.name,
            created_at=now,
            updated_at=now,
        )
        await self._collections.add_area(area)
        return area


@dataclass(frozen=True, slots=True)
class UpdateCollectionAreaInput:
    caller: Actor
    area_id: CollectionAreaId
    name: str


class UpdateCollectionArea:
    """Renames a collection area."""

    def __init__(self, collections: CollectionRepository, clock: Clock) -> None:
        self._collections = collections
        self._clock = clock

    async def execute(self, data: UpdateCollectionAreaInput) -> CollectionArea:
        require_catalog_admin(data.caller)
        area = await self._collections.get_area_by_id(data.area_id)
        if area is None:
            raise CollectionAreaNotFound(data.area_id)
        area.rename(data.name, updated_at=self._clock.now())
        await self._collections.save_area(area)
        return area


class RemoveCollectionArea:
    """Blocks removal while any collection is still assigned to the area —
    unlike ``RemoveCollection``, cascading here would take out every
    collection (and its documents/index/files) under the area."""

    def __init__(self, collections: CollectionRepository) -> None:
        self._collections = collections

    async def execute(self, caller: Actor, area_id: CollectionAreaId) -> None:
        require_catalog_admin(caller)
        if await self._collections.get_area_by_id(area_id) is None:
            raise CollectionAreaNotFound(area_id)
        counts = await self._collections.count_collections_by_area()
        if counts.get(area_id, 0) > 0:
            raise CollectionAreaInUse(area_id)
        await self._collections.delete_area(area_id)


# ── Objects -> Search (read side) ────────────────────────────────────────────
#
# Search is deliberately broad: any authenticated staff member searches across
# every indexed collection. This
# avoids row-level ACLs in the index; the per-collection management scope
# above governs who may *change* the index, not who may search it.


@dataclass(frozen=True, slots=True)
class SearchableCollectionView:
    id: CollectionId
    name: str
    searchable_columns: tuple[str, ...]
    searchable_columns_total: int


_EMPTY_SCOPE = SearchableColumnScope(
    collection_id=CollectionId(""),
    searchable_columns=(),
    searchable_columns_total=0,
)


class ListSearchableCollections:
    """The collection catalogue, for the search screen's facet."""

    def __init__(
        self, collections: CollectionRepository, index: CollectionObjectIndexPort
    ) -> None:
        self._collections = collections
        self._index = index

    async def execute(self, caller: Actor) -> list[SearchableCollectionView]:
        require_staff(caller)
        collections = await self._collections.list_all()
        scopes = await self._index.list_searchable_collection_scopes(
            [collection.id for collection in collections], limit=12
        )
        return [
            SearchableCollectionView(
                id=collection.id,
                name=collection.name,
                searchable_columns=scopes.get(
                    collection.id, _EMPTY_SCOPE
                ).searchable_columns,
                searchable_columns_total=scopes.get(
                    collection.id, _EMPTY_SCOPE
                ).searchable_columns_total,
            )
            for collection in collections
        ]


class SearchCollectionObjects:
    def __init__(self, index: CollectionObjectIndexPort) -> None:
        self._index = index

    async def execute(
        self, caller: Actor, query: CollectionObjectSearchQuery
    ) -> CollectionObjectSearchResult:
        require_staff(caller)
        return await self._index.search(query)
