"""The agentic cycle, end to end.

Coordination only. Every decision belongs to a domain service: authorisation to
``AgentActionPolicy``, termination to ``AgentStopPolicy``, evidence to the
deterministic rules. This module's job is to run them in order, persist between
external calls, and make sure every path ends with a typed reason.

The commit points matter as much as the order. Each step is persisted before the
next external call, so a crash mid-cycle leaves a readable partial trajectory
rather than nothing, and no transaction is ever open while a model or a source is
answering.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from app.identity.public import Actor, GroupName
from app.scientific_return.application.agent_contracts import AgentPlanSchemaError
from app.scientific_return.application.agent_tools import tool_idempotency_key
from app.scientific_return.application.ports import (
    AgentToolRegistry,
    Clock,
    DiscoveredRecord,
    InvestigationLock,
    InvestigationReasoner,
    InvestigationUnitOfWork,
    ScientificReturnInvestigationRepository,
    ScientificReturnRepository,
    ToolExecutionContext,
    ToolExecutionRecord,
    UnknownAgentTool,
)
from app.scientific_return.domain.agent_policies import (
    ActionPolicyContext,
    AgentActionPolicy,
    AgentStopPolicy,
    AuthorizedExecution,
    StopPolicyContext,
)
from app.scientific_return.domain.enums import (
    AgentRecommendedAction,
    CandidateStatus,
    InvestigationMode,
    InvestigationObjective,
    StopReason,
    WatchStatus,
)
from app.scientific_return.domain.evidence_delta import (
    calculate_evidence_delta,
    evidence_hash,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentObservation,
    AgentPlan,
    AgentReflection,
    EvidenceDelta,
    ExecutionBudget,
    ObservedCandidate,
    ObservedObject,
    ReasonerTelemetry,
    ReflectionContext,
    ToolResultSummary,
)
from app.scientific_return.domain.investigation_models import (
    InvestigationId,
    ScientificReturnInvestigation,
    ToolExecutionId,
)
from app.scientific_return.domain.models import (
    CandidateEvidence,
    CandidatePublication,
    CandidatePublicationId,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)
from app.shared.authorization import require_group

logger = logging.getLogger(__name__)

_REVIEW_GROUPS = (
    GroupName.CURATORIAL,
    GroupName.COLLECTIONS_MANAGEMENT,
    GroupName.DIRECTION,
)


class InvestigationDisabled(RuntimeError):
    """The operating mode does not run investigations."""


class InvestigationAlreadyRunning(RuntimeError):
    """A non-terminal investigation already covers this target."""


class InvestigationNotPossible(ValueError):
    """A precondition of the objective is not met."""


@dataclass(frozen=True, slots=True)
class AgentConfiguration:
    mode: InvestigationMode
    allowed_actions: frozenset[AgentRecommendedAction]
    allowed_sources: tuple[str, ...]
    budget: ExecutionBudget


@dataclass(frozen=True, slots=True)
class RunInvestigationInput:
    watch_id: ScientificReturnWatchId
    objective: InvestigationObjective
    caller: Actor
    candidate_id: CandidatePublicationId | None = None
    idempotency_key: str | None = None


class RunScientificReturnInvestigation:
    """Runs one bounded investigation and returns it already terminal."""

    def __init__(
        self,
        repository: ScientificReturnRepository,
        investigations: ScientificReturnInvestigationRepository,
        reasoner: InvestigationReasoner,
        tools: AgentToolRegistry,
        unit_of_work: InvestigationUnitOfWork,
        clock: Clock,
        configuration: AgentConfiguration,
        lock: InvestigationLock,
    ) -> None:
        self._repository = repository
        self._investigations = investigations
        self._reasoner = reasoner
        self._tools = tools
        self._uow = unit_of_work
        self._clock = clock
        self._config = configuration
        self._lock = lock
        self._action_policy = AgentActionPolicy()
        self._stop_policy = AgentStopPolicy()

    async def execute(
        self, data: RunInvestigationInput
    ) -> ScientificReturnInvestigation:
        require_group(data.caller, *_REVIEW_GROUPS)
        if self._config.mode is InvestigationMode.DISABLED:
            raise InvestigationDisabled("Agentic investigation is disabled")

        watch, snapshot, candidate = await self._load(data)
        if data.idempotency_key:
            # Command-level idempotency: the same key returns the investigation
            # it already produced instead of contacting a source again.
            replayed = await self._investigations.find_by_idempotency_key(
                data.idempotency_key
            )
            if replayed is not None:
                logger.info(
                    "Returning investigation %s for repeated key", replayed.id
                )
                return replayed
        existing = await self._investigations.find_live(
            data.watch_id, data.objective, data.candidate_id
        )
        if existing is not None:
            raise InvestigationAlreadyRunning(
                f"Investigation {existing.id} is already running for this target"
            )

        runs, _ = await self._repository.list_runs(data.watch_id, 0, 1)
        if not runs:
            raise InvestigationNotPossible(
                "The watch needs at least one completed deterministic run"
            )

        # Held until the cycle ends, including while a model or a source is
        # answering, which is exactly when a second runner would collide.
        await self._lock.acquire(
            f"scientific-return:{data.watch_id}:{data.objective.value}:"
            f"{data.candidate_id or '-'}"
        )
        investigation = ScientificReturnInvestigation(
            id=InvestigationId(str(uuid4())),
            watch_id=data.watch_id,
            objective=data.objective,
            mode=self._config.mode,
            initial_run_id=runs[0].id,
            budget=self._config.budget,
            created_by=data.caller.id,
            started_at=self._clock.now(),
            candidate_id=data.candidate_id,
            idempotency_key=data.idempotency_key,
        )
        await self._investigations.add(investigation)
        await self._uow.commit()

        try:
            await self._run(investigation, snapshot.payload, candidate)
        except Exception as exc:
            logger.exception("Investigation %s failed", investigation.id)
            await self._fail(investigation, StopReason.TOOL_FAILED, str(exc))
        finally:
            await self._lock.release()
        return investigation

    # --- the cycle -----------------------------------------------------------

    async def _run(
        self,
        investigation: ScientificReturnInvestigation,
        snapshot: ProjectSnapshotPayload,
        candidate: CandidatePublication | None,
    ) -> None:
        observation = await self._observe(investigation, snapshot, candidate)
        investigation.begin_observation(self._clock.now())
        investigation.record_observation(observation, self._clock.now())
        await self._investigations.save(investigation)
        await self._uow.commit()

        # External call: planning. Nothing is open while the model thinks.
        try:
            plan_result = await self._reasoner.plan(observation, self._config.mode)
        except AgentPlanSchemaError as exc:
            # Nothing safe can be done with a malformed instruction.
            await self._fail(investigation, StopReason.INVALID_PLAN, str(exc))
            return
        except Exception as exc:
            # Prompt missing, model down, timeout: the cycle ends and the human
            # queue is untouched.
            await self._fail(investigation, StopReason.REASONER_UNAVAILABLE, str(exc))
            return

        plan = plan_result.plan
        telemetry = ReasonerTelemetry(
            model=plan_result.call.model,
            prompt_version=plan_result.call.prompt_version,
            plan_latency_ms=plan_result.call.latency_ms,
            plan_response_hash=plan_result.call.response_hash,
        )
        investigation.record_plan(plan, self._clock.now())
        investigation.record_telemetry(telemetry)
        await self._investigations.save(investigation)
        await self._uow.commit()

        candidate_status = candidate.status if candidate is not None else None
        outcome = self._action_policy.evaluate(
            plan.action,
            ActionPolicyContext(
                objective=investigation.objective,
                mode=self._config.mode,
                status=investigation.status,
                budget=investigation.budget,
                objects=observation.objects,
                allowed_actions=self._config.allowed_actions,
                allowed_sources=self._config.allowed_sources,
                tried_queries=observation.tried_queries,
                candidate_status=candidate_status,
            ),
        )
        execution = outcome.execution
        investigation.record_policy_decision(
            outcome.decision,
            self._clock.now(),
            reserved_queries=execution.query_count if execution else 0,
        )
        await self._investigations.save(investigation)
        await self._uow.commit()

        if not outcome.decision.authorized:
            await self._close(
                investigation,
                StopPolicyContext(
                    objective=investigation.objective,
                    budget=investigation.budget,
                    proposed_action=plan.action.type,
                    decision=outcome.decision,
                    has_reviewable_candidate=candidate is not None,
                ),
                plan.action.type,
                EvidenceDelta(),
            )
            return

        if execution is None:
            # An authorised action that contacts nothing: the model asked to end.
            await self._close(
                investigation,
                StopPolicyContext(
                    objective=investigation.objective,
                    budget=investigation.budget,
                    proposed_action=plan.action.type,
                    decision=outcome.decision,
                    has_reviewable_candidate=candidate is not None,
                ),
                plan.action.type,
                EvidenceDelta(),
            )
            return

        await self._execute(investigation, execution, snapshot, candidate, plan)

    async def _execute(
        self,
        investigation: ScientificReturnInvestigation,
        execution: AuthorizedExecution,
        snapshot: ProjectSnapshotPayload,
        candidate: CandidatePublication | None,
        plan: AgentPlan,
    ) -> None:
        iteration = investigation.current
        assert iteration is not None
        key = tool_idempotency_key(
            str(investigation.id), iteration.number, execution
        )
        before = tuple(candidate.evidences) if candidate is not None else ()
        # Claimed before the call: a replay finds this row instead of searching
        # again, which is what makes repeating the command safe.
        previous = await self._investigations.find_tool_execution(key)
        if previous is not None and previous.succeeded:
            await self._replay(investigation, previous, candidate, before, plan)
            return

        started = self._clock.now()
        record = ToolExecutionRecord(
            id=ToolExecutionId(str(uuid4())),
            investigation_id=investigation.id,
            iteration_id=str(iteration.id),
            idempotency_key=key,
            action=execution.action,
            started_at=started,
            queries=tuple(variant.text for variant in execution.queries),
            sources=execution.sources,
        )
        if previous is None:
            await self._investigations.add_tool_execution(record)
            await self._uow.commit()
        else:
            # A previous attempt was claimed but did not succeed, so the source
            # may never have answered. Retrying is correct; the attempt count
            # keeps that visible.
            record = previous
            record.attempts += 1

        try:
            tool = self._tools.resolve(execution.action)
        except UnknownAgentTool as exc:
            await self._finish_tool(record, error=str(exc))
            investigation.record_tool_failure(str(exc), self._clock.now())
            await self._close_after_tool(
                investigation,
                candidate,
                EvidenceDelta(),
                None,
                str(exc),
                True,
                execution.action,
            )
            return

        try:
            result = await tool.execute(
                execution,
                ToolExecutionContext(
                    objective=investigation.objective,
                    snapshot=snapshot,
                    now=self._clock.now(),
                    candidate=candidate,
                ),
            )
        except Exception as exc:
            await self._finish_tool(record, error=str(exc))
            investigation.record_tool_failure(str(exc), self._clock.now())
            await self._close_after_tool(
                investigation,
                candidate,
                EvidenceDelta(),
                None,
                str(exc),
                False,
                execution.action,
            )
            return

        executed_queries = tuple(item.query for item in result.queries if item.query)
        if not executed_queries:
            # The tool contacted nothing: an authorised source has no adapter
            # wired, so no query was ever issued. There is no execution to
            # summarise, and closing here keeps the deployment mismatch visible
            # as TOOL_UNAVAILABLE instead of failing on an empty summary.
            message = result.error or "The tool issued no query"
            await self._finish_tool(record, error=message)
            investigation.record_tool_failure(message, self._clock.now())
            await self._close_after_tool(
                investigation,
                candidate,
                EvidenceDelta(),
                None,
                message,
                True,
                execution.action,
            )
            return

        created, added = await self._persist_findings(
            investigation, result.records, candidate
        )
        after = await self._evidence_now(candidate)
        delta = calculate_evidence_delta(before, after)

        summary = ToolResultSummary(
            executed_queries=executed_queries,
            sources=execution.sources,
            total_results=result.total_results,
            created_candidate_ids=created,
            added_evidence_ids=added,
            result_hash=result.result_hash,
        )
        record.total_results = result.total_results
        record.created_candidate_ids = created
        record.added_evidence_ids = added
        record.result_hash = result.result_hash
        record.succeeded = not result.unavailable
        record.error_message = result.error
        record.completed_at = self._clock.now()
        await self._investigations.save_tool_execution(record)

        investigation.record_tool_result(
            summary,
            evidence_hash(before),
            evidence_hash(after),
            delta,
            self._clock.now(),
            tool_execution_id=record.id,
        )
        await self._investigations.save(investigation)
        await self._uow.commit()

        await self._close_after_tool(
            investigation,
            candidate,
            delta,
            summary,
            result.error,
            result.unavailable,
            plan.action.type,
            created=created,
        )

    async def _replay(
        self,
        investigation: ScientificReturnInvestigation,
        previous: ToolExecutionRecord,
        candidate: CandidatePublication | None,
        before: tuple[CandidateEvidence, ...],
        plan: AgentPlan,
    ) -> None:
        """Close the iteration from a previous successful execution.

        The source was already contacted and the findings already written, so
        doing either again would double-charge the source and could duplicate
        evidence. The recorded outcome is replayed instead, which is what makes
        "the same key never runs the tool twice" true rather than aspirational.

        The delta is empty by construction: nothing new was verified this time.
        """
        logger.info(
            "Replaying tool execution %s for investigation %s",
            previous.id,
            investigation.id,
        )
        summary = ToolResultSummary(
            executed_queries=previous.queries,
            sources=previous.sources,
            total_results=previous.total_results,
            created_candidate_ids=previous.created_candidate_ids,
            added_evidence_ids=previous.added_evidence_ids,
            result_hash=previous.result_hash or "",
        )
        after = await self._evidence_now(candidate)
        delta = calculate_evidence_delta(before, after)
        investigation.record_tool_result(
            summary,
            evidence_hash(before),
            evidence_hash(after),
            delta,
            self._clock.now(),
            tool_execution_id=previous.id,
        )
        await self._investigations.save(investigation)
        await self._uow.commit()
        await self._close_after_tool(
            investigation,
            candidate,
            delta,
            summary,
            None,
            False,
            plan.action.type,
            created=previous.created_candidate_ids,
        )

    async def _evidence_now(
        self, candidate: CandidatePublication | None
    ) -> tuple[CandidateEvidence, ...]:
        if candidate is None:
            return ()
        current = await self._repository.get_candidate(candidate.id)
        return tuple(current.evidences) if current is not None else ()

    # --- persistence of findings --------------------------------------------

    async def _persist_findings(
        self,
        investigation: ScientificReturnInvestigation,
        records: tuple[DiscoveredRecord, ...],
        candidate: CandidatePublication | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Create candidates or append evidence, each with its provenance.

        Discovery creates a candidate only when the same actionable gate the
        scheduled pipeline uses says so. Enrichment never touches the
        candidate's metadata or status: correcting a title stays a human act.
        """
        iteration = investigation.current
        assert iteration is not None
        created: list[str] = []
        added: list[str] = []
        remaining = investigation.budget.remaining_candidates

        for found in records:
            provenance = {
                "investigation_id": str(investigation.id),
                "iteration_id": str(iteration.id),
                "source_record_id": found.record.source_record_id,
                "content_hash": found.record.raw_metadata_hash,
            }
            evidences = tuple(
                _with_provenance(item, provenance) for item in found.evidences
            )
            if found.matches_candidate and candidate is not None:
                written = await self._repository.append_candidate_evidences(
                    candidate.id, evidences
                )
                added.extend(str(item.id) for item in written)
                continue
            if candidate is not None or not found.is_actionable:
                continue
            if len(created) >= remaining:
                break
            existing = await self._repository.get_candidate_by_key(
                investigation.watch_id, found.deduplication_key
            )
            if existing is not None:
                written = await self._repository.append_candidate_evidences(
                    existing.id, evidences
                )
                added.extend(str(item.id) for item in written)
                continue
            await self._repository.add_candidate(
                CandidatePublication(
                    id=found.candidate_id,
                    watch_id=investigation.watch_id,
                    first_seen_run_id=investigation.initial_run_id,
                    source=found.record.source,
                    source_record_id=found.record.source_record_id,
                    deduplication_key=found.deduplication_key,
                    doi=found.record.doi,
                    title=found.record.title,
                    authors=found.record.authors,
                    publication_date=found.record.publication_date,
                    abstract=found.record.abstract,
                    url=found.record.url,
                    raw_metadata_hash=found.record.raw_metadata_hash,
                    created_at=self._clock.now(),
                    evidences=list(evidences),
                )
            )
            created.append(str(found.candidate_id))
        return tuple(created), tuple(added)

    # --- closing -------------------------------------------------------------

    async def _close_after_tool(
        self,
        investigation: ScientificReturnInvestigation,
        candidate: CandidatePublication | None,
        delta: EvidenceDelta,
        summary: ToolResultSummary | None,
        error: str | None,
        unavailable: bool,
        action: AgentRecommendedAction | None,
        created: tuple[str, ...] = (),
    ) -> None:
        context = StopPolicyContext(
            objective=investigation.objective,
            budget=investigation.budget,
            proposed_action=None,
            tool_result=summary,
            tool_error=error,
            tool_unavailable=unavailable,
            delta=delta,
            has_reviewable_candidate=candidate is not None or bool(created),
        )
        await self._close(investigation, context, action, delta)

    async def _close(
        self,
        investigation: ScientificReturnInvestigation,
        context: StopPolicyContext,
        action: AgentRecommendedAction | None,
        delta: EvidenceDelta,
    ) -> None:
        reflection = await self._reflect(investigation, context, action, delta)
        investigation.record_reflection(reflection)
        decision = self._stop_policy.decide(context)
        now = self._clock.now()
        if decision.awaiting_human_review:
            investigation.present_for_review(decision.reason, now)
        else:
            investigation.stop(decision.reason, now)
        await self._investigations.save(investigation)
        await self._uow.commit()

    async def _reflect(
        self,
        investigation: ScientificReturnInvestigation,
        context: StopPolicyContext,
        action: AgentRecommendedAction | None,
        delta: EvidenceDelta,
    ) -> AgentReflection:
        iteration = investigation.current
        plan = iteration.plan if iteration else None
        try:
            result = await self._reasoner.reflect(
                ReflectionContext(
                    objective=investigation.objective,
                    iteration_objective=plan.objective if plan else "-",
                    action=action or AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE,
                    delta=delta,
                    budget=investigation.budget,
                    executed_queries=(
                        context.tool_result.executed_queries
                        if context.tool_result
                        else ()
                    ),
                    sources=(
                        context.tool_result.sources if context.tool_result else ()
                    ),
                    total_results=(
                        context.tool_result.total_results if context.tool_result else 0
                    ),
                    created_candidates=(
                        len(context.tool_result.created_candidate_ids)
                        if context.tool_result
                        else 0
                    ),
                    policy_rejection=(
                        context.decision.rejection_reason.value
                        if context.decision and context.decision.rejection_reason
                        else None
                    ),
                    tool_error=context.tool_error,
                )
            )
            iteration = investigation.current
            if iteration is not None and iteration.telemetry is not None:
                iteration.telemetry = iteration.telemetry.with_reflection(
                    result.call.latency_ms, result.call.response_hash
                )
            return result.reflection
        except Exception:
            # A commentary failure must not block the human queue: the delta is
            # already measured, so the reflection can be derived from it.
            logger.warning(
                "Reflection unavailable for %s; using the deterministic fallback",
                investigation.id,
            )
            return AgentReflection.deterministic_fallback(delta)

    async def _fail(
        self,
        investigation: ScientificReturnInvestigation,
        reason: StopReason,
        message: str,
    ) -> None:
        if investigation.is_terminal:
            return
        investigation.fail(reason, message, self._clock.now())
        await self._investigations.save(investigation)
        await self._uow.commit()

    async def _finish_tool(
        self, record: ToolExecutionRecord, *, error: str
    ) -> None:
        record.succeeded = False
        record.error_message = error[:2000]
        record.completed_at = self._clock.now()
        await self._investigations.save_tool_execution(record)
        await self._uow.commit()

    # --- loading -------------------------------------------------------------

    async def _load(
        self, data: RunInvestigationInput
    ) -> tuple[
        ScientificReturnWatch,
        ScientificReturnProjectSnapshot,
        CandidatePublication | None,
    ]:
        watch = await self._repository.get_watch(data.watch_id)
        if watch is None:
            raise InvestigationNotPossible(f"Watch {data.watch_id} not found")
        if watch.status is not WatchStatus.ACTIVE:
            raise InvestigationNotPossible("Only an active watch can be investigated")
        snapshot = await self._repository.get_snapshot_for_watch(data.watch_id)
        if snapshot is None:
            raise InvestigationNotPossible("The watch snapshot is missing")

        candidate: CandidatePublication | None = None
        if data.objective is InvestigationObjective.ENRICH_CANDIDATE:
            if data.candidate_id is None:
                raise InvestigationNotPossible("Enrichment requires a candidate")
            candidate = await self._repository.get_candidate(data.candidate_id)
            if candidate is None:
                raise InvestigationNotPossible(
                    f"Candidate {data.candidate_id} not found"
                )
            if candidate.status is not CandidateStatus.PENDING:
                raise InvestigationNotPossible(
                    "Only a pending candidate can be enriched"
                )
        return watch, snapshot, candidate

    async def _observe(
        self,
        investigation: ScientificReturnInvestigation,
        snapshot: ProjectSnapshotPayload,
        candidate: CandidatePublication | None,
    ) -> AgentObservation:
        queries = await self._repository.list_queries_for_watch(
            investigation.watch_id
        )
        objects = tuple(
            ObservedObject(
                object_id=item.id,
                inventory_number=item.inventory_number,
                object_name=item.object_name,
            )
            for item in snapshot.consulted_objects
        )
        observed_candidate = (
            None
            if candidate is None
            else ObservedCandidate(
                candidate_id=str(candidate.id),
                title=candidate.title,
                doi=candidate.doi,
                verified_evidence_types=tuple(
                    dict.fromkeys(item.type for item in candidate.evidences)
                ),
            )
        )
        return AgentObservation(
            objective=investigation.objective,
            project_reference=snapshot.project_reference,
            researcher=snapshot.researcher,
            objects=objects,
            tried_queries=tuple(dict.fromkeys(item.query_text for item in queries)),
            allowed_actions=tuple(sorted(self._config.allowed_actions))
            + (
                AgentRecommendedAction.PRESENT_FOR_REVIEW,
                AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE,
            ),
            budget=investigation.budget,
            candidate=observed_candidate,
        )


def _with_provenance(
    evidence: CandidateEvidence, provenance: dict[str, str]
) -> CandidateEvidence:
    evidence.investigation_id = provenance["investigation_id"]
    evidence.iteration_id = provenance["iteration_id"]
    evidence.source_record_id = provenance["source_record_id"]
    evidence.content_hash = provenance["content_hash"]
    return evidence
