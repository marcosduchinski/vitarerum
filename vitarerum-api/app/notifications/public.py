from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.notifications.domain.enums import NotificationKind, RelatedResourceType
from app.shared.kernel import PermissionId

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class NotificationDispatcher(Protocol):
    async def notify(
        self,
        *,
        recipient_permission_id: PermissionId,
        kind: NotificationKind,
        triggered_by: PermissionId | None,
        related_resource_type: RelatedResourceType | None = None,
        related_resource_id: str | None = None,
        related_resource_label: str | None = None,
        note: str | None = None,
    ) -> None: ...


def get_notification_dispatcher(session: AsyncSession) -> NotificationDispatcher:
    from app.notifications.application.dispatch import CreateNotification
    from app.notifications.infrastructure.repositories import (
        SqlAlchemyNotificationRepository,
    )

    return CreateNotification(SqlAlchemyNotificationRepository(session))


__all__ = [
    "NotificationDispatcher",
    "NotificationKind",
    "RelatedResourceType",
    "get_notification_dispatcher",
]
