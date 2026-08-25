"""The two deterministic policies that bound the agentic cycle.

``AgentActionPolicy`` decides whether a proposed action may run and, when it
may, derives exactly what will run. The model asks for an action type and one
consulted object; everything actually sent to a source — the query strings, the
sources, the result limit — is produced here. The model cannot widen it, and the
executor may not run anything the policy did not return.

``AgentStopPolicy`` decides when the cycle ends and with which typed reason. The
model's ``recommendedStop`` is advisory input, never the decision.

Both are pure: no model, no repository, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.scientific_return.domain.enums import (
    AgentRecommendedAction,
    CandidateStatus,
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
    PolicyRejectionReason,
    StopReason,
)
from app.scientific_return.domain.inventory_variants import (
    InventoryQueryVariant,
    generate_inventory_query_variants,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentReflection,
    EvidenceDelta,
    ExecutionBudget,
    ObservedObject,
    PolicyDecision,
    ProposedAction,
    ToolResultSummary,
)

SOURCE_PRIORITY: tuple[str, ...] = ("EUROPE_PMC", "CROSSREF", "OPENALEX")
"""Routing order. Europe PMC first because it is the only full-text source, and
an inventory number is far more often in the full text than in the metadata."""

EXACT_MATCH_SOURCES: frozenset[str] = frozenset({"EUROPE_PMC"})
"""Sources that honour an exact phrase, measured rather than assumed.

Looking up a specimen code only means anything against a source that can answer
"this exact string, or nothing". Crossref cannot: measured against the live API,
``"ZZZZ-NONSENSE-999999"`` returns five relevance-ranked works, and every
inventory variant returns a full page of unrelated results. Routing an inventory
search there would spend the budget to manufacture noise, and would hand the
human queue candidates that no evidence rule will ever support.

OpenAlex is absent because it has not been measured, not because it failed.
Adding a source here requires the same check.
"""

ALWAYS_AVAILABLE_ACTIONS = frozenset(
    {
        AgentRecommendedAction.PRESENT_FOR_REVIEW,
        AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE,
    }
)
"""Actions that end the cycle without contacting anything.

These are deliberately outside the allowlist: they are how the model asks to
stop. If they had to be enabled by configuration, a misconfigured allowlist
would leave the model with no legal way to end an iteration.
"""

_DECIDED_CANDIDATE_STATUSES = frozenset(
    {CandidateStatus.CONFIRMED, CandidateStatus.DISMISSED}
)

_REJECTION_TO_STOP: dict[PolicyRejectionReason, StopReason] = {
    PolicyRejectionReason.NO_NEW_QUERY_VARIANT: StopReason.QUERY_REPEATED,
    PolicyRejectionReason.BUDGET_EXHAUSTED: StopReason.BUDGET_EXHAUSTED,
    PolicyRejectionReason.ITERATION_LIMIT_REACHED: (StopReason.ITERATION_LIMIT_REACHED),
    PolicyRejectionReason.CANDIDATE_LIMIT_REACHED: (StopReason.CANDIDATE_LIMIT_REACHED),
    PolicyRejectionReason.CANDIDATE_ALREADY_DECIDED: (
        StopReason.CANDIDATE_ALREADY_DECIDED
    ),
}


@dataclass(frozen=True, slots=True)
class ActionPolicyContext:
    """Everything the policy is allowed to consider."""

    objective: InvestigationObjective
    mode: InvestigationMode
    status: InvestigationStatus
    budget: ExecutionBudget
    objects: tuple[ObservedObject, ...]
    allowed_actions: frozenset[AgentRecommendedAction]
    allowed_sources: tuple[str, ...]
    tried_queries: tuple[str, ...] = field(default_factory=tuple)
    candidate_status: CandidateStatus | None = None

    def object_by_id(self, object_id: str) -> ObservedObject | None:
        return next(
            (item for item in self.objects if item.object_id == object_id), None
        )


@dataclass(frozen=True, slots=True)
class AuthorizedExecution:
    """Exactly what the executor is permitted to do. No more."""

    action: AgentRecommendedAction
    object_id: str
    queries: tuple[InventoryQueryVariant, ...]
    sources: tuple[str, ...]
    result_limit: int

    @property
    def query_count(self) -> int:
        return len(self.queries)


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    decision: PolicyDecision
    execution: AuthorizedExecution | None = None


class AgentActionPolicy:
    """Authorises a proposed action and derives what will actually run."""

    def evaluate(
        self, action: ProposedAction, context: ActionPolicyContext
    ) -> PolicyOutcome:
        if context.status is not InvestigationStatus.VALIDATING:
            return _reject(
                PolicyRejectionReason.INVESTIGATION_NOT_ACTIONABLE,
                f"The investigation is {context.status.value}, not VALIDATING.",
            )
        if (
            context.candidate_status is not None
            and context.candidate_status in _DECIDED_CANDIDATE_STATUSES
        ):
            return _reject(
                PolicyRejectionReason.CANDIDATE_ALREADY_DECIDED,
                "A human already decided this candidate during the cycle.",
            )
        if action.type in ALWAYS_AVAILABLE_ACTIONS:
            return PolicyOutcome(
                PolicyDecision.authorize(
                    f"{action.type.value} ends the cycle without contacting a source."
                )
            )
        if action.type not in context.allowed_actions:
            return _reject(
                PolicyRejectionReason.ACTION_NOT_ALLOWED,
                f"{action.type.value} is not in the configured allowlist.",
            )
        if not context.mode.may_execute_tools:
            return _reject(
                PolicyRejectionReason.MODE_FORBIDS_EXECUTION,
                f"Mode {context.mode.value} does not execute tools.",
            )

        # The iteration is already open, so only the per-action limits apply.
        exhaustion = context.budget.action_exhaustion()
        if exhaustion is not None:
            return _reject(
                _BUDGET_REJECTION[exhaustion], f"Budget: {exhaustion.value}."
            )

        if action.type is not AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS:
            return _reject(
                PolicyRejectionReason.ACTION_NOT_ALLOWED,
                f"{action.type.value} has no executor in this increment.",
            )
        if not action.object_id:
            return _reject(
                PolicyRejectionReason.OBJECT_ID_REQUIRED,
                f"{action.type.value} requires a consulted object.",
            )

        # The object must belong to this watch's snapshot. This is the data
        # boundary: an object id the model invented, or borrowed from another
        # project, cannot reach a source.
        observed = context.object_by_id(action.object_id)
        if observed is None:
            return _reject(
                PolicyRejectionReason.OBJECT_NOT_IN_SNAPSHOT,
                f"Object {action.object_id} is not in the project snapshot.",
            )
        if not observed.inventory_number.strip():
            return _reject(
                PolicyRejectionReason.INVENTORY_MISSING,
                f"Object {action.object_id} has no inventory number.",
            )

        sources = self._route(context.allowed_sources)
        if not sources:
            return _reject(
                PolicyRejectionReason.SOURCE_NOT_ALLOWED,
                "No configured source can answer an exact inventory phrase.",
            )

        variants = generate_inventory_query_variants(
            observed.inventory_number,
            already_tried=context.tried_queries,
            limit=context.budget.remaining_queries,
        )
        if not variants:
            return _reject(
                PolicyRejectionReason.NO_NEW_QUERY_VARIANT,
                "Every inventory variant has already been queried for this watch.",
            )

        return PolicyOutcome(
            PolicyDecision.authorize(
                f"{len(variants)} untried inventory variant(s) over "
                f"{len(sources)} source(s)."
            ),
            AuthorizedExecution(
                action=action.type,
                object_id=action.object_id,
                queries=variants,
                sources=sources,
                result_limit=context.budget.max_results_per_query,
            ),
        )

    @staticmethod
    def _route(allowed_sources: tuple[str, ...]) -> tuple[str, ...]:
        """Route only to sources that can answer an exact phrase.

        Narrower than the general allowlist on purpose: a source that ranks by
        relevance always returns something, so sending it a specimen code
        produces confident-looking noise rather than an honest empty result.
        """
        configured = {item.strip().upper() for item in allowed_sources if item.strip()}
        usable = configured & EXACT_MATCH_SOURCES
        return tuple(name for name in SOURCE_PRIORITY if name in usable)


_BUDGET_REJECTION: dict[StopReason, PolicyRejectionReason] = {
    StopReason.CANDIDATE_LIMIT_REACHED: PolicyRejectionReason.CANDIDATE_LIMIT_REACHED,
    StopReason.BUDGET_EXHAUSTED: PolicyRejectionReason.BUDGET_EXHAUSTED,
}


def _reject(reason: PolicyRejectionReason, justification: str) -> PolicyOutcome:
    return PolicyOutcome(PolicyDecision.reject(reason, justification))


@dataclass(frozen=True, slots=True)
class StopPolicyContext:
    """What the stop policy is allowed to consider."""

    objective: InvestigationObjective
    budget: ExecutionBudget
    proposed_action: AgentRecommendedAction | None = None
    decision: PolicyDecision | None = None
    tool_result: ToolResultSummary | None = None
    tool_error: str | None = None
    tool_unavailable: bool = False
    delta: EvidenceDelta | None = None
    reflection: AgentReflection | None = None
    has_reviewable_candidate: bool = False
    candidate_decided: bool = False


@dataclass(frozen=True, slots=True)
class StopDecision:
    reason: StopReason
    awaiting_human_review: bool


class AgentStopPolicy:
    """Decides when the cycle ends, and with which typed reason.

    Every path through an iteration reaches exactly one reason. There is no
    branch that leaves an investigation without one, which is what makes
    "100% of investigations have a stop reason" an invariant rather than a hope.
    """

    def decide(self, context: StopPolicyContext) -> StopDecision:
        reason = self._reason(context)
        reviewable = context.has_reviewable_candidate and not context.candidate_decided
        return StopDecision(
            reason=reason,
            awaiting_human_review=reviewable,
        )

    def _reason(self, context: StopPolicyContext) -> StopReason:
        # A human decision taken during the cycle outranks everything: the
        # candidate is settled and nothing the iteration found may reopen it.
        if context.candidate_decided:
            return StopReason.CANDIDATE_ALREADY_DECIDED

        decision = context.decision
        if decision is not None and not decision.authorized:
            reason = decision.rejection_reason
            if reason is not None and reason in _REJECTION_TO_STOP:
                return _REJECTION_TO_STOP[reason]
            return StopReason.ACTION_REJECTED

        if context.tool_unavailable:
            return StopReason.TOOL_UNAVAILABLE
        if context.tool_error:
            return StopReason.TOOL_FAILED

        if context.proposed_action is AgentRecommendedAction.PRESENT_FOR_REVIEW:
            return StopReason.PRESENTED_FOR_REVIEW
        if context.proposed_action is AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE:
            return StopReason.INSUFFICIENT_EVIDENCE

        result = context.tool_result
        if result is not None and result.found_nothing:
            return StopReason.NO_RESULTS

        delta = context.delta
        if delta is not None and delta.has_new_evidence:
            return StopReason.EVIDENCE_SUFFICIENT
        if result is not None and result.created_candidate_ids:
            return StopReason.EVIDENCE_SUFFICIENT

        exhaustion = context.budget.exhaustion()
        if exhaustion is not None and exhaustion is not (
            StopReason.ITERATION_LIMIT_REACHED
        ):
            return exhaustion

        if result is not None:
            return StopReason.NO_EVIDENCE_ADDED
        return StopReason.NO_PROGRESS
