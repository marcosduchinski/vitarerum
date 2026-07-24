from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_async_session
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission

_SYS_ADMIN = Actor(
    id=PermissionId("perm-admin"), group=GroupName.SYS_ADMIN, email="admin@museum.pt"
)
_STAFF = Actor(
    id=PermissionId("perm-staff"),
    group=GroupName.CURATORIAL,
    email="staff@museum.pt",
)


@asynccontextmanager
async def _client(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    caller: Actor,
) -> AsyncIterator[AsyncClient]:
    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_async_session] = session_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_factory


async def test_sys_admin_can_preview_and_create_reference_policy() -> None:
    session_factory = await _session_factory()

    async with _client(session_factory, caller=_SYS_ADMIN) as client:
        preview = await client.post(
            "/api/v1/admin/reference-number-policies/preview",
            json={
                "kind": "COLLECTION_USE_PROJECT",
                "mask": "MUHNAC/COL/YYYY/XXXX",
                "sampleDate": "2026-07-23",
            },
        )
        created = await client.post(
            "/api/v1/admin/reference-number-policies",
            json={
                "kind": "COLLECTION_USE_PROJECT",
                "mask": "MUHNAC/COL/YYYY/XXXX",
            },
        )
        listed = await client.get("/api/v1/admin/reference-number-policies")

    assert preview.status_code == 200
    assert preview.json()["sequenceScope"] == "YEAR"
    assert preview.json()["example"] == "MUHNAC/COL/2026/0001"
    assert created.status_code == 201
    assert created.json()["status"] == "DRAFT"
    assert listed.status_code == 200
    assert [item["mask"] for item in listed.json()] == ["MUHNAC/COL/YYYY/XXXX"]


async def test_staff_cannot_read_or_mutate_reference_policies() -> None:
    session_factory = await _session_factory()

    async with _client(session_factory, caller=_STAFF) as client:
        listed = await client.get("/api/v1/admin/reference-number-policies")
        preview = await client.post(
            "/api/v1/admin/reference-number-policies/preview",
            json={
                "kind": "COLLECTION_USE_PROJECT",
                "mask": "MUHNAC/COL/YYYY/XXXX",
                "sampleDate": "2026-07-23",
            },
        )
        created = await client.post(
            "/api/v1/admin/reference-number-policies",
            json={
                "kind": "COLLECTION_USE_PROJECT",
                "mask": "MUHNAC/COL/YYYY/XXXX",
            },
        )

    assert listed.status_code == 403
    assert preview.status_code == 403
    assert created.status_code == 403
