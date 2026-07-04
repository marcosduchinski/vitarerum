"""DB-backed coverage for the collection data-source management flow.

Exercises the SQLAlchemy repositories/index and the use cases over a real
(in-memory SQLite) session, with a real .xlsx parsed by openpyxl and an
in-memory file storage.
"""

import io
from datetime import UTC, datetime

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.collection_object_index.application.use_cases import (
    AssignCollectionCurator,
    DeleteSourceDocument,
    ListCollectionSourceDocuments,
    ListManageableCollections,
    ReindexSourceDocument,
    RemoveCollectionCurator,
    UploadSourceDocument,
    UploadSourceDocumentInput,
)
from app.collection_object_index.domain.enums import SourceDocumentStatus
from app.collection_object_index.domain.models import CollectionId
from app.collection_object_index.infrastructure.models import (
    CollectionObjectRecord,
    CollectionRecord,
)
from app.collection_object_index.infrastructure.parser_openpyxl import (
    OpenpyxlCollectionObjectParser,
)
from app.collection_object_index.infrastructure.repositories import (
    SqlAlchemyCollectionObjectIndex,
    SqlAlchemyCollectionRepository,
    SqlAlchemySourceDocumentRepository,
)
from app.database import Base
from app.identity.public import Actor, GroupName, PermissionId
from app.shared.exceptions import AccessDenied, InsufficientGroup

_NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
_ZOOLOGY = CollectionId("col-zoo")
_BOTANY = CollectionId("col-bot")

_ADMIN = Actor(
    id=PermissionId("perm-admin"), group=GroupName.SYS_ADMIN, email="a@museum.pt"
)
_MANAGER = Actor(
    id=PermissionId("perm-mgmt"),
    group=GroupName.COLLECTIONS_MANAGEMENT,
    email="m@museum.pt",
)
_CURATOR = Actor(
    id=PermissionId("perm-cur"), group=GroupName.CURATORIAL, email="c@museum.pt"
)


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


class _FakeStorage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, content: bytes, file_reference: str) -> str:
        self.saved[file_reference] = content
        return file_reference

    async def read(self, file_reference: str) -> bytes:
        return self.saved[file_reference]

    async def delete(self, file_reference: str) -> None:
        self.deleted.append(file_reference)
        self.saved.pop(file_reference, None)


def _xlsx(rows: list[list[str]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Objects"
    sheet.append(["Inventory No", "Name"])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def _session_factory() -> async_sessionmaker:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                CollectionRecord(
                    id=str(_ZOOLOGY),
                    name="Zoology",
                    active=True,
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
                CollectionRecord(
                    id=str(_BOTANY),
                    name="Botany",
                    active=True,
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
            ]
        )
        await session.commit()
    return factory


def _uploader(session: AsyncSession, storage: _FakeStorage) -> UploadSourceDocument:
    return UploadSourceDocument(
        SqlAlchemyCollectionRepository(session),
        SqlAlchemySourceDocumentRepository(session),
        storage,
        OpenpyxlCollectionObjectParser(),
        SqlAlchemyCollectionObjectIndex(session),
        _FakeClock(),
    )


async def _object_rows(session: AsyncSession) -> list[CollectionObjectRecord]:
    result = await session.execute(
        select(CollectionObjectRecord).order_by(CollectionObjectRecord.row_number)
    )
    return list(result.scalars())


async def _upload(
    factory: async_sessionmaker,
    storage: _FakeStorage,
    caller: Actor = _ADMIN,
    collection_id: CollectionId = _ZOOLOGY,
    file_name: str = "zoo.xlsx",
    rows: list[list[str]] | None = None,
):
    async with factory() as session:
        result = await _uploader(session, storage).execute(
            UploadSourceDocumentInput(
                caller=caller,
                collection_id=collection_id,
                file_name=file_name,
                content=_xlsx(rows if rows is not None else [["ZOO-1", "Jaguar"]]),
            )
        )
        await session.commit()
    return result


async def test_upload_indexes_rows_and_marks_indexed() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    result = await _upload(
        factory, storage, rows=[["ZOO-1", "Jaguar"], ["ZOO-2", "Arara"]]
    )

    assert result.created is True
    document = result.document
    assert document.status == SourceDocumentStatus.INDEXED
    assert document.row_count == 2
    assert document.indexed_at == _NOW
    async with factory() as session:
        rows = await _object_rows(session)
    assert [(r.sheet, r.row_number) for r in rows] == [("Objects", 2), ("Objects", 3)]
    assert rows[0].cells == {"Inventory No": "ZOO-1", "Name": "Jaguar"}
    assert rows[0].collection_id == str(_ZOOLOGY)


async def test_identical_reupload_dedupes() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    first = await _upload(factory, storage)
    second = await _upload(factory, storage)

    assert second.created is False
    assert second.document.id == first.document.id
    async with factory() as session:
        assert len(await _object_rows(session)) == 1


async def test_new_version_replaces_previous_source_and_rows() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    first = await _upload(factory, storage, rows=[["ZOO-1", "Jaguar"]])
    second = await _upload(
        factory, storage, rows=[["ZOO-1", "Jaguar"], ["ZOO-9", "Tuiuiú"]]
    )

    assert second.created is True
    assert second.document.id != first.document.id
    assert second.replaced_file_reference == first.document.file_reference
    async with factory() as session:
        repo = SqlAlchemySourceDocumentRepository(session)
        old = await repo.get_by_id(first.document.id)
        assert old is not None and old.is_deleted
        live = await repo.list_live_by_collection(_ZOOLOGY)
        assert [d.id for d in live] == [second.document.id]
        rows = await _object_rows(session)
        assert {r.source_document_id for r in rows} == {str(second.document.id)}
        assert len(rows) == 2


async def test_delete_removes_index_rows_and_soft_deletes() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    uploaded = await _upload(factory, storage)

    async with factory() as session:
        reference = await DeleteSourceDocument(
            SqlAlchemyCollectionRepository(session),
            SqlAlchemySourceDocumentRepository(session),
            SqlAlchemyCollectionObjectIndex(session),
            _FakeClock(),
        ).execute(_ADMIN, uploaded.document.id)
        await session.commit()

    assert reference == uploaded.document.file_reference
    async with factory() as session:
        assert await _object_rows(session) == []
        repo = SqlAlchemySourceDocumentRepository(session)
        record = await repo.get_by_id(uploaded.document.id)
        assert record is not None and record.is_deleted
        assert await repo.list_live_by_collection(_ZOOLOGY) == []


async def test_reindex_rebuilds_rows_from_stored_file() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    uploaded = await _upload(factory, storage, rows=[["ZOO-1", "Jaguar"]])

    async with factory() as session:
        document = await ReindexSourceDocument(
            SqlAlchemyCollectionRepository(session),
            SqlAlchemySourceDocumentRepository(session),
            storage,
            OpenpyxlCollectionObjectParser(),
            SqlAlchemyCollectionObjectIndex(session),
            _FakeClock(),
        ).execute(_ADMIN, uploaded.document.id)
        await session.commit()

    assert document.status == SourceDocumentStatus.INDEXED
    assert document.row_count == 1
    async with factory() as session:
        assert len(await _object_rows(session)) == 1


async def test_curator_cannot_manage_unassigned_collection() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    with pytest.raises(AccessDenied):
        await _upload(factory, storage, caller=_CURATOR, collection_id=_BOTANY)
    assert storage.saved == {}  # nothing persisted before the scope check


async def test_assigned_curator_manages_their_collection() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    async with factory() as session:
        await AssignCollectionCurator(
            SqlAlchemyCollectionRepository(session), _FakeClock()
        ).execute(_ADMIN, _ZOOLOGY, _CURATOR.id)
        await session.commit()

    result = await _upload(factory, storage, caller=_CURATOR)
    assert result.document.status == SourceDocumentStatus.INDEXED

    async with factory() as session:
        documents = await ListCollectionSourceDocuments(
            SqlAlchemyCollectionRepository(session),
            SqlAlchemySourceDocumentRepository(session),
        ).execute(_CURATOR, _ZOOLOGY)
    assert [d.id for d in documents] == [result.document.id]


async def test_collections_management_manages_any_collection() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    result = await _upload(factory, storage, caller=_MANAGER, collection_id=_BOTANY)
    assert result.document.status == SourceDocumentStatus.INDEXED


async def test_curator_cannot_assign_curators() -> None:
    factory = await _session_factory()
    async with factory() as session:
        with pytest.raises(InsufficientGroup):
            await AssignCollectionCurator(
                SqlAlchemyCollectionRepository(session), _FakeClock()
            ).execute(_CURATOR, _ZOOLOGY, _CURATOR.id)


async def test_assign_records_assigned_by_and_remove_revokes() -> None:
    factory = await _session_factory()
    async with factory() as session:
        repo = SqlAlchemyCollectionRepository(session)
        assignment = await AssignCollectionCurator(repo, _FakeClock()).execute(
            _MANAGER, _ZOOLOGY, _CURATOR.id
        )
        await session.commit()
    assert assignment.assigned_by == _MANAGER.id

    async with factory() as session:
        repo = SqlAlchemyCollectionRepository(session)
        # Idempotent: re-assigning returns the existing assignment.
        again = await AssignCollectionCurator(repo, _FakeClock()).execute(
            _ADMIN, _ZOOLOGY, _CURATOR.id
        )
        assert again.assigned_by == _MANAGER.id
        await RemoveCollectionCurator(repo).execute(_ADMIN, _ZOOLOGY, _CURATOR.id)
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyCollectionRepository(session)
        assert await repo.list_curated_collection_ids(_CURATOR.id) == set()


async def test_list_manageable_collections_flags_scope() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    await _upload(factory, storage)  # one live document in Zoology
    async with factory() as session:
        repo = SqlAlchemyCollectionRepository(session)
        await AssignCollectionCurator(repo, _FakeClock()).execute(
            _ADMIN, _BOTANY, _CURATOR.id
        )
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyCollectionRepository(session)
        views = {
            v.collection.name: v
            for v in await ListManageableCollections(repo).execute(_CURATOR)
        }
    assert views["Botany"].manageable is True
    assert views["Zoology"].manageable is False
    assert views["Zoology"].document_count == 1
    assert [c.permission_id for c in views["Botany"].curators] == [str(_CURATOR.id)]


async def test_error_status_when_stored_file_is_not_a_spreadsheet() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    uploaded = await _upload(factory, storage)
    # Corrupt the stored file, then reindex: the failure must surface as ERROR.
    storage.saved[uploaded.document.file_reference] = b"corrupted"

    async with factory() as session:
        document = await ReindexSourceDocument(
            SqlAlchemyCollectionRepository(session),
            SqlAlchemySourceDocumentRepository(session),
            storage,
            OpenpyxlCollectionObjectParser(),
            SqlAlchemyCollectionObjectIndex(session),
            _FakeClock(),
        ).execute(_ADMIN, uploaded.document.id)
        await session.commit()

    assert document.status == SourceDocumentStatus.ERROR
    assert document.error_message is not None
    async with factory() as session:
        count = await session.scalar(select(func.count(CollectionObjectRecord.id)))
    assert count == 0
