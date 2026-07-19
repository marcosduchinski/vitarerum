"""Integration tests for the Postgres-specific search query (full-text +
trigram).

tsvector, ts_headline and pg_trgm's word_similarity have no SQLite
equivalent, so this is the one part of the codebase tested against a real
Postgres — the same instance docker-compose.yml brings up for local dev
(``DATABASE_URL`` in .env), with the Collection Object Index migrations
(0011, 0014) already applied — the latter seeds at least one collection
area, which every seeded test collection borrows (``area_id`` is a required
FK). Skips gracefully if that database isn't reachable (e.g. in an
environment without docker-compose up), since every other test in the suite
runs against in-memory SQLite and doesn't need it.

Each test seeds its own collection/source document/rows (unique ids) and
tears them down in a ``finally``, so runs don't collide or leave litter in
a shared dev database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.collection_object_index.application.ports import CollectionObjectSearchQuery
from app.collection_object_index.domain.models import CollectionId
from app.collection_object_index.infrastructure.models import (
    CollectionAreaRecord,
    CollectionObjectRecord,
    CollectionRecord,
    SourceDocumentRecord,
)
from app.collection_object_index.infrastructure.repositories import (
    SqlAlchemyCollectionObjectIndex,
)
from app.config import settings

_NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)


@asynccontextmanager
async def _live_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A fresh engine per test (never the shared ``app.database.engine``):
    asyncpg connections are bound to the event loop they were created on, and
    pytest-asyncio gives each test function its own loop, so a shared,
    module-level engine breaks on the second test with "attached to a
    different loop"."""
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment-dependent
        await engine.dispose()
        pytest.skip(f"Postgres is not reachable at settings.database_url: {exc}")
        return
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        await engine.dispose()


class _Seed:
    """A collection with one live source document, ready to take object rows.
    Cleans up all three tables' rows it created, regardless of outcome."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory
        self.collection_id = str(uuid4())
        self.document_id = str(uuid4())

    async def __aenter__(self) -> _Seed:
        async with self._factory() as session:
            area_id = await session.scalar(select(CollectionAreaRecord.id).limit(1))
            assert area_id is not None, (
                "No collection area found — has migration 0014 been applied?"
            )
            session.add(
                CollectionRecord(
                    id=self.collection_id,
                    area_id=area_id,
                    name=f"Test Collection {self.collection_id}",
                    created_at=_NOW,
                    updated_at=_NOW,
                )
            )
            session.add(
                SourceDocumentRecord(
                    id=self.document_id,
                    collection_id=self.collection_id,
                    file_name="test.xlsx",
                    file_reference="unused",
                    source_kind="UPLOAD",
                    content_hash=str(uuid4()),
                    status="INDEXED",
                    uploaded_by=str(uuid4()),
                    uploaded_at=_NOW,
                    indexed_at=_NOW,
                    inventory_number_column="Inventory No",
                    display_title_columns=("Name",),
                    object_name_column=None,
                    description_columns=["Notes"],
                )
            )
            await session.commit()
        return self

    async def add_rows(self, rows: list[tuple[str, int, str, dict[str, str]]]) -> None:
        async with self._factory() as session:
            session.add_all(
                CollectionObjectRecord(
                    id=str(uuid4()),
                    collection_id=self.collection_id,
                    source_document_id=self.document_id,
                    sheet=sheet,
                    row_number=row_number,
                    content=content,
                    cells=cells,
                )
                for sheet, row_number, content, cells in rows
            )
            await session.commit()

    async def soft_delete_document(self) -> None:
        async with self._factory() as session:
            record = await session.get(SourceDocumentRecord, self.document_id)
            assert record is not None
            record.deleted_at = _NOW
            await session.commit()

    async def __aexit__(self, *exc_info: object) -> None:
        async with self._factory() as session:
            await session.execute(
                text("DELETE FROM collection_index_object WHERE collection_id = :c"),
                {"c": self.collection_id},
            )
            await session.execute(
                text("DELETE FROM collection_index_source_document WHERE id = :d"),
                {"d": self.document_id},
            )
            await session.execute(
                text("DELETE FROM collection_index_collection WHERE id = :c"),
                {"c": self.collection_id},
            )
            await session.commit()


async def test_search_matches_full_text() -> None:
    async with _live_session_factory() as factory:
        async with _Seed(factory) as seed:
            await seed.add_rows(
                [
                    (
                        "Objects",
                        2,
                        "ZOO-1 Jaguar found near the river",
                        {
                            "Inventory No": "ZOO-1",
                            "Name": "Jaguar",
                            "Notes": "found near the river",
                        },
                    ),
                    (
                        "Objects",
                        3,
                        "BOT-9 Quercus robur",
                        {"Sample": "BOT-9", "Name": "Quercus robur"},
                    ),
                ]
            )
            async with factory() as session:
                result = await SqlAlchemyCollectionObjectIndex(session).search(
                    CollectionObjectSearchQuery(
                        q="jaguar",
                        collection_id=CollectionId(seed.collection_id),
                        page=0,
                        size=20,
                    )
                )
            assert result.total == 1
            assert result.items[0].cells == {
                "Inventory No": "ZOO-1",
                "Name": "Jaguar",
                "Notes": "found near the river",
            }
            assert "<b>Jaguar</b>" in result.items[0].highlight
            # Locks in the join to collection_index_collection for the name
            # (not just the now-removed active filter).
            expected_name = f"Test Collection {seed.collection_id}"
            assert result.items[0].collection_name == expected_name
            assert result.items[0].object_snapshot is not None
            assert result.items[0].object_snapshot.inventory_number == "ZOO-1"
            assert result.items[0].object_snapshot.display_title == "Jaguar"
            assert result.items[0].object_snapshot.object_name == "Jaguar"
            assert (
                result.items[0].object_snapshot.brief_description_snapshot
                == "found near the river"
            )
            assert result.items[0].object_snapshot.category == expected_name


async def test_search_matches_hyphenated_code_partially() -> None:
    """'abc123' must find a row whose code is stored as 'ABC-123' — the
    reason word_similarity, not a plain ILIKE substring, backs the match.

    Unscoped (``collection_id=None``, exercising that code path): the dev
    database may carry unrelated real collection data matching "abc123" by
    trigram chance in long rows too, so this asserts the seeded hit is
    *present*, not that it's the only result."""
    async with _live_session_factory() as factory:
        async with _Seed(factory) as seed:
            await seed.add_rows(
                [
                    (
                        "Objects",
                        2,
                        "the item ABC-123 is filed here",
                        {"Code": "ABC-123"},
                    )
                ]
            )
            async with factory() as session:
                result = await SqlAlchemyCollectionObjectIndex(session).search(
                    CollectionObjectSearchQuery(
                        q="abc123", collection_id=None, page=0, size=200
                    )
                )
            assert {"Code": "ABC-123"} in [item.cells for item in result.items]


async def test_search_filters_by_collection() -> None:
    async with _live_session_factory() as factory:
        async with _Seed(factory) as seed_a, _Seed(factory) as seed_b:
            await seed_a.add_rows(
                [("Objects", 2, "shared term alpha", {"Name": "alpha"})]
            )
            await seed_b.add_rows(
                [("Objects", 2, "shared term beta", {"Name": "beta"})]
            )
            async with factory() as session:
                result = await SqlAlchemyCollectionObjectIndex(session).search(
                    CollectionObjectSearchQuery(
                        q="shared",
                        collection_id=CollectionId(seed_a.collection_id),
                        page=0,
                        size=20,
                    )
                )
            assert [item.cells["Name"] for item in result.items] == ["alpha"]


async def test_search_excludes_rows_of_deleted_source_document() -> None:
    async with _live_session_factory() as factory:
        async with _Seed(factory) as seed:
            await seed.add_rows(
                [("Objects", 2, "vanishing term gamma", {"Name": "gamma"})]
            )
            scope = CollectionId(seed.collection_id)
            async with factory() as session:
                before = await SqlAlchemyCollectionObjectIndex(session).search(
                    CollectionObjectSearchQuery(
                        q="gamma", collection_id=scope, page=0, size=20
                    )
                )
            assert before.total == 1

            await seed.soft_delete_document()

            async with factory() as session:
                after = await SqlAlchemyCollectionObjectIndex(session).search(
                    CollectionObjectSearchQuery(
                        q="gamma", collection_id=scope, page=0, size=20
                    )
                )
            assert after.total == 0


async def test_search_paginates_without_overlap() -> None:
    async with _live_session_factory() as factory:
        async with _Seed(factory) as seed:
            await seed.add_rows(
                [
                    ("Objects", n, f"pagination term delta row {n}", {"Row": str(n)})
                    for n in range(2, 7)
                ]
            )
            scope = CollectionId(seed.collection_id)
            async with factory() as session:
                index = SqlAlchemyCollectionObjectIndex(session)
                page0 = await index.search(
                    CollectionObjectSearchQuery(
                        q="delta", collection_id=scope, page=0, size=2
                    )
                )
                page1 = await index.search(
                    CollectionObjectSearchQuery(
                        q="delta", collection_id=scope, page=1, size=2
                    )
                )
            assert page0.total == 5
            assert len(page0.items) == 2
            assert len(page1.items) == 2
            rows_page0 = {item.cells["Row"] for item in page0.items}
            rows_page1 = {item.cells["Row"] for item in page1.items}
            assert rows_page0.isdisjoint(rows_page1)


async def test_search_finds_no_match_returns_empty() -> None:
    async with _live_session_factory() as factory:
        async with _Seed(factory) as seed:
            await seed.add_rows([("Objects", 2, "completely unrelated content", {})])
            async with factory() as session:
                result = await SqlAlchemyCollectionObjectIndex(session).search(
                    CollectionObjectSearchQuery(
                        q="nonexistentxyz", collection_id=None, page=0, size=20
                    )
                )
            assert result.total == 0
            assert result.items == []
