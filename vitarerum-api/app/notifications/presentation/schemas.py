from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.identity.public import GroupName
from app.notifications.domain.enums import NotificationKind, RelatedResourceType


class UserSummary(BaseModel):
    id: str
    name: str
    email: str


class PermissionPrincipal(BaseModel):
    permissionId: str
    user: UserSummary
    group: GroupName


class NotificationResponse(BaseModel):
    id: str
    kind: NotificationKind
    relatedResourceType: RelatedResourceType | None = None
    relatedResourceId: str | None = None
    relatedResourceLabel: str | None = None
    triggeredBy: PermissionPrincipal | None = None
    note: str | None = None
    createdAt: datetime
    readAt: datetime | None = None


class PaginatedNotificationsResponse(BaseModel):
    content: list[NotificationResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class UnreadCountResponse(BaseModel):
    count: int


class MarkAllNotificationsReadResponse(BaseModel):
    count: int

