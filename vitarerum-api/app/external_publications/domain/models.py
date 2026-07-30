from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType

from app.shared.kernel import PermissionId

ExternalPublicationId = NewType("ExternalPublicationId", str)
ExternalPublicationAccessId = NewType("ExternalPublicationAccessId", str)


class ExternalPublicationResourceType(StrEnum):
    PROPOSAL = "PROPOSAL"
    PROJECT = "PROJECT"
    IN_SITU_VISIT_REPORT = "IN_SITU_VISIT_REPORT"


class ExternalPublicationStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    REVOKED = "REVOKED"


class ExternalPublicationAccessMode(StrEnum):
    TOKEN = "TOKEN"
    INTEGRATION_CLIENT = "INTEGRATION_CLIENT"


class ExternalPublicationProfile(StrEnum):
    SUMMARY = "SUMMARY"
    DETAIL = "DETAIL"
    JSON_LD = "JSON_LD"


class ExternalPublicationAccessOutcome(StrEnum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"


class ExternalProposalStatus(StrEnum):
    APPROVED = "APPROVED"


class ExternalProjectStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class PublicationInaccessible(ValueError):
    pass


@dataclass(slots=True)
class ExternalPublication:
    id: ExternalPublicationId
    resource_type: ExternalPublicationResourceType
    resource_id: str
    status: ExternalPublicationStatus
    access_mode: ExternalPublicationAccessMode
    profile: ExternalPublicationProfile
    token_hash: str | None
    integration_client_id: str | None
    expires_at: datetime | None
    created_by: PermissionId
    created_at: datetime
    published_at: datetime
    revoked_by: PermissionId | None = None
    revoked_at: datetime | None = None

    @classmethod
    def publish(
        cls,
        *,
        resource_type: ExternalPublicationResourceType,
        resource_id: str,
        access_mode: ExternalPublicationAccessMode,
        profile: ExternalPublicationProfile,
        created_by: PermissionId,
        token_hash: str | None,
        integration_client_id: str | None = None,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> ExternalPublication:
        if not resource_id.strip():
            raise ValueError("resourceId is required")
        if access_mode == ExternalPublicationAccessMode.TOKEN and not token_hash:
            raise ValueError("tokenHash is required for token publications")
        if (
            access_mode == ExternalPublicationAccessMode.INTEGRATION_CLIENT
            and not integration_client_id
        ):
            raise ValueError(
                "integrationClientId is required for integration-client publications"
            )
        if (
            profile == ExternalPublicationProfile.JSON_LD
            and resource_type != ExternalPublicationResourceType.IN_SITU_VISIT_REPORT
        ):
            raise ValueError("JSON_LD profile is only valid for in-situ visit reports")
        timestamp = _aware_utc(now or datetime.now(UTC))
        return cls(
            id=ExternalPublicationId(str(uuid.uuid4())),
            resource_type=resource_type,
            resource_id=resource_id,
            status=ExternalPublicationStatus.PUBLISHED,
            access_mode=access_mode,
            profile=profile,
            token_hash=token_hash,
            integration_client_id=integration_client_id,
            expires_at=_aware_utc(expires_at) if expires_at is not None else None,
            created_by=created_by,
            created_at=timestamp,
            published_at=timestamp,
        )

    def revoke(self, *, revoked_by: PermissionId, now: datetime | None = None) -> None:
        if self.status == ExternalPublicationStatus.REVOKED:
            return
        self.status = ExternalPublicationStatus.REVOKED
        self.revoked_by = revoked_by
        self.revoked_at = _aware_utc(now or datetime.now(UTC))

    def ensure_accessible(self, now: datetime | None = None) -> None:
        timestamp = _aware_utc(now or datetime.now(UTC))
        if self.status != ExternalPublicationStatus.PUBLISHED:
            raise PublicationInaccessible("Publication is revoked")
        expires_at = (
            _aware_utc(self.expires_at) if self.expires_at is not None else None
        )
        if expires_at is not None and timestamp >= expires_at:
            raise PublicationInaccessible("Publication is expired")


@dataclass(slots=True)
class ExternalPublicationAccess:
    id: ExternalPublicationAccessId
    publication_id: ExternalPublicationId | None
    accessed_at: datetime
    access_mode: ExternalPublicationAccessMode
    integration_client_id: str | None
    remote_addr_hash: str | None
    user_agent: str | None
    outcome: ExternalPublicationAccessOutcome

    @classmethod
    def record(
        cls,
        *,
        publication_id: ExternalPublicationId | None,
        access_mode: ExternalPublicationAccessMode,
        outcome: ExternalPublicationAccessOutcome,
        integration_client_id: str | None = None,
        remote_addr_hash: str | None = None,
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> ExternalPublicationAccess:
        return cls(
            id=ExternalPublicationAccessId(str(uuid.uuid4())),
            publication_id=publication_id,
            accessed_at=now or datetime.now(UTC),
            access_mode=access_mode,
            integration_client_id=integration_client_id,
            remote_addr_hash=remote_addr_hash,
            user_agent=user_agent,
            outcome=outcome,
        )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
