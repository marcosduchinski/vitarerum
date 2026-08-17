"""Measures the agentic cycle over the fixture, without a database.

The deterministic evaluator answers "does the pipeline find this case". This one
answers the questions the promotion gates ask: does the model return a valid
plan, does the policy authorise it, and does the authorised action actually
close the gap the fixture declares.

It runs the same policy and the same tool the production cycle runs, but skips
persistence. That keeps it runnable against live sources on a laptop, and keeps
a measurement run from writing candidates into anyone's review queue.

Modes stack, each adding one stage:

- ``SHADOW`` asks for a plan and a reflection; nothing is validated or executed;
- ``POLICY_ONLY`` adds the authorisation decision, still executing nothing;
- ``SUPERVISED`` executes the authorised action.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from app.scientific_return.application.agent_contracts import (
    AGENT_CONTRACT_VERSION,
    AgentPlanSchemaError,
    AgentReflectionSchemaError,
)
from app.scientific_return.application.agent_tools import InventoryVariantSearchTool
from app.scientific_return.application.analysis import plan_queries
from app.scientific_return.application.evaluation import (
    BaselineStatus,
    EvaluationCase,
    ExpectedGap,
    load_evaluation_fixture,
)
from app.scientific_return.application.ports import (
    BibliographicSource,
    InvestigationReasoner,
    ToolExecutionContext,
)
from app.scientific_return.domain.agent_policies import (
    ActionPolicyContext,
    AgentActionPolicy,
)
from app.scientific_return.domain.enums import (
    AgentRecommendedAction,
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentObservation,
    AgentPlan,
    EvidenceDelta,
    ExecutionBudget,
    ObservedObject,
    ReflectionContext,
)

_SEARCH = AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS


@dataclass(frozen=True, slots=True)
class AgenticCaseResult:
    case_id: str
    declared_status: str
    expected_gap: str
    plan_valid: bool
    plan_action: str | None
    plan_error: str | None
    reflection_valid: bool
    reflection_error: str | None
    authorized: bool
    rejection_reason: str | None
    queries: tuple[str, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    total_results: int = 0
    actionable_records: int = 0
    target_retrieved: bool = False
    target_actionable: bool = False
    gap_closed: bool = False
    tool_error: str | None = None


def _observation(case: EvaluationCase, budget: ExecutionBudget) -> AgentObservation:
    snapshot = case.snapshot()
    return AgentObservation(
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        project_reference=snapshot.project_reference,
        researcher=snapshot.researcher,
        objects=tuple(
            ObservedObject(item.id, item.inventory_number, item.object_name)
            for item in snapshot.consulted_objects
        ),
        # The deterministic pipeline has already spent these, so the cycle must
        # find something new or refuse.
        tried_queries=tuple(item.text for item in plan_queries(snapshot)),
        allowed_actions=(
            _SEARCH,
            AgentRecommendedAction.PRESENT_FOR_REVIEW,
            AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE,
        ),
        budget=budget,
    )


def _normalized_doi(value: str | None) -> str:
    return (value or "").casefold().removeprefix("https://doi.org/")


async def evaluate_agentic_cases(
    sources: tuple[BibliographicSource, ...],
    reasoner: InvestigationReasoner,
    *,
    mode: InvestigationMode,
    budget: ExecutionBudget,
    allowed_sources: tuple[str, ...],
    cases: tuple[EvaluationCase, ...] | None = None,
) -> dict[str, object]:
    fixture = load_evaluation_fixture()
    selected = cases if cases is not None else fixture.cases
    policy = AgentActionPolicy()
    tool = InventoryVariantSearchTool(sources)
    results: list[AgenticCaseResult] = []

    for case in selected:
        observation = _observation(case, budget)
        plan_valid = True
        plan_error: str | None = None
        plan = None
        try:
            plan = (await reasoner.plan(observation, mode)).plan
        except AgentPlanSchemaError as exc:
            plan_valid, plan_error = False, str(exc)[:300]
        except Exception as exc:
            plan_valid, plan_error = False, f"{type(exc).__name__}: {exc}"[:300]

        authorized = False
        rejection: str | None = None
        execution = None
        if plan is not None and mode.may_evaluate_policy:
            outcome = policy.evaluate(
                plan.action,
                ActionPolicyContext(
                    objective=InvestigationObjective.DISCOVER_CANDIDATE,
                    mode=mode,
                    status=InvestigationStatus.VALIDATING,
                    budget=budget,
                    objects=observation.objects,
                    allowed_actions=frozenset({_SEARCH}),
                    allowed_sources=allowed_sources,
                    tried_queries=observation.tried_queries,
                ),
            )
            authorized = outcome.decision.authorized
            execution = outcome.execution
            rejection = (
                outcome.decision.rejection_reason.value
                if outcome.decision.rejection_reason
                else None
            )

        queries: tuple[str, ...] = ()
        used_sources: tuple[str, ...] = ()
        total_results = 0
        actionable = 0
        retrieved = False
        target_actionable = False
        tool_error: str | None = None
        if execution is not None and mode.may_execute_tools:
            outcome_tool = await tool.execute(
                execution,
                ToolExecutionContext(
                    objective=InvestigationObjective.DISCOVER_CANDIDATE,
                    snapshot=case.snapshot(),
                    now=datetime.now(tz=UTC),
                ),
            )
            queries = tuple(item.query for item in outcome_tool.queries if item.query)
            used_sources = execution.sources
            total_results = outcome_tool.total_results
            actionable = len(outcome_tool.actionable_records)
            tool_error = outcome_tool.error
            expected = _normalized_doi(case.expected_doi)
            for found in outcome_tool.records:
                if _normalized_doi(found.record.doi) != expected:
                    continue
                retrieved = True
                target_actionable = target_actionable or found.is_actionable

        reflection_valid, reflection_error = await _reflect(reasoner, plan, budget)
        results.append(
            AgenticCaseResult(
                case_id=case.case_id,
                declared_status=case.baseline_status,
                expected_gap=case.expected_gap,
                plan_valid=plan_valid,
                plan_action=plan.action.type.value if plan else None,
                plan_error=plan_error,
                reflection_valid=reflection_valid,
                reflection_error=reflection_error,
                authorized=authorized,
                rejection_reason=rejection,
                queries=queries,
                sources=used_sources,
                total_results=total_results,
                actionable_records=actionable,
                target_retrieved=retrieved,
                target_actionable=target_actionable,
                # The gap is closed only when the case the baseline could not
                # reach becomes an actionable candidate. Retrieval alone is what
                # the old metric counted, and it hid the worst failure mode.
                gap_closed=(
                    case.baseline_status is BaselineStatus.GAP and target_actionable
                ),
                tool_error=tool_error,
            )
        )

    return _report(results, mode, budget, allowed_sources, fixture.version)


async def _reflect(
    reasoner: InvestigationReasoner,
    plan: AgentPlan | None,
    budget: ExecutionBudget,
) -> tuple[bool, str | None]:
    """Whether the reflection came back valid, and why not when it did not."""
    if plan is None:
        return False, "no plan to reflect on"
    try:
        await reasoner.reflect(
            ReflectionContext(
                objective=InvestigationObjective.DISCOVER_CANDIDATE,
                iteration_objective=plan.objective,
                action=_SEARCH,
                delta=EvidenceDelta(),
                budget=budget,
                executed_queries=(),
                sources=(),
            )
        )
        return True, None
    except AgentReflectionSchemaError as exc:
        return False, str(exc)[:300]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:300]


def _report(
    results: list[AgenticCaseResult],
    mode: InvestigationMode,
    budget: ExecutionBudget,
    allowed_sources: tuple[str, ...],
    fixture_version: str,
) -> dict[str, object]:
    total = len(results)
    gap_cases = [item for item in results if item.declared_status == "GAP"]
    closable = [
        item
        for item in results
        if item.expected_gap
        in {ExpectedGap.INVENTORY_FORMAT, ExpectedGap.INSTITUTIONAL_ACRONYM}
    ]
    rejections: dict[str, int] = {}
    for item in results:
        if item.rejection_reason:
            rejections[item.rejection_reason] = (
                rejections.get(item.rejection_reason, 0) + 1
            )
    return {
        "generatedAt": datetime.now(tz=UTC).isoformat(),
        "fixtureVersion": fixture_version,
        "contractVersion": AGENT_CONTRACT_VERSION,
        "mode": mode.value,
        "allowedSources": list(allowed_sources),
        "budget": {
            "maxQueries": budget.max_queries,
            "maxResultsPerQuery": budget.max_results_per_query,
            "maxNewCandidates": budget.max_new_candidates,
        },
        "caseCount": total,
        # Gate G1 reads these two.
        "planValidRate": (
            sum(item.plan_valid for item in results) / total if total else 0.0
        ),
        "reflectionValidRate": (
            sum(item.reflection_valid for item in results) / total if total else 0.0
        ),
        "authorizedCount": sum(item.authorized for item in results),
        "rejectionsByReason": rejections,
        # Gate G2 reads these.
        "gapCaseCount": len(gap_cases),
        "gapsClosed": sum(item.gap_closed for item in results),
        "gapsClosedCaseIds": [item.case_id for item in results if item.gap_closed],
        "closableGapCaseCount": len(closable),
        "queriesIssued": sum(len(item.queries) for item in results),
        "cases": [asdict(item) for item in results],
    }
