"""Group-membership policy on the published Actor view.

HTTP-free and aggregate-free: depends only on Identity's published language
and the shared exceptions. Proposal/project access policies live in
use_of_collections/application/authorization.py (they need the Proposal
aggregate, which must not leak into shared code).
"""

from collections.abc import Iterable

from app.identity.public import Actor, GroupName
from app.shared.exceptions import InsufficientGroup

STAFF_GROUPS = frozenset(
    {
        GroupName.CURATORIAL,
        GroupName.COLLECTIONS_MANAGEMENT,
        GroupName.DIRECTION,
        GroupName.SYS_ADMIN,
    }
)


def is_in_group(caller: Actor, groups: Iterable[GroupName]) -> bool:
    return caller.group is not None and caller.group in groups


def is_staff(caller: Actor) -> bool:
    return is_in_group(caller, STAFF_GROUPS)


def require_group(caller: Actor, *groups: GroupName) -> None:
    if is_in_group(caller, groups):
        return
    names = " or ".join(group.value for group in groups)
    raise InsufficientGroup(f"Only {names} members can perform this action")


def require_staff(caller: Actor) -> None:
    require_group(caller, *STAFF_GROUPS)
