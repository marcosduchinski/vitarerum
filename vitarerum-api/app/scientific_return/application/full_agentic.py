from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import uuid4

from app.identity.public import Actor, GroupName
from app.scientific_return.application.agent_tools import (
    normalized_tool_idempotency_key,
)
from app.scientific_return.application.analysis import deduplication_key
from app.scientific_return.application.full_agentic_grounding import (
    ground_article_assessment,
)
from app.scientific_return.application.full_agentic_ports import (
    AgenticInvestigationDispatcher,
    AgenticPlan,
    AssessmentResult,
    FullAgenticClock,
    FullAgenticReasoner,
    FullAgenticRepository,
    FullAgenticUnitOfWork,
    InvestigationConcurrencyConflict,
)
from app.scientific_return.application.full_agentic_strategy import (
    bibliographic_surname_hypotheses,
    deterministic_floor,
    search_is_supported,
    source_result_limit,
    suggested_inventory_variants,
)
from app.scientific_return.application.knowledge import retrieve_relevant_knowledge
from app.scientific_return.application.ports import (
    AgentReasonerTimeout,
    BibliographicRecord,
    BibliographicSource,
    BibliographicSourceCapabilities,
    ScientificReturnRepository,
    SourceWaitBudgetExceeded,
)
from app.scientific_return.application.run_deadline import RunDeadline
from app.scientific_return.domain.enums import (
    AgentAnalysisStatus,
    AgenticCandidateRelationKind,
    AgenticToolExecutionStatus,
    AgenticTrajectoryEventKind,
    AgentRecommendedAction,
    CandidateStatus,
    FullAgenticInvestigationStatus,
    InvestigationObjective,
    QueryStatus,
    QueryType,
    RunKind,
    RunStatus,
    SearchIntent,
    SearchStrategy,
)
from app.scientific_return.domain.full_agentic_models import (
    AgenticBudget,
    AgenticBudgetExhausted,
    AgenticCandidateLink,
    AgenticSearchSpec,
    AgenticToolExecution,
    AgenticToolExecutionId,
    AgenticTrajectoryEvent,
    AgenticTrajectoryEventId,
    AgenticUsage,
    FullAgenticInvestigation,
    FullAgenticInvestigationId,
)
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateAnalysisResult,
    CandidatePublication,
    CandidatePublicationId,
    ProjectSnapshotPayload,
    ScientificReturnQuery,
    ScientificReturnQueryId,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnWatchId,
)
from app.scientific_return.domain.publication_identity import (
    is_component,
    publication_identity,
)
from app.shared.authorization import require_group, require_staff

logger = logging.getLogger(__name__)

_MUTATION_GROUPS = (
    GroupName.CURATORIAL,
    GroupName.COLLECTIONS_MANAGEMENT,
    GroupName.DIRECTION,
)


def _string_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


# Named in the trajectory when the plan came from the deterministic floor,
# where no prompt and no model were involved.
_DETERMINISTIC_FLOOR_CONTRACT = "deterministic-floor"


class FullAgenticDisabled(RuntimeError):
    pass


class FullAgenticAlreadyRunning(RuntimeError):
    pass


class FullAgenticCircuitOpen(RuntimeError):
    pass


class FullAgenticSourceConfigurationInvalid(RuntimeError):
    pass


class _InvestigationLeaseLost(RuntimeError):
    pass


class _SliceExhausted(RuntimeError):
    """The worker ran out of slice where it could not simply return a value."""


@dataclass(frozen=True, slots=True)
class FullAgenticConfiguration:
    enabled: bool
    allowed_sources: tuple[str, ...]
    budget: AgenticBudget
    memory_limit: int = 30
    tool_lease_seconds: int = 120
    investigation_lease_seconds: int = 900
    circuit_min_decisions: int = 0
    circuit_min_precision: float = 0.0
    operational_sources: tuple[str, ...] | None = None
    evidence_sources: tuple[str, ...] | None = None
    # Every external call must be able to finish inside the lease, and a whole
    # worker slice must finish before the platform's own window closes. The
    # nesting is checked here rather than trusted to whoever writes the
    # environment, because getting it wrong produces exactly the failure the
    # deadlines exist to prevent: a process killed mid-call, with the work
    # neither finished nor accounted for.
    llm_total_timeout_seconds: float = 300.0
    source_total_timeout_seconds: float = 120.0
    run_deadline_seconds: float = 1500.0
    # The platform's own timeout for one worker process, which the application
    # cannot observe and must therefore be told.
    platform_window_seconds: float = 1800.0
    max_objects: int = 15
    max_recoveries: int = 3
    max_age_seconds: int = 86400

    def __post_init__(self) -> None:
        if self.circuit_min_decisions < 0:
            raise ValueError("Circuit-breaker sample cannot be negative")
        if not 0.0 <= self.circuit_min_precision <= 1.0:
            raise ValueError("Circuit-breaker precision must be between zero and one")
        if self.investigation_lease_seconds < 60:
            raise ValueError("Investigation lease must be at least 60 seconds")
        if self.max_objects < 1:
            raise ValueError("At least one consulted object must be investigated")
        if self.max_recoveries < 0:
            raise ValueError("Recovery ceiling cannot be negative")
        if self.max_age_seconds <= 0:
            raise ValueError("Investigation age ceiling must be positive")
        longest_call = max(
            self.llm_total_timeout_seconds, self.source_total_timeout_seconds
        )
        if longest_call >= self.investigation_lease_seconds:
            raise ValueError(
                "The longest external call must finish inside the investigation "
                f"lease: {longest_call:.0f}s call against a "
                f"{self.investigation_lease_seconds}s lease"
            )
        if self.run_deadline_seconds <= self.investigation_lease_seconds:
            raise ValueError(
                "The worker slice must outlast one lease renewal: "
                f"{self.run_deadline_seconds:.0f}s slice against a "
                f"{self.investigation_lease_seconds}s lease"
            )
        # A slice that outlives the platform's window is not a longer slice: the
        # process is killed before it can hand its work back, every run then
        # reads as a recovery, and enough of them end a healthy investigation as
        # poisoned. The last operation may start with exactly its own timeout
        # left, so the window must hold the slice plus one full call.
        if self.platform_window_seconds < self.run_deadline_seconds + longest_call:
            raise ValueError(
                "The worker slice must finish inside the platform window: "
                f"{self.run_deadline_seconds:.0f}s slice plus a "
                f"{longest_call:.0f}s call against a "
                f"{self.platform_window_seconds:.0f}s window"
            )

    def validate_operational_sources(self) -> None:
        if not self.allowed_sources:
            raise FullAgenticSourceConfigurationInvalid(
                "No bibliographic source is allowed"
            )
        if self.operational_sources is None:
            return
        operational = {item.upper() for item in self.operational_sources}
        requested = {item.upper() for item in self.allowed_sources}
        available = requested & operational
        if not available:
            unavailable = ", ".join(sorted(requested - operational)) or "none"
            raise FullAgenticSourceConfigurationInvalid(
                "No requested bibliographic source is operational; unavailable: "
                f"{unavailable}"
            )
        evidence = {item.upper() for item in (self.evidence_sources or ())}
        if not (available & evidence):
            raise FullAgenticSourceConfigurationInvalid(
                "No operational source can return inspectable inventory text"
            )

    def source_diagnostics(self) -> dict[str, object]:
        requested = {item.upper() for item in self.allowed_sources}
        operational = {
            item.upper() for item in (self.operational_sources or self.allowed_sources)
        }
        evidence = {item.upper() for item in (self.evidence_sources or ())}
        available = requested & operational
        message: str | None = None
        valid = True
        try:
            self.validate_operational_sources()
        except FullAgenticSourceConfigurationInvalid as exc:
            valid = False
            message = str(exc)
        return {
            "enabled": self.enabled,
            "requestedSources": sorted(requested),
            "operationalSources": sorted(available),
            "unavailableSources": sorted(requested - operational),
            "inspectableEvidenceSources": sorted(available & evidence),
            "configurationValid": valid,
            "message": message,
        }


@dataclass(frozen=True, slots=True)
class StartFullAgenticInput:
    watch_id: ScientificReturnWatchId
    objective: InvestigationObjective
    candidate_id: CandidatePublicationId | None
    idempotency_key: str
    caller: Actor
    # Which consulted object to investigate. ``None`` keeps the older shape, in
    # which one investigation covered the whole project.
    object_id: str | None = None


class StartFullAgenticScientificReturn:
    def __init__(
        self,
        scientific_repository: ScientificReturnRepository,
        repository: FullAgenticRepository,
        dispatcher: AgenticInvestigationDispatcher,
        unit_of_work: FullAgenticUnitOfWork,
        clock: FullAgenticClock,
        configuration: FullAgenticConfiguration,
    ) -> None:
        self._scientific_repository = scientific_repository
        self._repository = repository
        self._dispatcher = dispatcher
        self._uow = unit_of_work
        self._clock = clock
        self._configuration = configuration

    async def execute(self, data: StartFullAgenticInput) -> FullAgenticInvestigation:
        require_group(data.caller, *_MUTATION_GROUPS)
        return await self._start(data)

    async def execute_scheduled(
        self, data: StartFullAgenticInput
    ) -> FullAgenticInvestigation:
        """Queue an investigation from the scheduled sweep, with no human caller.

        The authorisation check is the only thing skipped. Every other guard —
        the feature switch, the operational-source check, the circuit breaker
        and the live-target check — still applies, because those are what keep
        an unattended sweep from spending a budget it should not.
        """
        return await self._start(data)

    async def _start(self, data: StartFullAgenticInput) -> FullAgenticInvestigation:
        existing = await self._repository.get_by_idempotency_key(data.idempotency_key)
        if existing is not None:
            if (
                existing.watch_id != data.watch_id
                or existing.objective is not data.objective
                or existing.candidate_id != data.candidate_id
                or existing.object_id != data.object_id
            ):
                raise ValueError(
                    "Idempotency-Key is already bound to another full-agentic target"
                )
            return existing
        if (
            data.objective is not InvestigationObjective.DISCOVER_CANDIDATE
            or data.candidate_id is not None
        ):
            raise ValueError(
                "The full-agentic flow currently supports only DISCOVER_CANDIDATE"
            )
        if not self._configuration.enabled:
            raise FullAgenticDisabled("The full-agentic flow is disabled")
        self._configuration.validate_operational_sources()
        minimum = self._configuration.circuit_min_decisions
        if minimum:
            metrics = await self._scientific_repository.get_metrics()
            decided = (
                metrics.full_agentic_confirmed_candidates
                + metrics.full_agentic_dismissed_candidates
            )
            precision = (
                metrics.full_agentic_confirmed_candidates / decided if decided else 1.0
            )
            if (
                decided >= minimum
                and precision < self._configuration.circuit_min_precision
            ):
                raise FullAgenticCircuitOpen(
                    "New autonomous investigations are paused because curator "
                    f"precision is {precision:.1%} over {decided} decided candidates"
                )
        watch = await self._scientific_repository.get_watch(data.watch_id)
        if watch is None:
            raise LookupError(f"Scientific-return watch {data.watch_id} not found")
        if (
            data.caller.institution_id is not None
            and watch.institution_id is not None
            and data.caller.institution_id != watch.institution_id
        ):
            raise ValueError("Scientific-return watch belongs to another institution")
        if data.candidate_id is not None:
            candidate = await self._scientific_repository.get_candidate(
                data.candidate_id
            )
            if candidate is None or candidate.watch_id != data.watch_id:
                raise ValueError("candidateId does not belong to the watch")
        if data.object_id is not None:
            # Checked against the snapshot, not the live project: the snapshot
            # is what the investigation will actually read.
            snapshot = await self._scientific_repository.get_snapshot_for_watch(
                data.watch_id
            )
            if snapshot is None:
                raise RuntimeError("Watch snapshot is missing")
            if data.object_id not in {
                item.id for item in snapshot.payload.consulted_objects
            }:
                raise ValueError("objectId is not a consulted object of this watch")
        live = await self._repository.find_live_target(
            str(data.watch_id),
            data.objective.value,
            str(data.candidate_id) if data.candidate_id else None,
            data.object_id,
        )
        if live is not None:
            raise FullAgenticAlreadyRunning(
                f"Investigation {live.id} is already live for this target"
            )
        investigation = FullAgenticInvestigation(
            id=FullAgenticInvestigationId(str(uuid4())),
            watch_id=data.watch_id,
            objective=data.objective,
            candidate_id=data.candidate_id,
            object_id=data.object_id,
            status=FullAgenticInvestigationStatus.QUEUED,
            idempotency_key=data.idempotency_key,
            budget=self._configuration.budget,
            usage=AgenticUsage(),
            created_by=data.caller.id,
            created_at=self._clock.now(),
            institution_id=watch.institution_id or data.caller.institution_id,
        )
        await self._repository.add_investigation(investigation)
        await self._uow.commit()
        try:
            await self._dispatcher.enqueue(investigation.id)
        except Exception:
            # The durable QUEUED row remains claimable by a polling worker.
            raise
        return investigation


async def close_envelope_run(
    scientific_repository: ScientificReturnRepository,
    investigation: FullAgenticInvestigation,
    reason: str,
    now: datetime,
) -> None:
    """Close the search run an ending investigation left open.

    The envelope is only completed on the normal path, so every other ending —
    a crash, an exhausted recovery allowance, the age reaper — used to leave a
    run RUNNING for good. A yielded slice is the one case that must stay open,
    because the investigation it belongs to has not ended.
    """
    if investigation.search_run_id is None:
        return
    run = await scientific_repository.get_run(investigation.search_run_id)
    if run is None or run.status is not RunStatus.RUNNING:
        return
    run.status = RunStatus.FAILED
    run.completed_at = now
    run.error_message = reason[:2000]
    await scientific_repository.save_run(run)


def snapshot_for_object(
    payload: ProjectSnapshotPayload, object_id: str | None
) -> ProjectSnapshotPayload:
    """The snapshot as one investigation sees it.

    An investigation targets a single consulted object, so it sees a snapshot
    of that object alone: the floor spends its whole reservation on it, the
    curatorial memory is looked up by its inventory number only, and the
    planner's prompt stops growing with the size of the project — fifteen
    objects used to send fifteen objects and a hundred and fifty inventory
    variants into a single call.

    ``None`` keeps the older shape, where one investigation covered the whole
    project, so investigations queued before this existed still run.
    """
    if object_id is None:
        return payload
    objects = tuple(item for item in payload.consulted_objects if item.id == object_id)
    if not objects:
        raise RuntimeError(
            f"Object {object_id} is no longer in the watch snapshot; "
            "the snapshot was rebuilt without it"
        )
    return replace(payload, consulted_objects=objects)


def one_record_per_publication(
    records: list[tuple[BibliographicRecord, AgenticSearchSpec]],
) -> tuple[list[tuple[BibliographicRecord, AgenticSearchSpec]], int]:
    """Collapse the parts of a publication onto the publication.

    Indexes register figures and tables as works of their own, so one article
    could occupy the whole candidate ceiling with its own components — and the
    ceiling stops the search, so those near-duplicates displaced candidates that
    were never looked for. A component only holds its group's place until the
    work itself appears, so a publication that surfaces only through a figure is
    still presented rather than lost.
    """
    groups: dict[str, tuple[BibliographicRecord, AgenticSearchSpec]] = {}
    order: list[str] = []
    collapsed = 0
    for record, search in records:
        identity = publication_identity(
            record.doi, record.title, deduplication_key(record)
        )
        if identity not in groups:
            groups[identity] = (record, search)
            order.append(identity)
            continue
        collapsed += 1
        kept, _ = groups[identity]
        if is_component(kept.doi, kept.title) and not is_component(
            record.doi, record.title
        ):
            groups[identity] = (record, search)
    return [groups[identity] for identity in order], collapsed


class CloseAbandonedFullAgenticInvestigations:
    """Terminate live rows that have outlived their age ceiling.

    The recovery counter ends a row that keeps being taken over; this ends the
    ones nothing takes over at all — a queued row whose dispatch was lost, a
    cancellation nobody ever claimed. Both matter for the same reason: a live
    row blocks every future investigation of the same target, so an
    investigation that cannot finish must at least stop being live.
    """

    def __init__(
        self,
        repository: FullAgenticRepository,
        scientific_repository: ScientificReturnRepository,
        unit_of_work: FullAgenticUnitOfWork,
        clock: FullAgenticClock,
        max_age: timedelta,
    ) -> None:
        self._repository = repository
        self._scientific_repository = scientific_repository
        self._uow = unit_of_work
        self._clock = clock
        self._max_age = max_age

    async def execute(self, *, limit: int) -> int:
        now = self._clock.now()
        abandoned = await self._repository.list_abandoned(now - self._max_age, limit)
        closed = 0
        for investigation in abandoned:
            if investigation.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED:
                investigation.cancel(now)
                reason = "Cancellation was never claimed by a worker"
            else:
                investigation.fail(
                    "The investigation outlived its age ceiling without finishing",
                    now,
                )
                reason = investigation.failure_reason or ""
            investigation.lease_owner = None
            investigation.lease_expires_at = None
            try:
                await self._repository.save_investigation(investigation)
                await close_envelope_run(
                    self._scientific_repository, investigation, reason, now
                )
                await self._append_terminal_event(investigation, reason)
                await self._uow.commit()
            except InvestigationConcurrencyConflict:
                # A worker picked it up between the listing and the write. Its
                # own guards apply from here; nothing is lost by leaving it.
                await self._uow.rollback()
                continue
            closed += 1
        return closed

    async def _append_terminal_event(
        self, investigation: FullAgenticInvestigation, reason: str
    ) -> None:
        sequence = await self._repository.next_event_sequence(investigation.id)
        await self._repository.append_event(
            AgenticTrajectoryEvent(
                id=AgenticTrajectoryEventId(str(uuid4())),
                investigation_id=investigation.id,
                sequence=sequence,
                kind=AgenticTrajectoryEventKind.ABANDONED,
                payload={
                    "status": investigation.status.value,
                    "reason": reason,
                    "recoveryCount": investigation.recovery_count,
                },
                occurred_at=self._clock.now(),
            )
        )


@dataclass(frozen=True, slots=True)
class ExecuteFullAgenticInput:
    investigation_id: FullAgenticInvestigationId
    worker_id: str


class ExecuteFullAgenticScientificReturn:
    def __init__(
        self,
        scientific_repository: ScientificReturnRepository,
        repository: FullAgenticRepository,
        reasoner: FullAgenticReasoner,
        sources: tuple[BibliographicSource, ...],
        unit_of_work: FullAgenticUnitOfWork,
        clock: FullAgenticClock,
        configuration: FullAgenticConfiguration,
        deadline: RunDeadline | None = None,
        dispatcher: AgenticInvestigationDispatcher | None = None,
    ) -> None:
        self._scientific_repository = scientific_repository
        self._repository = repository
        self._reasoner = reasoner
        self._sources = {source.name.upper(): source for source in sources}
        self._capabilities = {
            name: self._source_capabilities(source)
            for name, source in self._sources.items()
        }
        self._uow = unit_of_work
        self._clock = clock
        self._configuration = configuration
        # Without one, the only clock is the platform's, and reaching it means
        # being killed rather than stopping.
        self._deadline = deadline
        # Only needed to announce a continuation. The durable QUEUED row is the
        # real queue; this is what tells a push-based worker it exists.
        self._dispatcher = dispatcher

    def _has_room_for(self, seconds: float) -> bool:
        return self._deadline is None or self._deadline.allows(seconds)

    async def execute(self, data: ExecuteFullAgenticInput) -> FullAgenticInvestigation:
        investigation = await self._repository.get_investigation(data.investigation_id)
        if investigation is None:
            raise LookupError(f"Investigation {data.investigation_id} not found")
        if investigation.status.is_terminal:
            return investigation
        now = self._clock.now()
        investigation = await self._repository.claim_investigation(
            data.investigation_id,
            data.worker_id,
            now,
            now + timedelta(seconds=self._configuration.investigation_lease_seconds),
        )
        await self._uow.commit()
        if investigation is None:
            current = await self._repository.get_investigation(data.investigation_id)
            if current is None:
                raise LookupError(f"Investigation {data.investigation_id} not found")
            return current
        if investigation.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED:
            investigation.cancel(now)
            await self._repository.save_investigation(investigation)
            await close_envelope_run(
                self._scientific_repository,
                investigation,
                "The investigation was cancelled before this run could continue",
                now,
            )
            await self._uow.commit()
            return investigation
        if investigation.recoveries_exhausted(self._configuration.max_recoveries):
            # Checked here rather than only in the reaper: a Cloud Tasks worker
            # calls straight into this use case, and must not be able to start a
            # run the sweep would have refused.
            investigation.fail(
                "The investigation was recovered "
                f"{investigation.recovery_count} times without finishing",
                now,
            )
            investigation.lease_owner = None
            investigation.lease_expires_at = None
            await self._repository.save_investigation(investigation)
            await close_envelope_run(
                self._scientific_repository,
                investigation,
                investigation.failure_reason or "",
                now,
            )
            await self._append_event(
                investigation,
                AgenticTrajectoryEventKind.RECOVERY_LIMIT_EXHAUSTED,
                {
                    "recoveryCount": investigation.recovery_count,
                    "maxRecoveries": self._configuration.max_recoveries,
                    "lastRecoveryReason": investigation.last_recovery_reason,
                },
            )
            await self._uow.commit()
            return investigation
        try:
            await self._run(investigation)
        except _InvestigationLeaseLost:
            await self._uow.rollback()
            current = await self._repository.get_investigation(investigation.id)
            if current is None:
                raise LookupError(
                    f"Investigation {investigation.id} not found"
                ) from None
            if current.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED:
                now = self._clock.now()
                current.cancel(now)
                try:
                    await self._repository.save_investigation(current)
                    await close_envelope_run(
                        self._scientific_repository,
                        current,
                        "The investigation was cancelled while a worker held it",
                        now,
                    )
                    await self._uow.commit()
                except InvestigationConcurrencyConflict:
                    await self._uow.rollback()
                    latest = await self._repository.get_investigation(investigation.id)
                    if latest is not None:
                        return latest
            return current
        except Exception as exc:
            await self._uow.rollback()
            current = await self._repository.get_investigation(investigation.id)
            if current is not None and not current.status.is_terminal:
                now = self._clock.now()
                if current.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED:
                    current.cancel(now)
                else:
                    current.fail(f"{type(exc).__name__}: {exc}", now)
                try:
                    await self._repository.save_investigation(current)
                    await close_envelope_run(
                        self._scientific_repository,
                        current,
                        f"{type(exc).__name__}: {exc}",
                        now,
                    )
                    await self._append_event(
                        current,
                        AgenticTrajectoryEventKind.ERROR,
                        {"message": str(exc)[:2000]},
                    )
                    await self._uow.commit()
                    return current
                except InvestigationConcurrencyConflict:
                    await self._uow.rollback()
                    latest = await self._repository.get_investigation(investigation.id)
                    if latest is not None:
                        return latest
            raise
        return investigation

    async def _run(self, investigation: FullAgenticInvestigation) -> None:
        snapshot = await self._scientific_repository.get_snapshot_for_watch(
            investigation.watch_id
        )
        if snapshot is None:
            raise RuntimeError("Watch snapshot is missing")
        payload = snapshot_for_object(snapshot.payload, investigation.object_id)
        inventories = tuple(item.inventory_number for item in payload.consulted_objects)
        # Legacy investigations without an institutional owner must never fall
        # back to a cross-institution knowledge corpus.
        memory = (
            await retrieve_relevant_knowledge(
                self._repository,
                inventories,
                limit=self._configuration.memory_limit,
                institution_id=investigation.institution_id,
            )
            if investigation.institution_id is not None
            else ()
        )
        existing_events = await self._repository.list_events(investigation.id)
        if not any(
            event.kind is AgenticTrajectoryEventKind.MEMORY_RETRIEVED
            for event in existing_events
        ):
            for item in memory:
                await self._repository.add_knowledge_usage(
                    str(investigation.id), str(item.id), "PLANNER", self._clock.now()
                )
            await self._append_event(
                investigation,
                AgenticTrajectoryEventKind.MEMORY_RETRIEVED,
                {"knowledgeItemIds": [str(item.id) for item in memory]},
            )
        if investigation.search_run_id is not None:
            existing_run = await self._scientific_repository.get_run(
                investigation.search_run_id
            )
            if existing_run is None:
                raise RuntimeError("Full-agentic envelope run is missing")
            run = existing_run
        else:
            run = ScientificReturnSearchRun(
                id=ScientificReturnRunId(str(uuid4())),
                watch_id=investigation.watch_id,
                status=RunStatus.RUNNING,
                started_at=self._clock.now(),
                run_kind=RunKind.FULL_AGENTIC,
            )
            await self._scientific_repository.add_run(run)
            investigation.search_run_id = run.id
            await self._repository.save_investigation(investigation)
            await self._uow.commit()

        history: list[dict[str, object]] = [
            event.payload
            for event in existing_events
            if event.kind is AgenticTrajectoryEventKind.PLAN_CREATED
        ]
        observation: dict[str, object] = {
            "projectReference": payload.project_reference,
            "researcher": payload.researcher,
            "suggestedAuthorHypotheses": list(
                bibliographic_surname_hypotheses(payload.researcher)
            ),
            "objects": [
                {
                    "id": item.id,
                    "inventoryNumber": item.inventory_number,
                    "objectName": item.object_name,
                }
                for item in payload.consulted_objects
            ],
            "suggestedInventoryVariants": suggested_inventory_variants(payload),
            "sourceCapabilities": [
                item.as_prompt_payload() for item in self._capabilities.values()
            ],
        }
        seen_records: set[str] = {
            f"{event.payload.get('source')}|{event.payload.get('sourceRecordId')}"
            for event in existing_events
            if event.kind is AgenticTrajectoryEventKind.ARTICLE_ASSESSED
            or (
                event.kind is AgenticTrajectoryEventKind.ERROR
                and event.payload.get("phase") == "ARTICLE_ASSESSMENT"
            )
        }
        # A resumed pass must not present a figure of an article it already read.
        seen_publications: set[str] = {
            str(event.payload["publicationIdentity"])
            for event in existing_events
            if event.kind is AgenticTrajectoryEventKind.ARTICLE_ASSESSED
            and event.payload.get("publicationIdentity")
        }
        executed_sources: set[str] = set()
        executed_attempts: set[tuple[str, str, str]] = set()
        for event in existing_events:
            if event.kind is not AgenticTrajectoryEventKind.TOOL_COMPLETED:
                continue
            executed_attempts.add(
                self._attempt_identity(
                    source=str(event.payload.get("source", "")),
                    query=str(event.payload.get("query", "")),
                    author=(
                        str(event.payload["author"])
                        if event.payload.get("author")
                        else None
                    ),
                    intent=(
                        SearchIntent(str(event.payload["intent"]))
                        if event.payload.get("intent")
                        else SearchIntent.DISCOVERY
                    ),
                )
            )
        new_candidate_count = sum(
            1
            for event in existing_events
            if event.kind is AgenticTrajectoryEventKind.CANDIDATE_LINKED
            and event.payload.get("relationKind")
            == AgenticCandidateRelationKind.CREATED.value
        )
        # The floor is a bounded reservation, never the whole budget: a project
        # with many consulted objects must still leave the planner queries to
        # spend, so it takes at most half the global ceiling. It covers both
        # author+object and the bare inventory code, because a planner contract
        # failure must not cost the highest-yield strategy of this domain.
        floor_reservation = max(1, investigation.budget.max_queries // 2)
        floor_searches = deterministic_floor(
            payload,
            tuple(self._capabilities.values()),
            floor_reservation,
        )

        for iteration in range(1, investigation.budget.max_iterations + 1):
            fresh = await self._repository.get_investigation(investigation.id)
            if (
                fresh
                and fresh.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED
            ):
                investigation.status = fresh.status
                investigation.cancel(self._clock.now())
                break
            remaining_queries = (
                investigation.budget.max_queries - investigation.usage.queries
            )
            remaining_llm = (
                investigation.budget.max_llm_calls - investigation.usage.llm_calls
            )
            if remaining_queries <= 0 or remaining_llm <= 0:
                break
            # An iteration is a model call plus a source call at worst. Starting
            # one that cannot finish inside the slice is how a worker ends up
            # killed by the platform instead of stopping on its own terms.
            if not self._has_room_for(
                self._configuration.llm_total_timeout_seconds
                + self._configuration.source_total_timeout_seconds
            ):
                await self._yield_slice(investigation, run, iteration)
                return
            persisted_plan = next(
                (
                    event
                    for event in existing_events
                    if event.kind is AgenticTrajectoryEventKind.PLAN_CREATED
                    and event.payload.get("iteration") == iteration
                ),
                None,
            )
            if persisted_plan is not None:
                persisted_payload = persisted_plan.payload
                plan = AgenticPlan(
                    searches=self._searches_from_payload(persisted_payload),
                    reasoning=str(persisted_payload.get("reasoning", "")),
                    should_stop=bool(persisted_payload.get("shouldStop", False)),
                )
            else:
                if iteration == 1 and floor_searches:
                    plan = AgenticPlan(
                        searches=floor_searches[:remaining_queries],
                        reasoning=(
                            "Deterministic floor: bare inventory code and "
                            "author plus object; reserved "
                            f"{floor_reservation} of "
                            f"{investigation.budget.max_queries} queries"
                        ),
                    )
                    investigation.usage = replace(
                        investigation.usage,
                        iterations=iteration,
                    )
                else:
                    # No separate lease renewal: reserving the call renews it,
                    # so the two cannot disagree about who holds the row.
                    try:
                        plan = await self._plan_with_retry(
                            investigation,
                            observation=observation,
                            memory=tuple(item.as_prompt_example() for item in memory),
                            history=tuple(history),
                            remaining_queries=remaining_queries,
                            iteration=iteration,
                        )
                    except _SliceExhausted:
                        await self._yield_slice(investigation, run, iteration)
                        return
                await self._append_event(
                    investigation,
                    AgenticTrajectoryEventKind.PLAN_CREATED,
                    {
                        "iteration": iteration,
                        # The published planner prompt names itself, so the
                        # trajectory records the version that actually ran
                        # instead of a literal that drifts on the next publish.
                        # The floor produces a plan with no prompt at all.
                        "contractVersion": (
                            plan.prompt_version or _DETERMINISTIC_FLOOR_CONTRACT
                        ),
                        "promptVersionId": plan.prompt_version_id,
                        "searches": [
                            self._search_payload(search) for search in plan.searches
                        ],
                        "reasoning": plan.reasoning,
                        "shouldStop": plan.should_stop,
                    },
                )
            if plan.should_stop:
                break
            records = await self._execute_searches(
                investigation,
                run,
                iteration,
                plan.searches,
                executed_sources,
                executed_attempts,
            )
            records, collapsed = one_record_per_publication(records)
            if collapsed:
                await self._append_event(
                    investigation,
                    AgenticTrajectoryEventKind.COMPONENTS_COLLAPSED,
                    {"iteration": iteration, "collapsedRecords": collapsed},
                )
            relevant_count = 0
            for record, search in records:
                key = f"{record.source}|{record.source_record_id}"
                if key in seen_records:
                    continue
                identity = publication_identity(
                    record.doi, record.title, deduplication_key(record)
                )
                if identity in seen_publications:
                    continue
                seen_records.add(key)
                seen_publications.add(identity)
                if not self._has_room_for(
                    self._configuration.llm_total_timeout_seconds
                ):
                    await self._yield_slice(investigation, run, iteration)
                    return
                try:
                    await self._reserve_llm_call(
                        investigation,
                        phase="ARTICLE_ASSESSMENT",
                        iteration=iteration,
                        subject=f"{record.source}|{record.source_record_id}",
                    )
                except AgenticBudgetExhausted:
                    break
                started_at = self._clock.now()
                try:
                    assessment_result = await self._reasoner.assess(
                        record=record,
                        trusted_context={
                            **observation,
                            "query": search.query,
                            "searchIntent": search.intent.value,
                            "searchStrategy": search.strategy.value,
                            "curatorialMemory": [
                                item.as_prompt_example() for item in memory
                            ],
                        },
                    )
                except Exception as exc:
                    await self._record_llm_outcome(
                        investigation,
                        exc,
                        phase="ARTICLE_ASSESSMENT",
                        iteration=iteration,
                        subject=f"{record.source}|{record.source_record_id}",
                        started_at=started_at,
                    )
                    await self._append_event(
                        investigation,
                        AgenticTrajectoryEventKind.ERROR,
                        {
                            "phase": "ARTICLE_ASSESSMENT",
                            "source": record.source,
                            "sourceRecordId": record.source_record_id,
                            "message": f"{type(exc).__name__}: {exc}"[:2000],
                        },
                    )
                    await self._repository.save_investigation(investigation)
                    await self._uow.commit()
                    continue
                await self._record_llm_outcome(
                    investigation,
                    None,
                    phase="ARTICLE_ASSESSMENT",
                    iteration=iteration,
                    subject=f"{record.source}|{record.source_record_id}",
                    started_at=started_at,
                )
                grounded = ground_article_assessment(
                    assessment_result.assessment,
                    record,
                    self._capabilities.get(record.source.upper()),
                )
                assessment = grounded.assessment
                await self._append_event(
                    investigation,
                    AgenticTrajectoryEventKind.ARTICLE_ASSESSED,
                    {
                        "source": record.source,
                        "sourceRecordId": record.source_record_id,
                        "relevant": assessment.relevant,
                        "confidence": assessment.confidence.value,
                        "explanation": assessment.explanation,
                        "passages": list(assessment.passages),
                        "inventoryForms": list(assessment.inventory_forms),
                        "contradictions": list(assessment.contradictions),
                        "query": search.query,
                        "author": search.author,
                        "objectId": search.object_id,
                        "publicationIdentity": identity,
                        "searchIntent": search.intent.value,
                        "searchStrategy": search.strategy.value,
                        "discoveryBasis": search.strategy.value,
                        "inventoryEvidenceStatus": (
                            grounded.inventory_evidence_status.value
                        ),
                        "groundedInventoryForms": [
                            {
                                "observedForm": item.observed_form,
                                "sourceField": item.source_field.value,
                                "sourceLocator": item.source_locator,
                            }
                            for item in grounded.inventory_forms
                        ],
                        "rejectedPassageCount": grounded.rejected_passages,
                        "rejectedInventoryFormCount": (
                            grounded.rejected_inventory_forms
                        ),
                        "groundingRejections": [
                            {
                                "claimKind": item.claim_kind.value,
                                "reason": item.reason.value,
                                "excerpt": item.excerpt,
                            }
                            for item in grounded.rejections
                        ],
                    },
                )
                if assessment.relevant:
                    relevant_count += 1
                    created = await self._present_candidate(
                        investigation,
                        run,
                        record,
                        search,
                        grounded,
                        tuple(str(item.id) for item in memory),
                        assessment_result,
                    )
                    new_candidate_count += int(created)
                if (
                    investigation.usage.candidates
                    >= investigation.budget.max_candidates
                ):
                    break
            history.append(
                {
                    "iteration": iteration,
                    "searches": [
                        self._search_payload(search) for search in plan.searches
                    ],
                    "resultCount": len(records),
                    "relevantCount": relevant_count,
                }
            )
            fresh = await self._repository.get_investigation(investigation.id)
            if (
                fresh
                and fresh.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED
            ):
                investigation.status = fresh.status
                investigation.cancel(self._clock.now())
                break
            investigation.heartbeat(self._clock.now())
            await self._repository.save_investigation(investigation)
            await self._uow.commit()
            if investigation.usage.candidates >= investigation.budget.max_candidates:
                break

        if investigation.status is FullAgenticInvestigationStatus.RUNNING:
            investigation.complete(self._clock.now())
        run.status = RunStatus.COMPLETED
        run.completed_at = self._clock.now()
        run.source_count = len(executed_sources)
        run.candidate_count = investigation.usage.candidates
        run.new_candidate_count = new_candidate_count
        await self._scientific_repository.save_run(run)
        await self._repository.save_investigation(investigation)
        await self._append_event(
            investigation,
            AgenticTrajectoryEventKind.STOPPED,
            {"status": investigation.status.value},
        )
        await self._uow.commit()

    async def _yield_slice(
        self,
        investigation: FullAgenticInvestigation,
        run: ScientificReturnSearchRun,
        iteration: int,
    ) -> None:
        """Stop on the worker's own clock and hand the work back untouched.

        Everything already done is durable — the plan, the searches, every
        assessment, every charged model call — so the continuation resumes from
        the trajectory exactly as a recovery would, but without any of it having
        been lost to a kill. The envelope run stays open because the
        investigation it belongs to has not finished.
        """
        now = self._clock.now()
        investigation.yield_slice(
            "The worker slice ended before the investigation finished", now
        )
        await self._append_event(
            investigation,
            AgenticTrajectoryEventKind.EXECUTION_SLICE_EXHAUSTED,
            {
                "iteration": iteration,
                "queries": investigation.usage.queries,
                "llmCalls": investigation.usage.llm_calls,
                "candidates": investigation.usage.candidates,
            },
        )
        await self._repository.save_investigation(investigation)
        await self._scientific_repository.save_run(run)
        await self._uow.commit()
        await self._announce_continuation(investigation)

    async def _announce_continuation(
        self, investigation: FullAgenticInvestigation
    ) -> None:
        """Tell a push-based queue that the work is waiting again.

        With the database dispatcher the QUEUED row is enough, because a poller
        will find it. Under Cloud Tasks the task that was running has just ended
        successfully, and nothing else would ever create the next one.

        Best effort by design: the row stays QUEUED either way, so a failure
        here costs the next sweep's latency rather than the investigation.
        """
        if self._dispatcher is None:
            return
        try:
            await self._dispatcher.enqueue(investigation.id)
        except Exception:
            logger.warning(
                "Could not announce the continuation of investigation %s; "
                "it stays queued for the next sweep.",
                investigation.id,
                exc_info=True,
            )

    async def _execute_searches(
        self,
        investigation: FullAgenticInvestigation,
        run: ScientificReturnSearchRun,
        iteration: int,
        searches: tuple[AgenticSearchSpec, ...],
        executed_sources: set[str],
        executed_attempts: set[tuple[str, str, str]],
    ) -> list[tuple[BibliographicRecord, AgenticSearchSpec]]:
        found: list[tuple[BibliographicRecord, AgenticSearchSpec]] = []
        for search in searches:
            attempt_identity = self._attempt_identity(
                search.source, search.query, search.author, search.intent
            )
            source = self._sources.get(search.source)
            capabilities = self._capabilities.get(search.source)
            if (
                source is None
                or capabilities is None
                or not search_is_supported(search, capabilities)
            ):
                continue
            invocation = {
                "contractVersion": "structured-search-v3",
                **self._search_payload(search),
            }
            key = normalized_tool_idempotency_key(str(investigation.id), 0, invocation)
            prior = await self._repository.get_tool_execution(key)
            if prior and prior.status is AgenticToolExecutionStatus.COMPLETED:
                # A search already paid for is replayed from its stored result,
                # never skipped. Skipping it was silently dropping the records
                # of an interrupted pass: the query had been spent, the reader
                # had not seen them, and nothing would deliver them again. The
                # already-assessed ones are filtered by the caller, so replaying
                # costs nothing and is what makes a resumed run complete.
                replayed = self._records_from_result(prior.result or {}, search)
                found.extend(replayed)
                executed_sources.add(search.source)
                if attempt_identity in executed_attempts:
                    await self._append_event(
                        investigation,
                        AgenticTrajectoryEventKind.SEARCH_SKIPPED_DUPLICATE,
                        self._search_payload(search),
                    )
                executed_attempts.add(attempt_identity)
                continue
            if attempt_identity in executed_attempts:
                await self._append_event(
                    investigation,
                    AgenticTrajectoryEventKind.SEARCH_SKIPPED_DUPLICATE,
                    self._search_payload(search),
                )
                continue
            if investigation.usage.queries >= investigation.budget.max_queries:
                break
            # An iteration may carry several searches — the floor alone can send
            # six — so the slice is checked per search, not only per iteration.
            # What was already fetched is returned and stays replayable.
            if not self._has_room_for(
                self._configuration.source_total_timeout_seconds
            ):
                break
            if prior is not None:
                execution = prior
                execution.status = AgenticToolExecutionStatus.RUNNING
                execution.attempts += 1
                execution.lease_expires_at = self._clock.now() + timedelta(
                    seconds=self._configuration.tool_lease_seconds
                )
                await self._repository.save_tool_execution(execution)
            else:
                execution = AgenticToolExecution(
                    id=AgenticToolExecutionId(str(uuid4())),
                    investigation_id=investigation.id,
                    trajectory_sequence=iteration,
                    idempotency_key=key,
                    status=AgenticToolExecutionStatus.RUNNING,
                    invocation=invocation,
                    started_at=self._clock.now(),
                    lease_expires_at=self._clock.now()
                    + timedelta(seconds=self._configuration.tool_lease_seconds),
                )
                await self._repository.add_tool_execution(execution)
            await self._append_event(
                investigation,
                AgenticTrajectoryEventKind.TOOL_STARTED,
                self._search_payload(search),
            )
            await self._uow.commit()
            executed_attempts.add(attempt_identity)
            executed_sources.add(search.source)
            sent_at = self._clock.now()
            error: str | None = None
            try:
                await self._renew_lease(investigation)
                records = await source.search(
                    search.query,
                    source_result_limit(capabilities, investigation.budget.max_results),
                    author=search.author,
                )
            except _InvestigationLeaseLost:
                raise
            except SourceWaitBudgetExceeded as exc:
                # Named apart from any other source failure: this one says the
                # source is healthy and simply slower than the deployment can
                # afford, which is a capacity decision rather than a fault.
                records = []
                error = f"{type(exc).__name__}: {exc}"[:500]
                await self._append_event(
                    investigation,
                    AgenticTrajectoryEventKind.SOURCE_WAIT_REJECTED,
                    {
                        "source": search.source,
                        "query": search.query,
                        "message": error,
                    },
                )
            except Exception as exc:
                records = []
                error = f"{type(exc).__name__}: {exc}"[:500]
            await self._scientific_repository.add_query(
                ScientificReturnQuery(
                    id=ScientificReturnQueryId(str(uuid4())),
                    run_id=run.id,
                    source=search.source,
                    query_text=search.query,
                    query_type=QueryType.AGENTIC,
                    sent_at=sent_at,
                    result_count=len(records),
                    status=QueryStatus.FAILED if error else QueryStatus.COMPLETED,
                    error_message=error,
                )
            )
            remaining = investigation.budget.max_results - investigation.usage.results
            accepted = records[: max(0, remaining)]
            current = [(record, search) for record in accepted]
            found.extend(current)
            investigation.usage = replace(
                investigation.usage,
                queries=investigation.usage.queries + 1,
                results=investigation.usage.results + len(accepted),
            )
            result: dict[str, object] = {
                "records": [
                    self._record_payload(record, search.query) for record in accepted
                ]
            }
            execution.status = AgenticToolExecutionStatus.COMPLETED
            execution.result = result
            execution.result_hash = hashlib.sha256(repr(result).encode()).hexdigest()
            execution.completed_at = self._clock.now()
            await self._repository.save_tool_execution(execution)
            await self._append_event(
                investigation,
                AgenticTrajectoryEventKind.TOOL_COMPLETED,
                {
                    "resultCount": len(accepted),
                    "toolExecutionId": str(execution.id),
                    **self._search_payload(search),
                },
            )
            await self._uow.commit()
            if investigation.usage.results >= investigation.budget.max_results:
                break
        return found

    async def _present_candidate(
        self,
        investigation: FullAgenticInvestigation,
        run: ScientificReturnSearchRun,
        record: BibliographicRecord,
        search: AgenticSearchSpec,
        grounded: object,
        knowledge_ids: tuple[str, ...],
        assessment_result: AssessmentResult,
    ) -> bool:
        from app.scientific_return.domain.full_agentic_models import (
            GroundedArticleAssessment,
        )

        assert isinstance(grounded, GroundedArticleAssessment)
        assessment = grounded.assessment
        key = deduplication_key(record)
        candidate = await self._scientific_repository.get_candidate_by_key(
            investigation.watch_id, key
        )
        relation = AgenticCandidateRelationKind.REDISCOVERED
        if candidate is None:
            relation = AgenticCandidateRelationKind.CREATED
            candidate = CandidatePublication(
                id=CandidatePublicationId(str(uuid4())),
                watch_id=investigation.watch_id,
                first_seen_run_id=run.id,
                source=record.source,
                source_record_id=record.source_record_id,
                deduplication_key=key,
                doi=record.doi,
                title=record.title,
                authors=record.authors,
                publication_date=record.publication_date,
                abstract=record.abstract,
                url=record.url,
                raw_metadata_hash=record.raw_metadata_hash,
                status=CandidateStatus.PENDING,
                created_at=self._clock.now(),
            )
            await self._scientific_repository.add_candidate(candidate)
        linked = await self._repository.link_candidate(
            AgenticCandidateLink(
                investigation_id=investigation.id,
                candidate_id=candidate.id,
                relation_kind=relation,
                rank=investigation.usage.candidates + 1,
                linked_at=self._clock.now(),
            )
        )
        analysis = CandidateAgentAnalysis(
            id=CandidateAgentAnalysisId(str(uuid4())),
            candidate_id=candidate.id,
            run_id=run.id,
            status=AgentAnalysisStatus.RUNNING,
            model=self._reasoner.model_name,
            prompt_version_id=assessment_result.prompt_version_id,
            prompt_version=assessment_result.prompt_version,
            input_payload={
                "query": search.query,
                "source": record.source,
                "passages": list(assessment.passages),
                "inventoryForms": list(assessment.inventory_forms),
                "knowledgeItemIds": list(knowledge_ids),
                "discoveryBasis": search.strategy.value,
                "searchIntent": search.intent.value,
                "searchStrategy": search.strategy.value,
                "inventoryEvidenceStatus": (grounded.inventory_evidence_status.value),
                "groundedInventoryForms": [
                    {
                        "observedForm": item.observed_form,
                        "sourceField": item.source_field.value,
                        "sourceLocator": item.source_locator,
                    }
                    for item in grounded.inventory_forms
                ],
                "rejectedPassageCount": grounded.rejected_passages,
                "rejectedInventoryFormCount": grounded.rejected_inventory_forms,
            },
            input_hash=hashlib.sha256(
                f"{record.source}|{record.source_record_id}|{search.query}".encode()
            ).hexdigest(),
            started_at=self._clock.now(),
            created_by=investigation.created_by,
        )
        analysis.complete(
            CandidateAnalysisResult(
                summary=assessment.explanation,
                supporting_evidence=assessment.passages,
                contradictions=assessment.contradictions,
                missing_evidence=(),
                recommended_action=AgentRecommendedAction.PRESENT_FOR_REVIEW,
                proposed_queries=(),
                reasoning_summary=assessment.explanation,
                confidence=assessment.confidence,
            ),
            response_hash=hashlib.sha256(assessment.explanation.encode()).hexdigest(),
            completed_at=self._clock.now(),
        )
        await self._scientific_repository.add_agent_analysis(analysis)
        if linked:
            investigation.usage = replace(
                investigation.usage,
                candidates=investigation.usage.candidates + 1,
            )
            await self._append_event(
                investigation,
                AgenticTrajectoryEventKind.CANDIDATE_LINKED,
                {
                    "candidateId": str(candidate.id),
                    "relationKind": relation.value,
                    "analysisId": str(analysis.id),
                },
            )
        return linked and relation is AgenticCandidateRelationKind.CREATED

    async def _renew_lease(self, investigation: FullAgenticInvestigation) -> None:
        now = self._clock.now()
        investigation.lease_expires_at = now + timedelta(
            seconds=self._configuration.investigation_lease_seconds
        )
        next_version = await self._repository.renew_investigation_lease(
            investigation.id,
            investigation.lease_owner or "unknown-worker",
            now,
            investigation.lease_expires_at,
        )
        if next_version is None:
            raise _InvestigationLeaseLost(
                f"Worker lost the lease for investigation {investigation.id}"
            )
        investigation.version = next_version
        await self._uow.commit()

    async def _reserve_llm_call(
        self,
        investigation: FullAgenticInvestigation,
        *,
        phase: str,
        iteration: int,
        subject: str,
    ) -> None:
        """Charge the call, renew the lease and commit — before calling.

        The commit is the point of the exercise. Until it lands, a worker that
        dies leaves the budget as it found it and the retry repeats the same
        work at no cost, which is how an investigation can be retried forever.
        Afterwards, every death is progress.
        """
        investigation.reserve_llm_call()
        now = self._clock.now()
        investigation.heartbeat_at = now
        investigation.lease_expires_at = now + timedelta(
            seconds=self._configuration.investigation_lease_seconds
        )
        next_version = await self._repository.reserve_llm_call(
            investigation,
            investigation.lease_owner or "unknown-worker",
            now,
            investigation.lease_expires_at,
        )
        if next_version is None:
            raise _InvestigationLeaseLost(
                f"Worker lost the lease for investigation {investigation.id}"
            )
        investigation.version = next_version
        await self._append_event(
            investigation,
            AgenticTrajectoryEventKind.LLM_CALL_STARTED,
            {
                "phase": phase,
                "iteration": iteration,
                "subject": subject,
                "llmCalls": investigation.usage.llm_calls,
                "maxLlmCalls": investigation.budget.max_llm_calls,
            },
        )
        await self._uow.commit()

    async def _record_llm_outcome(
        self,
        investigation: FullAgenticInvestigation,
        error: Exception | None,
        *,
        phase: str,
        iteration: int,
        subject: str,
        started_at: datetime,
    ) -> None:
        """Close the reservation's record, keeping timeouts distinguishable.

        A timeout is not the same fact as a malformed answer: one says the model
        never finished, the other that it finished badly. The distinction is
        what makes a slow backend visible before it starts costing whole runs.
        """
        if error is None:
            kind = AgenticTrajectoryEventKind.LLM_CALL_COMPLETED
        elif isinstance(error, AgentReasonerTimeout):
            kind = AgenticTrajectoryEventKind.LLM_CALL_TIMED_OUT
        else:
            kind = AgenticTrajectoryEventKind.LLM_CALL_FAILED
        payload: dict[str, object] = {
            "phase": phase,
            "iteration": iteration,
            "subject": subject,
            "durationMs": max(
                0, int((self._clock.now() - started_at).total_seconds() * 1000)
            ),
        }
        if error is not None:
            payload["message"] = f"{type(error).__name__}: {error}"[:500]
        await self._append_event(investigation, kind, payload)

    async def _append_event(
        self,
        investigation: FullAgenticInvestigation,
        kind: AgenticTrajectoryEventKind,
        payload: dict[str, object],
    ) -> None:
        sequence = await self._repository.next_event_sequence(investigation.id)
        await self._repository.append_event(
            AgenticTrajectoryEvent(
                id=AgenticTrajectoryEventId(str(uuid4())),
                investigation_id=investigation.id,
                sequence=sequence,
                kind=kind,
                payload=payload,
                occurred_at=self._clock.now(),
            )
        )

    async def _plan_with_retry(
        self,
        investigation: FullAgenticInvestigation,
        *,
        observation: dict[str, object],
        memory: tuple[str, ...],
        history: tuple[dict[str, object], ...],
        remaining_queries: int,
        iteration: int,
    ) -> AgenticPlan:
        last_error: Exception | None = None
        exhausted_budget = False
        for attempt in range(1, 3):
            # The iteration's own check reserved room for one model call; a
            # second attempt is a second call and needs its own room, or the
            # retry is what carries the worker past the platform's window.
            if not self._has_room_for(self._configuration.llm_total_timeout_seconds):
                raise _SliceExhausted(
                    "The worker slice ended before the planner could answer"
                )
            investigation.usage = replace(investigation.usage, iterations=iteration)
            try:
                await self._reserve_llm_call(
                    investigation,
                    phase="PLAN",
                    iteration=iteration,
                    subject=f"attempt-{attempt}",
                )
            except AgenticBudgetExhausted:
                exhausted_budget = True
                break
            started_at = self._clock.now()
            retry_observation = dict(observation)
            if last_error is not None:
                retry_observation["previousPlannerContractError"] = (
                    f"{type(last_error).__name__}: {last_error}"[:500]
                )
            try:
                plan = await self._reasoner.plan(
                    observation=retry_observation,
                    memory=memory,
                    history=history,
                    source_capabilities=tuple(
                        item.as_prompt_payload() for item in self._capabilities.values()
                    ),
                    remaining_queries=remaining_queries,
                )
            except Exception as exc:
                last_error = exc
                await self._record_llm_outcome(
                    investigation,
                    exc,
                    phase="PLAN",
                    iteration=iteration,
                    subject=f"attempt-{attempt}",
                    started_at=started_at,
                )
                await self._append_event(
                    investigation,
                    AgenticTrajectoryEventKind.PLANNER_ERROR,
                    {
                        "iteration": iteration,
                        "attempt": attempt,
                        "message": f"{type(exc).__name__}: {exc}"[:500],
                    },
                )
                await self._repository.save_investigation(investigation)
                await self._uow.commit()
                continue
            await self._record_llm_outcome(
                investigation,
                None,
                phase="PLAN",
                iteration=iteration,
                subject=f"attempt-{attempt}",
                started_at=started_at,
            )
            return plan
        # The two ways out of the loop are not the same fact, and the curator
        # reads this reason: one says the model could not be understood, the
        # other that there was no budget left to ask it again.
        investigation.degrade(
            "The model-call budget ran out before a plan could be produced, so "
            "the investigation finished on its deterministic floor alone"
            if exhausted_budget
            else "The planner contract stayed invalid after a retry, so the "
            "investigation finished on its deterministic floor alone"
        )
        await self._append_event(
            investigation,
            AgenticTrajectoryEventKind.PLANNER_FALLBACK,
            {
                "iteration": iteration,
                "reason": "planner contract remained invalid after retry",
                "degraded": True,
            },
        )
        return AgenticPlan((), "Planner unavailable; finish with completed floor", True)

    @staticmethod
    def _source_capabilities(
        source: BibliographicSource,
    ) -> BibliographicSourceCapabilities:
        capabilities = getattr(source, "capabilities", None)
        if isinstance(capabilities, BibliographicSourceCapabilities):
            return capabilities
        # An adapter that does not describe itself stays searchable, but is
        # never credited with returning an inspectable body: absence of an
        # inventory form in what it sent back must not read as "not observed".
        return BibliographicSourceCapabilities(
            name=source.name,
            searches_metadata=True,
            searches_indexed_full_text=True,
            returns_abstract=True,
            returns_inspectable_full_text=False,
            supports_structured_author=True,
        )

    def _attempt_identity(
        self,
        source: str,
        query: str,
        author: str | None,
        intent: SearchIntent,
    ) -> tuple[str, str, str]:
        normalized_query = " ".join(query.casefold().split())
        capabilities = self._capabilities.get(source.upper())
        if (
            intent is SearchIntent.INVENTORY_EVIDENCE
            and capabilities is not None
            and capabilities.normalizes_inventory_separators
        ):
            normalized_query = re.sub(r"[-:/.\s]", "", normalized_query)
        return (
            source.upper(),
            normalized_query,
            " ".join((author or "").casefold().split()),
        )

    @staticmethod
    def _search_payload(search: AgenticSearchSpec) -> dict[str, object]:
        return {
            "source": search.source,
            "query": search.query,
            "author": search.author,
            "objectId": search.object_id,
            "intent": search.intent.value,
            "strategy": search.strategy.value,
        }

    @staticmethod
    def _searches_from_payload(
        payload: dict[str, object],
    ) -> tuple[AgenticSearchSpec, ...]:
        raw_searches = payload.get("searches")
        if not isinstance(raw_searches, list):
            return ()
        searches: list[AgenticSearchSpec] = []
        for item in raw_searches:
            if not isinstance(item, dict):
                continue
            try:
                searches.append(
                    AgenticSearchSpec(
                        source=str(item["source"]),
                        query=str(item["query"]),
                        author=str(item["author"]) if item.get("author") else None,
                        object_id=(
                            str(item["objectId"]) if item.get("objectId") else None
                        ),
                        intent=SearchIntent(str(item["intent"])),
                        strategy=SearchStrategy(str(item["strategy"])),
                    )
                )
            except (KeyError, ValueError):
                continue
        return tuple(searches)

    @staticmethod
    def _record_payload(record: BibliographicRecord, query: str) -> dict[str, object]:
        return {
            "query": query,
            "source": record.source,
            "source_record_id": record.source_record_id,
            "title": record.title,
            "authors": list(record.authors),
            "publication_date": record.publication_date,
            "abstract": record.abstract,
            "url": record.url,
            "doi": record.doi,
            "raw_metadata_hash": record.raw_metadata_hash,
            "indexed_text_hash": (
                hashlib.sha256(record.indexed_text.encode()).hexdigest()
                if record.indexed_text
                else None
            ),
            # Tool results are encrypted by the repository. Persist exactly the
            # bounded text exposed to the reader so a COMPLETED attempt can be
            # replayed without either re-querying the source or losing grounding.
            "indexed_text": record.indexed_text[:16000]
            if record.indexed_text
            else None,
            "indexed_text_source": record.indexed_text_source,
        }

    @staticmethod
    def _records_from_result(
        result: dict[str, object], search: AgenticSearchSpec
    ) -> list[tuple[BibliographicRecord, AgenticSearchSpec]]:
        raw = result.get("records")
        if not isinstance(raw, list):
            return []
        output: list[tuple[BibliographicRecord, AgenticSearchSpec]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            output.append(
                (
                    BibliographicRecord(
                        source=str(item["source"]),
                        source_record_id=str(item["source_record_id"]),
                        title=str(item["title"]),
                        authors=tuple(str(value) for value in item.get("authors", [])),
                        publication_date=str(item["publication_date"])
                        if item.get("publication_date")
                        else None,
                        abstract=str(item["abstract"])
                        if item.get("abstract")
                        else None,
                        url=str(item["url"]) if item.get("url") else None,
                        doi=str(item["doi"]) if item.get("doi") else None,
                        raw_metadata_hash=str(item["raw_metadata_hash"]),
                        indexed_text=str(item["indexed_text"])
                        if item.get("indexed_text")
                        else None,
                        indexed_text_source=str(item["indexed_text_source"])
                        if item.get("indexed_text_source")
                        else None,
                    ),
                    search,
                )
            )
        return output


class GetFullAgenticInvestigation:
    def __init__(self, repository: FullAgenticRepository) -> None:
        self._repository = repository

    async def execute(
        self, investigation_id: FullAgenticInvestigationId, caller: Actor
    ) -> FullAgenticInvestigation:
        require_staff(caller)
        item = await self._repository.get_investigation(investigation_id)
        if item is None:
            raise LookupError(f"Investigation {investigation_id} not found")
        return item


class CancelFullAgenticInvestigation:
    def __init__(
        self,
        repository: FullAgenticRepository,
        unit_of_work: FullAgenticUnitOfWork,
        clock: FullAgenticClock,
    ) -> None:
        self._repository = repository
        self._uow = unit_of_work
        self._clock = clock

    async def execute(
        self, investigation_id: FullAgenticInvestigationId, caller: Actor
    ) -> FullAgenticInvestigation:
        require_group(caller, *_MUTATION_GROUPS)
        item = await self._repository.get_investigation(investigation_id)
        if item is None:
            raise LookupError(f"Investigation {investigation_id} not found")
        item.request_cancel(caller.id, self._clock.now())
        await self._repository.save_investigation(item)
        await self._uow.commit()
        return item
