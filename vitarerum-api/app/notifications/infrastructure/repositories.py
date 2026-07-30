from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.domain.models import Notification, NotificationId
from app.notifications.infrastructure.models import NotificationRecord
from app.shared.kernel import PermissionId


def notification_to_record(notification: Notification) -> NotificationRecord:
    return NotificationRecord(
        id=notification.id,
        recipient_permission_id=notification.recipient_permission_id,
        kind=notification.kind,
        related_resource_type=notification.related_resource_type,
        related_resource_id=notification.related_resource_id,
        related_resource_label=notification.related_resource_label,
        triggered_by=notification.triggered_by,
        note=notification.note,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


def notification_to_domain(record: NotificationRecord) -> Notification:
    return Notification(
        id=NotificationId(record.id),
        recipient_permission_id=PermissionId(record.recipient_permission_id),
        kind=record.kind,
        related_resource_type=record.related_resource_type,
        related_resource_id=record.related_resource_id,
        related_resource_label=record.related_resource_label,
        triggered_by=PermissionId(record.triggered_by) if record.triggered_by else None,
        note=record.note,
        created_at=record.created_at,
        read_at=record.read_at,
    )


class SqlAlchemyNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> None:
        self._session.add(notification_to_record(notification))

    async def get_by_id(self, notification_id: NotificationId) -> Notification | None:
        record = await self._session.get(NotificationRecord, notification_id)
        return notification_to_domain(record) if record is not None else None

    async def list_for_recipient(
        self,
        recipient_permission_id: PermissionId,
        page: int,
        size: int,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        filters = [
            NotificationRecord.recipient_permission_id == recipient_permission_id
        ]
        if unread_only:
            filters.append(NotificationRecord.read_at.is_(None))
        total_result = await self._session.execute(
            select(func.count()).select_from(NotificationRecord).where(*filters)
        )
        total = int(total_result.scalar_one())
        result = await self._session.execute(
            select(NotificationRecord)
            .where(*filters)
            .order_by(
                NotificationRecord.created_at.desc(),
                NotificationRecord.id.desc(),
            )
            .offset(page * size)
            .limit(size)
        )
        return [notification_to_domain(r) for r in result.scalars().all()], total

    async def count_unread(self, recipient_permission_id: PermissionId) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(NotificationRecord)
            .where(
                NotificationRecord.recipient_permission_id == recipient_permission_id,
                NotificationRecord.read_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def save(self, notification: Notification) -> None:
        existing = await self._session.get(NotificationRecord, notification.id)
        if existing is None:
            self._session.add(notification_to_record(notification))
            return
        existing.recipient_permission_id = notification.recipient_permission_id
        existing.kind = notification.kind
        existing.related_resource_type = notification.related_resource_type
        existing.related_resource_id = notification.related_resource_id
        existing.related_resource_label = notification.related_resource_label
        existing.triggered_by = notification.triggered_by
        existing.note = notification.note
        existing.created_at = notification.created_at
        existing.read_at = notification.read_at

    async def mark_all_read(self, recipient_permission_id: PermissionId) -> int:
        result = await self._session.execute(
            update(NotificationRecord)
            .where(
                NotificationRecord.recipient_permission_id == recipient_permission_id,
                NotificationRecord.read_at.is_(None),
            )
            .values(read_at=datetime.now(tz=UTC))
        )
        return cast(CursorResult[Any], result).rowcount or 0
