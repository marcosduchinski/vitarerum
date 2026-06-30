"""Integration tests for the Institution admin CRUD (Identity & Access).

Exercises the routes end-to-end against a real in-memory SQLite session and the
real SqlAlchemyInstitutionRepository, so unique-name conflicts and the
delete-with-groups guard are covered against actual SQL behaviour.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.database import Base, get_async_session
from app.identity.infrastructure.models import GroupRecord, InstitutionRecord
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission

_SYS_ADMIN = Actor(
    id=PermissionId("perm-admin"),
    group=GroupName.SYS_ADMIN,
    email="admin@museum.pt",
)

_EXTERNAL = Actor(
    id=PermissionId("perm-ext"),
    group=GroupName.EXTERNAL,
    email="citizen@example.org",
)


@asynccontextmanager
async def client_with_db(
    caller: Actor = _SYS_ADMIN,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[get_caller_permission] = lambda: caller

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, session
    finally:
        await session.close()
        app.dependency_overrides.clear()


async def test_create_institution_returns_201_with_body() -> None:
    async with client_with_db() as (client, _session):
        response = await client.post(
            "/api/v1/institutions",
            json={
                "name": "MUHNAC",
                "email": "info@muhnac.pt",
                "address": "Lisboa",
                "phone": "+351 000",
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["name"] == "MUHNAC"
    assert body["email"] == "info@muhnac.pt"
    assert body["address"] == "Lisboa"
    assert body["phone"] == "+351 000"


async def test_create_duplicate_name_returns_409() -> None:
    async with client_with_db() as (client, _session):
        first = await client.post("/api/v1/institutions", json={"name": "MUHNAC"})
        assert first.status_code == 201
        second = await client.post("/api/v1/institutions", json={"name": "MUHNAC"})
    assert second.status_code == 409
    assert second.json()["error"] == "INSTITUTION_NAME_ALREADY_EXISTS"


async def test_list_institutions_is_paginated() -> None:
    async with client_with_db() as (client, _session):
        await client.post("/api/v1/institutions", json={"name": "Alpha"})
        await client.post("/api/v1/institutions", json={"name": "Beta"})
        response = await client.get(
            "/api/v1/institutions", params={"page": 0, "size": 20}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 2
    names = [item["name"] for item in body["content"]]
    assert names == ["Alpha", "Beta"]  # ordered by name


async def test_get_unknown_institution_returns_404() -> None:
    async with client_with_db() as (client, _session):
        response = await client.get("/api/v1/institutions/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"] == "INSTITUTION_NOT_FOUND"


async def test_update_institution_changes_fields() -> None:
    async with client_with_db() as (client, _session):
        created = (
            await client.post("/api/v1/institutions", json={"name": "Old"})
        ).json()
        response = await client.put(
            f"/api/v1/institutions/{created['id']}",
            json={"name": "New", "email": "new@x.pt", "address": "A", "phone": "1"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New"
    assert body["email"] == "new@x.pt"


async def test_delete_institution_returns_204() -> None:
    async with client_with_db() as (client, _session):
        created = (
            await client.post("/api/v1/institutions", json={"name": "Temp"})
        ).json()
        response = await client.delete(f"/api/v1/institutions/{created['id']}")
        assert response.status_code == 204
        after = await client.get(f"/api/v1/institutions/{created['id']}")
    assert after.status_code == 404


async def test_delete_institution_with_groups_returns_409() -> None:
    async with client_with_db() as (client, session):
        created = (
            await client.post("/api/v1/institutions", json={"name": "Owned"})
        ).json()
        session.add(
            GroupRecord(
                id="g1",
                name=GroupName.CURATORIAL,
                institution_id=created["id"],
            )
        )
        await session.commit()
        response = await client.delete(f"/api/v1/institutions/{created['id']}")
    assert response.status_code == 409
    assert response.json()["error"] == "INSTITUTION_IN_USE"


async def test_non_sysadmin_is_forbidden() -> None:
    async with client_with_db(caller=_EXTERNAL) as (client, _session):
        response = await client.post("/api/v1/institutions", json={"name": "Nope"})
    assert response.status_code == 403


async def test_groups_listing_includes_institution_id() -> None:
    async with client_with_db() as (client, session):
        session.add(
            InstitutionRecord(
                id="inst-1", name="MUHNAC", email="", address="", phone=""
            )
        )
        session.add(
            GroupRecord(
                id="grp-cur",
                name=GroupName.CURATORIAL,
                institution_id="inst-1",
            )
        )
        await session.commit()
        response = await client.get("/api/v1/groups")
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert groups[0]["institutionId"] == "inst-1"
