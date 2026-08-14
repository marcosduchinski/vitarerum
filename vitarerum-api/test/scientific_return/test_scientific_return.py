from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from app.identity.public import Actor, GroupName, PermissionId
from app.scientific_return.application.analysis import build_evidences, plan_queries
from app.scientific_return.application.ports import BibliographicRecord
from app.scientific_return.application.use_cases import (
    ActivateScientificReturnWatch,
    ActivateWatchInput,
    DecideCandidate,
    DecideCandidateInput,
    RunScientificReturnSearch,
)
from app.scientific_return.domain.enums import (
    CandidateStatus,
    DecisionType,
    EvidenceType,
    QueryType,
)
from app.scientific_return.domain.models import (
    CandidateDecision,
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
    async def get_completed_project(
        self, project_id: str
    ) -> ProjectSnapshotPayload | None:
        return _snapshot() if project_id == "project-1" else None


class _Source:
    name = "TEST_SOURCE"

    def __init__(self, record: BibliographicRecord) -> None:
        self.record = record
        self.queries: list[str] = []

    async def search(self, query: str, limit: int) -> list[BibliographicRecord]:
        self.queries.append(query)
        return [self.record]


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

    async def list_decisions(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateDecision]:
        return [item for item in self.decisions if item.candidate_id == candidate_id]


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
    assert len(repository.candidates) == 1
    assert len(repository.queries) == 4
    assert watch.last_run_at is not None
    assert watch.next_run_at > watch.last_run_at


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


def test_snooze_requires_a_future_date() -> None:
    candidate = CandidatePublication(
        id=CandidatePublicationId("candidate-1"),
        watch_id=ScientificReturnWatchId("watch-1"),
        first_seen_run_id=ScientificReturnRunId("run-1"),
        source="TEST",
        source_record_id="record-1",
        deduplication_key="key-1",
        title="Title",
        authors=(),
        publication_date=None,
        abstract=None,
        url=None,
        raw_metadata_hash="hash",
        created_at=datetime.now(tz=UTC),
    )
    now = datetime.now(tz=UTC)

    with pytest.raises(ValueError, match="future"):
        candidate.snooze(now - timedelta(days=1), now)
