from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.notifications.application.ports import NotificationRepository
from app.notifications.domain.enums import NotificationKind, RelatedResourceType
from app.notifications.domain.models import Notification, NotificationId
from app.shared.kernel import PermissionId


def _now() -> datetime:
    return datetime.now(tz=UTC)


class CreateNotification:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repo = repository

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
    ) -> None:
        notification = Notification(
            id=NotificationId(str(uuid4())),
            recipient_permission_id=recipient_permission_id,
            kind=kind,
            related_resource_type=related_resource_type,
            related_resource_id=related_resource_id,
            related_resource_label=related_resource_label,
            triggered_by=triggered_by,
            note=note,
            created_at=_now(),
        )
        await self._repo.add(notification)
