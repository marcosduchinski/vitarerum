from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from uuid import uuid4

from app.identity.application.ports import (
    GroupRepository,
    InstitutionRepository,
    PasswordHasher,
    PermissionRepository,
    UserFilters,
    UserRepository,
)
from app.identity.application.read_models import Actor
from app.identity.domain.enums import GroupName
from app.identity.domain.models import (
    GroupId,
    Institution,
    InstitutionId,
    Permission,
    PermissionId,
    User,
    UserId,
)


class InvalidCredentials(Exception):
    """Raised when login fails: unknown email, bad password, or no permissions."""


class InstitutionInUse(Exception):
    """Raised when deleting an institution that still owns groups."""


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
        if user is None or not self._hasher.verify(password, user.password_hash):
            raise InvalidCredentials("Invalid email or password")
        permissions = await self._permission_repo.get_by_user_id(UserId(user.id))
        if not permissions:
            # A principal with no group membership cannot establish a session.
            raise InvalidCredentials("Invalid email or password")
        return user, permissions


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
