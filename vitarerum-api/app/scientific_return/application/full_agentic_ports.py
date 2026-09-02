from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.scientific_return.application.ports import (
    BibliographicRecord,
    InvestigationConcurrencyConflict,
)
from app.scientific_return.domain.enums import KnowledgeKind, KnowledgeStatus
from app.scientific_return.domain.full_agentic_models import (
    AgenticCandidateLink,
    AgenticSearchSpec,
    AgenticToolExecution,
    AgenticTrajectoryEvent,
    ArticleAssessment,
    FullAgenticInvestigation,
    FullAgenticInvestigationId,
    KnowledgeItemId,
    ScientificReturnKnowledgeItem,
)


@dataclass(frozen=True, slots=True)
class KnowledgeFilters:
    institution_id: str
    status: KnowledgeStatus | None = None
    kind: KnowledgeKind | None = None
    # Free text: an inventory citation, or any words of the lesson content.
    search: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeCounts:
    active: int = 0
    proposed: int = 0
    retired: int = 0


@dataclass(frozen=True, slots=True)
class KnowledgePage:
    content: tuple[ScientificReturnKnowledgeItem, ...]
    page: int
    size: int
    total_elements: int
    counts: KnowledgeCounts


@dataclass(frozen=True, slots=True)
class AgenticPlan:
    searches: tuple[AgenticSearchSpec, ...]
    reasoning: str
    should_stop: bool = False
    # Absent when no model produced the plan, as on the deterministic floor.
    prompt_version_id: str | None = None
    prompt_version: str | None = None


@dataclass(frozen=True, slots=True)
class AssessmentResult:
    assessment: ArticleAssessment
    prompt_version_id: str
    prompt_version: str


@dataclass(frozen=True, slots=True)
class LearningProposal:
    content: str
    registered_number: str | None
    observed_form: str | None


class FullAgenticReasoner(Protocol):
    @property
    def model_name(self) -> str: ...

    async def plan(
        self,
        *,
        observation: dict[str, object],
        memory: tuple[str, ...],
        history: tuple[dict[str, object], ...],
        source_capabilities: tuple[dict[str, object], ...],
        remaining_queries: int,
    ) -> AgenticPlan: ...

    async def assess(
        self,
        *,
        record: BibliographicRecord,
        trusted_context: dict[str, object],
    ) -> AssessmentResult: ...

    async def learn(
        self,
        *,
        decision: str,
        explanation: str,
        context: dict[str, object],
    ) -> LearningProposal: ...


class FullAgenticRepository(Protocol):
    async def add_knowledge(self, item: ScientificReturnKnowledgeItem) -> None: ...
    async def save_knowledge(self, item: ScientificReturnKnowledgeItem) -> None: ...
    async def get_knowledge(
        self, item_id: KnowledgeItemId
    ) -> ScientificReturnKnowledgeItem | None: ...
    async def list_knowledge(
        self, *, active_only: bool, limit: int, institution_id: str | None = None
    ) -> list[ScientificReturnKnowledgeItem]: ...
    async def find_knowledge_exact(
        self,
        registered_number: str,
        limit: int,
        institution_id: str | None = None,
    ) -> list[ScientificReturnKnowledgeItem]: ...
    async def page_knowledge(
        self, filters: KnowledgeFilters, page: int, size: int
    ) -> KnowledgePage: ...
    async def list_knowledge_lineage(
        self, item_id: KnowledgeItemId, institution_id: str
    ) -> list[ScientificReturnKnowledgeItem]: ...

    async def add_investigation(
        self, investigation: FullAgenticInvestigation
    ) -> None: ...
    async def save_investigation(
        self, investigation: FullAgenticInvestigation
    ) -> None: ...
    async def claim_investigation(
        self,
        investigation_id: FullAgenticInvestigationId,
        worker_id: str,
        claimed_at: datetime,
        lease_expires_at: datetime,
    ) -> FullAgenticInvestigation | None: ...
    async def renew_investigation_lease(
        self,
        investigation_id: FullAgenticInvestigationId,
        worker_id: str,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> int | None: ...
    async def reserve_llm_call(
        self,
        investigation: FullAgenticInvestigation,
        worker_id: str,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> int | None: ...
    async def get_investigation(
        self, investigation_id: FullAgenticInvestigationId
    ) -> FullAgenticInvestigation | None: ...
    async def get_by_idempotency_key(
        self, key: str
    ) -> FullAgenticInvestigation | None: ...
    async def find_live_target(
        self,
        watch_id: str,
        objective: str,
        candidate_id: str | None,
        object_id: str | None = None,
    ) -> FullAgenticInvestigation | None: ...
    async def list_investigations(
        self, watch_id: str, limit: int
    ) -> list[FullAgenticInvestigation]: ...
    async def list_abandoned(
        self, created_before: datetime, limit: int
    ) -> list[FullAgenticInvestigation]: ...
    async def append_event(self, event: AgenticTrajectoryEvent) -> None: ...
    async def list_events(
        self, investigation_id: FullAgenticInvestigationId
    ) -> list[AgenticTrajectoryEvent]: ...
    async def next_event_sequence(
        self, investigation_id: FullAgenticInvestigationId
    ) -> int: ...
    async def add_knowledge_usage(
        self,
        investigation_id: str,
        knowledge_item_id: str,
        prompt_step: str,
        used_at: datetime,
    ) -> None: ...
    async def link_candidate(self, link: AgenticCandidateLink) -> bool: ...
    async def add_tool_execution(self, execution: AgenticToolExecution) -> None: ...
    async def save_tool_execution(self, execution: AgenticToolExecution) -> None: ...
    async def get_tool_execution(self, key: str) -> AgenticToolExecution | None: ...


class AgenticInvestigationDispatcher(Protocol):
    async def enqueue(self, investigation_id: FullAgenticInvestigationId) -> None: ...


class FullAgenticUnitOfWork(Protocol):
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class FullAgenticClock(Protocol):
    def now(self) -> datetime: ...


__all__ = ["InvestigationConcurrencyConflict"]  # noqa: F822 re-export
