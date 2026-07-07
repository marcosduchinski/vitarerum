"""Anti-corruption adapter over the Collection Object Index's search use case.

Implements ``ObjectSearchPort`` by calling ``SearchCollectionObjects``
directly (the same use case Objects -> Search uses), mapping its result into
this context's own ``ObjectHitView``. Receives an already-built
``CollectionObjectIndexPort`` through the constructor — no ``Depends`` here;
infrastructure must not depend on FastAPI. The composition root
(``presentation/dependencies.py``) resolves the index via the Collection
Object Index's own ``get_object_index`` provider and passes it in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.ai.museum_question_triage.domain.models import ObjectHitView
from app.collection_object_index.application.ports import (
    CollectionObjectIndexPort,
    CollectionObjectSearchQuery,
)
from app.collection_object_index.application.use_cases import SearchCollectionObjects

if TYPE_CHECKING:
    from app.identity.public import Actor


class ObjectSearchAdapter:
    def __init__(self, index: CollectionObjectIndexPort) -> None:
        self._search = SearchCollectionObjects(index)

    async def search(
        self, caller: Actor, query: str, limit: int
    ) -> list[ObjectHitView]:
        result = await self._search.execute(
            caller,
            CollectionObjectSearchQuery(
                q=query, collection_id=None, page=0, size=limit
            ),
        )
        return [
            ObjectHitView(
                collection_id=str(hit.collection_id),
                collection_name=hit.collection_name,
                file_name=hit.file_name,
                highlight=hit.highlight,
            )
            for hit in result.items
        ]
