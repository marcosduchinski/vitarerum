from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from app.identity.public import Actor, GroupName, PermissionId
from app.scientific_return.application.agent_analysis import (
    AgentAnalysisNotFound,
    ListCandidateAgentAnalyses,
    RecordAgentAnalysisFeedback,
    RecordAgentAnalysisFeedbackInput,
)
from app.scientific_return.application.analysis import (
    build_evidences,
    plan_adaptive_queries,
    plan_queries,
)
from app.scientific_return.application.evaluation import (
    EvaluationCase,
    evaluate_cases,
    finalize_human_review_report,
    parse_human_reviews,
)
from app.scientific_return.application.ports import (
    BibliographicRecord,
    CandidateReviewItem,
    ProjectSnapshotAssessment,
    ScientificReturnMetrics,
)
from app.scientific_return.application.use_cases import (
    ActivateScientificReturnWatch,
    ActivateWatchInput,
    ChangeWatchReviewInterval,
    ChangeWatchScheduleAnchor,
    ChangeWatchStatus,
    DecideCandidate,
    DecideCandidateInput,
    LookupScientificReturnWatches,
    RunScientificReturnSearch,
    WatchIneligible,
)
from app.scientific_return.domain.enums import (
    AgentAnalysisFeedback,
    AgentAnalysisStatus,
    AgentConfidence,
    AgentRecommendedAction,
    CandidateStatus,
    DecisionType,
    EvidenceStrength,
    EvidenceType,
    QueryType,
    WatchIneligibilityReason,
    WatchStatus,
)
from app.scientific_return.domain.evidence_delta import evidence_identity
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateAnalysisResult,
    CandidateDecision,
    CandidateEvidence,
    CandidateEvidenceId,
    CandidatePublication,
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnQuery,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)


def _caller(group: GroupName = GroupName.CURATORIAL) -> Actor:
    return Actor(
        id=PermissionId("permission-1"),
        group=group,
        email="curator@example.test",
    )


def _analysis_result(
    summary: str,
    confidence: AgentConfidence = AgentConfidence.HIGH,
) -> CandidateAnalysisResult:
    return CandidateAnalysisResult(
        summary=summary,
        supporting_evidence=(),
        contradictions=(),
        missing_evidence=(),
        recommended_action=AgentRecommendedAction.PRESENT_FOR_REVIEW,
        proposed_queries=(),
        reasoning_summary=summary,
        confidence=confidence,
    )


def _snapshot() -> ProjectSnapshotPayload:
    return ProjectSnapshotPayload(
        project_id="project-1",
        project_reference="PRJ-0001",
        researcher="Mariana P. Marques",
        consulted_objects=(
            ConsultedObjectSnapshot(
                id="object-1",
                inventory_number="MUHNAC/MB03-001524",
                object_name="Acontias mukwando",
            ),
        ),
    )


class _ProjectProvider:
    async def assess_completed_project(
        self, project_id: str
    ) -> ProjectSnapshotAssessment:
        return ProjectSnapshotAssessment(
            payload=_snapshot() if project_id == "project-1" else None
        )

    async def assess_completed_projects(
        self, project_ids: tuple[str, ...]
    ) -> dict[str, ProjectSnapshotAssessment]:
        return {
            project_id: await self.assess_completed_project(project_id)
            for project_id in project_ids
        }


class _Source:
    name = "TEST_SOURCE"

    def __init__(self, record: BibliographicRecord) -> None:
        self.record = record
        self.queries: list[str] = []

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        self.queries.append(query)
        return [self.record]


class _AdaptiveSource(_Source):
    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        self.queries.append(query)
        return [self.record] if query.endswith('"Acontias"') else []


class _PublicationWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, CandidatePublication]] = []

    async def add_confirmed_publication(
        self,
        project_id: str,
        caller: Actor,
        candidate: CandidatePublication,
    ) -> str:
        self.calls.append((project_id, candidate))
        return "publication-entry-1"


class _Repository:
    def __init__(self) -> None:
        self.watches: dict[str, ScientificReturnWatch] = {}
        self.snapshots: dict[str, ScientificReturnProjectSnapshot] = {}
        self.runs: dict[str, ScientificReturnSearchRun] = {}
        self.queries: list[ScientificReturnQuery] = []
        self.candidates: dict[str, CandidatePublication] = {}
        self.decisions: list[CandidateDecision] = []
        self.cited_objects: dict[str, int] = {}
        self.agent_analyses: dict[str, CandidateAgentAnalysis] = {}

    async def add_watch(self, watch: ScientificReturnWatch) -> None:
        self.watches[str(watch.id)] = watch

    async def save_watch(self, watch: ScientificReturnWatch) -> None:
        self.watches[str(watch.id)] = watch

    async def get_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnWatch | None:
        return self.watches.get(str(watch_id))

    async def get_watch_by_project(
        self, project_id: str
    ) -> ScientificReturnWatch | None:
        return next(
            (
                watch
                for watch in self.watches.values()
                if watch.project_id == project_id
            ),
            None,
        )

    async def list_watches_by_project_ids(
        self, project_ids: tuple[str, ...]
    ) -> list[ScientificReturnWatch]:
        return [
            watch for watch in self.watches.values() if watch.project_id in project_ids
        ]

    async def list_due_watches(
        self, now: datetime, limit: int
    ) -> list[ScientificReturnWatch]:
        return [
            watch
            for watch in self.watches.values()
            if watch.status is WatchStatus.ACTIVE and watch.next_run_at <= now
        ][:limit]

    async def add_snapshot(self, snapshot: ScientificReturnProjectSnapshot) -> None:
        self.snapshots[str(snapshot.id)] = snapshot

    async def get_snapshot_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnProjectSnapshot | None:
        watch = await self.get_watch(watch_id)
        return self.snapshots.get(str(watch.project_snapshot_id)) if watch else None

    async def add_run(self, run: ScientificReturnSearchRun) -> None:
        self.runs[str(run.id)] = run

    async def save_run(self, run: ScientificReturnSearchRun) -> None:
        self.runs[str(run.id)] = run

    async def get_run(
        self, run_id: ScientificReturnRunId
    ) -> ScientificReturnSearchRun | None:
        return self.runs.get(str(run_id))

    async def list_runs(
        self, watch_id: ScientificReturnWatchId, page: int, size: int
    ) -> tuple[list[ScientificReturnSearchRun], int]:
        items = [run for run in self.runs.values() if run.watch_id == watch_id]
        return items[page * size : page * size + size], len(items)

    async def add_query(self, query: ScientificReturnQuery) -> None:
        self.queries.append(query)

    async def list_queries(self, run_id: str) -> list[ScientificReturnQuery]:
        return [query for query in self.queries if str(query.run_id) == run_id]

    async def get_candidate(
        self, candidate_id: CandidatePublicationId
    ) -> CandidatePublication | None:
        return self.candidates.get(str(candidate_id))

    async def get_candidate_by_key(
        self, watch_id: ScientificReturnWatchId, key: str
    ) -> CandidatePublication | None:
        return next(
            (
                candidate
                for candidate in self.candidates.values()
                if candidate.watch_id == watch_id and candidate.deduplication_key == key
            ),
            None,
        )

    async def add_candidate(self, candidate: CandidatePublication) -> None:
        self.candidates[str(candidate.id)] = candidate

    async def save_candidate(self, candidate: CandidatePublication) -> None:
        self.candidates[str(candidate.id)] = candidate

    async def list_candidates(
        self,
        project_id: str,
        status: CandidateStatus | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidatePublication], int]:
        watch = await self.get_watch_by_project(project_id)
        items = [
            candidate
            for candidate in self.candidates.values()
            if watch is not None
            and candidate.watch_id == watch.id
            and (status is None or candidate.status is status)
        ]
        return items[page * size : page * size + size], len(items)

    async def add_decision(self, decision: CandidateDecision) -> None:
        self.decisions.append(decision)

    async def list_candidates_needing_inventory_proof(
        self, watch_id: ScientificReturnWatchId, limit: int
    ) -> list[CandidatePublication]:
        proof = {
            EvidenceType.INVENTORY_NUMBER,
            EvidenceType.AUTHOR_INVENTORY,
            EvidenceType.INVENTORY_OBJECT,
        }
        return [
            candidate
            for candidate in self.candidates.values()
            if candidate.watch_id == watch_id
            and candidate.status is CandidateStatus.PENDING
            and not proof & {item.type for item in candidate.evidences}
        ][:limit]

    async def list_candidate_queue(
        self,
        status: CandidateStatus | None,
        project_id: str | None,
        source: str | None,
        evidence_strength: EvidenceStrength | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidateReviewItem], int]:
        items = [
            CandidateReviewItem(
                project_id=self.watches[str(candidate.watch_id)].project_id,
                candidate=candidate,
            )
            for candidate in self.candidates.values()
            if (status is None or candidate.status is status)
            and (source is None or candidate.source == source)
            and (
                evidence_strength is None
                or any(
                    evidence.strength is evidence_strength
                    for evidence in candidate.evidences
                )
            )
        ]
        if project_id is not None:
            items = [item for item in items if item.project_id == project_id]
        return items[page * size : page * size + size], len(items)

    async def list_decisions(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateDecision]:
        return [item for item in self.decisions if item.candidate_id == candidate_id]

    async def count_cited_objects(self, candidate_id: CandidatePublicationId) -> int:
        return self.cited_objects.get(str(candidate_id), 0)

    async def add_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None:
        self.agent_analyses[str(analysis.id)] = analysis

    async def save_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None:
        self.agent_analyses[str(analysis.id)] = analysis

    async def get_agent_analysis(
        self, analysis_id: CandidateAgentAnalysisId
    ) -> CandidateAgentAnalysis | None:
        return self.agent_analyses.get(str(analysis_id))

    async def list_agent_analyses(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateAgentAnalysis]:
        return [
            item
            for item in self.agent_analyses.values()
            if item.candidate_id == candidate_id
        ]

    async def list_queries_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> list[ScientificReturnQuery]:
        runs = {str(run.id) for run in self.runs.values() if run.watch_id == watch_id}
        return [item for item in self.queries if str(item.run_id) in runs]

    async def append_candidate_evidences(
        self,
        candidate_id: CandidatePublicationId,
        evidences: tuple[CandidateEvidence, ...],
    ) -> tuple[CandidateEvidence, ...]:
        candidate = self.candidates[str(candidate_id)]
        known = {evidence_identity(item) for item in candidate.evidences}
        written: list[CandidateEvidence] = []
        for evidence in evidences:
            if evidence_identity(evidence) in known:
                continue
            known.add(evidence_identity(evidence))
            candidate.evidences.append(evidence)
            written.append(evidence)
        return tuple(written)

    async def get_metrics(self) -> ScientificReturnMetrics:
        return ScientificReturnMetrics(
            active_watches=len(self.watches),
            runs=len(self.runs),
            failed_runs=0,
            pending_candidates=sum(
                item.status is CandidateStatus.PENDING
                for item in self.candidates.values()
            ),
            confirmed_candidates=0,
            dismissed_candidates=0,
        )


def _record() -> BibliographicRecord:
    return BibliographicRecord(
        source="TEST_SOURCE",
        source_record_id="10.1000/example",
        title="A new species of Acontias mukwando",
        authors=("Mariana P Marques", "Diogo Parrinha"),
        publication_date="2023",
        abstract="The paratype MUNHAC MB03 MB03 001524 was examined.",
        url="https://doi.org/10.1000/example",
        doi="10.1000/example",
        raw_metadata_hash=hashlib.sha256(b"record").hexdigest(),
    )


async def _repository_with_candidate() -> tuple[_Repository, CandidatePublication]:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    await RunScientificReturnSearch(repository, (_Source(_record()),)).execute(
        watch.id, _caller()
    )
    return repository, next(iter(repository.candidates.values()))


@pytest.mark.asyncio
async def test_watch_creation_can_be_paused_without_changing_the_default() -> None:
    repository = _Repository()
    active = await ActivateScientificReturnWatch(
        repository, _ProjectProvider()
    ).execute(ActivateWatchInput("project-1", 90, _caller()))
    assert active.status is WatchStatus.ACTIVE

    second_repository = _Repository()
    paused = await ActivateScientificReturnWatch(
        second_repository, _ProjectProvider()
    ).execute(ActivateWatchInput("project-1", 90, _caller(), start_immediately=False))
    assert paused.status is WatchStatus.PAUSED
    assert await second_repository.list_due_watches(paused.next_run_at, 10) == []


@pytest.mark.asyncio
async def test_watch_creation_reports_typed_and_human_readable_ineligibility() -> None:
    class Provider(_ProjectProvider):
        async def assess_completed_project(
            self, project_id: str
        ) -> ProjectSnapshotAssessment:
            return ProjectSnapshotAssessment(
                ProjectSnapshotPayload(project_id, "PRJ-EMPTY", "Researcher", ())
            )

    with pytest.raises(WatchIneligible) as raised:
        await ActivateScientificReturnWatch(_Repository(), Provider()).execute(
            ActivateWatchInput("empty", 90, _caller())
        )

    assert raised.value.reason is WatchIneligibilityReason.NO_CONSULTED_OBJECTS
    assert str(raised.value) == (
        "The project must contain at least one consulted object."
    )


@pytest.mark.asyncio
async def test_watch_lookup_preserves_order_and_reports_eligibility() -> None:
    repository = _Repository()

    class Provider:
        calls: list[tuple[str, ...]] = []

        async def assess_completed_project(
            self, project_id: str
        ) -> ProjectSnapshotAssessment:
            if project_id == "eligible":
                return ProjectSnapshotAssessment(
                    payload=ProjectSnapshotPayload(
                        project_id="eligible",
                        project_reference="PRJ-2",
                        researcher="Researcher",
                        consulted_objects=(
                            ConsultedObjectSnapshot("object-2", "MUHNAC-2", "Taxon"),
                        ),
                    )
                )
            return ProjectSnapshotAssessment(
                payload=None,
                ineligibility_reason=WatchIneligibilityReason.REQUESTER_NOT_FOUND,
            )

        async def assess_completed_projects(
            self, project_ids: tuple[str, ...]
        ) -> dict[str, ProjectSnapshotAssessment]:
            self.calls.append(project_ids)
            return {
                project_id: await self.assess_completed_project(project_id)
                for project_id in project_ids
            }

    provider = Provider()
    items = await LookupScientificReturnWatches(repository, provider).execute(
        ("missing", "eligible", "missing"), _caller()
    )

    assert [item.project_id for item in items] == ["missing", "eligible"]
    assert items[0].eligible is False
    assert items[0].ineligibility_reason is WatchIneligibilityReason.REQUESTER_NOT_FOUND
    assert items[1].eligible is True
    assert items[1].ineligibility_reason is None
    assert provider.calls == [("missing", "eligible")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "provider_reason", "expected"),
    [
        (
            ProjectSnapshotPayload("p", "PRJ", "Researcher", ()),
            None,
            WatchIneligibilityReason.NO_CONSULTED_OBJECTS,
        ),
        (
            ProjectSnapshotPayload(
                "p", "PRJ", "Researcher", (ConsultedObjectSnapshot("o", "", "Taxon"),)
            ),
            None,
            WatchIneligibilityReason.MISSING_INVENTORY_NUMBER,
        ),
        (
            ProjectSnapshotPayload(
                "p",
                "PRJ",
                "Researcher",
                (ConsultedObjectSnapshot("o", "MUHNAC-1", ""),),
            ),
            None,
            WatchIneligibilityReason.MISSING_OBJECT_NAME,
        ),
        (
            None,
            WatchIneligibilityReason.REQUESTER_NOT_FOUND,
            WatchIneligibilityReason.REQUESTER_NOT_FOUND,
        ),
        (
            None,
            WatchIneligibilityReason.PROJECT_NOT_COMPLETED,
            WatchIneligibilityReason.PROJECT_NOT_COMPLETED,
        ),
    ],
)
async def test_watch_lookup_exposes_each_typed_ineligibility_reason(
    payload: ProjectSnapshotPayload | None,
    provider_reason: WatchIneligibilityReason | None,
    expected: WatchIneligibilityReason,
) -> None:
    class Provider:
        async def assess_completed_project(
            self, project_id: str
        ) -> ProjectSnapshotAssessment:
            return ProjectSnapshotAssessment(payload, provider_reason)

        async def assess_completed_projects(
            self, project_ids: tuple[str, ...]
        ) -> dict[str, ProjectSnapshotAssessment]:
            return {
                project_id: await self.assess_completed_project(project_id)
                for project_id in project_ids
            }

    item = (
        await LookupScientificReturnWatches(_Repository(), Provider()).execute(
            ("project",), _caller()
        )
    )[0]

    assert item.eligible is False
    assert item.ineligibility_reason is expected


def test_planner_uses_only_author_inventory_and_object() -> None:
    queries = plan_queries(_snapshot())

    assert [query.query_type for query in queries] == [
        QueryType.INVENTORY,
        QueryType.AUTHOR_INVENTORY,
        QueryType.INVENTORY_OBJECT,
        QueryType.AUTHOR_OBJECT,
    ]
    assert all("PRJ-0001" not in query.text for query in queries)
    assert all("curator@example.test" not in query.text for query in queries)


def test_adaptive_planner_broadens_only_binomial_object_to_genus() -> None:
    queries = plan_adaptive_queries(_snapshot())

    assert len(queries) == 2
    assert all('"Acontias"' in query.text for query in queries)
    assert all("mukwando" not in query.text for query in queries)


def test_evidence_normalizes_museum_prefix_and_repeated_inventory_segments() -> None:
    evidences = build_evidences(
        CandidatePublicationId("candidate-1"),
        _snapshot(),
        _record(),
        datetime.now(tz=UTC),
    )

    types = {evidence.type for evidence in evidences}
    assert EvidenceType.AUTHOR in types
    assert EvidenceType.OBJECT_NAME in types
    assert EvidenceType.INVENTORY_NUMBER in types
    assert EvidenceType.AUTHOR_INVENTORY in types
    assert all(
        evidence.object_id == "object-1"
        for evidence in evidences
        if evidence.type is not EvidenceType.AUTHOR
    )


@pytest.mark.asyncio
async def test_a_new_interval_is_re_derived_from_the_anchor_not_from_now() -> None:
    """Re-cadencing keeps the curator's anchor and never grants a fresh period."""
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    anchor = watch.schedule_anchor_at
    await RunScientificReturnSearch(repository, (_Source(_record()),)).execute(
        watch.id, _caller()
    )
    assert watch.last_run_at is not None

    updated = await ChangeWatchReviewInterval(repository).execute(
        watch.id, 30, _caller()
    )

    assert updated.review_interval_days == 30
    assert updated.schedule_anchor_at == anchor
    assert updated.next_run_at == anchor + timedelta(days=30)


@pytest.mark.asyncio
async def test_a_late_search_does_not_push_the_series_later() -> None:
    """The grid is measured from the anchor, so a late run does not shift it.

    This is the whole point of the anchor: "every 90 days from 1 March" has to
    keep meaning that even when a sweep starts hours or days behind schedule.
    """
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    anchor = watch.schedule_anchor_at

    watch.record_run(anchor + timedelta(days=3))

    assert watch.next_run_at == anchor + timedelta(days=90)


@pytest.mark.asyncio
async def test_a_long_outage_resumes_at_the_next_future_slot() -> None:
    """A review exists to be current, so missed slots are skipped, not replayed."""
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 30, _caller())
    )
    anchor = watch.schedule_anchor_at

    watch.record_run(anchor + timedelta(days=95))

    assert watch.next_run_at == anchor + timedelta(days=120)


@pytest.mark.asyncio
async def test_a_future_anchor_postpones_the_first_review() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    future = watch.created_at + timedelta(days=200)

    updated = await ChangeWatchScheduleAnchor(repository).execute(
        watch.id, future, _caller()
    )

    assert updated.next_run_at == future


@pytest.mark.parametrize("interval_days", [1, 2, 10])
@pytest.mark.asyncio
async def test_a_daily_sweep_runs_the_watch_every_interval_from_the_anchor(
    interval_days: int,
) -> None:
    """A daily sweep runs the watch on the anchor and every interval after it.

    The panel stores the anchor at midnight UTC and the scheduler wakes the job
    once a day, a few hours later. Only the watch's own interval may decide
    which of those wake-ups search; the wake-up cadence must never show through.
    """
    repository = _Repository()
    anchor = datetime(2026, 9, 5, tzinfo=UTC)
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput(
            "project-1", interval_days, _caller(), schedule_anchor_at=anchor
        )
    )

    searched_on = []
    for day in range(30):
        sweep_at = anchor + timedelta(days=day, hours=2)
        if watch.next_run_at <= sweep_at:
            watch.record_run(sweep_at + timedelta(minutes=1))
            searched_on.append(sweep_at.date())

    assert searched_on == [
        (anchor + timedelta(days=day)).date() for day in range(0, 30, interval_days)
    ]


@pytest.mark.asyncio
async def test_a_new_interval_leaves_a_never_run_watch_due() -> None:
    """Re-cadencing is not a way to postpone a review that is already owed."""
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    due_at = watch.next_run_at

    updated = await ChangeWatchReviewInterval(repository).execute(
        watch.id, 365, _caller()
    )

    assert updated.review_interval_days == 365
    assert updated.next_run_at == due_at
    assert updated.last_run_at is None


@pytest.mark.asyncio
async def test_a_closed_watch_cannot_be_rescheduled() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    await ChangeWatchStatus(repository).execute(watch.id, WatchStatus.CLOSED, _caller())

    with pytest.raises(ValueError, match="closed watch cannot be rescheduled"):
        await ChangeWatchReviewInterval(repository).execute(watch.id, 30, _caller())


@pytest.mark.asyncio
async def test_an_interval_outside_the_allowed_range_is_refused() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )

    for days in (0, 366):
        with pytest.raises(ValueError, match="between 1 and 365"):
            await ChangeWatchReviewInterval(repository).execute(
                watch.id, days, _caller()
            )


@pytest.mark.asyncio
async def test_pipeline_deduplicates_same_record_across_query_trajectories() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput(
            project_id="project-1",
            review_interval_days=90,
            caller=_caller(),
        )
    )
    source = _Source(_record())

    run = await RunScientificReturnSearch(repository, (source,)).execute(
        watch.id, _caller()
    )

    assert run.candidate_count == 1
    assert run.new_candidate_count == 1
    assert len(repository.candidates) == 1
    assert len(repository.queries) == 4
    assert watch.last_run_at is not None
    assert watch.next_run_at > watch.last_run_at


@pytest.mark.asyncio
async def test_pipeline_uses_adaptive_query_after_exact_queries_fail() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    source = _AdaptiveSource(_record())

    run = await RunScientificReturnSearch(repository, (source,)).execute(
        watch.id, _caller()
    )

    assert run.new_candidate_count == 1
    assert len(source.queries) == 6
    assert source.queries[-2].endswith('"Acontias"')
    assert source.queries[-1].endswith('"Acontias"')


@pytest.mark.asyncio
async def test_pipeline_caps_external_queries_per_run() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    source = _Source(_record())

    await RunScientificReturnSearch(
        repository,
        (source,),
        max_queries=2,
    ).execute(watch.id, _caller())

    assert len(source.queries) == 2
    assert len(repository.queries) == 2


@pytest.mark.asyncio
async def test_pipeline_query_cap_is_shared_across_sources() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    first = _Source(_record())
    second = _Source(_record())
    second.name = "SECOND_SOURCE"

    run = await RunScientificReturnSearch(
        repository,
        (first, second),
        max_queries=5,
    ).execute(watch.id, _caller())

    assert len(first.queries) == 4
    assert len(second.queries) == 1
    assert len(repository.queries) == 5
    assert run.source_count == 2


@pytest.mark.asyncio
async def test_dismissed_candidate_is_remembered_on_later_run() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    source = _Source(_record())
    await RunScientificReturnSearch(repository, (source,)).execute(watch.id, _caller())
    candidate = next(iter(repository.candidates.values()))
    candidate.dismiss()

    second_run = await RunScientificReturnSearch(repository, (source,)).execute(
        watch.id, _caller()
    )

    assert second_run.candidate_count == 1
    assert second_run.new_candidate_count == 0
    assert len(repository.candidates) == 1
    assert candidate.status is CandidateStatus.DISMISSED


@pytest.mark.asyncio
async def test_confirm_materializes_publication_and_audits_evidence() -> None:
    repository = _Repository()
    watch = await ActivateScientificReturnWatch(repository, _ProjectProvider()).execute(
        ActivateWatchInput("project-1", 90, _caller())
    )
    await RunScientificReturnSearch(repository, (_Source(_record()),)).execute(
        watch.id, _caller()
    )
    candidate = next(iter(repository.candidates.values()))
    writer = _PublicationWriter()

    confirmed = await DecideCandidate(repository, writer).execute(
        DecideCandidateInput(
            candidate_id=candidate.id,
            decision=DecisionType.CONFIRM,
            caller=_caller(),
        )
    )

    assert confirmed.status is CandidateStatus.CONFIRMED
    assert confirmed.confirmed_publication_entry_id == "publication-entry-1"
    assert writer.calls[0][0] == "project-1"
    assert repository.decisions[0].evidence_snapshot


@pytest.mark.asyncio
async def test_decision_context_uses_latest_full_agentic_reader_only() -> None:
    repository, candidate = await _repository_with_candidate()

    def completed_analysis(
        analysis_id: str,
        prompt_id: str,
        query: str,
        explanation: str,
    ) -> CandidateAgentAnalysis:
        analysis = CandidateAgentAnalysis(
            id=CandidateAgentAnalysisId(analysis_id),
            candidate_id=candidate.id,
            run_id=candidate.first_seen_run_id,
            status=AgentAnalysisStatus.RUNNING,
            model="test-model",
            prompt_version_id=prompt_id,
            prompt_version="v1",
            input_payload={
                "query": query,
                "source": "OPENALEX",
                "passages": [f"passage {query}"],
                "inventoryForms": ["MB06-5747"],
                "knowledgeItemIds": [],
            },
            input_hash=analysis_id,
            started_at=datetime.now(tz=UTC),
            created_by=PermissionId("permission-1"),
        )
        analysis.complete(
            _analysis_result(explanation),
            "response-hash",
            datetime.now(tz=UTC),
        )
        return analysis

    unrelated = completed_analysis(
        "unrelated", "pver-other-analysis", "unrelated query", "unrelated"
    )
    newest = completed_analysis(
        "newest",
        "pver-sr-full-reader-v2",
        "new query",
        "new explanation",
    )
    newest.prompt_version = "scientific-return-full-agentic-reader-v2"
    # The registry labelled the archived v1 with underscores, so a rollback to
    # it must still be recognised as a full-agentic reader analysis.
    oldest = completed_analysis(
        "oldest",
        "pver-sr-full-reader-v1",
        "old query",
        "old explanation",
    )
    oldest.prompt_version = "scientific_return_full_agentic_reader-v1"
    repository.agent_analyses = {
        str(unrelated.id): unrelated,
        str(newest.id): newest,
        str(oldest.id): oldest,
    }

    context = await DecideCandidate(repository, _PublicationWriter())._decision_context(
        candidate.id
    )

    assert context is not None
    assert context.queries == ("new query",)
    assert context.explanation == "new explanation"


@pytest.mark.asyncio
async def test_a_rolled_back_reader_version_still_yields_a_decision_context() -> None:
    repository, candidate = await _repository_with_candidate()
    analysis = CandidateAgentAnalysis(
        id=CandidateAgentAnalysisId("v1-only"),
        candidate_id=candidate.id,
        run_id=candidate.first_seen_run_id,
        status=AgentAnalysisStatus.RUNNING,
        model="test-model",
        prompt_version_id="pver-sr-full-reader-v1",
        prompt_version="scientific_return_full_agentic_reader-v1",
        input_payload={
            "query": "rolled back query",
            "source": "EUROPE_PMC",
            "passages": ["Specimen MB06-5747 was examined."],
            "inventoryForms": ["MB06-5747"],
            "knowledgeItemIds": [],
        },
        input_hash="v1-only",
        started_at=datetime.now(tz=UTC),
        created_by=PermissionId("permission-1"),
    )
    analysis.complete(
        _analysis_result("rolled back explanation"),
        "response-hash",
        datetime.now(tz=UTC),
    )
    repository.agent_analyses = {str(analysis.id): analysis}

    context = await DecideCandidate(repository, _PublicationWriter())._decision_context(
        candidate.id
    )

    assert context is not None
    assert context.queries == ("rolled back query",)


@pytest.mark.asyncio
async def test_non_reader_analysis_does_not_create_agentic_decision_context() -> None:
    repository, candidate = await _repository_with_candidate()
    analysis = CandidateAgentAnalysis(
        id=CandidateAgentAnalysisId("non-reader"),
        candidate_id=candidate.id,
        run_id=candidate.first_seen_run_id,
        status=AgentAnalysisStatus.RUNNING,
        model="test-model",
        prompt_version_id="pver-other-analysis",
        prompt_version="v1",
        input_payload={"query": "not an agentic trajectory"},
        input_hash="non-reader",
        started_at=datetime.now(tz=UTC),
        created_by=PermissionId("permission-1"),
    )
    analysis.complete(
        _analysis_result("unrelated", AgentConfidence.LOW),
        "response-hash",
        datetime.now(tz=UTC),
    )
    await repository.add_agent_analysis(analysis)

    context = await DecideCandidate(repository, _PublicationWriter())._decision_context(
        candidate.id
    )

    assert context is None


@pytest.mark.asyncio
async def test_evaluation_reports_per_source_metrics_and_review_queue() -> None:
    case = EvaluationCase(
        case_id="known-case",
        author="Mariana P. Marques",
        inventory_number="MUHNAC/MB03-001524",
        object_name="Acontias mukwando",
        expected_title="A new species of Acontias",
        expected_doi="10.1000/example",
        notes="Known evaluation case.",
    )

    report = await evaluate_cases((_Source(_record()),), cases=(case,), result_limit=10)

    assert report["retrievedCount"] == 1
    assert report["actionableCandidates"] == 1
    assert report["knownActionableMatches"] == 1
    source_metrics = report["sourceMetrics"]
    assert isinstance(source_metrics, list)
    assert source_metrics[0]["source"] == "TEST_SOURCE"
    assert source_metrics[0]["recall"] == 1.0
    review_queue = report["reviewQueue"]
    assert isinstance(review_queue, list)
    assert review_queue[0]["known_case_match"] is True
    assert review_queue[0]["human_decision"] is None

    review_queue[0].update(
        {
            "human_decision": "CONFIRMED",
            "human_justification": "Inventory and taxon verified in the article.",
            "reviewer": "curator-1",
            "reviewed_at": "2026-08-16T12:00:00Z",
        }
    )
    reviewed_report = await evaluate_cases(
        (_Source(_record()),),
        cases=(case,),
        result_limit=10,
        human_reviews=parse_human_reviews({"reviewQueue": review_queue}),
    )

    review_metrics = reviewed_report["humanReviewMetrics"]
    assert isinstance(review_metrics, dict)
    assert review_metrics["review_coverage"] == 1.0
    assert review_metrics["human_precision"] == 1.0

    finalized = finalize_human_review_report({**report, "reviewQueue": review_queue})
    finalized_metrics = finalized["humanReviewMetrics"]
    assert isinstance(finalized_metrics, dict)
    assert finalized_metrics["review_coverage"] == 1.0
    assert finalized_metrics["human_precision"] == 1.0
    assert "reviewFinalizedAt" in finalized


def test_phase_zero_review_requires_a_timezone() -> None:
    with pytest.raises(ValueError, match="timezone"):
        parse_human_reviews(
            {
                "reviews": [
                    {
                        "review_id": "case|doi:10.1000/example",
                        "human_decision": "CONFIRMED",
                        "human_justification": "Verified by staff.",
                        "reviewer": "curator-1",
                        "reviewed_at": "2026-08-16T12:00:00",
                    }
                ]
            }
        )


@pytest.mark.asyncio
async def test_curator_can_record_feedback_once_on_completed_analysis() -> None:
    repository, candidate = await _repository_with_candidate()
    analysis = CandidateAgentAnalysis(
        id=CandidateAgentAnalysisId("reader-analysis"),
        candidate_id=candidate.id,
        run_id=candidate.first_seen_run_id,
        status=AgentAnalysisStatus.RUNNING,
        model="reader-model",
        prompt_version_id="pver-sr-full-reader-v2",
        prompt_version="scientific-return-full-agentic-reader-v2",
        input_payload={"query": "reader query"},
        input_hash="reader-analysis",
        started_at=datetime.now(tz=UTC),
        created_by=PermissionId("permission-1"),
    )
    analysis.complete(
        _analysis_result("Evidence is sufficient for human review."),
        "response-hash",
        datetime.now(tz=UTC),
    )
    await repository.add_agent_analysis(analysis)

    reviewed = await RecordAgentAnalysisFeedback(repository).execute(
        RecordAgentAnalysisFeedbackInput(
            analysis_id=analysis.id,
            feedback=AgentAnalysisFeedback.USEFUL,
            comment="The recommendation accelerated the review.",
            caller=_caller(),
        )
    )

    assert reviewed.staff_feedback is AgentAnalysisFeedback.USEFUL
    assert reviewed.feedback_at is not None
    with pytest.raises(ValueError, match="already been recorded"):
        await RecordAgentAnalysisFeedback(repository).execute(
            RecordAgentAnalysisFeedbackInput(
                analysis_id=analysis.id,
                feedback=AgentAnalysisFeedback.NOT_USEFUL,
                comment=None,
                caller=_caller(),
            )
        )


@pytest.mark.asyncio
async def test_analysis_history_and_feedback_exclude_non_reader_records() -> None:
    repository, candidate = await _repository_with_candidate()
    non_reader = CandidateAgentAnalysis(
        id=CandidateAgentAnalysisId("non-reader-feedback"),
        candidate_id=candidate.id,
        run_id=candidate.first_seen_run_id,
        status=AgentAnalysisStatus.RUNNING,
        model="unrelated-model",
        prompt_version_id="pver-other-analysis",
        prompt_version="other-v1",
        input_payload={},
        input_hash="non-reader-feedback",
        started_at=datetime.now(tz=UTC),
        created_by=PermissionId("permission-1"),
    )
    non_reader.complete(
        _analysis_result("Unrelated analysis."),
        "response-hash",
        datetime.now(tz=UTC),
    )
    await repository.add_agent_analysis(non_reader)

    assert (
        await ListCandidateAgentAnalyses(repository).execute(candidate.id, _caller())
        == []
    )
    with pytest.raises(AgentAnalysisNotFound):
        await RecordAgentAnalysisFeedback(repository).execute(
            RecordAgentAnalysisFeedbackInput(
                analysis_id=non_reader.id,
                feedback=AgentAnalysisFeedback.USEFUL,
                comment=None,
                caller=_caller(),
            )
        )


def _unproven_candidate(
    candidate_id: str,
    watch_id: ScientificReturnWatchId,
    evidences: list[CandidateEvidence],
) -> CandidatePublication:
    return CandidatePublication(
        id=CandidatePublicationId(candidate_id),
        watch_id=watch_id,
        first_seen_run_id=ScientificReturnRunId("run-1"),
        source="OPENALEX",
        source_record_id="record-1",
        deduplication_key=f"key-{candidate_id}",
        title="First record of Cynoscion regalis",
        authors=("Gomes",),
        publication_date=None,
        abstract=None,
        url=None,
        raw_metadata_hash="hash",
        created_at=datetime.now(tz=UTC),
        evidences=evidences,
    )


def _evidence(kind: EvidenceType) -> CandidateEvidence:
    return CandidateEvidence(
        id=CandidateEvidenceId("evidence-1"),
        candidate_id=CandidatePublicationId("candidate-x"),
        type=kind,
        strength=EvidenceStrength.PRIMARY,
        value="MB06-005747",
        source_field="indexed_text",
        explanation="",
        created_at=datetime.now(tz=UTC),
    )


@pytest.mark.asyncio
async def test_only_candidates_without_inventory_proof_are_selected() -> None:
    """The enrichment chain must skip candidates already tied to a specimen.

    Re-querying a proven candidate spends exact-phrase budget to learn nothing,
    and the whole point of the third rung is the unproven remainder the semantic
    search leaves behind.
    """
    repository = _Repository()
    watch_id = ScientificReturnWatchId("watch-1")
    unproven = _unproven_candidate("no-evidence", watch_id, [])
    by_object = _unproven_candidate(
        "object-only", watch_id, [_evidence(EvidenceType.OBJECT_NAME)]
    )
    proven = _unproven_candidate(
        "inventory", watch_id, [_evidence(EvidenceType.INVENTORY_NUMBER)]
    )
    pair = _unproven_candidate(
        "author-inventory", watch_id, [_evidence(EvidenceType.AUTHOR_INVENTORY)]
    )
    for candidate in (unproven, by_object, proven, pair):
        repository.candidates[str(candidate.id)] = candidate

    selected = await repository.list_candidates_needing_inventory_proof(watch_id, 10)

    assert {str(item.id) for item in selected} == {str(unproven.id), str(by_object.id)}


@pytest.mark.asyncio
async def test_decided_candidates_are_never_re_proven() -> None:
    repository = _Repository()
    watch_id = ScientificReturnWatchId("watch-1")
    dismissed = _unproven_candidate("dismissed", watch_id, [])
    dismissed.dismiss()
    repository.candidates[str(dismissed.id)] = dismissed

    assert await repository.list_candidates_needing_inventory_proof(watch_id, 10) == []
