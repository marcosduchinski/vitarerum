"""Management-scope policy for collection data sources.

Single rule (see docs/plans/plano-collection-data-sources-admin.md §6):
SYS_ADMIN and COLLECTIONS_MANAGEMENT manage any collection and assign curators;
CURATORIAL manages only collections assigned to them and cannot assign.
"""

from __future__ import annotations

from app.collection_object_index.domain.models import CollectionId
from app.identity.public import Actor, GroupName
from app.shared.exceptions import AccessDenied, InsufficientGroup

MANAGE_ALL_GROUPS = frozenset({GroupName.SYS_ADMIN, GroupName.COLLECTIONS_MANAGEMENT})


def can_manage_all_collections(caller: Actor) -> bool:
    return caller.group is not None and caller.group in MANAGE_ALL_GROUPS


def require_curator_admin(caller: Actor) -> None:
    """Guard for assigning/removing curators: never the curator themselves."""
    if can_manage_all_collections(caller):
        return
    raise InsufficientGroup(
        "Only SYS_ADMIN or COLLECTIONS_MANAGEMENT members can manage curators"
    )


def require_collection_scope(
    caller: Actor,
    collection_id: CollectionId,
    curated_ids: set[CollectionId],
) -> None:
    """Guard for managing a collection's source documents."""
    if can_manage_all_collections(caller):
        return
    if caller.group == GroupName.CURATORIAL and collection_id in curated_ids:
        return
    raise AccessDenied("You are not a curator of this collection")
