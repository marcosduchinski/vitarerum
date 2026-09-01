from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.identity.public import Actor, GroupName
from app.scientific_return.application.full_agentic_ports import (
    KnowledgeCounts,
    KnowledgeFilters,
    KnowledgePage,
)
from app.scientific_return.application.knowledge import (
    ActivateCuratorialKnowledge,
    CreateCuratorialKnowledge,
    CreateKnowledgeInput,
    GetKnowledgeHistory,
    ListCuratorialKnowledge,
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
        self, *, active_only: bool, limit: int, institution_id: str | None = None
    ) -> list[ScientificReturnKnowledgeItem]:
        values = list(self.items.values())
        if institution_id is not None:
            values = [item for item in values if item.institution_id == institution_id]
        if active_only:
            values = [item for item in values if item.status is KnowledgeStatus.ACTIVE]
        return values[:limit]

    async def find_knowledge_exact(
        self,
        registered_number: str,
        limit: int,
        institution_id: str | None = None,
    ) -> list[ScientificReturnKnowledgeItem]:
        return [
            item
            for item in self.items.values()
            if item.status is KnowledgeStatus.ACTIVE
            and item.registered_number == registered_number
            and (institution_id is None or item.institution_id == institution_id)
        ][:limit]

    async def page_knowledge(
        self, filters: KnowledgeFilters, page: int, size: int
    ) -> KnowledgePage:
        institution_items = [
            item
            for item in self.items.values()
            if item.institution_id == filters.institution_id
        ]
        values = list(institution_items)
        if filters.status is not None:
            values = [item for item in values if item.status is filters.status]
        if filters.kind is not None:
            values = [item for item in values if item.kind is filters.kind]
        if filters.inventory_number is not None:
            values = [
                item
                for item in values
                if filters.inventory_number
                in {item.registered_number, item.observed_form}
            ]
        values.sort(key=lambda item: (item.created_at, str(item.id)), reverse=True)
        counts = KnowledgeCounts(
            active=sum(
                item.status is KnowledgeStatus.ACTIVE for item in institution_items
            ),
            proposed=sum(
                item.status is KnowledgeStatus.PROPOSED for item in institution_items
            ),
            retired=sum(
                item.status is KnowledgeStatus.RETIRED for item in institution_items
            ),
        )
        return KnowledgePage(
            content=tuple(values[page * size : page * size + size]),
            page=page,
            size=size,
            total_elements=len(values),
            counts=counts,
        )

    async def list_knowledge_lineage(
        self, item_id: KnowledgeItemId, institution_id: str
    ) -> list[ScientificReturnKnowledgeItem]:
        items = [
            item
            for item in self.items.values()
            if item.institution_id == institution_id
        ]
        by_id = {item.id: item for item in items}
        current = by_id[item_id]
        while current.supersedes_id is not None:
            current = by_id[current.supersedes_id]
        lineage = [current]
        while successor := next(
            (item for item in items if item.supersedes_id == current.id), None
        ):
            lineage.append(successor)
            current = successor
        return lineage


def curator() -> Actor:
    return Actor(
        PermissionId("permission-1"),
        GroupName.CURATORIAL,
        institution_id="institution-1",
    )


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
    assert item.institution_id == "institution-1"
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
        institution_id="institution-1",
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
async def test_reactivating_active_knowledge_keeps_the_original_validation() -> None:
    repository = MemoryRepository()
    proposal = ScientificReturnKnowledgeItem(
        id=KnowledgeItemId("knowledge-proposal-1"),
        kind=KnowledgeKind.CURATORIAL_LESSON,
        content="Proposta do agente",
        status=KnowledgeStatus.PROPOSED,
        institution_id="institution-1",
        created_by=PermissionId("permission-1"),
        created_at=datetime.now(tz=UTC),
    )
    await repository.add_knowledge(proposal)
    validated = await ActivateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        proposal.id, curator()
    )
    first_validation = validated.validated_at

    other_curator = Actor(
        PermissionId("permission-2"),
        GroupName.DIRECTION,
        institution_id="institution-1",
    )
    reactivated = await ActivateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        proposal.id, other_curator
    )

    assert reactivated.status is KnowledgeStatus.ACTIVE
    assert reactivated.validated_by == PermissionId("permission-1")
    assert reactivated.validated_at == first_validation


@pytest.mark.asyncio
async def test_discarded_proposal_stays_unvalidated_and_unretrieved() -> None:
    """A turned-down proposal is retired without ever gaining a validation.

    The absence of ``validated_at`` is what tells a discarded proposal apart
    from knowledge the institution used and later retired.
    """
    repository = MemoryRepository()
    proposal = ScientificReturnKnowledgeItem(
        id=KnowledgeItemId("knowledge-proposal-1"),
        kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
        content="Proposta do agente",
        status=KnowledgeStatus.PROPOSED,
        institution_id="institution-1",
        registered_number="MB06-005747",
        observed_form="MB06-5747",
        created_by=PermissionId("permission-1"),
        created_at=datetime.now(tz=UTC),
    )
    await repository.add_knowledge(proposal)

    discarded = await RetireCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        proposal.id, curator()
    )

    assert discarded.status is KnowledgeStatus.RETIRED
    assert discarded.validated_by is None
    assert discarded.validated_at is None
    assert discarded.retired_by == PermissionId("permission-1")
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


@pytest.mark.asyncio
async def test_knowledge_page_is_scoped_to_the_callers_institution() -> None:
    repository = MemoryRepository()
    own = await CreateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        CreateKnowledgeInput(
            caller=curator(),
            kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
            content="Own example",
            registered_number="MB06-005747",
            observed_form="MB06-5747",
        )
    )
    other_caller = Actor(
        PermissionId("permission-2"),
        GroupName.CURATORIAL,
        institution_id="institution-2",
    )
    await CreateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        CreateKnowledgeInput(
            caller=other_caller,
            kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
            content="Other example",
            registered_number="BOT-0001",
            observed_form="BOT-1",
        )
    )

    page = await ListCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        curator(),
        status=None,
        kind=None,
        inventory_number=None,
        page=0,
        size=25,
    )

    assert page.content == (own,)
    assert page.total_elements == 1
    assert page.counts.active == 1


@pytest.mark.asyncio
async def test_institutional_listing_requires_an_active_institution() -> None:
    repository = MemoryRepository()
    caller = Actor(PermissionId("permission-1"), GroupName.CURATORIAL)

    with pytest.raises(ValueError, match="institutional permission"):
        await ListCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
            caller,
            status=None,
            kind=None,
            inventory_number=None,
            page=0,
            size=25,
        )


@pytest.mark.asyncio
async def test_retrieval_uses_only_active_knowledge_from_the_institution() -> None:
    repository = MemoryRepository()
    for item_id, institution_id, status in (
        ("own-active", "institution-1", KnowledgeStatus.ACTIVE),
        ("other-active", "institution-2", KnowledgeStatus.ACTIVE),
        ("own-retired", "institution-1", KnowledgeStatus.RETIRED),
    ):
        await repository.add_knowledge(
            ScientificReturnKnowledgeItem(
                id=KnowledgeItemId(item_id),
                institution_id=institution_id,
                kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
                content=item_id,
                status=status,
                registered_number="MUHNAC/MB06-005747",
                observed_form="MB06-5747",
                created_by=PermissionId("permission-1"),
                created_at=datetime.now(tz=UTC),
                validated_by=PermissionId("permission-1"),
            )
        )

    selected = await retrieve_relevant_knowledge(  # type: ignore[arg-type]
        repository,
        ("MUHNAC/MB06-005747",),
        limit=10,
        institution_id="institution-1",
    )

    assert [item.id for item in selected] == [KnowledgeItemId("own-active")]


@pytest.mark.asyncio
async def test_mutation_hides_another_institutions_knowledge() -> None:
    repository = MemoryRepository()
    other_caller = Actor(
        PermissionId("permission-2"),
        GroupName.CURATORIAL,
        institution_id="institution-2",
    )
    other = await CreateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        CreateKnowledgeInput(
            caller=other_caller,
            kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
            content="Other example",
            registered_number="BOT-0001",
            observed_form="BOT-1",
        )
    )

    with pytest.raises(LookupError):
        await ActivateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
            other.id, curator()
        )


@pytest.mark.asyncio
async def test_history_returns_the_complete_supersession_chain() -> None:
    repository = MemoryRepository()
    original = await CreateCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        CreateKnowledgeInput(
            caller=curator(),
            kind=KnowledgeKind.INVENTORY_VARIATION_EXAMPLE,
            content="Original",
            registered_number="MB06-005747",
            observed_form="MB06-5747",
        )
    )
    successor = await ReplaceCuratorialKnowledge(repository).execute(  # type: ignore[arg-type]
        original.id,
        ReplaceKnowledgeInput(
            caller=curator(),
            content="Corrected",
            registered_number="MB06-005747",
            observed_form="MB06 5747",
        ),
    )

    history = await GetKnowledgeHistory(repository).execute(  # type: ignore[arg-type]
        successor.id, curator()
    )

    assert [item.id for item in history] == [original.id, successor.id]
