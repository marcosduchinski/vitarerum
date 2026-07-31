"""Identity's published language (Open Host Service).

This is the ONLY Identity module other contexts may import (enforced by
import-linter). It exposes the cross-context vocabulary the PUML assigns to
Identity & Access, the read port other contexts consume, and the token
primitives the shared HTTP caller dependency needs.

`User`, `Group`, `Permission`, `UserId`, `GroupId` remain exported for tests
and seeds only; production cross-context code must use the read models and
published use cases instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.identity.application.ports import PermissionReader
from app.identity.application.read_models import Actor, PermissionView, UserView
from app.identity.application.use_cases import (
    ProvisionedRequester,
    ProvisionExternalRequester,
)
from app.identity.domain.enums import GroupName, UserStatus
from app.identity.domain.models import (
    Group,
    GroupId,
    Permission,
    User,
    UserId,
)
from app.identity.infrastructure.security import (
    BcryptPasswordHasher,
    DecodedAccessToken,
    TokenError,
    decode_access_token,
)
from app.shared.kernel import PermissionId

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def get_permission_reader(session: AsyncSession) -> PermissionReader:
    """Default composition hook: the SQLAlchemy-backed PermissionReader."""
    from app.identity.infrastructure.repositories import SqlAlchemyPermissionReader

    return SqlAlchemyPermissionReader(session)


def get_requester_provisioner(session: AsyncSession) -> ProvisionExternalRequester:
    """Default composition hook: a SQLAlchemy-backed ProvisionExternalRequester."""
    from app.identity.infrastructure.repositories import (
        SqlAlchemyGroupRepository,
        SqlAlchemyPermissionRepository,
        SqlAlchemyUserRepository,
    )

    return ProvisionExternalRequester(
        user_repo=SqlAlchemyUserRepository(session),
        group_repo=SqlAlchemyGroupRepository(session),
        permission_repo=SqlAlchemyPermissionRepository(session),
        hasher=BcryptPasswordHasher(),
    )


__all__ = [
    "Actor",
    "DecodedAccessToken",
    "Group",
    "GroupId",
    "GroupName",
    "Permission",
    "PermissionId",
    "PermissionReader",
    "PermissionView",
    "ProvisionExternalRequester",
    "ProvisionedRequester",
    "TokenError",
    "User",
    "UserId",
    "UserStatus",
    "UserView",
    "decode_access_token",
    "get_permission_reader",
    "get_requester_provisioner",
]
