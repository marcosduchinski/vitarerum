"""Management-scope policy for collection data sources.

Two rules:
- SYS_ADMIN alone administers the collection catalog itself — create, rename,
  remove a collection (permanent), and assign/remove its curators.
- SYS_ADMIN and COLLECTIONS_MANAGEMENT manage any collection's source
  documents; CURATORIAL manages only collections assigned to them.
"""

from __future__ import annotations

from app.collection_object_index.domain.models import CollectionId
from app.identity.public import Actor, GroupName
from app.shared.exceptions import AccessDenied, InsufficientGroup

MANAGE_ALL_GROUPS = frozenset({GroupName.SYS_ADMIN, GroupName.COLLECTIONS_MANAGEMENT})
CATALOG_ADMIN_GROUPS = frozenset({GroupName.SYS_ADMIN})


def can_manage_all_collections(caller: Actor) -> bool:
    return caller.group is not None and caller.group in MANAGE_ALL_GROUPS


def require_catalog_admin(caller: Actor) -> None:
    """Guard for administering the collection catalog itself: create/rename/
    remove a collection (permanent), and assign/remove its curators."""
    if caller.group is not None and caller.group in CATALOG_ADMIN_GROUPS:
        return
    raise InsufficientGroup("Only SYS_ADMIN members can manage the collection catalog")


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
