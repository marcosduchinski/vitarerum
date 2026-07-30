from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

from app.identity.application.password_policy import validate_password_policy
from app.identity.application.ports import (
    Clock,
    GroupRepository,
    InstitutionRepository,
    PasswordHasher,
    PasswordResetTokenRepository,
    PermissionRepository,
    RateLimiter,
    UserFilters,
    UserRepository,
)
from app.identity.application.read_models import Actor
from app.identity.domain.enums import GroupName, UserStatus
from app.identity.domain.models import (
    GroupId,
    Institution,
    InstitutionId,
    PasswordResetToken,
    Permission,
    PermissionId,
    User,
    UserId,
)


def _hash_token(raw_token: str) -> str:
    """SHA-256 of an opaque raw token (password-reset link), so only the hash
    — never the raw value — is persisted. Mirrors the equivalent helper in
    ``public_submission``'s amendment-token adapter (same pattern, duplicated
    per context rather than a cross-context import)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# Rate limits as (max_requests, window_seconds), mirroring public_submission's
# and museum_questions' reference implementation (same policy, duplicated code
# per context rather than a cross-context import).
RATE_LIMIT_PER_IP = (5, 60 * 60)
RATE_LIMIT_PER_EMAIL = (3, 24 * 60 * 60)
RATE_LIMIT_PER_TOKEN = (10, 60 * 60)
RETRY_AFTER_SECONDS = 60


class InvalidCredentials(Exception):
    """Raised when login fails: unknown email, bad password, or no permissions."""


class IncorrectCurrentPassword(Exception):
    """Raised when change-password's currentPassword does not match the
    stored hash. Distinct from InvalidCredentials: the caller already holds a
    valid session, so this must not be surfaced as a 401 (the frontend's
    session-expired interceptor treats any 401 as "log the user out")."""


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int = RETRY_AFTER_SECONDS) -> None:
        super().__init__("Too many requests. Please try again later.")
        self.retry_after = retry_after


class InvalidOrExpiredResetToken(Exception):
    """Raised for a reset token that is unknown, expired, or already used.

    Deliberately doesn't distinguish which: mirrors public_submission's
    amendment-token 404 so a probing client can't learn which links exist."""


class InstitutionInUse(Exception):
    """Raised when deleting an institution that still owns groups."""


class LastActiveSysAdmin(Exception):
    """Raised when an operation would leave the system without an active admin."""


def _new_id() -> str:
    return str(uuid4())


def _normalize_email(email: str) -> str:
    """Case-insensitive, whitespace-trimmed email key, so uniqueness and
    lookups are consistent regardless of how the address was typed."""
    return email.strip().lower()


# Excludes visually-ambiguous characters (0/O, 1/l/I) since this is meant to be
# read from an e-mail and typed back in, not stored in a password manager.
_TEMPORARY_PASSWORD_ALPHABET = (
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
)
_TEMPORARY_PASSWORD_LENGTH = 16


def _generate_temporary_password() -> str:
    return "".join(
        secrets.choice(_TEMPORARY_PASSWORD_ALPHABET)
        for _ in range(_TEMPORARY_PASSWORD_LENGTH)
    )


@dataclass(slots=True)
class ProvisionedRequester:
    actor: Actor
    user_created: bool
    temporary_password: str | None = field(default=None, repr=False)


class ProvisionExternalRequester:
    """Get-or-create a user (by email) with an EXTERNAL permission.

    Published use case (Open Host Service): lets inbound orchestrators obtain an
    acting EXTERNAL requester without touching Identity aggregates. When the
    user is newly created, a temporary password is generated and hashed onto
    it (there is no password-reset/self-service flow yet, so this is the only
    way a freshly provisioned requester can ever log in) and returned in the
    clear — once, in this call's result — for the caller to relay by e-mail.
    An already-existing user's password is never touched.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        group_repo: GroupRepository,
        permission_repo: PermissionRepository,
        hasher: PasswordHasher,
    ) -> None:
        self._user_repo = user_repo
        self._group_repo = group_repo
        self._permission_repo = permission_repo
        self._hasher = hasher

    async def execute(self, email: str, name: str) -> ProvisionedRequester:
        email = _normalize_email(email)
        user_created = False
        temporary_password: str | None = None
        user = await self._user_repo.get_by_email(email)
        if user is None:
            temporary_password = _generate_temporary_password()
            user = User(
                id=UserId(_new_id()),
                name=name,
                email=email,
                password_hash=self._hasher.hash(temporary_password),
            )
            await self._user_repo.add(user)
            user_created = True

        external_group = await self._group_repo.get_by_name(GroupName.EXTERNAL)
        if external_group is None:
            raise RuntimeError("EXTERNAL group not found — run seed_groups first")

        permission = await self._permission_repo.get_by_user_and_group(
            user.id, external_group.id
        )
        if permission is None:
            permission = Permission(
                id=PermissionId(_new_id()),
                user_id=user.id,
                group_id=external_group.id,
                user=user,
                group=external_group,
            )
            await self._permission_repo.add(permission)

        return ProvisionedRequester(
            actor=Actor(
                id=permission.id,
                group=GroupName.EXTERNAL,
                email=user.email,
            ),
            user_created=user_created,
            temporary_password=temporary_password,
        )


class CreateUser:
    def __init__(
        self, repo: UserRepository, hasher: PasswordHasher | None = None
    ) -> None:
        self._repo = repo
        self._hasher = hasher

    async def execute(self, name: str, email: str, password: str | None = None) -> User:
        password_hash = ""
        if password:
            if self._hasher is None:
                raise ValueError("A PasswordHasher is required to set a password")
            validate_password_policy(password)
            password_hash = self._hasher.hash(password)
        user = User(
            id=UserId(str(uuid4())),
            name=name,
            email=_normalize_email(email),
            password_hash=password_hash,
        )
        await self._repo.add(user)
        return user


class AuthenticateUser:
    def __init__(
        self,
        user_repo: UserRepository,
        permission_repo: PermissionRepository,
        hasher: PasswordHasher,
    ) -> None:
        self._user_repo = user_repo
        self._permission_repo = permission_repo
        self._hasher = hasher

    async def execute(
        self, email: str, password: str
    ) -> tuple[User, list[Permission]]:
        user = await self._user_repo.get_by_email(_normalize_email(email))
        if (
            user is None
            or user.status is not UserStatus.ACTIVE
            or not self._hasher.verify(password, user.password_hash)
        ):
            raise InvalidCredentials("Invalid email or password")
        permissions = await self._permission_repo.get_by_user_id(UserId(user.id))
        if not permissions:
            # A principal with no group membership cannot establish a session.
            raise InvalidCredentials("Invalid email or password")
        return user, permissions


class ChangeOwnPassword:
    """Self-service password change for an already-authenticated user.

    Bumps ``password_changed_at`` so every bearer token issued before this
    call — including the one used to call it — stops working; the client is
    expected to sign the user out and require a fresh login.

    Only writes; it never e-mails. The "password changed" notice (optional,
    see ``PasswordChangedEmailSender``) must be sent by the caller *after* the
    transaction commits, the same way ``PublicAmendmentInvitationAdapter``
    sequences its own token/e-mail — otherwise a rolled-back write could still
    notify the user of a change that never happened.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        hasher: PasswordHasher,
        clock: Clock,
    ) -> None:
        self._user_repo = user_repo
        self._hasher = hasher
        self._clock = clock

    async def execute(
        self, email: str, current_password: str, new_password: str
    ) -> User:
        user = await self._user_repo.get_by_email(_normalize_email(email))
        if user is None or not self._hasher.verify(
            current_password, user.password_hash
        ):
            raise IncorrectCurrentPassword("Current password is incorrect")
        validate_password_policy(new_password)
        user.password_hash = self._hasher.hash(new_password)
        user.password_changed_at = self._clock.now()
        await self._user_repo.update(user)
        return user


@dataclass(slots=True)
class PasswordResetOutcome:
    """What the route needs to e-mail the reset link, once it has committed
    the token write. ``None`` from ``RequestPasswordReset.execute`` means "no
    such account" — the route must still return 204, but sends no e-mail."""

    email: str
    display_name: str
    raw_token: str


class RequestPasswordReset:
    """Pedido de reset: get-or-silently-ignore by e-mail, then mint a fresh
    single-use token. Never e-mails — like ``ChangeOwnPassword``, the route
    commits the write first and only then sends the link, so a rolled-back
    token is never delivered."""

    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: PasswordResetTokenRepository,
        rate_limiter: RateLimiter,
        clock: Clock,
        token_ttl: timedelta,
    ) -> None:
        self._user_repo = user_repo
        self._token_repo = token_repo
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._token_ttl = token_ttl

    async def execute(
        self, email: str, remote_ip: str
    ) -> PasswordResetOutcome | None:
        normalized = _normalize_email(email)
        if self._rate_limiter.too_many(
            f"ip:{remote_ip}", *RATE_LIMIT_PER_IP
        ) or self._rate_limiter.too_many(f"email:{normalized}", *RATE_LIMIT_PER_EMAIL):
            raise RateLimitExceeded()

        user = await self._user_repo.get_by_email(normalized)
        if user is None:
            return None

        now = self._clock.now()
        # At most one active link per account at a time.
        await self._token_repo.invalidate_active_for_user(UserId(user.id), now)
        raw_token = secrets.token_urlsafe(32)
        await self._token_repo.add(
            PasswordResetToken(
                id=str(uuid4()),
                user_id=UserId(user.id),
                token_hash=_hash_token(raw_token),
                created_at=now,
                expires_at=now + self._token_ttl,
            )
        )
        return PasswordResetOutcome(
            email=user.email, display_name=user.name, raw_token=raw_token
        )


class ConfirmPasswordReset:
    """Confirmação de reset: consumes a single-use token to set a new
    password. Raises ``InvalidOrExpiredResetToken`` uniformly for unknown,
    expired, or already-used tokens (never distinguishes which — see the
    exception's docstring)."""

    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: PasswordResetTokenRepository,
        hasher: PasswordHasher,
        rate_limiter: RateLimiter,
        clock: Clock,
    ) -> None:
        self._user_repo = user_repo
        self._token_repo = token_repo
        self._hasher = hasher
        self._rate_limiter = rate_limiter
        self._clock = clock

    async def execute(
        self, raw_token: str, new_password: str, remote_ip: str
    ) -> User:
        token_hash = _hash_token(raw_token)
        if self._rate_limiter.too_many(
            f"ip:{remote_ip}", *RATE_LIMIT_PER_IP
        ) or self._rate_limiter.too_many(f"token:{token_hash}", *RATE_LIMIT_PER_TOKEN):
            raise RateLimitExceeded()

        now = self._clock.now()
        token = await self._token_repo.get_by_hash(token_hash)
        if token is None or not token.is_active(now):
            raise InvalidOrExpiredResetToken("Invalid, expired, or already used token")

        user = await self._user_repo.get_by_id(token.user_id)
        if user is None:
            raise InvalidOrExpiredResetToken("Invalid, expired, or already used token")

        validate_password_policy(new_password)
        user.password_hash = self._hasher.hash(new_password)
        user.password_changed_at = now
        await self._user_repo.update(user)

        token.used_at = now
        await self._token_repo.save(token)
        return user


class ListUsers:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        filters: UserFilters,
        page: int,
        size: int,
    ) -> tuple[list[User], int]:
        return await self._repo.list(filters, page, size)


class GetUser:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: UserId) -> User | None:
        return await self._repo.get_by_id(user_id)


class UpdateUserName:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: UserId, name: str) -> User:
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise LookupError(f"No user found with id {user_id}")
        user.name = name.strip()
        await self._repo.update(user)
        return user


class SetUserStatus:
    def __init__(
        self,
        user_repo: UserRepository,
        permission_repo: PermissionRepository,
    ) -> None:
        self._user_repo = user_repo
        self._permission_repo = permission_repo

    async def execute(self, user_id: UserId, status: UserStatus) -> User:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise LookupError(f"No user found with id {user_id}")
        if status is UserStatus.DISABLED and user.status is UserStatus.ACTIVE:
            permissions = await self._permission_repo.get_by_user_id(user_id)
            is_sys_admin = any(
                p.group is not None and p.group.name is GroupName.SYS_ADMIN
                for p in permissions
            )
            if (
                is_sys_admin
                and await self._permission_repo.count_active_by_group_name(
                    GroupName.SYS_ADMIN
                )
                <= 1
            ):
                raise LastActiveSysAdmin(
                    "Cannot disable the last active system administrator"
                )
        user.status = status
        await self._user_repo.update(user)
        return user


class RequestAdminPasswordReset:
    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: PasswordResetTokenRepository,
        clock: Clock,
        token_ttl: timedelta,
    ) -> None:
        self._user_repo = user_repo
        self._token_repo = token_repo
        self._clock = clock
        self._token_ttl = token_ttl

    async def execute(self, user_id: UserId) -> PasswordResetOutcome:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise LookupError(f"No user found with id {user_id}")
        now = self._clock.now()
        await self._token_repo.invalidate_active_for_user(user.id, now)
        raw_token = secrets.token_urlsafe(32)
        await self._token_repo.add(
            PasswordResetToken(
                id=str(uuid4()),
                user_id=user.id,
                token_hash=_hash_token(raw_token),
                created_at=now,
                expires_at=now + self._token_ttl,
            )
        )
        return PasswordResetOutcome(
            email=user.email,
            display_name=user.name,
            raw_token=raw_token,
        )


class AssignUserToGroup:
    def __init__(
        self,
        user_repo: UserRepository,
        group_repo: GroupRepository,
        permission_repo: PermissionRepository,
    ) -> None:
        self._user_repo = user_repo
        self._group_repo = group_repo
        self._permission_repo = permission_repo

    async def execute(
        self, user_id: UserId, group_id: GroupId
    ) -> tuple[Permission, bool]:
        """Returns (permission, created). created=False means it already existed."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise LookupError(f"No user found with id {user_id}")
        group = await self._group_repo.get_by_id(group_id)
        if group is None:
            raise LookupError(f"No group found with id {group_id}")
        existing = await self._permission_repo.get_by_user_and_group(user_id, group_id)
        if existing is not None:
            existing.user = user
            existing.group = group
            return existing, False
        permission = Permission(
            id=PermissionId(_new_id()),
            user_id=user_id,
            group_id=group_id,
            user=user,
            group=group,
        )
        await self._permission_repo.add(permission)
        return permission, True


class RemoveUserFromGroup:
    def __init__(
        self,
        permission_repo: PermissionRepository,
    ) -> None:
        self._permission_repo = permission_repo

    async def execute(self, user_id: UserId, group_id: GroupId) -> None:
        existing = await self._permission_repo.get_by_user_and_group(user_id, group_id)
        if existing is None:
            raise LookupError(
                f"User {user_id} is not a member of group {group_id}"
            )
        if (
            existing.group is not None
            and existing.group.name is GroupName.SYS_ADMIN
            and existing.user is not None
            and existing.user.status is UserStatus.ACTIVE
            and await self._permission_repo.count_active_by_group_name(
                GroupName.SYS_ADMIN
            )
            <= 1
        ):
            raise LastActiveSysAdmin(
                "Cannot remove the last active system administrator"
            )
        await self._permission_repo.delete(existing.id)


class CreateInstitution:
    def __init__(self, repo: InstitutionRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        name: str,
        email: str = "",
        address: str = "",
        phone: str = "",
    ) -> Institution:
        institution = Institution(
            id=InstitutionId(_new_id()),
            name=name,
            email=email,
            address=address,
            phone=phone,
        )
        await self._repo.add(institution)
        return institution


class ListInstitutions:
    def __init__(self, repo: InstitutionRepository) -> None:
        self._repo = repo

    async def execute(
        self, page: int, size: int
    ) -> tuple[list[Institution], int]:
        return await self._repo.list(page, size)


class GetInstitution:
    def __init__(self, repo: InstitutionRepository) -> None:
        self._repo = repo

    async def execute(self, institution_id: InstitutionId) -> Institution | None:
        return await self._repo.get_by_id(institution_id)


class UpdateInstitution:
    def __init__(self, repo: InstitutionRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        institution_id: InstitutionId,
        name: str,
        email: str = "",
        address: str = "",
        phone: str = "",
    ) -> Institution:
        institution = await self._repo.get_by_id(institution_id)
        if institution is None:
            raise LookupError(f"No institution found with id {institution_id}")
        institution.name = name
        institution.email = email
        institution.address = address
        institution.phone = phone
        await self._repo.update(institution)
        return institution


class DeleteInstitution:
    def __init__(
        self,
        repo: InstitutionRepository,
        group_repo: GroupRepository,
    ) -> None:
        self._repo = repo
        self._group_repo = group_repo

    async def execute(self, institution_id: InstitutionId) -> None:
        institution = await self._repo.get_by_id(institution_id)
        if institution is None:
            raise LookupError(f"No institution found with id {institution_id}")
        if await self._group_repo.count_by_institution(institution_id) > 0:
            raise InstitutionInUse(
                f"Institution {institution_id} still owns groups"
            )
        await self._repo.delete(institution_id)
