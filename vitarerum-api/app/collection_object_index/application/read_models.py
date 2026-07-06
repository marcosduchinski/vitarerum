"""Read models returned by the management queries."""

from __future__ import annotations

from dataclasses import dataclass

from app.collection_object_index.domain.models import (
    Collection,
    CollectionArea,
    CuratorAssignment,
)


@dataclass(frozen=True, slots=True)
class CollectionView:
    """A collection with its curators and live-document count, plus whether the
    caller may manage it (drives the management UI)."""

    collection: Collection
    area_name: str
    curators: list[CuratorAssignment]
    document_count: int
    manageable: bool


@dataclass(frozen=True, slots=True)
class CollectionAreaView:
    """A collection area with how many collections are currently assigned to
    it — the count backs both the admin listing and the removal guard
    (``CollectionAreaInUse``)."""

    area: CollectionArea
    collection_count: int
