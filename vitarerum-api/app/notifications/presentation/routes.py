from __future__ import annotations

from math import ceil

from fastapi import APIRouter, HTTPException, Query, status

from app.identity.public import PermissionView
from app.notifications.application.use_cases import (
    ClearAllNotifications,
    CountUnreadNotifications,
    MarkAllNotificationsRead,
    MarkNotificationRead,
)
from app.notifications.domain.models import Notification, NotificationId
from app.notifications.presentation.dependencies import (
    DBSession,
    NotificationListQuery,
    NotificationRepo,
    PermReader,
)
from app.notifications.presentation.schemas import (
    MarkAllNotificationsReadResponse,
    NotificationResponse,
    PaginatedNotificationsResponse,
    PermissionPrincipal,
    UnreadCountResponse,
    UserSummary,
)
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission

notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


def _not_found(notification_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "NOT_FOUND",
            "message": f"Notification {notification_id} not found",
        },
    )


def _permission_principal(view: PermissionView | None) -> PermissionPrincipal | None:
    if view is None:
        return None
    return PermissionPrincipal(
        permissionId=view.permission_id,
        user=UserSummary(id=view.user.id, name=view.user.name, email=view.user.email),
        group=view.group,
    )


def _notification_response(
    notification: Notification,
    triggered_by: PermissionView | None,
) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        kind=notification.kind,
        relatedResourceType=notification.related_resource_type,
        relatedResourceId=notification.related_resource_id,
        relatedResourceLabel=notification.related_resource_label,
        triggeredBy=_permission_principal(triggered_by),
        note=notification.note,
        createdAt=notification.created_at,
        readAt=notification.read_at,
    )


@notifications_router.get("", response_model=PaginatedNotificationsResponse)
async def list_notifications(
    caller: CallerPermission,
    query: NotificationListQuery,
    unreadOnly: bool = Query(False),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
) -> PaginatedNotificationsResponse:
    require_staff(caller)
    result = await query.execute(caller.id, page, size, unreadOnly)
    return PaginatedNotificationsResponse(
        content=[
            _notification_response(item.notification, item.triggered_by)
            for item in result.items
        ],
        page=page,
        size=size,
        totalElements=result.total,
        totalPages=ceil(result.total / size) if result.total else 0,
    )


@notifications_router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    caller: CallerPermission,
    repo: NotificationRepo,
) -> UnreadCountResponse:
    require_staff(caller)
    count = await CountUnreadNotifications(repo).execute(caller.id)
    return UnreadCountResponse(count=count)


@notifications_router.post(
    "/{notification_id}/read", response_model=NotificationResponse
)
async def mark_notification_read(
    notification_id: str,
    caller: CallerPermission,
    repo: NotificationRepo,
    reader: PermReader,
    session: DBSession,
) -> NotificationResponse:
    require_staff(caller)
    try:
        notification = await MarkNotificationRead(repo).execute(
            NotificationId(notification_id), caller.id
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "ACCESS_DENIED",
                "message": "Notification belongs to another permission",
            },
        ) from exc
    if notification is None:
        raise _not_found(notification_id)
    await session.commit()
    triggered_by = (
        await reader.get_detail(notification.triggered_by)
        if notification.triggered_by
        else None
    )
    return _notification_response(
        notification,
        triggered_by,
    )


@notifications_router.post("/read-all", response_model=MarkAllNotificationsReadResponse)
async def mark_all_notifications_read(
    caller: CallerPermission,
    repo: NotificationRepo,
    session: DBSession,
) -> MarkAllNotificationsReadResponse:
    require_staff(caller)
    count = await MarkAllNotificationsRead(repo).execute(caller.id)
    await session.commit()
    return MarkAllNotificationsReadResponse(count=count)


@notifications_router.post(
    "/clear-all", response_model=MarkAllNotificationsReadResponse
)
async def clear_all_notifications(
    caller: CallerPermission,
    repo: NotificationRepo,
    session: DBSession,
) -> MarkAllNotificationsReadResponse:
    require_staff(caller)
    count = await ClearAllNotifications(repo).execute(caller.id)
    await session.commit()
    return MarkAllNotificationsReadResponse(count=count)
