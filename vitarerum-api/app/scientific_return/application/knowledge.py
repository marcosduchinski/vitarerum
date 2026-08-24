from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.identity.public import Actor, GroupName
from app.scientific_return.application.full_agentic_ports import (
    FullAgenticReasoner,
    FullAgenticRepository,
)
from app.scientific_return.domain.enums import KnowledgeKind, KnowledgeStatus
from app.scientific_return.domain.full_agentic_models import (
    KnowledgeItemId,
    ScientificReturnKnowledgeItem,
)
from app.scientific_return.domain.models import CandidateDecision
from app.shared.authorization import require_group, require_staff

_CURATOR_GROUPS = (
    GroupName.CURATORIAL,
    GroupName.COLLECTIONS_MANAGEMENT,
    GroupName.DIRECTION,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True, slots=True)
class CreateKnowledgeInput:
    caller: Actor
    kind: KnowledgeKind
    content: str
    registered_number: str | None = None
    observed_form: str | None = None
    institution_id: str | None = None


class CreateCuratorialKnowledge:
    def __init__(self, repository: FullAgenticRepository) -> None:
        self._repository = repository

    async def execute(
        self, data: CreateKnowledgeInput
    ) -> ScientificReturnKnowledgeItem:
        require_group(data.caller, *_CURATOR_GROUPS)
        occurred_at = _now()
        item = ScientificReturnKnowledgeItem(
            id=KnowledgeItemId(str(uuid4())),
            kind=data.kind,
            content=data.content,
            status=KnowledgeStatus.ACTIVE,
            institution_id=data.institution_id,
            registered_number=data.registered_number,
            observed_form=data.observed_form,
            created_by=data.caller.id,
            created_at=occurred_at,
            validated_by=data.caller.id,
            validated_at=occurred_at,
        )
        await self._repository.add_knowledge(item)
        return item


class ListCuratorialKnowledge:
    def __init__(self, repository: FullAgenticRepository) -> None:
        self._repository = repository

    async def execute(
        self, caller: Actor, *, active_only: bool, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        require_staff(caller)
        return await self._repository.list_knowledge(
            active_only=active_only, limit=limit
        )


class RetireCuratorialKnowledge:
    def __init__(self, repository: FullAgenticRepository) -> None:
        self._repository = repository

    async def execute(
        self, item_id: KnowledgeItemId, caller: Actor
    ) -> ScientificReturnKnowledgeItem:
        require_group(caller, *_CURATOR_GROUPS)
        item = await self._repository.get_knowledge(item_id)
        if item is None:
            raise LookupError(f"Knowledge item {item_id} not found")
        item.retire(caller.id, _now())
        await self._repository.save_knowledge(item)
        return item


class ActivateCuratorialKnowledge:
    def __init__(self, repository: FullAgenticRepository) -> None:
        self._repository = repository

    async def execute(
        self, item_id: KnowledgeItemId, caller: Actor
    ) -> ScientificReturnKnowledgeItem:
        require_group(caller, *_CURATOR_GROUPS)
        item = await self._repository.get_knowledge(item_id)
        if item is None:
            raise LookupError(f"Knowledge item {item_id} not found")
        item.activate(caller.id, _now())
        await self._repository.save_knowledge(item)
        return item


class ProposeKnowledgeFromDecision:
    def __init__(
        self,
        repository: FullAgenticRepository,
        reasoner: FullAgenticReasoner,
    ) -> None:
        self._repository = repository
        self._reasoner = reasoner

    async def execute(
        self, decision: CandidateDecision, explanation: str, caller: Actor
    ) -> ScientificReturnKnowledgeItem:
        require_group(caller, *_CURATOR_GROUPS)
        if not explanation.strip():
            raise ValueError("A curator explanation is required for learning")
        context = decision.decision_context
        proposal = await self._reasoner.learn(
            decision=decision.decision.value,
            explanation=explanation,
            context=(
                {
                    "inventoryForms": list(context.inventory_forms),
                    "queries": list(context.queries),
                    "sources": list(context.sources),
                    "explanation": context.explanation,
                    "contradictions": list(context.contradictions),
                }
                if context is not None
                else {}
            ),
        )
        kind = (
            KnowledgeKind.INVENTORY_VARIATION_EXAMPLE
            if proposal.registered_number and proposal.observed_form
            else KnowledgeKind.CURATORIAL_LESSON
        )
        item = ScientificReturnKnowledgeItem(
            id=KnowledgeItemId(str(uuid4())),
            kind=kind,
            content=proposal.content,
            status=KnowledgeStatus.PROPOSED,
            registered_number=proposal.registered_number,
            observed_form=proposal.observed_form,
            source_candidate_id=decision.candidate_id,
            source_decision_id=decision.id,
            proposed_by_model=self._reasoner.model_name,
            prompt_version="scientific-return-full-agentic-learning-v1",
            created_by=caller.id,
            created_at=_now(),
        )
        await self._repository.add_knowledge(item)
        return item


@dataclass(frozen=True, slots=True)
class ReplaceKnowledgeInput:
    caller: Actor
    content: str
    registered_number: str | None
    observed_form: str | None


class ReplaceCuratorialKnowledge:
    """Preserves history: correction creates a successor and retires the old item."""

    def __init__(self, repository: FullAgenticRepository) -> None:
        self._repository = repository

    async def execute(
        self, item_id: KnowledgeItemId, data: ReplaceKnowledgeInput
    ) -> ScientificReturnKnowledgeItem:
        require_group(data.caller, *_CURATOR_GROUPS)
        previous = await self._repository.get_knowledge(item_id)
        if previous is None:
            raise LookupError(f"Knowledge item {item_id} not found")
        occurred_at = _now()
        successor = ScientificReturnKnowledgeItem(
            id=KnowledgeItemId(str(uuid4())),
            kind=previous.kind,
            content=data.content,
            status=KnowledgeStatus.ACTIVE,
            institution_id=previous.institution_id,
            registered_number=data.registered_number,
            observed_form=data.observed_form,
            source_candidate_id=previous.source_candidate_id,
            source_decision_id=previous.source_decision_id,
            supersedes_id=previous.id,
            created_by=data.caller.id,
            created_at=occurred_at,
            validated_by=data.caller.id,
            validated_at=occurred_at,
        )
        previous.retire(data.caller.id, occurred_at)
        await self._repository.save_knowledge(previous)
        await self._repository.add_knowledge(successor)
        return successor


async def retrieve_relevant_knowledge(
    repository: FullAgenticRepository,
    inventory_numbers: tuple[str, ...],
    *,
    limit: int,
) -> tuple[ScientificReturnKnowledgeItem, ...]:
    """Exact matches first, then structurally similar examples within one cap."""
    if limit <= 0:
        return ()
    selected: dict[str, ScientificReturnKnowledgeItem] = {}
    for inventory_number in inventory_numbers:
        for item in await repository.find_knowledge_exact(inventory_number, limit):
            selected[str(item.id)] = item
            if len(selected) >= limit:
                return tuple(selected.values())
    if len(selected) < limit:
        corpus = await repository.list_knowledge(
            active_only=True,
            limit=max(limit, limit * 4),
        )
        corpus.sort(
            key=lambda item: _knowledge_relevance(item, inventory_numbers),
            reverse=True,
        )
        for item in corpus:
            selected.setdefault(str(item.id), item)
            if len(selected) >= limit:
                break
    return tuple(selected.values())


def _knowledge_relevance(
    item: ScientificReturnKnowledgeItem,
    inventory_numbers: tuple[str, ...],
) -> tuple[int, int, int]:
    candidate = item.registered_number or item.observed_form or ""
    candidate_letters, candidate_widths, candidate_separators = _inventory_shape(
        candidate
    )
    best = (0, 0, 0)
    for inventory_number in inventory_numbers:
        letters, widths, separators = _inventory_shape(inventory_number)
        score = (
            int(bool(candidate_letters) and candidate_letters == letters),
            sum(
                left == right
                for left, right in zip(candidate_widths, widths, strict=False)
            ),
            int(bool(candidate_separators) and candidate_separators == separators),
        )
        best = max(best, score)
    return best


def _inventory_shape(value: str) -> tuple[str, tuple[int, ...], str]:
    upper = value.upper().strip()
    letters = "".join(re.findall(r"[A-Z]+", upper))
    widths = tuple(len(part) for part in re.findall(r"\d+", upper))
    separators = "".join(re.findall(r"[^A-Z0-9\s]", upper))
    return letters, widths, separators
