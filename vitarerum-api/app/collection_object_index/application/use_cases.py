"""Use cases for the Collection Object Index context.

Commands manage a collection's source documents (upload / delete / reindex)
and curator assignments; queries back the management UI. Indexing is
synchronous in the MVP: the upload request parses the spreadsheet and writes
the object rows before returning.

File-cleanup protocol (mirrors Document Templates): commands never delete
stored files themselves — they return the affected file references so the
caller can reclaim them only *after* its transaction commits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import uuid4

from app.collection_object_index.application.authorization import (
    can_manage_all_collections,
    require_collection_scope,
    require_curator_admin,
)
from app.collection_object_index.application.ports import (
    Clock,
    CollectionObjectIndexPort,
    CollectionObjectParserPort,
    CollectionRepository,
    FileStorage,
    InvalidSpreadsheet,
    SourceDocumentRepository,
)
from app.collection_object_index.application.read_models import CollectionView
from app.collection_object_index.domain.enums import SourceDocumentStatus, SourceKind
from app.collection_object_index.domain.models import (
    CollectionId,
    CollectionNotFound,
    CuratorAssignment,
    SourceDocument,
    SourceDocumentId,
    SourceDocumentNotFound,
)
from app.identity.public import Actor, GroupName
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
    """Every active collection, flagged with whether the caller may manage it.

    Staff outside the management groups and without assignments (e.g.
    DIRECTION) still see the catalogue, with nothing manageable."""

    def __init__(self, collections: CollectionRepository) -> None:
        self._collections = collections

    async def execute(self, caller: Actor) -> list[CollectionView]:
        manage_all = can_manage_all_collections(caller)
        curated = await _curated_ids(caller, self._collections)
        curators = await self._collections.list_curators()
        counts = await self._collections.count_live_documents()
        by_collection: dict[CollectionId, list[CuratorAssignment]] = {}
        for assignment in curators:
            by_collection.setdefault(assignment.collection_id, []).append(assignment)
        return [
            CollectionView(
                collection=collection,
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


@dataclass(frozen=True, slots=True)
class UploadSourceDocumentResult:
    document: SourceDocument
    created: bool
    # File reference of a replaced previous version, reclaimed by the caller
    # after commit; None when nothing was replaced.
    replaced_file_reference: str | None


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
            count = await self._index.index(document.id, document.collection_id, rows)
        except InvalidSpreadsheet as exc:
            document.mark_error(str(exc))
        else:
            document.mark_indexed(indexed_at=self._clock.now(), row_count=count)


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
        await self._index.remove_document(document.id)
        try:
            rows = self._parser.parse(content)
            if len(rows) > MAX_INDEXED_ROWS:
                raise InvalidSpreadsheet(
                    f"Spreadsheet has {len(rows)} rows; "
                    f"the limit is {MAX_INDEXED_ROWS}."
                )
            count = await self._index.index(document.id, document.collection_id, rows)
        except InvalidSpreadsheet as exc:
            document.mark_error(str(exc))
        else:
            document.mark_indexed(indexed_at=self._clock.now(), row_count=count)
        await self._documents.save(document)
        return document


class AssignCollectionCurator:
    def __init__(self, collections: CollectionRepository, clock: Clock) -> None:
        self._collections = collections
        self._clock = clock

    async def execute(
        self, caller: Actor, collection_id: CollectionId, permission_id: PermissionId
    ) -> CuratorAssignment:
        require_curator_admin(caller)
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
        require_curator_admin(caller)
        if await self._collections.get_by_id(collection_id) is None:
            raise CollectionNotFound(collection_id)
        await self._collections.remove_curator(collection_id, permission_id)
