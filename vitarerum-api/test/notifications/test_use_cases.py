from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.identity.application.read_models import PermissionView, UserView
from app.identity.public import GroupName
from app.notifications.application.dispatch import CreateNotification
from app.notifications.application.use_cases import (
    ListNotifications,
    MarkAllNotificationsRead,
    MarkNotificationRead,
)
from app.notifications.domain.enums import NotificationKind, RelatedResourceType
from app.notifications.domain.models import Notification, NotificationId
from app.shared.kernel import PermissionId


class _Repo:
    def __init__(self) -> None:
        self.items: dict[str, Notification] = {}

    async def add(self, notification: Notification) -> None:
        self.items[notification.id] = notification

    async def get_by_id(self, notification_id: NotificationId) -> Notification | None:
        return self.items.get(notification_id)

    async def list_for_recipient(
        self,
        recipient_permission_id: PermissionId,
        page: int,
        size: int,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        items = [
            item
            for item in self.items.values()
            if item.recipient_permission_id == recipient_permission_id
            and (not unread_only or item.read_at is None)
        ]
        items = sorted(items, key=lambda item: item.created_at, reverse=True)
        return items[page * size : page * size + size], len(items)

    async def count_unread(self, recipient_permission_id: PermissionId) -> int:
        return sum(
            1
            for item in self.items.values()
            if item.recipient_permission_id == recipient_permission_id
            and item.read_at is None
        )

    async def save(self, notification: Notification) -> None:
        self.items[notification.id] = notification

    async def mark_all_read(self, recipient_permission_id: PermissionId) -> int:
        count = await self.count_unread(recipient_permission_id)
        now = datetime.now(tz=UTC)
        for item in self.items.values():
            if item.recipient_permission_id == recipient_permission_id:
                item.read_at = item.read_at or now
        return count


class _Reader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_detail(self, permission_id: PermissionId) -> PermissionView | None:
        self.calls.append(permission_id)
        return PermissionView(
            permission_id=permission_id,
            user=UserView(
                id=f"user-{permission_id}",
                name=f"User {permission_id}",
                email=f"{permission_id}@example.test",
                password_changed_at=None,
            ),
            group=GroupName.CURATORIAL,
        )

    async def list_by_group(self, group: GroupName) -> list[PermissionView]:
        return []


def _notification(
    notification_id: str,
    recipient: str = "perm-recipient",
    triggered_by: str | None = "perm-trigger",
    read: bool = False,
) -> Notification:
    return Notification(
        id=NotificationId(notification_id),
        recipient_permission_id=PermissionId(recipient),
        kind=NotificationKind.PROPOSAL_FORWARDED,
        related_resource_type=RelatedResourceType.PROPOSAL,
        related_resource_id="proposal-1",
        related_resource_label="VRP-1",
        triggered_by=PermissionId(triggered_by) if triggered_by else None,
        note=None,
        created_at=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        read_at=datetime(2026, 7, 30, 12, 5, tzinfo=UTC) if read else None,
    )


async def test_create_notification_persists_unread_item() -> None:
    repo = _Repo()

    await CreateNotification(repo).notify(
        recipient_permission_id=PermissionId("perm-recipient"),
        kind=NotificationKind.PROPOSAL_ASSIGNED,
        triggered_by=PermissionId("perm-trigger"),
        related_resource_type=RelatedResourceType.PROPOSAL,
        related_resource_id="proposal-1",
        related_resource_label="VRP-1",
        note="Review this",
    )

    [item] = repo.items.values()
    assert item.kind == NotificationKind.PROPOSAL_ASSIGNED
    assert item.related_resource_label == "VRP-1"
    assert item.read_at is None


async def test_list_notifications_dedupes_triggered_by_resolution() -> None:
    repo = _Repo()
    repo.items = {
        "n1": _notification("n1", triggered_by="perm-trigger"),
        "n2": _notification("n2", triggered_by="perm-trigger"),
    }
    reader = _Reader()

    page = await ListNotifications(repo, reader).execute(
        PermissionId("perm-recipient"), page=0, size=20
    )

    assert len(page.items) == 2
    assert reader.calls == ["perm-trigger"]
    assert page.items[0].triggered_by is not None


async def test_mark_read_is_idempotent_and_scoped_to_recipient() -> None:
    repo = _Repo()
    repo.items = {"n1": _notification("n1")}

    first = await MarkNotificationRead(repo).execute(
        NotificationId("n1"), PermissionId("perm-recipient")
    )
    second = await MarkNotificationRead(repo).execute(
        NotificationId("n1"), PermissionId("perm-recipient")
    )

    assert first is not None
    assert second is not None
    assert first.read_at == second.read_at
    with pytest.raises(PermissionError):
        await MarkNotificationRead(repo).execute(
            NotificationId("n1"), PermissionId("perm-other")
        )


async def test_mark_all_read_scopes_to_active_permission() -> None:
    repo = _Repo()
    repo.items = {
        "n1": _notification("n1"),
        "n2": _notification("n2", recipient="perm-other"),
    }

    count = await MarkAllNotificationsRead(repo).execute(PermissionId("perm-recipient"))

    assert count == 1
    assert repo.items["n1"].read_at is not None
    assert repo.items["n2"].read_at is None
