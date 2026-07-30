"""Identity & Access domain — owns User, Group, Permission (per the PUML)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NewType

from app.identity.domain.enums import GroupName, UserStatus
from app.shared.kernel import PermissionId as PermissionId

UserId = NewType("UserId", str)
GroupId = NewType("GroupId", str)
InstitutionId = NewType("InstitutionId", str)


@dataclass(slots=True)
class Institution:
    id: InstitutionId
    name: str = ""
    email: str = ""
    address: str = ""
    phone: str = ""


@dataclass(slots=True)
class User:
    id: UserId
    name: str = ""
    email: str = ""
    password_hash: str = ""
    status: UserStatus = UserStatus.ACTIVE
    # Bumped to "now" on every password change/reset. Access tokens issued
    # before this instant are rejected (see get_caller_permission), so a
    # stolen bearer token stops working once the owner reacts.
    password_changed_at: datetime | None = None


@dataclass(slots=True)
class Group:
    id: GroupId
    name: GroupName
    institution_id: InstitutionId


@dataclass(slots=True)
class Permission:
    id: PermissionId
    user_id: UserId
    group_id: GroupId
    user: User | None = None
    group: Group | None = None


@dataclass(slots=True)
class PasswordResetToken:
    """Narrow, single-use authorisation to set a new password for ``user_id``.

    ``token_hash`` is a SHA-256 of the opaque raw token; the raw value only
    ever lives in the e-mailed link. Dies on confirm (``used_at``) or once
    past ``expires_at``."""

    id: str
    user_id: UserId
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def is_expired(self, now: datetime) -> bool:
        return not self.is_used and now >= self.expires_at

    def is_active(self, now: datetime) -> bool:
        return not self.is_used and not self.is_expired(now)
