"""The ``ScientificReturnInvestigation`` aggregate and its iteration entity.

The aggregate owns the state machine. Every transition is a method, so a caller
cannot move an investigation by assigning to a field, and a terminal
investigation cannot be reopened: a retry is a new investigation linked to the
previous one, which keeps each trajectory a complete and immutable record.

The aggregate never calls a model, a source or a repository. It records what
happened and refuses what may not happen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import NewType

from app.scientific_return.domain.enums import (
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
    IterationStatus,
    StopReason,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentObservation,
    AgentPlan,
    AgentReflection,
    EvidenceDelta,
    ExecutionBudget,
    PolicyDecision,
    ReasonerTelemetry,
    ToolResultSummary,
)
from app.scientific_return.domain.models import (
    CandidatePublicationId,
    ScientificReturnRunId,
    ScientificReturnWatchId,
)
from app.shared.kernel import PermissionId

InvestigationId = NewType("InvestigationId", str)
InvestigationIterationId = NewType("InvestigationIterationId", str)
ToolExecutionId = NewType("ToolExecutionId", str)

_ALLOWED_TRANSITIONS: dict[InvestigationStatus, frozenset[InvestigationStatus]] = {
    InvestigationStatus.CREATED: frozenset({InvestigationStatus.OBSERVING}),
    InvestigationStatus.OBSERVING: frozenset({InvestigationStatus.PLANNING}),
    InvestigationStatus.PLANNING: frozenset({InvestigationStatus.VALIDATING}),
    InvestigationStatus.VALIDATING: frozenset(
        {InvestigationStatus.EXECUTING, InvestigationStatus.REFLECTING}
    ),
    InvestigationStatus.EXECUTING: frozenset({InvestigationStatus.REFLECTING}),
    InvestigationStatus.REFLECTING: frozenset(
        {
            InvestigationStatus.AWAITING_HUMAN_REVIEW,
            InvestigationStatus.STOPPED,
            # Re-entering OBSERVING is E3; the aggregate already allows it so the
            # state machine does not have to change when iterations arrive.
            InvestigationStatus.OBSERVING,
        }
    ),
}


class InvestigationTransitionError(ValueError):
    """An investigation was asked to do something its state forbids."""


@dataclass(slots=True)
class InvestigationIteration:
    """One pass through observe, plan, validate, act and reflect."""

    id: InvestigationIterationId
    investigation_id: InvestigationId
    number: int
    started_at: datetime
    status: IterationStatus = IterationStatus.RUNNING
    observation: AgentObservation | None = None
    plan: AgentPlan | None = None
    policy_decision: PolicyDecision | None = None
    tool_execution_id: ToolExecutionId | None = None
    tool_result: ToolResultSummary | None = None
    evidence_before_hash: str | None = None
    evidence_after_hash: str | None = None
    evidence_delta: EvidenceDelta | None = None
    reflection: AgentReflection | None = None
    telemetry: ReasonerTelemetry | None = None
    error_message: str | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("An iteration number starts at 1")

    def complete(self, completed_at: datetime) -> None:
        if self.status is not IterationStatus.RUNNING:
            raise InvestigationTransitionError(
                "Only a running iteration can be completed"
            )
        self.status = IterationStatus.COMPLETED
        self.completed_at = completed_at

    def fail(self, message: str, completed_at: datetime) -> None:
        if self.status is not IterationStatus.RUNNING:
            raise InvestigationTransitionError("Only a running iteration can fail")
        self.status = IterationStatus.FAILED
        self.error_message = message.strip()[:2000] or "Unknown iteration failure"
        self.completed_at = completed_at


@dataclass(slots=True)
class ScientificReturnInvestigation:
    """A bounded agentic investigation over one watch and, optionally, one candidate.

    Discovery starts without a candidate so a watch whose deterministic run found
    nothing actionable can still be investigated; enrichment starts from a
    pending candidate and may only add verified evidence to it.
    """

    id: InvestigationId
    watch_id: ScientificReturnWatchId
    objective: InvestigationObjective
    mode: InvestigationMode
    initial_run_id: ScientificReturnRunId
    budget: ExecutionBudget
    created_by: PermissionId
    started_at: datetime
    status: InvestigationStatus = InvestigationStatus.CREATED
    candidate_id: CandidatePublicationId | None = None
    previous_investigation_id: InvestigationId | None = None
    idempotency_key: str | None = None
    current_iteration: int = 0
    stop_reason: StopReason | None = None
    completed_at: datetime | None = None
    heartbeat_at: datetime | None = None
    version: int = 0
    iterations: list[InvestigationIteration] = field(default_factory=list)

    def __post_init__(self) -> None:
        if (
            self.objective is InvestigationObjective.ENRICH_CANDIDATE
            and self.candidate_id is None
        ):
            raise ValueError("Enrichment requires a candidate")
        if (
            self.objective is InvestigationObjective.DISCOVER_CANDIDATE
            and self.candidate_id is not None
        ):
            raise ValueError("Discovery starts without a candidate")
        if self.status.is_terminal and self.stop_reason is None:
            raise ValueError("A terminal investigation needs a stop reason")

    # --- state machine -------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    def _refuse_if_terminal(self, target: InvestigationStatus) -> None:
        if self.status.is_terminal:
            raise InvestigationTransitionError(
                f"Investigation {self.id} is {self.status.value} and cannot move to "
                f"{target.value}; retrying means creating a new investigation"
            )

    def _transition(self, target: InvestigationStatus, now: datetime) -> None:
        self._refuse_if_terminal(target)
        allowed = _ALLOWED_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise InvestigationTransitionError(
                f"Cannot move from {self.status.value} to {target.value}"
            )
        self.status = target
        self.heartbeat_at = now
        self.version += 1

    def begin_observation(self, now: datetime) -> InvestigationIteration:
        """Open the next iteration and move into ``OBSERVING``.

        Terminality is checked before the budget: an investigation that already
        ended must say so, rather than report whichever limit happens to bind.
        """
        self._refuse_if_terminal(InvestigationStatus.OBSERVING)
        exhaustion = self.budget.exhaustion()
        if exhaustion is not None:
            raise InvestigationTransitionError(
                f"The budget is exhausted ({exhaustion.value}); the investigation "
                "must stop instead of opening another iteration"
            )
        self._transition(InvestigationStatus.OBSERVING, now)
        self.budget = self.budget.reserve_iteration()
        self.current_iteration += 1
        iteration = InvestigationIteration(
            id=InvestigationIterationId(f"{self.id}:{self.current_iteration}"),
            investigation_id=self.id,
            number=self.current_iteration,
            started_at=now,
        )
        self.iterations.append(iteration)
        return iteration

    def record_observation(self, observation: AgentObservation, now: datetime) -> None:
        iteration = self._require_open_iteration()
        self._transition(InvestigationStatus.PLANNING, now)
        iteration.observation = observation

    def record_plan(self, plan: AgentPlan, now: datetime) -> None:
        iteration = self._require_open_iteration()
        self._transition(InvestigationStatus.VALIDATING, now)
        iteration.plan = plan

    def record_policy_decision(
        self,
        decision: PolicyDecision,
        now: datetime,
        *,
        reserved_queries: int = 0,
    ) -> None:
        """Authorised actions move to ``EXECUTING``; rejected ones to ``REFLECTING``.

        A rejected action still produces a reflection and a stop reason, so a
        refusal is as auditable as an execution.

        ``reserved_queries`` is charged to the budget *before* the tool runs, so
        a crash mid-execution can only leave the budget over-charged, never
        over-spent. The caller passes the number of queries the authorised
        action will actually issue.
        """
        iteration = self._require_open_iteration()
        plan = iteration.plan
        target = (
            InvestigationStatus.EXECUTING
            if decision.authorized
            else InvestigationStatus.REFLECTING
        )
        if (
            decision.authorized
            and plan is not None
            and plan.action.contacts_a_source
            and reserved_queries < 1
        ):
            raise ValueError(
                "An authorized action that contacts a source must reserve queries"
            )
        self._transition(target, now)
        iteration.policy_decision = decision
        if decision.authorized and reserved_queries > 0:
            self.budget = self.budget.reserve_action(queries=reserved_queries)

    def record_tool_result(
        self,
        result: ToolResultSummary,
        evidence_before_hash: str,
        evidence_after_hash: str,
        delta: EvidenceDelta,
        now: datetime,
        tool_execution_id: ToolExecutionId | None = None,
    ) -> None:
        iteration = self._require_executing()
        self._transition(InvestigationStatus.REFLECTING, now)
        iteration.tool_execution_id = tool_execution_id
        iteration.tool_result = result
        iteration.evidence_before_hash = evidence_before_hash
        iteration.evidence_after_hash = evidence_after_hash
        iteration.evidence_delta = delta
        self.budget = self.budget.record_candidates(len(result.created_candidate_ids))

    def record_tool_failure(self, message: str, now: datetime) -> None:
        iteration = self._require_executing()
        self._transition(InvestigationStatus.REFLECTING, now)
        iteration.error_message = message.strip()[:2000] or "Unknown tool failure"

    def record_telemetry(self, telemetry: ReasonerTelemetry) -> None:
        """Attach which model and prompt produced this iteration.

        Kept beside the trajectory rather than in a log, because a reviewer
        judging a proposal needs to know what produced it.
        """
        iteration = self._require_open_iteration()
        iteration.telemetry = telemetry

    def record_reflection(self, reflection: AgentReflection) -> None:
        iteration = self._require_open_iteration()
        if self.status is not InvestigationStatus.REFLECTING:
            raise InvestigationTransitionError(
                "A reflection can only be recorded while reflecting"
            )
        iteration.reflection = reflection

    def present_for_review(self, reason: StopReason, now: datetime) -> None:
        """Close the cycle with a candidate a human must decide on."""
        self._finish(InvestigationStatus.AWAITING_HUMAN_REVIEW, reason, now)

    def stop(self, reason: StopReason, now: datetime) -> None:
        self._finish(InvestigationStatus.STOPPED, reason, now)

    def fail(self, reason: StopReason, message: str, now: datetime) -> None:
        """End on an unrecoverable error, from any non-terminal state.

        Failure is deliberately reachable from anywhere: an investigation that
        cannot continue must still end with a typed reason rather than linger.
        """
        if self.status.is_terminal:
            raise InvestigationTransitionError(
                f"Investigation {self.id} has already ended"
            )
        iteration = self._open_iteration()
        if iteration is not None:
            iteration.fail(message, now)
        self.status = InvestigationStatus.FAILED
        self.stop_reason = reason
        self.completed_at = now
        self.heartbeat_at = now
        self.version += 1

    def _finish(
        self, target: InvestigationStatus, reason: StopReason, now: datetime
    ) -> None:
        if self.status is not InvestigationStatus.REFLECTING:
            raise InvestigationTransitionError(
                "An investigation can only close from REFLECTING; use fail() for "
                "an unrecoverable error"
            )
        iteration = self._open_iteration()
        if iteration is not None:
            iteration.complete(now)
        self.status = target
        self.stop_reason = reason
        self.completed_at = now
        self.heartbeat_at = now
        self.version += 1

    # --- iteration access ----------------------------------------------------

    def _open_iteration(self) -> InvestigationIteration | None:
        for iteration in reversed(self.iterations):
            if iteration.status is IterationStatus.RUNNING:
                return iteration
        return None

    def _require_open_iteration(self) -> InvestigationIteration:
        iteration = self._open_iteration()
        if iteration is None:
            raise InvestigationTransitionError("No iteration is open")
        return iteration

    def _require_executing(self) -> InvestigationIteration:
        """Guard the tool-outcome methods.

        ``VALIDATING -> REFLECTING`` is a legal transition, but only for a
        rejected action. Without this check a caller could record a tool result
        for an action the policy never authorised, so the outcome methods assert
        that execution actually started.
        """
        if self.status is not InvestigationStatus.EXECUTING:
            raise InvestigationTransitionError(
                "A tool outcome can only be recorded while executing; the action "
                f"was not authorized (status is {self.status.value})"
            )
        return self._require_open_iteration()

    @property
    def current(self) -> InvestigationIteration | None:
        return self.iterations[-1] if self.iterations else None
