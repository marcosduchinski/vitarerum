from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_async_session
from app.identity.infrastructure.models import (
    GroupRecord,
    InstitutionRecord,
    PermissionRecord,
    UserRecord,
)
from app.identity.public import Actor, GroupName
from app.main import app
from app.notifications.domain.enums import NotificationKind, RelatedResourceType
from app.notifications.domain.models import Notification, NotificationId
from app.notifications.infrastructure.repositories import (
    SqlAlchemyNotificationRepository,
)
from app.shared.dependencies import get_caller_permission
from app.shared.kernel import PermissionId

_NOW = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
_CALLER = Actor(
    id=PermissionId("perm-recipient"),
    group=GroupName.CURATORIAL,
    email="recipient@example.test",
)
_OTHER_CALLER = Actor(
    id=PermissionId("perm-other"),
    group=GroupName.DIRECTION,
    email="other@example.test",
)
_EXTERNAL_CALLER = Actor(
    id=PermissionId("perm-external"),
    group=GroupName.EXTERNAL,
    email="external@example.test",
)


async def _session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def _client(
    session_factory: async_sessionmaker[AsyncSession],
    caller: Actor = _CALLER,
) -> AsyncIterator[AsyncClient]:
    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = session_override
    app.dependency_overrides[get_caller_permission] = lambda: caller
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def _seed_identity(session: AsyncSession) -> None:
    institution = InstitutionRecord(
        id="institution-1",
        name="Museum",
        email="museum@example.test",
        address="Museum street",
        phone="123",
    )
    curatorial = GroupRecord(
        id="group-curatorial",
        name=GroupName.CURATORIAL,
        institution_id=institution.id,
    )
    direction = GroupRecord(
        id="group-direction",
        name=GroupName.DIRECTION,
        institution_id=institution.id,
    )
    recipient = UserRecord(
        id="user-recipient",
        name="Recipient User",
        email="recipient@example.test",
        password_hash="",
    )
    actor = UserRecord(
        id="user-actor",
        name="Actor User",
        email="actor@example.test",
        password_hash="",
    )
    other = UserRecord(
        id="user-other",
        name="Other User",
        email="other@example.test",
        password_hash="",
    )
    session.add_all(
        [
            institution,
            curatorial,
            direction,
            recipient,
            actor,
            other,
            PermissionRecord(
                id="perm-recipient",
                user_id=recipient.id,
                group_id=curatorial.id,
            ),
            PermissionRecord(id="perm-actor", user_id=actor.id, group_id=direction.id),
            PermissionRecord(id="perm-other", user_id=other.id, group_id=direction.id),
        ]
    )


def _notification(
    notification_id: str,
    *,
    recipient_permission_id: str = "perm-recipient",
    read_at: datetime | None = None,
    cleared_at: datetime | None = None,
) -> Notification:
    return Notification(
        id=NotificationId(notification_id),
        recipient_permission_id=PermissionId(recipient_permission_id),
        kind=NotificationKind.PROPOSAL_FORWARDED,
        related_resource_type=RelatedResourceType.PROPOSAL,
        related_resource_id="proposal-1",
        related_resource_label="VRP-20260730-0001",
        triggered_by=PermissionId("perm-actor"),
        note="Please review",
        created_at=_NOW,
        read_at=read_at,
        cleared_at=cleared_at,
    )


async def test_sqlalchemy_notification_repository_round_trip_and_mark_all_read() -> (
    None
):
    session_factory = await _session_factory()
    async with session_factory() as session:
        repo = SqlAlchemyNotificationRepository(session)
        await repo.add(_notification("notification-1"))
        await repo.add(_notification("notification-2", read_at=_NOW))
        await session.commit()

        listed, total = await repo.list_for_recipient(
            PermissionId("perm-recipient"), page=0, size=10
        )
        unread_count = await repo.count_unread(PermissionId("perm-recipient"))
        marked_count = await repo.mark_all_read(PermissionId("perm-recipient"))
        await session.commit()
        unread_after_mark = await repo.count_unread(PermissionId("perm-recipient"))

    assert total == 2
    assert [item.id for item in listed] == ["notification-2", "notification-1"]
    assert unread_count == 1
    assert marked_count == 1
    assert unread_after_mark == 0


async def test_repo_clear_all_hides_active_permission() -> None:
    session_factory = await _session_factory()
    async with session_factory() as session:
        repo = SqlAlchemyNotificationRepository(session)
        await repo.add(_notification("notification-1"))
        await repo.add(_notification("notification-2", read_at=_NOW))
        await repo.add(
            _notification(
                "notification-3",
                recipient_permission_id="perm-other",
            )
        )
        await session.commit()

        cleared_count = await repo.clear_all(PermissionId("perm-recipient"))
        await session.commit()
        listed, total = await repo.list_for_recipient(
            PermissionId("perm-recipient"), page=0, size=10
        )
        unread_count = await repo.count_unread(PermissionId("perm-recipient"))
        other_listed, other_total = await repo.list_for_recipient(
            PermissionId("perm-other"), page=0, size=10
        )

    assert cleared_count == 2
    assert listed == []
    assert total == 0
    assert unread_count == 0
    assert other_total == 1
    assert [item.id for item in other_listed] == ["notification-3"]


async def test_notifications_routes_list_filter_count_and_mark_read() -> None:
    session_factory = await _session_factory()
    async with session_factory() as session:
        await _seed_identity(session)
        repo = SqlAlchemyNotificationRepository(session)
        await repo.add(_notification("notification-1"))
        await repo.add(_notification("notification-2", read_at=_NOW))
        await session.commit()

    async with _client(session_factory) as client:
        unread_response = await client.get("/api/v1/notifications/unread-count")
        list_response = await client.get("/api/v1/notifications?page=0&size=10")
        unread_list_response = await client.get(
            "/api/v1/notifications?unreadOnly=true&page=0&size=10"
        )
        mark_response = await client.post("/api/v1/notifications/notification-1/read")
        unread_after_mark_response = await client.get(
            "/api/v1/notifications/unread-count"
        )

    assert unread_response.status_code == 200
    assert unread_response.json() == {"count": 1}
    assert list_response.status_code == 200
    assert list_response.json()["totalElements"] == 2
    assert list_response.json()["content"][0]["triggeredBy"]["permissionId"] == (
        "perm-actor"
    )
    assert unread_list_response.status_code == 200
    assert unread_list_response.json()["totalElements"] == 1
    assert mark_response.status_code == 200
    assert mark_response.json()["readAt"] is not None
    assert unread_after_mark_response.json() == {"count": 0}


async def test_notifications_routes_clear_all_hides_list_and_clears_unread() -> None:
    session_factory = await _session_factory()
    async with session_factory() as session:
        await _seed_identity(session)
        repo = SqlAlchemyNotificationRepository(session)
        await repo.add(_notification("notification-1"))
        await repo.add(_notification("notification-2", read_at=_NOW))
        await session.commit()

    async with _client(session_factory) as client:
        clear_response = await client.post("/api/v1/notifications/clear-all")
        list_response = await client.get("/api/v1/notifications?page=0&size=10")
        unread_response = await client.get("/api/v1/notifications/unread-count")

    assert clear_response.status_code == 200
    assert clear_response.json() == {"count": 2}
    assert list_response.json()["totalElements"] == 0
    assert list_response.json()["content"] == []
    assert unread_response.json() == {"count": 0}


async def test_notification_routes_reject_other_recipient_and_external_callers() -> (
    None
):
    session_factory = await _session_factory()
    async with session_factory() as session:
        await _seed_identity(session)
        repo = SqlAlchemyNotificationRepository(session)
        await repo.add(_notification("notification-1"))
        await session.commit()

    async with _client(session_factory, caller=_OTHER_CALLER) as client:
        other_response = await client.post("/api/v1/notifications/notification-1/read")

    async with _client(session_factory, caller=_EXTERNAL_CALLER) as client:
        external_response = await client.get("/api/v1/notifications")

    assert other_response.status_code == 403
    assert external_response.status_code == 403
