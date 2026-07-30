from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NewType

from app.notifications.domain.enums import NotificationKind, RelatedResourceType
from app.shared.kernel import PermissionId

NotificationId = NewType("NotificationId", str)


@dataclass(slots=True)
class Notification:
    id: NotificationId
    recipient_permission_id: PermissionId
    kind: NotificationKind
    related_resource_type: RelatedResourceType | None
    related_resource_id: str | None
    related_resource_label: str | None
    triggered_by: PermissionId | None
    note: str | None
    created_at: datetime
    read_at: datetime | None = None

