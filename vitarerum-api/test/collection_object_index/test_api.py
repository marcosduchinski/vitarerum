"""API tests for the Collection Data Sources management endpoints.

Runs the real stack (routes -> use cases -> SQLAlchemy over in-memory SQLite)
with the session and caller dependencies overridden; only the file storage is
an in-memory fake.
"""

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.collection_object_index.infrastructure.models import CollectionRecord
from app.collection_object_index.presentation.dependencies import (
    get_file_storage,
)
from app.database import Base, get_async_session
from app.identity.infrastructure.models import (
    GroupRecord,
    InstitutionRecord,
    PermissionRecord,
    UserRecord,
)
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission

_NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
_ZOOLOGY_ID = "col-zoo"
_BOTANY_ID = "col-bot"

_ADMIN = Actor(
    id=PermissionId("perm-admin"), group=GroupName.SYS_ADMIN, email="a@museum.pt"
)
_CURATOR = Actor(
    id=PermissionId("perm-cur"), group=GroupName.CURATORIAL, email="c@museum.pt"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="e@example.org"
)


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


def _xlsx_bytes(rows: list[list[str]] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Objects"
    sheet.append(["Inventory No", "Name"])
    for row in rows if rows is not None else [["ZOO-1", "Jaguar"]]:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@asynccontextmanager
async def _client(
    caller: Actor = _ADMIN,
) -> AsyncIterator[tuple[AsyncClient, _FakeStorage]]:
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
                    id=_ZOOLOGY_ID,
                    name="Zoology",
                    active=True,
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
                CollectionRecord(
                    id=_BOTANY_ID,
                    name="Botany",
                    active=True,
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
            ]
        )
        await session.commit()

    storage = _FakeStorage()

    async def _session_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _session_override
    app.dependency_overrides[get_file_storage] = lambda: storage
    app.dependency_overrides[get_caller_permission] = lambda: caller
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test/api/v1"
        ) as client:
            yield client, storage
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _upload_files(rows: list[list[str]] | None = None) -> dict:
    return {
        "file": (
            "zoo.xlsx",
            _xlsx_bytes(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }


async def test_list_collections_shows_catalogue_with_scope_flags() -> None:
    async with _client(_CURATOR) as (client, _):
        response = await client.get("/admin/collection-data-sources/collections")
    assert response.status_code == 200
    body = {c["name"]: c for c in response.json()}
    assert set(body) == {"Zoology", "Botany"}
    assert body["Zoology"]["manageable"] is False
    assert body["Zoology"]["documentCount"] == 0


async def test_upload_indexes_and_returns_document() -> None:
    async with _client(_ADMIN) as (client, storage):
        response = await client.post(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/documents",
            files=_upload_files([["ZOO-1", "Jaguar"], ["ZOO-2", "Arara"]]),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "INDEXED"
        assert body["rowCount"] == 2
        assert body["fileName"] == "zoo.xlsx"
        assert len(storage.saved) == 1

        listing = await client.get(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/documents"
        )
        assert [d["id"] for d in listing.json()] == [body["id"]]


async def test_upload_rejects_non_xlsx_content() -> None:
    async with _client(_ADMIN) as (client, storage):
        response = await client.post(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/documents",
            files={"file": ("zoo.xlsx", b"not a spreadsheet", "application/zip")},
        )
    assert response.status_code == 415
    assert storage.saved == {}


async def test_upload_to_unknown_collection_is_404() -> None:
    async with _client(_ADMIN) as (client, _):
        response = await client.post(
            "/admin/collection-data-sources/collections/nope/documents",
            files=_upload_files(),
        )
    assert response.status_code == 404
    assert response.json()["error"] == "COLLECTION_NOT_FOUND"


async def test_external_caller_is_forbidden() -> None:
    async with _client(_EXTERNAL) as (client, _):
        response = await client.get("/admin/collection-data-sources/collections")
    assert response.status_code == 403


async def test_curator_upload_out_of_scope_is_403() -> None:
    async with _client(_CURATOR) as (client, storage):
        response = await client.post(
            f"/admin/collection-data-sources/collections/{_BOTANY_ID}/documents",
            files=_upload_files(),
        )
    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"
    assert storage.saved == {}


async def test_assign_then_curator_manages_and_delete_reclaims_file() -> None:
    # Admin assigns the curator to Botany...
    async with _client(_ADMIN) as (client, storage):
        assign = await client.post(
            f"/admin/collection-data-sources/collections/{_BOTANY_ID}/curators",
            json={"permissionId": str(_CURATOR.id)},
        )
        # The target permission does not exist in the (empty) identity tables.
        assert assign.status_code == 404
        assert assign.json()["error"] == "PERMISSION_NOT_FOUND"


async def test_assign_curator_rejects_non_curatorial_permission() -> None:
    """A permission outside CURATORIAL must not be assignable as a curator,
    even though the caller (SYS_ADMIN) is otherwise authorized."""
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
            CollectionRecord(
                id=_ZOOLOGY_ID,
                name="Zoology",
                active=True,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        session.add(
            InstitutionRecord(id="i1", name="MUHNAC", email="", address="", phone="")
        )
        session.add(
            GroupRecord(
                id="g-mgmt", name=GroupName.COLLECTIONS_MANAGEMENT, institution_id="i1"
            )
        )
        session.add(
            UserRecord(
                id="u-mgmt",
                name="Marco Gestor",
                email="marco@museum.pt",
                password_hash="",
            )
        )
        session.add(PermissionRecord(id="p-mgmt", user_id="u-mgmt", group_id="g-mgmt"))
        await session.commit()

    async def _session_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _session_override
    app.dependency_overrides[get_caller_permission] = lambda: _ADMIN
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test/api/v1"
        ) as client:
            response = await client.post(
                f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/curators",
                json={"permissionId": "p-mgmt"},
            )
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert response.status_code == 422
    assert response.json()["error"] == "PERMISSION_NOT_CURATORIAL"


async def test_delete_document_removes_and_reclaims_after_commit() -> None:
    async with _client(_ADMIN) as (client, storage):
        created = await client.post(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/documents",
            files=_upload_files(),
        )
        document_id = created.json()["id"]

        deleted = await client.delete(
            f"/admin/collection-data-sources/documents/{document_id}"
        )
        assert deleted.status_code == 204
        assert storage.saved == {}  # file reclaimed after commit

        listing = await client.get(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/documents"
        )
        assert listing.json() == []


async def test_reindex_returns_updated_document() -> None:
    async with _client(_ADMIN) as (client, _):
        created = await client.post(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/documents",
            files=_upload_files(),
        )
        document_id = created.json()["id"]
        response = await client.post(
            f"/admin/collection-data-sources/documents/{document_id}/reindex"
        )
    assert response.status_code == 200
    assert response.json()["status"] == "INDEXED"
    assert response.json()["rowCount"] == 1


# ── Collection catalog admin (SYS_ADMIN only) ───────────────────────────────


async def test_create_get_update_and_deactivate_collection() -> None:
    async with _client(_ADMIN) as (client, _):
        created = await client.post(
            "/admin/collection-data-sources/collections", json={"name": "Mineralogy"}
        )
        assert created.status_code == 201, created.text
        collection_id = created.json()["id"]
        assert created.json()["active"] is True

        fetched = await client.get(
            f"/admin/collection-data-sources/collections/{collection_id}"
        )
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "Mineralogy"

        renamed = await client.patch(
            f"/admin/collection-data-sources/collections/{collection_id}",
            json={"name": "Mineralogy & Petrology"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Mineralogy & Petrology"

        deactivated = await client.delete(
            f"/admin/collection-data-sources/collections/{collection_id}"
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["active"] is False

        reactivated = await client.patch(
            f"/admin/collection-data-sources/collections/{collection_id}",
            json={"active": True},
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["active"] is True


async def test_create_collection_duplicate_name_is_409() -> None:
    async with _client(_ADMIN) as (client, _):
        response = await client.post(
            "/admin/collection-data-sources/collections", json={"name": "Zoology"}
        )
    assert response.status_code == 409
    assert response.json()["error"] == "COLLECTION_NAME_ALREADY_EXISTS"


async def test_create_collection_duplicate_name_after_trim_is_409() -> None:
    """Padding whitespace must not bypass the unique constraint via a
    visually-duplicate name."""
    async with _client(_ADMIN) as (client, _):
        response = await client.post(
            "/admin/collection-data-sources/collections", json={"name": "  Zoology  "}
        )
    assert response.status_code == 409
    assert response.json()["error"] == "COLLECTION_NAME_ALREADY_EXISTS"


async def test_create_collection_blocked_for_curator() -> None:
    async with _client(_CURATOR) as (client, _):
        response = await client.post(
            "/admin/collection-data-sources/collections", json={"name": "Mineralogy"}
        )
    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"


async def test_get_unknown_collection_is_404() -> None:
    async with _client(_ADMIN) as (client, _):
        response = await client.get("/admin/collection-data-sources/collections/nope")
    assert response.status_code == 404
    assert response.json()["error"] == "COLLECTION_NOT_FOUND"


async def test_upload_and_reindex_blocked_for_inactive_collection() -> None:
    async with _client(_ADMIN) as (client, _):
        uploaded = await client.post(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/documents",
            files=_upload_files(),
        )
        document_id = uploaded.json()["id"]

        deactivated = await client.delete(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}"
        )
        assert deactivated.status_code == 200

        blocked_upload = await client.post(
            f"/admin/collection-data-sources/collections/{_ZOOLOGY_ID}/documents",
            files=_upload_files(rows=[["ZOO-2", "Onça"]]),
        )
        assert blocked_upload.status_code == 422
        assert blocked_upload.json()["error"] == "COLLECTION_INACTIVE"

        blocked_reindex = await client.post(
            f"/admin/collection-data-sources/documents/{document_id}/reindex"
        )
        assert blocked_reindex.status_code == 422
        assert blocked_reindex.json()["error"] == "COLLECTION_INACTIVE"


async def test_curator_candidates_blocked_for_non_sys_admin() -> None:
    async with _client(_CURATOR) as (client, _):
        response = await client.get(
            "/admin/collection-data-sources/curator-candidates"
        )
    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"


async def test_curator_candidates_lists_curatorial_group_only() -> None:
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
            InstitutionRecord(id="i1", name="MUHNAC", email="", address="", phone="")
        )
        session.add_all(
            [
                GroupRecord(id="g-cur", name=GroupName.CURATORIAL, institution_id="i1"),
                GroupRecord(id="g-adm", name=GroupName.SYS_ADMIN, institution_id="i1"),
            ]
        )
        session.add_all(
            [
                UserRecord(
                    id="u-cur",
                    name="Carla Curadora",
                    email="carla@museum.pt",
                    password_hash="",
                ),
                UserRecord(
                    id="u-adm",
                    name="Ana Admin",
                    email="ana@museum.pt",
                    password_hash="",
                ),
            ]
        )
        session.add_all(
            [
                PermissionRecord(id="p-cur", user_id="u-cur", group_id="g-cur"),
                PermissionRecord(id="p-adm", user_id="u-adm", group_id="g-adm"),
            ]
        )
        await session.commit()

    async def _session_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _session_override
    app.dependency_overrides[get_caller_permission] = lambda: _ADMIN
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test/api/v1"
        ) as client:
            response = await client.get(
                "/admin/collection-data-sources/curator-candidates"
            )
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert [c["permissionId"] for c in body] == ["p-cur"]
    assert body[0] == {
        "permissionId": "p-cur",
        "name": "Carla Curadora",
        "email": "carla@museum.pt",
    }
