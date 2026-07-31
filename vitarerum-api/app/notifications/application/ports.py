from __future__ import annotations

from typing import Protocol

from app.notifications.domain.models import Notification, NotificationId
from app.shared.kernel import PermissionId


class NotificationRepository(Protocol):
    async def add(self, notification: Notification) -> None: ...

    async def get_by_id(
        self, notification_id: NotificationId
    ) -> Notification | None: ...

    async def list_for_recipient(
        self,
        recipient_permission_id: PermissionId,
        page: int,
        size: int,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]: ...

    async def count_unread(self, recipient_permission_id: PermissionId) -> int: ...

    async def save(self, notification: Notification) -> None: ...

    async def mark_all_read(self, recipient_permission_id: PermissionId) -> int: ...

    async def clear_all(self, recipient_permission_id: PermissionId) -> int: ...
