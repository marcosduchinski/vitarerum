"""SQLAlchemy adapters for the Collection Object Index ports."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.collection_object_index.application.ports import (
    CollectionObjectSearchQuery,
    CollectionObjectSearchResult,
    ParsedRow,
    SearchHit,
)
from app.collection_object_index.domain.enums import (
    SourceDocumentStatus,
    SourceKind,
)
from app.collection_object_index.domain.models import (
    Collection,
    CollectionId,
    CuratorAssignment,
    SourceDocument,
    SourceDocumentId,
)
from app.collection_object_index.infrastructure.models import (
    CollectionObjectRecord,
    CollectionRecord,
    CuratorRecord,
    SourceDocumentRecord,
)
from app.shared.kernel import PermissionId


def _to_collection(record: CollectionRecord) -> Collection:
    return Collection(
        id=CollectionId(record.id),
        name=record.name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_assignment(record: CuratorRecord) -> CuratorAssignment:
    return CuratorAssignment(
        collection_id=CollectionId(record.collection_id),
        permission_id=PermissionId(record.permission_id),
        assigned_at=record.assigned_at,
        assigned_by=PermissionId(record.assigned_by),
    )


def _to_document(record: SourceDocumentRecord) -> SourceDocument:
    return SourceDocument(
        id=SourceDocumentId(record.id),
        collection_id=CollectionId(record.collection_id),
        file_name=record.file_name,
        file_reference=record.file_reference,
        source_kind=SourceKind(record.source_kind),
        content_hash=record.content_hash,
        status=SourceDocumentStatus(record.status),
        error_message=record.error_message,
        row_count=record.row_count,
        uploaded_by=PermissionId(record.uploaded_by),
        uploaded_at=record.uploaded_at,
        indexed_at=record.indexed_at,
        deleted_at=record.deleted_at,
    )


def _apply_collection(record: CollectionRecord, collection: Collection) -> None:
    record.name = collection.name
    record.updated_at = collection.updated_at


def _apply_document(record: SourceDocumentRecord, document: SourceDocument) -> None:
    record.status = document.status.value
    record.error_message = document.error_message
    record.row_count = document.row_count
    record.indexed_at = document.indexed_at
    record.deleted_at = document.deleted_at


class SqlAlchemyCollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, collection: Collection) -> None:
        self._session.add(
            CollectionRecord(
                id=str(collection.id),
                name=collection.name,
                created_at=collection.created_at,
                updated_at=collection.updated_at,
            )
        )
        await self._session.flush()

    async def save(self, collection: Collection) -> None:
        record = await self._session.get(CollectionRecord, str(collection.id))
        if record is None:
            raise LookupError(f"No collection found with id {collection.id}")
        _apply_collection(record, collection)
        await self._session.flush()

    async def delete(self, collection_id: CollectionId) -> None:
        await self._session.execute(
            delete(CollectionRecord).where(CollectionRecord.id == str(collection_id))
        )

    async def list_all(self) -> list[Collection]:
        result = await self._session.execute(
            select(CollectionRecord).order_by(CollectionRecord.name)
        )
        return [_to_collection(r) for r in result.scalars()]

    async def get_by_id(self, collection_id: CollectionId) -> Collection | None:
        record = await self._session.get(CollectionRecord, str(collection_id))
        return _to_collection(record) if record else None

    async def list_curators(
        self, collection_id: CollectionId | None = None
    ) -> list[CuratorAssignment]:
        query = select(CuratorRecord).order_by(CuratorRecord.assigned_at)
        if collection_id is not None:
            query = query.where(CuratorRecord.collection_id == str(collection_id))
        result = await self._session.execute(query)
        return [_to_assignment(r) for r in result.scalars()]

    async def list_curated_collection_ids(
        self, permission_id: PermissionId
    ) -> set[CollectionId]:
        result = await self._session.execute(
            select(CuratorRecord.collection_id).where(
                CuratorRecord.permission_id == str(permission_id)
            )
        )
        return {CollectionId(row) for row in result.scalars()}

    async def add_curator(self, assignment: CuratorAssignment) -> None:
        self._session.add(
            CuratorRecord(
                collection_id=str(assignment.collection_id),
                permission_id=str(assignment.permission_id),
                assigned_at=assignment.assigned_at,
                assigned_by=str(assignment.assigned_by),
            )
        )
        await self._session.flush()

    async def remove_curator(
        self, collection_id: CollectionId, permission_id: PermissionId
    ) -> None:
        await self._session.execute(
            delete(CuratorRecord).where(
                CuratorRecord.collection_id == str(collection_id),
                CuratorRecord.permission_id == str(permission_id),
            )
        )

    async def remove_all_curators(self, collection_id: CollectionId) -> None:
        await self._session.execute(
            delete(CuratorRecord).where(
                CuratorRecord.collection_id == str(collection_id)
            )
        )

    async def count_live_documents(self) -> dict[CollectionId, int]:
        result = await self._session.execute(
            select(
                SourceDocumentRecord.collection_id,
                func.count(SourceDocumentRecord.id),
            )
            .where(SourceDocumentRecord.deleted_at.is_(None))
            .group_by(SourceDocumentRecord.collection_id)
        )
        return {CollectionId(cid): count for cid, count in result.all()}


class SqlAlchemySourceDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: SourceDocument) -> None:
        self._session.add(
            SourceDocumentRecord(
                id=str(document.id),
                collection_id=str(document.collection_id),
                file_name=document.file_name,
                file_reference=document.file_reference,
                source_kind=document.source_kind.value,
                content_hash=document.content_hash,
                status=document.status.value,
                error_message=document.error_message,
                row_count=document.row_count,
                uploaded_by=str(document.uploaded_by),
                uploaded_at=document.uploaded_at,
                indexed_at=document.indexed_at,
                deleted_at=document.deleted_at,
            )
        )
        await self._session.flush()

    async def get_by_id(self, document_id: SourceDocumentId) -> SourceDocument | None:
        record = await self._session.get(SourceDocumentRecord, str(document_id))
        return _to_document(record) if record else None

    async def list_live_by_collection(
        self, collection_id: CollectionId
    ) -> list[SourceDocument]:
        result = await self._session.execute(
            select(SourceDocumentRecord)
            .where(
                SourceDocumentRecord.collection_id == str(collection_id),
                SourceDocumentRecord.deleted_at.is_(None),
            )
            .order_by(SourceDocumentRecord.uploaded_at.desc())
        )
        return [_to_document(r) for r in result.scalars()]

    async def list_all_by_collection(
        self, collection_id: CollectionId
    ) -> list[SourceDocument]:
        result = await self._session.execute(
            select(SourceDocumentRecord)
            .where(SourceDocumentRecord.collection_id == str(collection_id))
            .order_by(SourceDocumentRecord.uploaded_at.desc())
        )
        return [_to_document(r) for r in result.scalars()]

    async def find_live_by_hash(
        self, collection_id: CollectionId, content_hash: str
    ) -> SourceDocument | None:
        result = await self._session.execute(
            select(SourceDocumentRecord).where(
                SourceDocumentRecord.collection_id == str(collection_id),
                SourceDocumentRecord.content_hash == content_hash,
                SourceDocumentRecord.deleted_at.is_(None),
            )
        )
        record = result.scalars().first()
        return _to_document(record) if record else None

    async def find_live_by_file_name(
        self, collection_id: CollectionId, file_name: str
    ) -> SourceDocument | None:
        result = await self._session.execute(
            select(SourceDocumentRecord).where(
                SourceDocumentRecord.collection_id == str(collection_id),
                SourceDocumentRecord.file_name == file_name,
                SourceDocumentRecord.deleted_at.is_(None),
            )
        )
        record = result.scalars().first()
        return _to_document(record) if record else None

    async def save(self, document: SourceDocument) -> None:
        record = await self._session.get(SourceDocumentRecord, str(document.id))
        if record is None:
            raise LookupError(f"No source document found with id {document.id}")
        _apply_document(record, document)
        await self._session.flush()

    async def delete_all_by_collection(self, collection_id: CollectionId) -> None:
        await self._session.execute(
            delete(SourceDocumentRecord).where(
                SourceDocumentRecord.collection_id == str(collection_id)
            )
        )


# word_similarity() computed value (not the `<%` operator's default 0.6 GUC
# threshold, which is too strict for a short code embedded in a long row — see
# docs/plans/plano-objects-search.md). Chosen empirically against the running
# dev database; revisit during ranking calibration.
_WORD_SIMILARITY_THRESHOLD = 0.4

# Shared by the row-fetch and count queries: only live (non-deleted-source)
# objects, optionally scoped to one collection, matching full-text ('simple'
# config — no stemming, safer for scientific names/codes), substring, or
# trigram word-similarity (catches a hyphenated code inside a long row).
_SEARCH_MATCH_SQL = """
    sd.deleted_at IS NULL
    -- Explicit CAST: asyncpg's extended query protocol can't infer a bind
    -- parameter's type when it's NULL and only ever compared with `IS NULL OR
    -- ... = $n` (AmbiguousParameterError without it). A bare `::varchar`
    -- immediately after the bind name also confuses text()'s param parser, so
    -- CAST(...) is used instead of the `::` shorthand.
    AND (CAST(:collection_id AS varchar) IS NULL
         OR co.collection_id = CAST(:collection_id AS varchar))
    AND (
        co.tsv @@ plainto_tsquery('simple', :q)
        OR co.content ILIKE '%' || :q || '%'
        OR word_similarity(:q, co.content) > :threshold
    )
"""

_SEARCH_SELECT_SQL = text(
    f"""
    SELECT
        co.collection_id,
        col.name AS collection_name,
        co.source_document_id,
        sd.file_name,
        co.sheet,
        co.row_number,
        co.cells,
        ts_headline(
            'simple', co.content, plainto_tsquery('simple', :q),
            'MaxFragments=1, MaxWords=20, MinWords=5'
        ) AS highlight,
        -- Provisional ranking: ts_rank (~0.0x) and word_similarity (0..1) have
        -- different scales; summed as a starting point, to be calibrated with
        -- real data rather than tuned with made-up weights now.
        ts_rank(co.tsv, plainto_tsquery('simple', :q))
            + word_similarity(:q, co.content) AS rank
    FROM collection_index_object co
    JOIN collection_index_source_document sd ON sd.id = co.source_document_id
    JOIN collection_index_collection col ON col.id = co.collection_id
    WHERE {_SEARCH_MATCH_SQL}
    ORDER BY rank DESC, co.source_document_id, co.row_number
    LIMIT :size OFFSET :offset
    """
)

_SEARCH_COUNT_SQL = text(
    f"""
    SELECT count(*)
    FROM collection_index_object co
    JOIN collection_index_source_document sd ON sd.id = co.source_document_id
    JOIN collection_index_collection col ON col.id = co.collection_id
    WHERE {_SEARCH_MATCH_SQL}
    """
)


class SqlAlchemyCollectionObjectIndex:
    """The searchable object index: bulk insert/delete of object rows (the
    PostgreSQL ``tsv`` column is generated by the database on insert), plus the
    Postgres-specific full-text/trigram ``search`` read side."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def index(
        self,
        source_document_id: SourceDocumentId,
        collection_id: CollectionId,
        rows: Sequence[ParsedRow],
    ) -> int:
        await self.remove_document(source_document_id)
        self._session.add_all(
            CollectionObjectRecord(
                id=str(uuid4()),
                collection_id=str(collection_id),
                source_document_id=str(source_document_id),
                sheet=row.sheet,
                row_number=row.row_number,
                content=row.content,
                cells=dict(row.cells),
            )
            for row in rows
        )
        await self._session.flush()
        return len(rows)

    async def remove_document(self, source_document_id: SourceDocumentId) -> None:
        await self._session.execute(
            delete(CollectionObjectRecord).where(
                CollectionObjectRecord.source_document_id == str(source_document_id)
            )
        )

    async def remove_collection(self, collection_id: CollectionId) -> None:
        await self._session.execute(
            delete(CollectionObjectRecord).where(
                CollectionObjectRecord.collection_id == str(collection_id)
            )
        )

    async def search(
        self, query: CollectionObjectSearchQuery
    ) -> CollectionObjectSearchResult:
        params = {
            "q": query.q,
            "collection_id": str(query.collection_id) if query.collection_id else None,
            "threshold": _WORD_SIMILARITY_THRESHOLD,
            "size": query.size,
            "offset": query.page * query.size,
        }
        total = await self._session.scalar(_SEARCH_COUNT_SQL, params)
        rows = await self._session.execute(_SEARCH_SELECT_SQL, params)
        items = [
            SearchHit(
                collection_id=CollectionId(row.collection_id),
                collection_name=row.collection_name,
                source_document_id=SourceDocumentId(row.source_document_id),
                file_name=row.file_name,
                sheet=row.sheet,
                row_number=row.row_number,
                cells=row.cells,
                highlight=row.highlight,
            )
            for row in rows
        ]
        return CollectionObjectSearchResult(total=total or 0, items=items)
