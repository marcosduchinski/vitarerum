from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.identity.public import PermissionReader, PermissionView
from app.notifications.application.ports import NotificationRepository
from app.notifications.domain.models import Notification, NotificationId
from app.shared.kernel import PermissionId


def _now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(slots=True)
class NotificationListItemView:
    notification: Notification
    triggered_by: PermissionView | None


@dataclass(slots=True)
class NotificationListPage:
    items: list[NotificationListItemView]
    total: int


async def _resolve_views(
    reader: PermissionReader,
    permission_ids: list[PermissionId | None],
) -> dict[str, PermissionView]:
    views: dict[str, PermissionView] = {}
    for permission_id in permission_ids:
        if permission_id is None or permission_id in views:
            continue
        view = await reader.get_detail(permission_id)
        if view is not None:
            views[permission_id] = view
    return views


class ListNotifications:
    def __init__(
        self,
        repository: NotificationRepository,
        permission_reader: PermissionReader,
    ) -> None:
        self._repo = repository
        self._reader = permission_reader

    async def execute(
        self,
        recipient_permission_id: PermissionId,
        page: int,
        size: int,
        unread_only: bool = False,
    ) -> NotificationListPage:
        notifications, total = await self._repo.list_for_recipient(
            recipient_permission_id, page, size, unread_only
        )
        views = await _resolve_views(
            self._reader, [notification.triggered_by for notification in notifications]
        )
        return NotificationListPage(
            items=[
                NotificationListItemView(
                    notification=notification,
                    triggered_by=(
                        views.get(notification.triggered_by)
                        if notification.triggered_by
                        else None
                    ),
                )
                for notification in notifications
            ],
            total=total,
        )


class CountUnreadNotifications:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repo = repository

    async def execute(self, recipient_permission_id: PermissionId) -> int:
        return await self._repo.count_unread(recipient_permission_id)


class MarkNotificationRead:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repo = repository

    async def execute(
        self,
        notification_id: NotificationId,
        recipient_permission_id: PermissionId,
    ) -> Notification | None:
        notification = await self._repo.get_by_id(notification_id)
        if notification is None:
            return None
        if notification.recipient_permission_id != recipient_permission_id:
            raise PermissionError("Notification belongs to another permission")
        if notification.read_at is None:
            notification.read_at = _now()
            await self._repo.save(notification)
        return notification


class MarkAllNotificationsRead:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repo = repository

    async def execute(self, recipient_permission_id: PermissionId) -> int:
        return await self._repo.mark_all_read(recipient_permission_id)
