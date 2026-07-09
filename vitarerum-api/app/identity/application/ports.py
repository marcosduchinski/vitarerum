from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.identity.application.read_models import PermissionView
from app.identity.domain.enums import GroupName
from app.identity.domain.models import (
    Group,
    GroupId,
    Institution,
    InstitutionId,
    PasswordResetToken,
    Permission,
    PermissionId,
    User,
    UserId,
)


@dataclass(slots=True)
class UserFilters:
    group_id: str | None = None
    search: str | None = None


class PasswordHasher(Protocol):
    def hash(self, plain: str) -> str: ...
    def verify(self, plain: str, hashed: str) -> bool: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class PasswordChangedEmailSender(Protocol):
    async def send_password_changed_notice(
        self, to_email: str, display_name: str
    ) -> None:
        """Notify the account owner that their password just changed, so an
        unauthorized change can be noticed and reported."""
        ...


class UserRepository(Protocol):
    async def add(self, user: User) -> None: ...
    async def get_by_id(self, user_id: UserId) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def list(
        self, filters: UserFilters, page: int, size: int
    ) -> tuple[list[User], int]: ...
    async def update(self, user: User) -> None: ...


class GroupRepository(Protocol):
    async def get_by_id(self, group_id: GroupId) -> Group | None: ...
    async def get_by_name(self, name: GroupName) -> Group | None: ...
    async def list(self) -> list[Group]: ...
    async def count_by_institution(self, institution_id: InstitutionId) -> int: ...


class InstitutionRepository(Protocol):
    async def add(self, institution: Institution) -> None: ...
    async def get_by_id(self, institution_id: InstitutionId) -> Institution | None: ...
    async def get_by_name(self, name: str) -> Institution | None: ...
    async def list(self, page: int, size: int) -> tuple[list[Institution], int]: ...
    async def update(self, institution: Institution) -> None: ...
    async def delete(self, institution_id: InstitutionId) -> None: ...


class PermissionRepository(Protocol):
    async def add(self, permission: Permission) -> None: ...
    async def get_by_user_and_group(
        self, user_id: UserId, group_id: GroupId
    ) -> Permission | None: ...
    async def get_by_user_id(self, user_id: UserId) -> list[Permission]: ...
    async def get_by_group_id(
        self, group_id: GroupId, page: int, size: int
    ) -> tuple[list[Permission], int]: ...
    async def delete(self, permission_id: PermissionId) -> None: ...


class PasswordResetTokenRepository(Protocol):
    async def add(self, token: PasswordResetToken) -> None: ...
    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None: ...
    async def save(self, token: PasswordResetToken) -> None: ...
    async def invalidate_active_for_user(self, user_id: UserId, now: datetime) -> None:
        """Mark every not-yet-used token for ``user_id`` as used as of ``now``,
        so at most one reset link is ever active per account."""
        ...


class PasswordResetEmailSender(Protocol):
    async def send_password_reset(
        self, to_email: str, display_name: str, token: str
    ) -> None:
        """Deliver the reset link (built from the raw ``token``) to the user."""
        ...


class PasswordEmailSender(
    PasswordResetEmailSender, PasswordChangedEmailSender, Protocol
):
    """Combined identity mailer: reset link + changed notice.

    The concrete senders (SMTP/logging) implement both, so a single instance
    serves both the reset and change-password flows (mirrors
    ``public_submission``'s ``PublicEmailSender``)."""


class RateLimiter(Protocol):
    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Record a hit for ``key`` and report whether the limit is now exceeded."""
        ...


class PermissionReader(Protocol):
    """Identity's published read port (Open Host Service): resolves a
    permission id to its hydrated view for display or caller resolution."""

    async def get_detail(
        self, permission_id: PermissionId
    ) -> PermissionView | None: ...

    async def list_by_group(self, group: GroupName) -> list[PermissionView]: ...
