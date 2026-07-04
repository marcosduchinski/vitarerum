"""SQLAlchemy adapters for the Collection Object Index ports."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collection_object_index.application.ports import ParsedRow
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
        active=record.active,
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


def _apply_document(record: SourceDocumentRecord, document: SourceDocument) -> None:
    record.status = document.status.value
    record.error_message = document.error_message
    record.row_count = document.row_count
    record.indexed_at = document.indexed_at
    record.deleted_at = document.deleted_at


class SqlAlchemyCollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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

    async def get_by_id(
        self, document_id: SourceDocumentId
    ) -> SourceDocument | None:
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


class SqlAlchemyCollectionObjectIndex:
    """Write side of the object index: bulk insert/delete of object rows.
    The PostgreSQL ``tsv`` column is generated by the database on insert."""

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
