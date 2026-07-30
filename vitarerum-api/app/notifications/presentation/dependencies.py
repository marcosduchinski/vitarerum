from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.identity.public import PermissionReader, get_permission_reader
from app.notifications.application.ports import NotificationRepository
from app.notifications.application.use_cases import ListNotifications
from app.notifications.infrastructure.repositories import (
    SqlAlchemyNotificationRepository,
)

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_notification_repo(session: DBSession) -> NotificationRepository:
    return SqlAlchemyNotificationRepository(session)


def get_reader(session: DBSession) -> PermissionReader:
    return get_permission_reader(session)


NotificationRepo = Annotated[NotificationRepository, Depends(get_notification_repo)]
PermReader = Annotated[PermissionReader, Depends(get_reader)]


def get_list_notifications_query(
    repo: NotificationRepo, reader: PermReader
) -> ListNotifications:
    return ListNotifications(repo, reader)


NotificationListQuery = Annotated[
    ListNotifications, Depends(get_list_notifications_query)
]

