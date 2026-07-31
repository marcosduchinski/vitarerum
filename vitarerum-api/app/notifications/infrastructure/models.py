from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.notifications.domain.enums import NotificationKind, RelatedResourceType


class NotificationRecord(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recipient_permission_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[NotificationKind] = mapped_column(
        SAEnum(NotificationKind, name="notification_kind")
    )
    related_resource_type: Mapped[RelatedResourceType | None] = mapped_column(
        SAEnum(RelatedResourceType, name="notification_related_resource_type"),
        nullable=True,
    )
    related_resource_id: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )
    related_resource_label: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    triggered_by: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
