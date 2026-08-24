from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.identity.public import Actor, GroupName
from app.scientific_return.application.knowledge import (
    CreateCuratorialKnowledge,
    CreateKnowledgeInput,
    ReplaceCuratorialKnowledge,
    ReplaceKnowledgeInput,
    RetireCuratorialKnowledge,
    retrieve_relevant_knowledge,
)
from app.scientific_return.domain.enums import KnowledgeKind, KnowledgeStatus
from app.scientific_return.domain.full_agentic_models import (
    KnowledgeItemId,
    ScientificReturnKnowledgeItem,
)
from app.shared.kernel import PermissionId


class MemoryRepository:
    def __init__(self) -> None:
        self.items: dict[str, ScientificReturnKnowledgeItem] = {}

    async def add_knowledge(self, item: ScientificReturnKnowledgeItem) -> None:
        self.items[str(item.id)] = item

    async def save_knowledge(self, item: ScientificReturnKnowledgeItem) -> None:
        self.items[str(item.id)] = item

    async def get_knowledge(
        self, item_id: KnowledgeItemId
    ) -> ScientificReturnKnowledgeItem | None:
        return self.items.get(str(item_id))

    async def list_knowledge(
        self, *, active_only: bool, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        values = list(self.items.values())
        if active_only:
            values = [item for item in values if item.status is KnowledgeStatus.ACTIVE]
        return values[:limit]

    async def find_knowledge_exact(
        self, registered_number: str, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        return [
            item
            for item in self.items.values()
            if item.status is KnowledgeStatus.ACTIVE
            and item.registered_number == registered_number
        ][:limit]


def curator() -> Actor:
    return Actor(PermissionId("permission-1"), GroupName.CURATORIAL)


@pytest.mark.asyncio
async def test_curator_creates_active_textual_inventory_example() -> None:
    repository = MemoryRepository()
    item = await CreateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        CreateKnowledgeInput(
            caller=curator(),
            kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
            content="Zeros internos podem ser omitidos na citação.",
            registered_number="MUHNAC/MB06-005747",
            observed_form="MB06-5747",
        )
    )

    assert item.status is KnowledgeStatus.ACTIVE
    assert item.validated_by == PermissionId("permission-1")
    assert 'registra o exemplar como "MUHNAC/MB06-005747"' in item.as_prompt_example()


@pytest.mark.asyncio
async def test_replacement_retires_previous_and_preserves_supersession() -> None:
    repository = MemoryRepository()
    original = await CreateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        CreateKnowledgeInput(
            caller=curator(),
            kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
            content="Exemplo inicial",
            registered_number="MB06-005747",
            observed_form="MB06-5747",
        )
    )

    successor = await ReplaceCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        original.id,
        ReplaceKnowledgeInput(
            caller=curator(),
            content="Exemplo corrigido",
            registered_number="MB06-005747",
            observed_form="MB06 5747",
        ),
    )

    assert original.status is KnowledgeStatus.RETIRED
    assert successor.status is KnowledgeStatus.ACTIVE
    assert successor.supersedes_id == original.id


@pytest.mark.asyncio
async def test_retired_memory_is_not_retrieved() -> None:
    repository = MemoryRepository()
    item = ScientificReturnKnowledgeItem(
        id=KnowledgeItemId("knowledge-1"),
        kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
        content="Exemplo",
        status=KnowledgeStatus.ACTIVE,
        registered_number="MB06-005747",
        observed_form="MB06-5747",
        created_by=PermissionId("permission-1"),
        created_at=datetime.now(tz=UTC),
        validated_by=PermissionId("permission-1"),
    )
    await repository.add_knowledge(item)
    await RetireCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        item.id, curator()
    )

    selected = await retrieve_relevant_knowledge(  # type: ignore[arg-type]
        repository, ("MB06-005747",), limit=10
    )
    assert selected == ()


@pytest.mark.asyncio
async def test_memory_limit_is_global_across_multiple_objects() -> None:
    repository = MemoryRepository()
    for index in range(5):
        await repository.add_knowledge(
            ScientificReturnKnowledgeItem(
                id=KnowledgeItemId(f"knowledge-{index}"),
                kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
                content=f"Example {index}",
                status=KnowledgeStatus.ACTIVE,
                registered_number=f"MB0{index}-00000{index}",
                observed_form=f"MB0{index}-{index}",
                created_by=PermissionId("permission-1"),
                created_at=datetime.now(tz=UTC),
                validated_by=PermissionId("permission-1"),
            )
        )

    selected = await retrieve_relevant_knowledge(  # type: ignore[arg-type]
        repository,
        tuple(f"MB0{index}-00000{index}" for index in range(5)),
        limit=2,
    )

    assert len(selected) == 2


@pytest.mark.asyncio
async def test_structurally_similar_memory_precedes_unrelated_recent_item() -> None:
    repository = MemoryRepository()
    unrelated = ScientificReturnKnowledgeItem(
        id=KnowledgeItemId("unrelated"),
        kind=KnowledgeKind.CURATORIAL_LESSON,
        content="Unrelated lesson",
        status=KnowledgeStatus.ACTIVE,
        registered_number="HERB:ABC-12",
        created_by=PermissionId("permission-1"),
        created_at=datetime.now(tz=UTC),
        validated_by=PermissionId("permission-1"),
    )
    similar = ScientificReturnKnowledgeItem(
        id=KnowledgeItemId("similar"),
        kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
        content="Same collection-number structure",
        status=KnowledgeStatus.ACTIVE,
        registered_number="MUHNAC/MB04-001066",
        observed_form="MB04-1066",
        created_by=PermissionId("permission-1"),
        created_at=datetime.now(tz=UTC),
        validated_by=PermissionId("permission-1"),
    )
    await repository.add_knowledge(unrelated)
    await repository.add_knowledge(similar)

    selected = await retrieve_relevant_knowledge(  # type: ignore[arg-type]
        repository, ("MUHNAC/MB06-005747",), limit=1
    )

    assert selected[0].id == similar.id
