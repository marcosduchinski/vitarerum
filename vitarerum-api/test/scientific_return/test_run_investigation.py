"""The agentic cycle end to end, against fakes.

These are the acceptance scenarios of the increment: a full run, a refusal, a
model failure, a source failure, a candidate decided mid-cycle, and the
guarantee that a human decision is still required at the end.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from app.identity.public import Actor, GroupName, PermissionId
from app.scientific_return.application.agent_contracts import AgentPlanSchemaError
from app.scientific_return.application.agent_tools import (
    build_default_registry,
)
from app.scientific_return.application.ports import (
    BibliographicRecord,
    PlanResult,
    ReasonerCall,
    ReflectionResult,
    ToolExecutionRecord,
)
from app.scientific_return.application.run_investigation import (
    AgentConfiguration,
    InvestigationAlreadyRunning,
    InvestigationDisabled,
    InvestigationNotPossible,
    RunInvestigationInput,
    RunScientificReturnInvestigation,
)
from app.scientific_return.domain.enums import (
    AgentProgress,
    AgentRecommendedAction,
    CandidateStatus,
    EvidenceType,
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
    RunStatus,
    StopReason,
    WatchStatus,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentObservation,
    AgentPlan,
    AgentReflection,
    ExecutionBudget,
    ProposedAction,
    ReflectionContext,
)
from app.scientific_return.domain.investigation_models import (
    InvestigationId,
    ScientificReturnInvestigation,
)
from app.scientific_return.domain.models import (
    CandidatePublication,
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnSnapshotId,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)

from .test_scientific_return import _Repository

_NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_WATCH = ScientificReturnWatchId("watch-1")
_SEARCH = AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS

_SNAPSHOT = ProjectSnapshotPayload(
    project_id="project-1",
    project_reference="PRJ-1",
    researcher="Rita P. Eusébio",
    consulted_objects=(
        ConsultedObjectSnapshot(
            id="object-1",
            inventory_number="MUHNAC/MB11-001283",
            object_name="Trichoniscoides machadoi",
        ),
    ),
)


class _Clock:
    def __init__(self) -> None:
        self._step = 0

    def now(self) -> datetime:
        self._step += 1
        return _NOW + timedelta(seconds=self._step)


class _Lock:
    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.acquired: list[str] = []
        self.released = 0

    async def acquire(self, key: str) -> None:
        if not self._available:
            raise RuntimeError(f"locked: {key}")
        self.acquired.append(key)

    async def release(self) -> None:
        self.released += 1


class _UnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _Investigations:
    def __init__(self) -> None:
        self.saved: dict[str, ScientificReturnInvestigation] = {}
        self.tool_executions: dict[str, ToolExecutionRecord] = {}

    async def add(self, investigation: ScientificReturnInvestigation) -> None:
        self.saved[str(investigation.id)] = investigation

    async def save(self, investigation: ScientificReturnInvestigation) -> None:
        self.saved[str(investigation.id)] = investigation

    async def get(
        self, investigation_id: InvestigationId
    ) -> ScientificReturnInvestigation | None:
        return self.saved.get(str(investigation_id))

    async def list_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> list[ScientificReturnInvestigation]:
        return [item for item in self.saved.values() if item.watch_id == watch_id]

    async def list_for_candidate(
        self, candidate_id: CandidatePublicationId
    ) -> list[ScientificReturnInvestigation]:
        return [
            item for item in self.saved.values() if item.candidate_id == candidate_id
        ]

    async def find_live(
        self,
        watch_id: ScientificReturnWatchId,
        objective: InvestigationObjective,
        candidate_id: CandidatePublicationId | None,
    ) -> ScientificReturnInvestigation | None:
        for item in self.saved.values():
            if item.is_terminal:
                continue
            if (
                item.watch_id == watch_id
                and item.objective is objective
                and item.candidate_id == candidate_id
            ):
                return item
        return None

    async def find_by_idempotency_key(
        self, key: str
    ) -> ScientificReturnInvestigation | None:
        return next(
            (
                item
                for item in self.saved.values()
                if item.idempotency_key == key
            ),
            None,
        )

    async def find_tool_execution(self, key: str) -> ToolExecutionRecord | None:
        return self.tool_executions.get(key)

    async def add_tool_execution(self, execution: ToolExecutionRecord) -> None:
        self.tool_executions[execution.idempotency_key] = execution

    async def save_tool_execution(self, execution: ToolExecutionRecord) -> None:
        self.tool_executions[execution.idempotency_key] = execution


class _Reasoner:
    model_name = "test-model"

    def __init__(
        self,
        plan: AgentPlan | Exception | None = None,
        reflection: AgentReflection | Exception | None = None,
    ) -> None:
        self._plan = plan or AgentPlan(
            objective="Find inventory evidence.",
            action=ProposedAction(_SEARCH, "object-1"),
            reasoning_summary="No inventory evidence yet.",
        )
        self._reflection = reflection or AgentReflection(
            progress=AgentProgress.EVIDENCE_ADDED,
            evidence_delta_summary="Evidence added.",
            recommended_stop=True,
            reasoning_summary="Done.",
        )
        self.reflect_calls = 0

    def _call(self) -> ReasonerCall:
        return ReasonerCall("test-model", "pv-1", "v1", 10, "hash")

    async def plan(
        self, observation: AgentObservation, mode: InvestigationMode
    ) -> PlanResult:
        if isinstance(self._plan, Exception):
            raise self._plan
        return PlanResult(plan=self._plan, call=self._call())

    async def reflect(self, context: ReflectionContext) -> ReflectionResult:
        self.reflect_calls += 1
        if isinstance(self._reflection, Exception):
            raise self._reflection
        return ReflectionResult(reflection=self._reflection, call=self._call())


class _Source:
    name = "EUROPE_PMC"

    def __init__(
        self, records: list[BibliographicRecord] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._records = records or []
        self._error = error
        self.queries: list[str] = []

    async def search(self, query: str, limit: int) -> list[BibliographicRecord]:
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return list(self._records)


def _record(*, doi: str = "10.3897/subtbiol.53.163632") -> BibliographicRecord:
    return BibliographicRecord(
        source="EUROPE_PMC",
        source_record_id="PMC1",
        title="Terrestrial isopods from Portugal",
        authors=("Rita P. Eusébio",),
        publication_date="2025",
        abstract="A survey.",
        url=None,
        doi=doi,
        raw_metadata_hash=hashlib.sha256(b"PMC1").hexdigest(),
        indexed_text=(
            "Material examined. Portugal; MNHNC:MB11:001283; "
            "Trichoniscoides machadoi."
        ),
        indexed_text_source="full_text",
    )


def _caller() -> Actor:
    return Actor(
        id=PermissionId("perm-1"),
        group=GroupName.CURATORIAL,
        email="curator@example.test",
    )


def _configuration(**overrides: object) -> AgentConfiguration:
    values: dict[str, object] = {
        "mode": InvestigationMode.SUPERVISED,
        "allowed_actions": frozenset({_SEARCH}),
        "allowed_sources": ("EUROPE_PMC",),
        "budget": ExecutionBudget(1, 1, 4, 10, 5),
    }
    values.update(overrides)
    return AgentConfiguration(**values)  # type: ignore[arg-type]


async def _seed(repository: _Repository, *, candidate: bool = False) -> None:
    snapshot = ScientificReturnProjectSnapshot(
        id=ScientificReturnSnapshotId("snap-1"),
        project_id="project-1",
        payload=_SNAPSHOT,
        payload_hash="h",
        builder_version="v1",
        created_at=_NOW,
    )
    await repository.add_snapshot(snapshot)
    await repository.add_watch(
        ScientificReturnWatch(
            id=_WATCH,
            project_id="project-1",
            status=WatchStatus.ACTIVE,
            review_interval_days=30,
            created_by=PermissionId("perm-1"),
            created_at=_NOW,
            next_run_at=_NOW,
            project_snapshot_id=snapshot.id,
        )
    )
    await repository.add_run(
        ScientificReturnSearchRun(
            id=ScientificReturnRunId("run-1"),
            watch_id=_WATCH,
            status=RunStatus.COMPLETED,
            started_at=_NOW,
            completed_at=_NOW,
        )
    )
    if candidate:
        await repository.add_candidate(
            CandidatePublication(
                id=CandidatePublicationId("cand-1"),
                watch_id=_WATCH,
                first_seen_run_id=ScientificReturnRunId("run-1"),
                source="CROSSREF",
                source_record_id="rec-1",
                deduplication_key="doi:10.3897/subtbiol.53.163632",
                title="Terrestrial isopods from Portugal",
                authors=("Rita P. Eusébio",),
                publication_date="2025",
                abstract=None,
                url=None,
                raw_metadata_hash="h",
                created_at=_NOW,
                doi="10.3897/subtbiol.53.163632",
                status=CandidateStatus.PENDING,
            )
        )


def _use_case(
    repository: _Repository,
    *,
    reasoner: _Reasoner | None = None,
    source: _Source | None = None,
    configuration: AgentConfiguration | None = None,
    investigations: _Investigations | None = None,
    uow: _UnitOfWork | None = None,
    lock: _Lock | None = None,
) -> RunScientificReturnInvestigation:
    return RunScientificReturnInvestigation(
        repository,
        investigations or _Investigations(),
        reasoner or _Reasoner(),
        build_default_registry((source or _Source([_record()]),)),
        uow or _UnitOfWork(),
        _Clock(),
        configuration or _configuration(),
        lock or _Lock(),
    )


def _discover(caller: Actor | None = None) -> RunInvestigationInput:
    return RunInvestigationInput(
        watch_id=_WATCH,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        caller=caller or _caller(),
    )


# --- the happy path ----------------------------------------------------------


async def test_a_discovery_creates_a_candidate_and_awaits_a_human() -> None:
    repository = _Repository()
    await _seed(repository)

    investigation = await _use_case(repository).execute(_discover())

    assert investigation.status is InvestigationStatus.AWAITING_HUMAN_REVIEW
    assert investigation.stop_reason is StopReason.EVIDENCE_SUFFICIENT
    created = [
        item
        for item in repository.candidates.values()
        if item.status is CandidateStatus.PENDING
    ]
    assert len(created) == 1
    assert created[0].status is CandidateStatus.PENDING


async def test_the_created_candidate_carries_its_provenance() -> None:
    repository = _Repository()
    await _seed(repository)

    investigation = await _use_case(repository).execute(_discover())
    candidate = next(iter(repository.candidates.values()))

    assert candidate.evidences
    for evidence in candidate.evidences:
        assert evidence.investigation_id == str(investigation.id)
        assert evidence.iteration_id is not None
        assert evidence.source_record_id == "PMC1"
        assert evidence.is_agentic


async def test_enrichment_adds_evidence_without_touching_the_candidate() -> None:
    repository = _Repository()
    await _seed(repository, candidate=True)
    before = repository.candidates["cand-1"]
    original_title, original_status = before.title, before.status

    investigation = await _use_case(repository).execute(
        RunInvestigationInput(
            watch_id=_WATCH,
            objective=InvestigationObjective.ENRICH_CANDIDATE,
            caller=_caller(),
            candidate_id=CandidatePublicationId("cand-1"),
        )
    )

    candidate = repository.candidates["cand-1"]
    assert candidate.title == original_title
    assert candidate.status is original_status
    assert any(
        item.type is EvidenceType.INVENTORY_NUMBER for item in candidate.evidences
    )
    assert investigation.status is InvestigationStatus.AWAITING_HUMAN_REVIEW


async def test_the_trajectory_is_persisted_step_by_step() -> None:
    repository = _Repository()
    await _seed(repository)
    uow = _UnitOfWork()

    await _use_case(repository, uow=uow).execute(_discover())

    # Create, observe, plan, policy, tool claim, tool result, close.
    assert uow.commits >= 6


async def test_the_full_trajectory_is_readable_afterwards() -> None:
    repository = _Repository()
    await _seed(repository)

    investigation = await _use_case(repository).execute(_discover())
    iteration = investigation.iterations[0]

    assert iteration.observation is not None
    assert iteration.plan is not None
    assert iteration.policy_decision is not None
    assert iteration.tool_result is not None
    assert iteration.evidence_delta is not None
    assert iteration.reflection is not None
    assert iteration.evidence_before_hash and iteration.evidence_after_hash


# --- refusals and failures ---------------------------------------------------


async def test_a_disabled_mode_refuses_to_start() -> None:
    repository = _Repository()
    await _seed(repository)

    with pytest.raises(InvestigationDisabled):
        await _use_case(
            repository, configuration=_configuration(mode=InvestigationMode.DISABLED)
        ).execute(_discover())


async def test_a_second_investigation_for_the_same_target_is_refused() -> None:
    repository = _Repository()
    await _seed(repository)
    investigations = _Investigations()
    use_case = _use_case(repository, investigations=investigations)
    await use_case.execute(_discover())
    # The first one is terminal, so a repeat is allowed; force a live one.
    live = next(iter(investigations.saved.values()))
    live.status = InvestigationStatus.PLANNING
    live.stop_reason = None

    with pytest.raises(InvestigationAlreadyRunning):
        await use_case.execute(_discover())


async def test_a_watch_without_a_deterministic_run_is_refused() -> None:
    repository = _Repository()
    await _seed(repository)
    repository.runs.clear()

    with pytest.raises(InvestigationNotPossible, match="deterministic run"):
        await _use_case(repository).execute(_discover())


async def test_a_decided_candidate_cannot_be_enriched() -> None:
    repository = _Repository()
    await _seed(repository, candidate=True)
    repository.candidates["cand-1"].status = CandidateStatus.CONFIRMED

    with pytest.raises(InvestigationNotPossible, match="pending candidate"):
        await _use_case(repository).execute(
            RunInvestigationInput(
                watch_id=_WATCH,
                objective=InvestigationObjective.ENRICH_CANDIDATE,
                caller=_caller(),
                candidate_id=CandidatePublicationId("cand-1"),
            )
        )


async def test_a_malformed_plan_ends_the_investigation_as_invalid() -> None:
    repository = _Repository()
    await _seed(repository)

    investigation = await _use_case(
        repository, reasoner=_Reasoner(plan=AgentPlanSchemaError("bad json"))
    ).execute(_discover())

    assert investigation.status is InvestigationStatus.FAILED
    assert investigation.stop_reason is StopReason.INVALID_PLAN
    assert not repository.candidates


async def test_an_unavailable_reasoner_leaves_the_queue_untouched() -> None:
    repository = _Repository()
    await _seed(repository, candidate=True)

    investigation = await _use_case(
        repository, reasoner=_Reasoner(plan=TimeoutError("model down"))
    ).execute(
        RunInvestigationInput(
            watch_id=_WATCH,
            objective=InvestigationObjective.ENRICH_CANDIDATE,
            caller=_caller(),
            candidate_id=CandidatePublicationId("cand-1"),
        )
    )

    assert investigation.stop_reason is StopReason.REASONER_UNAVAILABLE
    assert repository.candidates["cand-1"].status is CandidateStatus.PENDING


async def test_an_unavailable_source_is_audited_without_blocking_review() -> None:
    repository = _Repository()
    await _seed(repository)

    investigation = await _use_case(
        repository, source=_Source(error=TimeoutError("503"))
    ).execute(_discover())

    assert investigation.is_terminal
    assert investigation.stop_reason in {
        StopReason.TOOL_UNAVAILABLE,
        StopReason.NO_RESULTS,
    }


async def test_an_unavailable_reflection_falls_back_to_the_delta() -> None:
    repository = _Repository()
    await _seed(repository)

    investigation = await _use_case(
        repository, reasoner=_Reasoner(reflection=TimeoutError("model down"))
    ).execute(_discover())

    reflection = investigation.iterations[0].reflection
    assert reflection is not None
    assert "Deterministic fallback" in reflection.evidence_delta_summary
    assert investigation.is_terminal


async def test_a_rejected_action_never_reaches_a_source() -> None:
    repository = _Repository()
    await _seed(repository)
    source = _Source([_record()])

    investigation = await _use_case(
        repository,
        source=source,
        configuration=_configuration(allowed_actions=frozenset()),
    ).execute(_discover())

    assert source.queries == []
    assert investigation.stop_reason is StopReason.ACTION_REJECTED
    assert not repository.candidates


async def test_a_source_that_cannot_match_exactly_is_refused() -> None:
    """Crossref ranks by relevance, so an inventory code there is noise."""
    repository = _Repository()
    await _seed(repository)
    source = _Source([_record()])

    investigation = await _use_case(
        repository,
        source=source,
        configuration=_configuration(allowed_sources=("CROSSREF",)),
    ).execute(_discover())

    assert source.queries == []
    assert investigation.stop_reason is StopReason.ACTION_REJECTED
    assert not repository.candidates


# --- authority ---------------------------------------------------------------


async def test_the_candidate_still_requires_a_human_decision() -> None:
    repository = _Repository()
    await _seed(repository)

    await _use_case(repository).execute(_discover())

    assert all(
        item.status is CandidateStatus.PENDING
        for item in repository.candidates.values()
    )
    assert all(
        item.confirmed_publication_entry_id is None
        for item in repository.candidates.values()
    )


async def test_a_caller_outside_the_review_groups_is_refused() -> None:
    repository = _Repository()
    await _seed(repository)
    outsider = Actor(
        id=PermissionId("perm-2"),
        group=GroupName.EXTERNAL,
        email="other@example.test",
    )

    with pytest.raises(PermissionError):
        await _use_case(repository).execute(_discover(outsider))


async def test_the_candidate_ceiling_is_respected() -> None:
    repository = _Repository()
    await _seed(repository)
    many = _Source(
        [_record(doi=f"10.0/{index}") for index in range(6)]
    )

    await _use_case(
        repository,
        source=many,
        configuration=_configuration(budget=ExecutionBudget(1, 1, 4, 10, 2)),
    ).execute(_discover())

    assert len(repository.candidates) <= 2



# --- idempotency -------------------------------------------------------------


async def test_the_same_client_key_never_contacts_a_source_twice() -> None:
    """The key exists to stop the second call, not merely to be recorded."""
    repository = _Repository()
    await _seed(repository)
    investigations = _Investigations()
    source = _Source([_record()])
    use_case = _use_case(repository, source=source, investigations=investigations)
    command = RunInvestigationInput(
        watch_id=_WATCH,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        caller=_caller(),
        idempotency_key="key-1",
    )

    first = await use_case.execute(command)
    calls = len(source.queries)
    second = await use_case.execute(command)

    assert calls > 0, "the first call must actually search"
    assert len(source.queries) == calls
    assert second.id == first.id


async def test_a_repeated_key_creates_no_second_candidate() -> None:
    repository = _Repository()
    await _seed(repository)
    investigations = _Investigations()
    command = RunInvestigationInput(
        watch_id=_WATCH,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        caller=_caller(),
        idempotency_key="key-1",
    )
    use_case = _use_case(
        repository, source=_Source([_record()]), investigations=investigations
    )

    await use_case.execute(command)
    created = len(repository.candidates)
    await use_case.execute(command)

    assert created == 1
    assert len(repository.candidates) == created


async def test_a_different_key_runs_a_new_investigation() -> None:
    repository = _Repository()
    await _seed(repository)
    investigations = _Investigations()
    source = _Source([_record()])
    use_case = _use_case(repository, source=source, investigations=investigations)

    def command(key: str) -> RunInvestigationInput:
        return RunInvestigationInput(
            watch_id=_WATCH,
            objective=InvestigationObjective.DISCOVER_CANDIDATE,
            caller=_caller(),
            idempotency_key=key,
        )

    first = await use_case.execute(command("key-1"))
    calls = len(source.queries)
    second = await use_case.execute(command("key-2"))

    assert second.id != first.id
    assert len(source.queries) > calls


async def test_a_command_without_a_key_is_not_deduplicated() -> None:
    """Absent key means the caller did not ask for idempotency."""
    repository = _Repository()
    await _seed(repository)
    investigations = _Investigations()
    source = _Source([_record()])
    use_case = _use_case(repository, source=source, investigations=investigations)

    first = await use_case.execute(_discover())
    second = await use_case.execute(_discover())

    assert first.id != second.id


# --- telemetry ---------------------------------------------------------------


async def test_the_iteration_records_which_model_and_prompt_produced_it() -> None:
    repository = _Repository()
    await _seed(repository)

    investigation = await _use_case(repository).execute(_discover())
    telemetry = investigation.iterations[0].telemetry

    assert telemetry is not None
    assert telemetry.model == "test-model"
    assert telemetry.prompt_version == "v1"
    assert telemetry.plan_latency_ms == 10
    assert telemetry.reflection_latency_ms == 10
    assert telemetry.total_latency_ms == 20


async def test_a_failed_reflection_keeps_the_plan_telemetry() -> None:
    repository = _Repository()
    await _seed(repository)

    investigation = await _use_case(
        repository, reasoner=_Reasoner(reflection=TimeoutError("down"))
    ).execute(_discover())
    telemetry = investigation.iterations[0].telemetry

    assert telemetry is not None
    assert telemetry.plan_latency_ms == 10
    assert telemetry.reflection_latency_ms == 0


# --- the lock ----------------------------------------------------------------


async def test_the_lock_is_taken_for_the_target_and_always_released() -> None:
    repository = _Repository()
    await _seed(repository)
    lock = _Lock()

    await _use_case(repository, lock=lock).execute(_discover())

    assert lock.acquired == [f"scientific-return:{_WATCH}:DISCOVER_CANDIDATE:-"]
    assert lock.released == 1


async def test_the_lock_is_released_even_when_the_cycle_fails() -> None:
    repository = _Repository()
    await _seed(repository)
    lock = _Lock()

    await _use_case(
        repository, reasoner=_Reasoner(plan=TimeoutError("down")), lock=lock
    ).execute(_discover())

    assert lock.released == 1


async def test_a_held_lock_stops_the_cycle_before_anything_runs() -> None:
    repository = _Repository()
    await _seed(repository)
    source = _Source([_record()])

    with pytest.raises(RuntimeError, match="locked"):
        await _use_case(
            repository, source=source, lock=_Lock(available=False)
        ).execute(_discover())

    assert source.queries == []
    assert not repository.candidates


async def test_enrichment_locks_a_different_target_than_discovery() -> None:
    repository = _Repository()
    await _seed(repository, candidate=True)
    lock = _Lock()

    await _use_case(repository, lock=lock).execute(
        RunInvestigationInput(
            watch_id=_WATCH,
            objective=InvestigationObjective.ENRICH_CANDIDATE,
            caller=_caller(),
            candidate_id=CandidatePublicationId("cand-1"),
        )
    )

    assert lock.acquired == [
        f"scientific-return:{_WATCH}:ENRICH_CANDIDATE:cand-1"
    ]
