"""Identity read models — the published language other contexts consume.

These are plain application DTOs (no ORM, no Pydantic). Other contexts receive
these views, never Identity aggregates (Anti-Corruption Layer rule).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.domain.enums import GroupName
from app.shared.kernel import PermissionId


@dataclass(frozen=True, slots=True)
class UserView:
    id: str
    name: str
    email: str


@dataclass(frozen=True, slots=True)
class PermissionView:
    permission_id: str
    user: UserView
    group: GroupName


@dataclass(frozen=True, slots=True)
class Actor:
    """The authenticated caller acting under a permission.

    This is what other contexts receive as the command caller: the permission
    identity plus the minimum acting context (group for policy decisions,
    email for outbound correspondence).
    """

    id: PermissionId
    group: GroupName | None = None
    email: str = ""
