from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import NewType

from app.scientific_return.domain.enums import (
    AgentConfidence,
    AgenticCandidateRelationKind,
    AgenticToolExecutionStatus,
    AgenticTrajectoryEventKind,
    EvidenceSourceField,
    FullAgenticInvestigationStatus,
    GroundedClaimKind,
    GroundingRejectionReason,
    InventoryEvidenceStatus,
    InvestigationObjective,
    KnowledgeKind,
    KnowledgeStatus,
    SearchIntent,
    SearchStrategy,
)
from app.scientific_return.domain.models import (
    CandidateDecisionId,
    CandidatePublicationId,
    ScientificReturnRunId,
    ScientificReturnWatchId,
)
from app.shared.kernel import PermissionId

KnowledgeItemId = NewType("KnowledgeItemId", str)
FullAgenticInvestigationId = NewType("FullAgenticInvestigationId", str)
AgenticTrajectoryEventId = NewType("AgenticTrajectoryEventId", str)
AgenticToolExecutionId = NewType("AgenticToolExecutionId", str)


@dataclass(frozen=True, slots=True)
class AgenticSearchSpec:
    """One concrete, auditable external search attempt."""

    source: str
    query: str
    intent: SearchIntent
    strategy: SearchStrategy
    author: str | None = None
    object_id: str | None = None

    def __post_init__(self) -> None:
        source = self.source.strip().upper()
        query = self.query.strip()
        author = self.author.strip() if self.author else None
        object_id = self.object_id.strip() if self.object_id else None
        if not source:
            raise ValueError("Search source is required")
        if not query:
            raise ValueError("Search query is required")
        if self.strategy is SearchStrategy.AUTHOR_OBJECT and not author:
            raise ValueError("AUTHOR_OBJECT requires an author hypothesis")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "author", author)
        object.__setattr__(self, "object_id", object_id)

    @property
    def identity(self) -> tuple[str, str, str]:
        return (
            self.source,
            " ".join(self.query.casefold().split()),
            " ".join((self.author or "").casefold().split()),
        )


@dataclass(frozen=True, slots=True)
class GroundedInventoryForm:
    observed_form: str
    source_field: EvidenceSourceField
    source_locator: str | None = None


@dataclass(frozen=True, slots=True)
class GroundingRejection:
    """One reader claim the validator refused, kept for auditing.

    ``excerpt`` is the truncated claim the model produced, never publication
    text: a rejected claim is by definition absent from what the source
    delivered.
    """

    claim_kind: GroundedClaimKind
    reason: GroundingRejectionReason
    excerpt: str


@dataclass(slots=True)
class ScientificReturnKnowledgeItem:
    """Curator-owned, immutable knowledge consumed as an LLM example."""

    id: KnowledgeItemId
    kind: KnowledgeKind
    content: str
    status: KnowledgeStatus
    created_by: PermissionId
    created_at: datetime
    institution_id: str | None = None
    registered_number: str | None = None
    observed_form: str | None = None
    source_candidate_id: CandidatePublicationId | None = None
    source_decision_id: CandidateDecisionId | None = None
    supersedes_id: KnowledgeItemId | None = None
    proposed_by_model: str | None = None
    prompt_version: str | None = None
    validated_by: PermissionId | None = None
    validated_at: datetime | None = None
    retired_by: PermissionId | None = None
    retired_at: datetime | None = None

    def __post_init__(self) -> None:
        self.content = self.content.strip()
        self.registered_number = (
            self.registered_number.strip() if self.registered_number else None
        )
        self.observed_form = self.observed_form.strip() if self.observed_form else None
        if not self.content:
            raise ValueError("Knowledge content is required")
        if len(self.content) > 4000:
            raise ValueError("Knowledge content may contain at most 4000 characters")
        if self.kind is KnowledgeKind.INVENTORY_VARIATION_EXAMPLE:
            if not (self.registered_number or "").strip():
                raise ValueError(
                    "registeredNumber is required for an inventory example"
                )
            if not (self.observed_form or "").strip():
                raise ValueError("observedForm is required for an inventory example")
        if self.status is KnowledgeStatus.ACTIVE and self.validated_by is None:
            raise ValueError("Active knowledge requires a curator validation")

    def activate(self, actor: PermissionId, occurred_at: datetime) -> None:
        """Records the validation that promoted a proposal to active knowledge.

        Activating an already active item is a no-op: the validation kept is
        the one that actually let the item reach investigations, so a repeated
        call must not reassign the audit trail to whoever pressed last.
        """
        if self.status is KnowledgeStatus.RETIRED:
            raise ValueError("Retired knowledge cannot be activated")
        if self.status is KnowledgeStatus.ACTIVE:
            return
        self.status = KnowledgeStatus.ACTIVE
        self.validated_by = actor
        self.validated_at = occurred_at

    def retire(self, actor: PermissionId, occurred_at: datetime) -> None:
        if self.status is KnowledgeStatus.RETIRED:
            return
        self.status = KnowledgeStatus.RETIRED
        self.retired_by = actor
        self.retired_at = occurred_at

    def as_prompt_example(self) -> str:
        if self.kind is KnowledgeKind.INVENTORY_VARIATION_EXAMPLE:
            return (
                f'O museu registra o exemplar como "{self.registered_number}"; '
                f'uma publicação o citou como "{self.observed_form}". '
                f"Conhecimento do curador: {self.content}"
            )
        return f"Lição curatorial validada: {self.content}"


@dataclass(frozen=True, slots=True)
class AgenticBudget:
    max_iterations: int
    max_queries: int
    max_results: int
    max_candidates: int
    max_llm_calls: int

    def __post_init__(self) -> None:
        if (
            min(
                self.max_iterations,
                self.max_queries,
                self.max_results,
                self.max_candidates,
                self.max_llm_calls,
            )
            < 1
        ):
            raise ValueError("Every full-agentic budget limit must be positive")


class AgenticBudgetExhausted(RuntimeError):
    """The investigation has no room left for the operation being attempted."""


@dataclass(frozen=True, slots=True)
class AgenticUsage:
    iterations: int = 0
    queries: int = 0
    results: int = 0
    candidates: int = 0
    llm_calls: int = 0


@dataclass(frozen=True, slots=True)
class AgenticTrajectoryEvent:
    id: AgenticTrajectoryEventId
    investigation_id: FullAgenticInvestigationId
    sequence: int
    kind: AgenticTrajectoryEventKind
    payload: dict[str, object]
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("Trajectory sequence starts at one")


@dataclass(slots=True)
class FullAgenticInvestigation:
    id: FullAgenticInvestigationId
    watch_id: ScientificReturnWatchId
    objective: InvestigationObjective
    status: FullAgenticInvestigationStatus
    idempotency_key: str
    budget: AgenticBudget
    usage: AgenticUsage
    created_by: PermissionId
    created_at: datetime
    institution_id: str | None = None
    candidate_id: CandidatePublicationId | None = None
    # Which consulted object this investigation is for. A project may consult
    # several, and the budgets were measured against one: giving each its own
    # investigation keeps those numbers meaningful instead of scaling them by a
    # count nobody has measured.
    object_id: str | None = None
    search_run_id: ScientificReturnRunId | None = None
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    # A completed investigation that could not run its full plan. Kept apart
    # from status because the run did finish and may carry candidates: what a
    # curator needs to know is that absence of results here is not evidence of
    # absence.
    degraded_reason: str | None = None
    cancel_requested_by: PermissionId | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    # How many times a worker took this row over after a lease went cold. Kept
    # on the aggregate because it is what decides whether the work itself is
    # the problem, and that judgement is not the repository's to make.
    recovery_count: int = 0
    last_recovered_at: datetime | None = None
    last_recovery_reason: str | None = None
    version: int = 0
    events: list[AgenticTrajectoryEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.idempotency_key.strip():
            raise ValueError("Idempotency-Key is required")

    def start(self, occurred_at: datetime) -> None:
        if self.status is not FullAgenticInvestigationStatus.QUEUED:
            raise ValueError("Only queued investigations can start")
        self.status = FullAgenticInvestigationStatus.RUNNING
        self.started_at = occurred_at
        self.heartbeat_at = occurred_at

    def heartbeat(self, occurred_at: datetime) -> None:
        if self.status not in {
            FullAgenticInvestigationStatus.RUNNING,
            FullAgenticInvestigationStatus.CANCEL_REQUESTED,
        }:
            raise ValueError("Only live investigations have a heartbeat")
        self.heartbeat_at = occurred_at

    def request_cancel(self, actor: PermissionId, occurred_at: datetime) -> None:
        if self.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED:
            return
        if self.status is FullAgenticInvestigationStatus.QUEUED:
            self.status = FullAgenticInvestigationStatus.CANCELLED
            self.cancel_requested_by = actor
            self.completed_at = occurred_at
            return
        if self.status is FullAgenticInvestigationStatus.RUNNING:
            self.status = FullAgenticInvestigationStatus.CANCEL_REQUESTED
            self.cancel_requested_by = actor
            return
        if not self.status.is_terminal:
            raise ValueError("Investigation cannot be cancelled in its current state")

    def cancel(self, occurred_at: datetime) -> None:
        if self.status is not FullAgenticInvestigationStatus.CANCEL_REQUESTED:
            raise ValueError("Cancellation was not requested")
        self.status = FullAgenticInvestigationStatus.CANCELLED
        self.completed_at = occurred_at

    def complete(self, occurred_at: datetime) -> None:
        if self.status is not FullAgenticInvestigationStatus.RUNNING:
            raise ValueError("Only a running investigation can complete")
        self.status = FullAgenticInvestigationStatus.COMPLETED
        self.completed_at = occurred_at

    def degrade(self, reason: str) -> None:
        """Record that part of the plan could not be produced.

        The first reason is kept: it is the one that explains what the run
        stopped being able to do.
        """
        if self.degraded_reason is None:
            self.degraded_reason = reason[:500]

    def fail(self, reason: str, occurred_at: datetime) -> None:
        if self.status.is_terminal:
            raise ValueError("A terminal investigation cannot fail again")
        self.status = FullAgenticInvestigationStatus.FAILED
        self.failure_reason = reason[:2000]
        self.completed_at = occurred_at

    def yield_slice(self, reason: str, occurred_at: datetime) -> None:
        """Hand the investigation back to the queue, still unfinished.

        A voluntary stop is not an abandonment: the row returns to QUEUED with
        no lease, so the next claim reads as a first claim rather than as a
        recovery from a dead worker. Counting it as a recovery would spend the
        recovery allowance on healthy long work and terminate it.
        """
        if self.status is not FullAgenticInvestigationStatus.RUNNING:
            raise ValueError("Only a running investigation can yield its slice")
        self.status = FullAgenticInvestigationStatus.QUEUED
        self.lease_owner = None
        self.lease_expires_at = None
        self.heartbeat_at = occurred_at
        self.last_recovery_reason = reason[:200]

    def record_recovery(self, occurred_at: datetime, reason: str) -> None:
        """Note that this run picked up work a previous worker did not finish."""
        self.recovery_count += 1
        self.last_recovered_at = occurred_at
        self.last_recovery_reason = reason[:200]

    def recoveries_exhausted(self, ceiling: int) -> bool:
        return self.recovery_count > ceiling

    def reserve_llm_call(self) -> None:
        """Spend one model call from the budget before the call is made.

        Reserving up front is what makes the ceiling mean anything. Counting
        afterwards only records calls that came back, so a worker killed mid
        call — by the platform's window, by a hang, by an out-of-memory kill —
        would resume with the budget untouched and repeat exactly the same work,
        forever. Charging first turns any such death into progress towards the
        end of the investigation.
        """
        if self.usage.llm_calls >= self.budget.max_llm_calls:
            raise AgenticBudgetExhausted(
                f"The model-call budget of {self.budget.max_llm_calls} is spent"
            )
        self.usage = replace(self.usage, llm_calls=self.usage.llm_calls + 1)

    def spend_query(self, results: int) -> None:
        """Charge one external query and the records it returned."""
        self.usage = replace(
            self.usage,
            queries=self.usage.queries + 1,
            results=self.usage.results + max(0, results),
        )


@dataclass(frozen=True, slots=True)
class ArticleAssessment:
    relevant: bool
    confidence: AgentConfidence
    explanation: str
    passages: tuple[str, ...]
    inventory_forms: tuple[str, ...]
    contradictions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GroundedArticleAssessment:
    assessment: ArticleAssessment
    passages: tuple[str, ...]
    inventory_forms: tuple[GroundedInventoryForm, ...]
    inventory_evidence_status: InventoryEvidenceStatus
    rejected_passages: int
    rejected_inventory_forms: int
    rejections: tuple[GroundingRejection, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateDecisionContext:
    version: int
    passages: tuple[str, ...]
    inventory_forms: tuple[str, ...]
    queries: tuple[str, ...]
    sources: tuple[str, ...]
    explanation: str
    confidence: AgentConfidence
    contradictions: tuple[str, ...]
    knowledge_item_ids: tuple[KnowledgeItemId, ...]
    discovery_basis: str | None = None
    search_intent: str | None = None
    search_strategy: str | None = None
    inventory_evidence_status: InventoryEvidenceStatus | None = None
    grounded_inventory_forms: tuple[GroundedInventoryForm, ...] = ()
    # Part of what the curator saw: how many consulted objects this publication
    # was found for. Kept in the snapshot so a confirmation can be read back
    # years later with the same context that produced it.
    cited_object_count: int = 0


@dataclass(frozen=True, slots=True)
class AgenticCandidateLink:
    investigation_id: FullAgenticInvestigationId
    candidate_id: CandidatePublicationId
    relation_kind: AgenticCandidateRelationKind
    rank: int
    linked_at: datetime


@dataclass(slots=True)
class AgenticToolExecution:
    id: AgenticToolExecutionId
    investigation_id: FullAgenticInvestigationId
    trajectory_sequence: int
    idempotency_key: str
    status: AgenticToolExecutionStatus
    invocation: dict[str, object]
    started_at: datetime
    attempts: int = 1
    result: dict[str, object] | None = None
    result_hash: str | None = None
    completed_at: datetime | None = None
    lease_expires_at: datetime | None = None
    error_message: str | None = None
