from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.external_publications.domain.models import (
    ExternalPublicationAccessMode,
    ExternalPublicationAccessOutcome,
    ExternalPublicationProfile,
    ExternalPublicationResourceType,
    ExternalPublicationStatus,
)


class ExternalPublicationOrm(Base):
    __tablename__ = "external_publications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_type: Mapped[ExternalPublicationResourceType] = mapped_column(
        SAEnum(
            ExternalPublicationResourceType,
            name="external_publication_resource_type",
        ),
        index=True,
    )
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[ExternalPublicationStatus] = mapped_column(
        SAEnum(ExternalPublicationStatus, name="external_publication_status"),
        index=True,
    )
    access_mode: Mapped[ExternalPublicationAccessMode] = mapped_column(
        SAEnum(ExternalPublicationAccessMode, name="external_publication_access_mode")
    )
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    integration_client_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    profile: Mapped[ExternalPublicationProfile] = mapped_column(
        SAEnum(ExternalPublicationProfile, name="external_publication_profile"),
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_by: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class ExternalPublicationAccessOrm(Base):
    __tablename__ = "external_publication_accesses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    access_mode: Mapped[ExternalPublicationAccessMode] = mapped_column(
        SAEnum(ExternalPublicationAccessMode, name="external_publication_access_mode")
    )
    integration_client_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    remote_addr_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[ExternalPublicationAccessOutcome] = mapped_column(
        SAEnum(
            ExternalPublicationAccessOutcome,
            name="external_publication_access_outcome",
        ),
        index=True,
    )
