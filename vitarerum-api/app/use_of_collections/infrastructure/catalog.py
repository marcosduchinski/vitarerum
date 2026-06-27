from __future__ import annotations

from app.use_of_collections.domain.models import ObjectReference


class StubObjectCatalog:
    """Resolves inventory numbers to :class:`ObjectReference` snapshots.

    There is no real collection catalog wired into the system yet, so this
    adapter returns a snapshot carrying only the inventory number. Swap it for a
    real catalog client (implementing :class:`ObjectCatalogPort`) when one
    exists, and the resolved ``displayTitle``/``objectName``/``briefDescription``
    fields will start to populate without touching the application layer.
    """

    async def resolve(self, inventory_number: str) -> ObjectReference:
        return ObjectReference(inventory_number=inventory_number)
