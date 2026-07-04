"""Read models returned by the management queries."""

from __future__ import annotations

from dataclasses import dataclass

from app.collection_object_index.domain.models import Collection, CuratorAssignment


@dataclass(frozen=True, slots=True)
class CollectionView:
    """A collection with its curators and live-document count, plus whether the
    caller may manage it (drives the management UI)."""

    collection: Collection
    curators: list[CuratorAssignment]
    document_count: int
    manageable: bool
