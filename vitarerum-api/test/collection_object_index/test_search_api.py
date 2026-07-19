"""API tests for the Objects -> Search endpoints.

Uses a fake CollectionObjectIndexPort (in-memory substring match) so the
routing/auth/pagination/collection-filter plumbing is exercised without a real
Postgres full-text/trigram engine — that SQL is covered separately in
test_search_postgres.py against the real database.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.collection_object_index.application.ports import (
    CollectionObjectSearchQuery,
    CollectionObjectSearchResult,
    SearchableColumnScope,
    SearchHit,
    SearchMatchReason,
)
from app.collection_object_index.domain.models import CollectionId, SourceDocumentId
from app.collection_object_index.infrastructure.models import (
    CollectionAreaRecord,
    CollectionRecord,
)
from app.collection_object_index.presentation.dependencies import get_object_index
from app.database import Base, get_async_session
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission

_NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="c@museum.pt"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="e@example.org"
)


@dataclass(frozen=True, slots=True)
class _Row:
    collection_id: str
    collection_name: str
    source_document_id: str
    file_name: str
    sheet: str
    row_number: int
    cells: dict[str, str]
    content: str


class _FakeIndex:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows
        self.search_calls: list[CollectionObjectSearchQuery] = []

    async def index(self, *args: object, **kwargs: object) -> int:
        raise NotImplementedError

    async def remove_document(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError

    async def list_columns(self, *args: object, **kwargs: object) -> list[str]:
        return []

    async def list_searchable_collection_scopes(
        self, *args: object, **kwargs: object
    ) -> dict[CollectionId, SearchableColumnScope]:
        return {
            CollectionId("col-zoo"): SearchableColumnScope(
                collection_id=CollectionId("col-zoo"),
                searchable_columns=("Inventory No", "Name"),
                searchable_columns_total=2,
            ),
            CollectionId("col-bot"): SearchableColumnScope(
                collection_id=CollectionId("col-bot"),
                searchable_columns=("Name", "Sample"),
                searchable_columns_total=2,
            ),
        }

    async def search(
        self, query: CollectionObjectSearchQuery
    ) -> CollectionObjectSearchResult:
        self.search_calls.append(query)
        matches = [
            r
            for r in self.rows
            if (query.collection_id is None or r.collection_id == query.collection_id)
            and query.q.lower() in r.content.lower()
        ]
        start = query.page * query.size
        page = matches[start : start + query.size]
        return CollectionObjectSearchResult(
            total=len(matches),
            items=[
                SearchHit(
                    collection_id=CollectionId(r.collection_id),
                    collection_name=r.collection_name,
                    source_document_id=SourceDocumentId(r.source_document_id),
                    file_name=r.file_name,
                    sheet=r.sheet,
                    row_number=r.row_number,
                    cells=r.cells,
                    highlight=f"...<b>{query.q}</b>...",
                    match_reasons=(
                        SearchMatchReason(
                            method="substring",
                            label="Contains phrase",
                            columns=("Name",),
                        ),
                    ),
                )
                for r in page
            ],
        )


_ROWS = [
    _Row(
        collection_id="col-zoo",
        collection_name="REPTILES & AMPHIBIANS",
        source_document_id="doc-1",
        file_name="zoo.xlsx",
        sheet="Objects",
        row_number=2,
        cells={"Inventory No": "ZOO-1", "Name": "Jaguar"},
        content="ZOO-1 Jaguar",
    ),
    _Row(
        collection_id="col-bot",
        collection_name="FISH",
        source_document_id="doc-2",
        file_name="bot.xlsx",
        sheet="Objects",
        row_number=2,
        cells={"Sample": "BOT-1", "Name": "Quercus robur"},
        content="BOT-1 Quercus robur",
    ),
]


@asynccontextmanager
async def _client(
    caller: Actor = _STAFF,
) -> AsyncIterator[tuple[AsyncClient, _FakeIndex]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            CollectionAreaRecord(
                id="area-nat-hist",
                name="Zoology",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        session.add_all(
            [
                CollectionRecord(
                    id="col-zoo",
                    area_id="area-nat-hist",
                    name="REPTILES & AMPHIBIANS",
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
                CollectionRecord(
                    id="col-bot",
                    area_id="area-nat-hist",
                    name="FISH",
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
            ]
        )
        await session.commit()

    index = _FakeIndex(list(_ROWS))

    async def _session_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _session_override
    app.dependency_overrides[get_object_index] = lambda: index
    app.dependency_overrides[get_caller_permission] = lambda: caller
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test/api/v1"
        ) as client:
            yield client, index
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_search_returns_matching_hits() -> None:
    async with _client() as (client, _):
        response = await client.get("/objects/search", params={"q": "jaguar"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["fileName"] == "zoo.xlsx"
    assert body["items"][0]["cells"] == {"Inventory No": "ZOO-1", "Name": "Jaguar"}
    assert "<b>jaguar</b>" in body["items"][0]["highlight"]
    assert body["items"][0]["matchReasons"] == [
        {"method": "substring", "label": "Contains phrase", "columns": ["Name"]}
    ]


async def test_search_filters_by_collection() -> None:
    async with _client() as (client, index):
        response = await client.get(
            "/objects/search", params={"q": "1", "collectionId": "col-bot"}
        )
    assert response.status_code == 200
    body = response.json()
    assert [item["fileName"] for item in body["items"]] == ["bot.xlsx"]
    assert index.search_calls[-1].collection_id == "col-bot"


async def test_search_paginates() -> None:
    async with _client() as (client, index):
        response = await client.get(
            "/objects/search", params={"q": "1", "page": 1, "size": 1}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["size"] == 1
    assert len(body["items"]) == 1
    assert index.search_calls[-1].page == 1
    assert index.search_calls[-1].size == 1


async def test_search_requires_non_empty_query() -> None:
    async with _client() as (client, _):
        missing = await client.get("/objects/search")
        empty = await client.get("/objects/search", params={"q": ""})
    assert missing.status_code == 422
    assert empty.status_code == 422


async def test_search_rejects_non_staff() -> None:
    async with _client(_EXTERNAL) as (client, _):
        response = await client.get("/objects/search", params={"q": "jaguar"})
    assert response.status_code == 403


async def test_searchable_collections_lists_full_catalogue() -> None:
    async with _client() as (client, _):
        response = await client.get("/objects/search/collections")
    assert response.status_code == 200
    body = response.json()
    names = {c["name"] for c in body}
    assert names == {"REPTILES & AMPHIBIANS", "FISH"}
    zoo = next(c for c in body if c["id"] == "col-zoo")
    assert zoo["searchableColumns"] == ["Inventory No", "Name"]
    assert zoo["searchableColumnsTotal"] == 2


async def test_searchable_collections_rejects_non_staff() -> None:
    async with _client(_EXTERNAL) as (client, _):
        response = await client.get("/objects/search/collections")
    assert response.status_code == 403
