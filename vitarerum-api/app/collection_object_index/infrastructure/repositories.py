"""SQLAlchemy adapters for the Collection Object Index ports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.collection_object_index.application.ports import (
    CollectionObjectSearchQuery,
    CollectionObjectSearchResult,
    ObjectSnapshot,
    ParsedRow,
    SearchableColumnScope,
    SearchHit,
    SearchMatchReason,
)
from app.collection_object_index.domain.enums import (
    SourceDocumentStatus,
    SourceKind,
)
from app.collection_object_index.domain.models import (
    Collection,
    CollectionArea,
    CollectionAreaId,
    CollectionId,
    CuratorAssignment,
    ObjectSnapshotMapping,
    SourceDocument,
    SourceDocumentId,
)
from app.collection_object_index.infrastructure.models import (
    CollectionAreaRecord,
    CollectionObjectRecord,
    CollectionRecord,
    CuratorRecord,
    SourceDocumentRecord,
)
from app.shared.kernel import PermissionId


def _to_collection(record: CollectionRecord) -> Collection:
    return Collection(
        id=CollectionId(record.id),
        area_id=CollectionAreaId(record.area_id),
        name=record.name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_area(record: CollectionAreaRecord) -> CollectionArea:
    return CollectionArea(
        id=CollectionAreaId(record.id),
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
    display_title_columns = tuple(
        record.display_title_columns
        or ([record.display_title_column] if record.display_title_column else [])
    )
    mapping = (
        ObjectSnapshotMapping(
            inventory_number_column=record.inventory_number_column,
            display_title_columns=display_title_columns,
            object_name_column=record.object_name_column,
            description_columns=tuple(record.description_columns or ()),
            searchable_columns=tuple(record.searchable_columns or ()),
        )
        if record.inventory_number_column and display_title_columns
        else None
    )
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
        object_snapshot_mapping=mapping,
        content_matches_searchable_columns=(
            record.content_matches_searchable_columns
            if record.content_matches_searchable_columns is not None
            else True
        ),
    )


def _apply_collection(record: CollectionRecord, collection: Collection) -> None:
    record.area_id = str(collection.area_id)
    record.name = collection.name
    record.updated_at = collection.updated_at


def _apply_area(record: CollectionAreaRecord, area: CollectionArea) -> None:
    record.name = area.name
    record.updated_at = area.updated_at


def _apply_document(record: SourceDocumentRecord, document: SourceDocument) -> None:
    record.status = document.status.value
    record.error_message = document.error_message
    record.row_count = document.row_count
    record.indexed_at = document.indexed_at
    record.deleted_at = document.deleted_at
    mapping = document.object_snapshot_mapping
    record.inventory_number_column = (
        mapping.inventory_number_column if mapping is not None else None
    )
    record.display_title_column = (
        mapping.display_title_column if mapping is not None else None
    )
    record.display_title_columns = (
        list(mapping.display_title_columns) if mapping is not None else []
    )
    record.object_name_column = (
        mapping.object_name_column if mapping is not None else None
    )
    record.description_columns = (
        list(mapping.description_columns) if mapping is not None else []
    )
    record.searchable_columns = (
        list(mapping.searchable_columns) if mapping is not None else []
    )
    record.content_matches_searchable_columns = (
        document.content_matches_searchable_columns
    )


class SqlAlchemyCollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, collection: Collection) -> None:
        self._session.add(
            CollectionRecord(
                id=str(collection.id),
                area_id=str(collection.area_id),
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

    # ── Collection areas ─────────────────────────────────────────────────────

    async def add_area(self, area: CollectionArea) -> None:
        self._session.add(
            CollectionAreaRecord(
                id=str(area.id),
                name=area.name,
                created_at=area.created_at,
                updated_at=area.updated_at,
            )
        )
        await self._session.flush()

    async def save_area(self, area: CollectionArea) -> None:
        record = await self._session.get(CollectionAreaRecord, str(area.id))
        if record is None:
            raise LookupError(f"No collection area found with id {area.id}")
        _apply_area(record, area)
        await self._session.flush()

    async def delete_area(self, area_id: CollectionAreaId) -> None:
        await self._session.execute(
            delete(CollectionAreaRecord).where(CollectionAreaRecord.id == str(area_id))
        )

    async def list_areas(self) -> list[CollectionArea]:
        result = await self._session.execute(
            select(CollectionAreaRecord).order_by(CollectionAreaRecord.name)
        )
        return [_to_area(r) for r in result.scalars()]

    async def get_area_by_id(self, area_id: CollectionAreaId) -> CollectionArea | None:
        record = await self._session.get(CollectionAreaRecord, str(area_id))
        return _to_area(record) if record else None

    async def count_collections_by_area(self) -> dict[CollectionAreaId, int]:
        result = await self._session.execute(
            select(CollectionRecord.area_id, func.count(CollectionRecord.id)).group_by(
                CollectionRecord.area_id
            )
        )
        return {CollectionAreaId(aid): count for aid, count in result.all()}


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
                inventory_number_column=(
                    document.object_snapshot_mapping.inventory_number_column
                    if document.object_snapshot_mapping is not None
                    else None
                ),
                display_title_column=(
                    document.object_snapshot_mapping.display_title_column
                    if document.object_snapshot_mapping is not None
                    else None
                ),
                display_title_columns=(
                    list(document.object_snapshot_mapping.display_title_columns)
                    if document.object_snapshot_mapping is not None
                    else []
                ),
                object_name_column=(
                    document.object_snapshot_mapping.object_name_column
                    if document.object_snapshot_mapping is not None
                    else None
                ),
                description_columns=(
                    list(document.object_snapshot_mapping.description_columns)
                    if document.object_snapshot_mapping is not None
                    else []
                ),
                searchable_columns=(
                    list(document.object_snapshot_mapping.searchable_columns)
                    if document.object_snapshot_mapping is not None
                    else []
                ),
                content_matches_searchable_columns=(
                    document.content_matches_searchable_columns
                ),
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
# threshold, which is too strict for a short code embedded in a long row).
# Chosen empirically against the running
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
        sd.inventory_number_column,
        sd.display_title_column,
        sd.display_title_columns,
        sd.object_name_column,
        sd.description_columns,
        sd.searchable_columns,
        co.sheet,
        co.row_number,
        co.cells,
        ts_headline(
            'simple', co.content, plainto_tsquery('simple', :q),
            'MaxFragments=1, MaxWords=20, MinWords=5'
        ) AS highlight,
        co.tsv @@ plainto_tsquery('simple', :q) AS matched_text,
        co.content ILIKE '%' || :q || '%' AS matched_substring,
        word_similarity(:q, co.content) > :threshold AS matched_approximate,
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

_SEARCHABLE_COLLECTION_SCOPES_SQL = text(
    """
    WITH source_columns AS (
        SELECT
            sd.id AS source_document_id,
            sd.collection_id,
            CASE
                WHEN jsonb_array_length(
                    COALESCE(sd.searchable_columns::jsonb, '[]'::jsonb)
                ) > 0
                    THEN sd.searchable_columns::jsonb
                ELSE COALESCE(
                    (
                        SELECT jsonb_agg(
                            DISTINCT cell_key.column_name
                            ORDER BY cell_key.column_name
                        )
                        FROM collection_index_object co
                        CROSS JOIN LATERAL jsonb_object_keys(co.cells)
                            AS cell_key(column_name)
                        WHERE co.source_document_id = sd.id
                    ),
                    '[]'::jsonb
                )
            END AS columns
        FROM collection_index_source_document sd
        WHERE sd.deleted_at IS NULL
          AND sd.collection_id IN :collection_ids
    ),
    distinct_columns AS (
        SELECT source_columns.collection_id, searchable_column.column_name
        FROM source_columns
        CROSS JOIN LATERAL jsonb_array_elements_text(source_columns.columns)
            AS searchable_column(column_name)
        GROUP BY source_columns.collection_id, searchable_column.column_name
    ),
    ranked AS (
        SELECT
            collection_id,
            column_name,
            row_number() OVER (
                PARTITION BY collection_id
                ORDER BY lower(column_name), column_name
            ) AS row_number,
            count(*) OVER (PARTITION BY collection_id) AS total
        FROM distinct_columns
    )
    SELECT
        collection_id,
        array_agg(column_name ORDER BY row_number)
            FILTER (WHERE row_number <= :limit) AS searchable_columns,
        max(total) AS searchable_columns_total
    FROM ranked
    GROUP BY collection_id
    """
).bindparams(bindparam("collection_ids", expanding=True))


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

    async def list_columns(self, source_document_id: SourceDocumentId) -> list[str]:
        result = await self._session.execute(
            select(CollectionObjectRecord.cells).where(
                CollectionObjectRecord.source_document_id == str(source_document_id)
            )
        )
        columns: set[str] = set()
        for cells in result.scalars():
            columns.update(str(key) for key in cells.keys())
        return sorted(columns, key=str.casefold)

    async def list_searchable_collection_scopes(
        self, collection_ids: Sequence[CollectionId], limit: int
    ) -> dict[CollectionId, SearchableColumnScope]:
        if not collection_ids:
            return {}
        result = await self._session.execute(
            _SEARCHABLE_COLLECTION_SCOPES_SQL,
            {
                "collection_ids": [
                    str(collection_id) for collection_id in collection_ids
                ],
                "limit": limit,
            },
        )
        scopes: dict[CollectionId, SearchableColumnScope] = {}
        for row in result:
            collection_id = CollectionId(row.collection_id)
            scopes[collection_id] = SearchableColumnScope(
                collection_id=collection_id,
                searchable_columns=tuple(row.searchable_columns or ()),
                searchable_columns_total=row.searchable_columns_total or 0,
            )
        return scopes

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
                object_snapshot=_object_snapshot_from_row(row),
                match_reasons=_match_reasons_from_row(row, query.q),
            )
            for row in rows
        ]
        return CollectionObjectSearchResult(total=total or 0, items=items)


def _cell(cells: dict[str, str], column: str | None) -> str:
    if column is None:
        return ""
    return str(cells.get(column, "")).strip()


_MATCH_LABELS = {
    "exact": "Exact",
    "substring": "Contains phrase",
    "text": "Text match",
    "approximate": "Approximate",
}


def _normalise_match_text(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _effective_searchable_columns(row: Any) -> tuple[str, ...]:
    cells = row.cells or {}
    searchable_columns = tuple(row.searchable_columns or ())
    if searchable_columns:
        return searchable_columns
    return tuple(str(column) for column in cells.keys())


def _columns_matching_exact(row: Any, query: str) -> tuple[str, ...]:
    q = _normalise_match_text(query)
    if not q:
        return ()
    cells = row.cells or {}
    return tuple(
        column
        for column in _effective_searchable_columns(row)
        if _normalise_match_text(str(cells.get(column, ""))) == q
    )


def _columns_matching_substring(row: Any, query: str) -> tuple[str, ...]:
    q = _normalise_match_text(query)
    if not q:
        return ()
    cells = row.cells or {}
    return tuple(
        column
        for column in _effective_searchable_columns(row)
        if q in _normalise_match_text(str(cells.get(column, "")))
    )


def _match_reasons_from_row(row: Any, query: str) -> tuple[SearchMatchReason, ...]:
    exact_columns = _columns_matching_exact(row, query)
    if exact_columns:
        return (
            SearchMatchReason(
                method="exact", label=_MATCH_LABELS["exact"], columns=exact_columns
            ),
        )

    substring_columns = _columns_matching_substring(row, query)
    if bool(row.matched_substring):
        return (
            SearchMatchReason(
                method="substring",
                label=_MATCH_LABELS["substring"],
                columns=substring_columns,
            ),
        )

    if bool(row.matched_text):
        return (SearchMatchReason(method="text", label=_MATCH_LABELS["text"]),)

    if bool(row.matched_approximate):
        return (
            SearchMatchReason(
                method="approximate", label=_MATCH_LABELS["approximate"]
            ),
        )

    return ()


def _object_snapshot_from_row(row: Any) -> ObjectSnapshot | None:
    inventory = _cell(row.cells, row.inventory_number_column)
    display_title_columns = row.display_title_columns or [row.display_title_column]
    display_title = " · ".join(
        part
        for part in (_cell(row.cells, column) for column in display_title_columns)
        if part
    )
    object_name = _cell(row.cells, row.object_name_column) or display_title
    if not inventory or not display_title or not object_name:
        return None
    description_parts = [
        _cell(row.cells, column) for column in (row.description_columns or [])
    ]
    description = " · ".join(part for part in description_parts if part) or None
    return ObjectSnapshot(
        inventory_number=inventory,
        display_title=display_title,
        object_name=object_name,
        brief_description_snapshot=description,
        category=row.collection_name,
    )
