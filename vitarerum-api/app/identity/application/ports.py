from dataclasses import dataclass
from typing import Protocol

from app.identity.application.read_models import PermissionView
from app.identity.domain.enums import GroupName
from app.identity.domain.models import (
    Group,
    GroupId,
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


class UserRepository(Protocol):
    async def add(self, user: User) -> None: ...
    async def get_by_id(self, user_id: UserId) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def list(
        self, filters: UserFilters, page: int, size: int
    ) -> tuple[list[User], int]: ...


class GroupRepository(Protocol):
    async def get_by_id(self, group_id: GroupId) -> Group | None: ...
    async def get_by_name(self, name: GroupName) -> Group | None: ...
    async def list(self) -> list[Group]: ...


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


class PermissionReader(Protocol):
    """Identity's published read port (Open Host Service): resolves a
    permission id to its hydrated view for display or caller resolution."""

    async def get_detail(
        self, permission_id: PermissionId
    ) -> PermissionView | None: ...
