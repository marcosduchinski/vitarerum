"""Value Objects of the agentic investigation cycle.

These types are the stable contract the plan asks to freeze early: the shape of
an observation, of a proposed action, of a policy decision, of a budget, of an
evidence delta and of a reflection. Sources, prompts, models, limits and
heuristics stay replaceable behind them.

Nothing here decides anything. Authorisation lives in ``AgentActionPolicy`` and
termination in ``AgentStopPolicy``; this module only makes an invalid contract
unrepresentable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.scientific_return.domain.enums import (
    AgentProgress,
    AgentRecommendedAction,
    EvidenceType,
    InvestigationObjective,
    PolicyRejectionReason,
    StopReason,
)

MAX_SUMMARY_LENGTH = 2000
MAX_LIST_ITEMS = 20
MAX_ITEM_LENGTH = 1000

_ACTIONS_REQUIRING_OBJECT = frozenset(
    {
        AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,
        AgentRecommendedAction.SEARCH_AUTHOR_VARIANTS,
        AgentRecommendedAction.SEARCH_TAXON_VARIANTS,
        AgentRecommendedAction.SEARCH_FULL_TEXT,
    }
)
_TERMINATING_ACTIONS = frozenset(
    {
        AgentRecommendedAction.PRESENT_FOR_REVIEW,
        AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE,
        AgentRecommendedAction.DEPRIORITIZE,
    }
)


def _require_text(value: str, label: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{label} is required")
    if len(text) > MAX_SUMMARY_LENGTH:
        raise ValueError(f"{label} is longer than {MAX_SUMMARY_LENGTH} characters")
    return text


def _require_items(values: tuple[str, ...], label: str) -> None:
    if len(values) > MAX_LIST_ITEMS:
        raise ValueError(f"{label} has more than {MAX_LIST_ITEMS} items")
    if any(len(item) > MAX_ITEM_LENGTH for item in values):
        raise ValueError(f"{label} contains an oversized item")


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    """Limits and consumption of one investigation.

    Consumption is reserved before an external call, never after, so a crash
    between the reservation and the call can only under-spend the budget.
    """

    max_iterations: int
    max_actions: int
    max_queries: int
    max_results_per_query: int
    max_new_candidates: int
    used_iterations: int = 0
    used_actions: int = 0
    used_queries: int = 0
    created_candidates: int = 0

    def __post_init__(self) -> None:
        limits = {
            "maxIterations": self.max_iterations,
            "maxActions": self.max_actions,
            "maxQueries": self.max_queries,
            "maxResultsPerQuery": self.max_results_per_query,
            "maxNewCandidates": self.max_new_candidates,
        }
        for label, value in limits.items():
            if value < 1:
                raise ValueError(f"{label} must be at least 1")
        used = {
            "usedIterations": (self.used_iterations, self.max_iterations),
            "usedActions": (self.used_actions, self.max_actions),
            "usedQueries": (self.used_queries, self.max_queries),
            "createdCandidates": (self.created_candidates, self.max_new_candidates),
        }
        for label, (value, limit) in used.items():
            if value < 0:
                raise ValueError(f"{label} cannot be negative")
            if value > limit:
                raise ValueError(f"{label} exceeds its limit")

    @property
    def remaining_iterations(self) -> int:
        return self.max_iterations - self.used_iterations

    @property
    def remaining_actions(self) -> int:
        return self.max_actions - self.used_actions

    @property
    def remaining_queries(self) -> int:
        return self.max_queries - self.used_queries

    @property
    def remaining_candidates(self) -> int:
        return self.max_new_candidates - self.created_candidates

    def exhaustion(self) -> StopReason | None:
        """Whether another *iteration* may be opened.

        Distinct from ``action_exhaustion``: once an iteration is open, having
        no iterations left is the normal state, not a reason to refuse the work
        that iteration exists to do.
        """
        if self.remaining_iterations <= 0:
            return StopReason.ITERATION_LIMIT_REACHED
        return self.action_exhaustion()

    def action_exhaustion(self) -> StopReason | None:
        """Whether another *action* may run inside the current iteration."""
        if self.remaining_candidates <= 0:
            return StopReason.CANDIDATE_LIMIT_REACHED
        if self.remaining_actions <= 0 or self.remaining_queries <= 0:
            return StopReason.BUDGET_EXHAUSTED
        return None

    def reserve_iteration(self) -> ExecutionBudget:
        return self._with(used_iterations=self.used_iterations + 1)

    def reserve_action(self, queries: int) -> ExecutionBudget:
        if queries < 1:
            raise ValueError("An action must reserve at least one query")
        return self._with(
            used_actions=self.used_actions + 1,
            used_queries=self.used_queries + queries,
        )

    def record_candidates(self, count: int) -> ExecutionBudget:
        if count < 0:
            raise ValueError("Created candidates cannot be negative")
        return self._with(created_candidates=self.created_candidates + count)

    def _with(self, **changes: int) -> ExecutionBudget:
        return ExecutionBudget(
            max_iterations=self.max_iterations,
            max_actions=self.max_actions,
            max_queries=self.max_queries,
            max_results_per_query=self.max_results_per_query,
            max_new_candidates=self.max_new_candidates,
            used_iterations=changes.get("used_iterations", self.used_iterations),
            used_actions=changes.get("used_actions", self.used_actions),
            used_queries=changes.get("used_queries", self.used_queries),
            created_candidates=changes.get(
                "created_candidates", self.created_candidates
            ),
        )


@dataclass(frozen=True, slots=True)
class ObservedObject:
    object_id: str
    inventory_number: str
    object_name: str


@dataclass(frozen=True, slots=True)
class ObservedCandidate:
    """The candidate under enrichment, as facts already verified by the system.

    Title and abstract come from an external source and are untrusted data. They
    are carried because the model needs them to reason, never as instructions.
    """

    candidate_id: str
    title: str
    doi: str | None
    verified_evidence_types: tuple[EvidenceType, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True, slots=True)
class AgentObservation:
    """The factual state offered to the reasoner at the start of an iteration.

    Only allowed, already-factualised data appears here: there is no free-form
    channel through which the model could receive an instruction.
    """

    objective: InvestigationObjective
    project_reference: str
    researcher: str
    objects: tuple[ObservedObject, ...]
    tried_queries: tuple[str, ...]
    allowed_actions: tuple[AgentRecommendedAction, ...]
    budget: ExecutionBudget
    candidate: ObservedCandidate | None = None

    def __post_init__(self) -> None:
        if not self.objects:
            raise ValueError("An observation needs at least one consulted object")
        if not self.allowed_actions:
            raise ValueError("An observation needs at least one allowed action")
        if (
            self.objective is InvestigationObjective.ENRICH_CANDIDATE
            and self.candidate is None
        ):
            raise ValueError("Enrichment requires the candidate under investigation")
        if (
            self.objective is InvestigationObjective.DISCOVER_CANDIDATE
            and self.candidate is not None
        ):
            raise ValueError("Discovery starts without a candidate")


@dataclass(frozen=True, slots=True)
class ProposedAction:
    """A typed action the model asks for.

    The model supplies an action type and, at most, which consulted object it
    concerns. It never supplies a query, a source, a URL or an inventory string:
    those are derived by the system, which is what makes an invented argument
    impossible rather than merely unlikely.
    """

    type: AgentRecommendedAction
    object_id: str | None = None

    def __post_init__(self) -> None:
        if self.type in _ACTIONS_REQUIRING_OBJECT and not self.object_id:
            raise ValueError(f"{self.type.value} requires an objectId")
        if self.type in _TERMINATING_ACTIONS and self.object_id:
            raise ValueError(f"{self.type.value} takes no arguments")

    @property
    def contacts_a_source(self) -> bool:
        return self.type in _ACTIONS_REQUIRING_OBJECT


@dataclass(frozen=True, slots=True)
class AgentPlan:
    objective: str
    action: ProposedAction
    reasoning_summary: str
    expected_evidence: tuple[EvidenceType, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_text(self.objective, "The plan objective")
        _require_text(self.reasoning_summary, "The plan reasoningSummary")
        if len(self.expected_evidence) > MAX_LIST_ITEMS:
            raise ValueError("expectedEvidence has too many items")


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """The deterministic verdict on a proposed action.

    An authorised decision carries no rejection reason and a rejected one always
    does, so "rejected but the reason was lost" cannot be represented.
    """

    authorized: bool
    justification: str
    rejection_reason: PolicyRejectionReason | None = None

    def __post_init__(self) -> None:
        _require_text(self.justification, "The policy justification")
        if self.authorized and self.rejection_reason is not None:
            raise ValueError("An authorized decision cannot carry a rejection reason")
        if not self.authorized and self.rejection_reason is None:
            raise ValueError("A rejected decision must carry a typed reason")

    @classmethod
    def authorize(cls, justification: str) -> PolicyDecision:
        return cls(authorized=True, justification=justification)

    @classmethod
    def reject(
        cls, reason: PolicyRejectionReason, justification: str
    ) -> PolicyDecision:
        return cls(
            authorized=False,
            justification=justification,
            rejection_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class ToolResultSummary:
    """Normalised outcome of one tool execution."""

    executed_queries: tuple[str, ...]
    sources: tuple[str, ...]
    total_results: int
    created_candidate_ids: tuple[str, ...] = field(default_factory=tuple)
    added_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    result_hash: str = ""

    def __post_init__(self) -> None:
        if self.total_results < 0:
            raise ValueError("totalResults cannot be negative")
        if not self.executed_queries:
            raise ValueError("A tool execution must record the queries it issued")

    @property
    def found_nothing(self) -> bool:
        return self.total_results == 0


@dataclass(frozen=True, slots=True)
class EvidenceDelta:
    """Difference between verified evidence before and after a tool ran.

    Computed from the deterministic evidence rules, never from what the model
    claims to have found.
    """

    added: tuple[EvidenceType, ...] = field(default_factory=tuple)
    preserved: tuple[EvidenceType, ...] = field(default_factory=tuple)
    removed: tuple[EvidenceType, ...] = field(default_factory=tuple)

    @property
    def has_new_evidence(self) -> bool:
        return bool(self.added)

    @property
    def has_primary_inventory_evidence(self) -> bool:
        return bool(set(self.added) & _PRIMARY_INVENTORY_EVIDENCE)


_PRIMARY_INVENTORY_EVIDENCE = frozenset(
    {
        EvidenceType.INVENTORY_NUMBER,
        EvidenceType.AUTHOR_INVENTORY,
        EvidenceType.INVENTORY_OBJECT,
    }
)


@dataclass(frozen=True, slots=True)
class ReasonerTelemetry:
    """Which model and prompt produced an iteration, and what they cost.

    Persisted with the trajectory: a reviewer weighing a proposal needs to know
    what produced it, and a promotion gate needs latency attributable to a run.
    """

    model: str = ""
    prompt_version: str = ""
    plan_latency_ms: int = 0
    reflection_latency_ms: int = 0
    plan_response_hash: str = ""
    reflection_response_hash: str = ""

    def with_reflection(
        self, latency_ms: int, response_hash: str
    ) -> ReasonerTelemetry:
        return ReasonerTelemetry(
            model=self.model,
            prompt_version=self.prompt_version,
            plan_latency_ms=self.plan_latency_ms,
            reflection_latency_ms=latency_ms,
            plan_response_hash=self.plan_response_hash,
            reflection_response_hash=response_hash,
        )

    @property
    def total_latency_ms(self) -> int:
        return self.plan_latency_ms + self.reflection_latency_ms


@dataclass(frozen=True, slots=True)
class ReflectionContext:
    """What the model is shown when asked to reflect on an iteration.

    Deliberately made of measured facts: which queries ran, how many records came
    back, what the deterministic rules verified. The model is asked to interpret
    an outcome, not to report one.
    """

    objective: InvestigationObjective
    iteration_objective: str
    action: AgentRecommendedAction
    delta: EvidenceDelta
    budget: ExecutionBudget
    executed_queries: tuple[str, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    total_results: int = 0
    created_candidates: int = 0
    policy_rejection: str | None = None
    tool_error: str | None = None


@dataclass(frozen=True, slots=True)
class AgentReflection:
    """The model's structured read of the iteration.

    ``recommended_stop`` is advisory. ``AgentStopPolicy`` takes the decision.
    """

    progress: AgentProgress
    evidence_delta_summary: str
    recommended_stop: bool
    reasoning_summary: str
    remaining_gaps: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_text(self.evidence_delta_summary, "The evidenceDeltaSummary")
        _require_text(self.reasoning_summary, "The reflection reasoningSummary")
        _require_items(self.remaining_gaps, "remainingGaps")

    @classmethod
    def deterministic_fallback(cls, delta: EvidenceDelta) -> AgentReflection:
        """Reflection produced without the model, from the measured delta.

        Used when the reasoner is unavailable: the cycle must still close with
        an auditable reflection rather than block the human queue.
        """
        if delta.has_new_evidence:
            progress = AgentProgress.EVIDENCE_ADDED
            summary = (
                "Deterministic fallback: "
                f"{len(delta.added)} new evidence item(s) were verified."
            )
        else:
            progress = AgentProgress.NO_NEW_EVIDENCE
            summary = "Deterministic fallback: no new evidence was verified."
        return cls(
            progress=progress,
            evidence_delta_summary=summary,
            recommended_stop=True,
            reasoning_summary=(
                "The reasoner was unavailable, so the reflection was derived "
                "from the evidence delta."
            ),
        )
