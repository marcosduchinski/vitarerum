from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.identity.public import Actor, GroupName
from app.scientific_return.application.agent_tools import (
    normalized_tool_idempotency_key,
)
from app.scientific_return.application.full_agentic import (
    CloseAbandonedFullAgenticInvestigations,
    ExecuteFullAgenticInput,
    ExecuteFullAgenticScientificReturn,
    FullAgenticCircuitOpen,
    FullAgenticConfiguration,
    FullAgenticSourceConfigurationInvalid,
    StartFullAgenticInput,
    StartFullAgenticScientificReturn,
)
from app.scientific_return.application.full_agentic_ports import (
    AgenticPlan,
    AssessmentResult,
    LearningProposal,
)
from app.scientific_return.application.ports import (
    AgentReasonerTimeout,
    BibliographicRecord,
    BibliographicSourceCapabilities,
    ScientificReturnMetrics,
)
from app.scientific_return.domain.enums import (
    AgentConfidence,
    AgenticToolExecutionStatus,
    AgenticTrajectoryEventKind,
    CandidateStatus,
    FullAgenticInvestigationStatus,
    InvestigationObjective,
    RunKind,
    RunStatus,
    SearchIntent,
    SearchStrategy,
    WatchStatus,
)
from app.scientific_return.domain.full_agentic_models import (
    AgenticBudget,
    AgenticCandidateLink,
    AgenticSearchSpec,
    AgenticToolExecution,
    AgenticToolExecutionId,
    AgenticTrajectoryEvent,
    AgenticTrajectoryEventId,
    AgenticUsage,
    ArticleAssessment,
    FullAgenticInvestigation,
    FullAgenticInvestigationId,
    KnowledgeItemId,
    ScientificReturnKnowledgeItem,
)
from app.scientific_return.domain.models import (
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnSnapshotId,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)
from app.shared.kernel import PermissionId

from .test_scientific_return import _Repository

_NOW = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.tick = 0

    def now(self) -> datetime:
        self.tick += 1
        return _NOW + timedelta(seconds=self.tick)


class Uow:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


class Dispatcher:
    def __init__(self) -> None:
        self.ids: list[str] = []

    async def enqueue(self, investigation_id: FullAgenticInvestigationId) -> None:
        self.ids.append(str(investigation_id))


class FullRepository:
    def __init__(self) -> None:
        self.investigations: dict[str, FullAgenticInvestigation] = {}
        self.events: list[AgenticTrajectoryEvent] = []
        self.tools: dict[str, AgenticToolExecution] = {}
        self.links: list[AgenticCandidateLink] = []
        self.knowledge: dict[str, ScientificReturnKnowledgeItem] = {}

    async def add_knowledge(self, item: ScientificReturnKnowledgeItem) -> None:
        self.knowledge[str(item.id)] = item

    async def save_knowledge(self, item: ScientificReturnKnowledgeItem) -> None:
        self.knowledge[str(item.id)] = item

    async def get_knowledge(
        self, item_id: KnowledgeItemId
    ) -> ScientificReturnKnowledgeItem | None:
        return self.knowledge.get(str(item_id))

    async def add_investigation(self, item: FullAgenticInvestigation) -> None:
        self.investigations[str(item.id)] = item

    async def save_investigation(self, item: FullAgenticInvestigation) -> None:
        item.version += 1
        self.investigations[str(item.id)] = item

    async def claim_investigation(
        self,
        investigation_id: FullAgenticInvestigationId,
        worker_id: str,
        claimed_at: datetime,
        lease_expires_at: datetime,
    ) -> FullAgenticInvestigation | None:
        item = self.investigations[str(investigation_id)]
        if item.status.is_terminal:
            return None
        if (
            item.status
            in {
                FullAgenticInvestigationStatus.RUNNING,
                FullAgenticInvestigationStatus.CANCEL_REQUESTED,
            }
            and item.lease_expires_at is not None
            and item.lease_expires_at > claimed_at
        ):
            return None
        if item.status is FullAgenticInvestigationStatus.QUEUED:
            item.start(claimed_at)
        else:
            # Mirrors the SQL: only a take-over from a cold lease is a recovery.
            item.record_recovery(claimed_at, "Lease expired before the worker finished")
        item.lease_owner = worker_id
        item.lease_expires_at = lease_expires_at
        item.version += 1
        return item

    async def list_abandoned(
        self, created_before: datetime, limit: int
    ) -> list[FullAgenticInvestigation]:
        return sorted(
            (
                item
                for item in self.investigations.values()
                if not item.status.is_terminal and item.created_at < created_before
            ),
            key=lambda item: item.created_at,
        )[:limit]

    async def renew_investigation_lease(
        self,
        investigation_id: FullAgenticInvestigationId,
        worker_id: str,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> int | None:
        item = self.investigations[str(investigation_id)]
        if (
            item.status is not FullAgenticInvestigationStatus.RUNNING
            or item.lease_owner != worker_id
            or item.lease_expires_at is None
            or item.lease_expires_at <= heartbeat_at
        ):
            return None
        item.heartbeat_at = heartbeat_at
        item.lease_expires_at = lease_expires_at
        item.version += 1
        return item.version

    async def reserve_llm_call(
        self,
        investigation: FullAgenticInvestigation,
        worker_id: str,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> int | None:
        item = self.investigations[str(investigation.id)]
        if (
            item.status is not FullAgenticInvestigationStatus.RUNNING
            or item.lease_owner != worker_id
            or item.lease_expires_at is None
            or item.lease_expires_at <= heartbeat_at
            or item.version != investigation.version
        ):
            return None
        item.usage = investigation.usage
        item.heartbeat_at = heartbeat_at
        item.lease_expires_at = lease_expires_at
        item.version += 1
        return item.version

    async def get_investigation(
        self, item_id: FullAgenticInvestigationId
    ) -> FullAgenticInvestigation | None:
        return self.investigations.get(str(item_id))

    async def get_by_idempotency_key(self, key: str) -> FullAgenticInvestigation | None:
        return next(
            (
                item
                for item in self.investigations.values()
                if item.idempotency_key == key
            ),
            None,
        )

    async def find_live_target(
        self, watch_id: str, objective: str, candidate_id: str | None
    ) -> FullAgenticInvestigation | None:
        return next(
            (
                item
                for item in self.investigations.values()
                if str(item.watch_id) == watch_id
                and item.objective.value == objective
                and str(item.candidate_id or "") == str(candidate_id or "")
                and not item.status.is_terminal
            ),
            None,
        )

    async def list_investigations(
        self, watch_id: str, limit: int
    ) -> list[FullAgenticInvestigation]:
        return list(self.investigations.values())[:limit]

    async def append_event(self, event: AgenticTrajectoryEvent) -> None:
        self.events.append(event)

    async def list_events(
        self, investigation_id: FullAgenticInvestigationId
    ) -> list[AgenticTrajectoryEvent]:
        return [
            event for event in self.events if event.investigation_id == investigation_id
        ]

    async def next_event_sequence(
        self, investigation_id: FullAgenticInvestigationId
    ) -> int:
        return (
            max(
                (
                    event.sequence
                    for event in self.events
                    if event.investigation_id == investigation_id
                ),
                default=0,
            )
            + 1
        )

    async def add_knowledge_usage(
        self,
        investigation_id: str,
        knowledge_item_id: str,
        prompt_step: str,
        used_at: datetime,
    ) -> None:
        pass

    async def list_knowledge(
        self, *, active_only: bool, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        return []

    async def find_knowledge_exact(
        self, registered_number: str, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        return []

    async def link_candidate(self, link: AgenticCandidateLink) -> bool:
        if any(
            existing.investigation_id == link.investigation_id
            and existing.candidate_id == link.candidate_id
            for existing in self.links
        ):
            return False
        self.links.append(link)
        return True

    async def add_tool_execution(self, execution: AgenticToolExecution) -> None:
        self.tools[execution.idempotency_key] = execution

    async def save_tool_execution(self, execution: AgenticToolExecution) -> None:
        self.tools[execution.idempotency_key] = execution

    async def get_tool_execution(self, key: str) -> AgenticToolExecution | None:
        return self.tools.get(key)


class Reasoner:
    model_name = "test-agent"

    def __init__(self) -> None:
        self.plans = 0

    async def plan(self, **kwargs: object) -> AgenticPlan:
        self.plans += 1
        if self.plans > 1:
            return AgenticPlan((), "Enough evidence", True)
        return AgenticPlan(
            (
                AgenticSearchSpec(
                    source="TEST",
                    query="MB06-5747 Cynoscion regalis",
                    intent=SearchIntent.INVENTORY_EVIDENCE,
                    strategy=SearchStrategy.INVENTORY_QUERY,
                    object_id="object-1",
                ),
            ),
            "Apply curator example",
        )

    async def assess(self, **kwargs: object) -> AssessmentResult:
        return AssessmentResult(
            assessment=ArticleAssessment(
                relevant=True,
                confidence=AgentConfidence.HIGH,
                explanation="The passage connects the inventory form to the specimen.",
                passages=("Specimen MB06-5747 was examined.",),
                inventory_forms=("MB06-5747",),
                contradictions=(),
            ),
            prompt_version_id="pver-sr-full-reader-v2",
            prompt_version="scientific-return-full-agentic-reader-v2",
        )

    async def learn(self, **kwargs: object) -> LearningProposal:
        return LearningProposal("Curator lesson", None, None)


class Source:
    name = "TEST"
    capabilities = BibliographicSourceCapabilities(
        name="TEST",
        searches_metadata=True,
        searches_indexed_full_text=True,
        returns_abstract=True,
        returns_inspectable_full_text=True,
        supports_structured_author=True,
    )

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        return [
            BibliographicRecord(
                source=self.name,
                source_record_id="record-1",
                title="Cynoscion study",
                authors=("Researcher",),
                publication_date="2025",
                abstract="Specimen MB06-5747 was examined.",
                url="https://example.test/article",
                doi="10.1/example",
                raw_metadata_hash="hash",
            )
        ]


class MultiSourceReasoner(Reasoner):
    async def plan(self, **kwargs: object) -> AgenticPlan:
        self.plans += 1
        if self.plans > 1:
            return AgenticPlan((), "Enough evidence", True)
        return AgenticPlan(
            tuple(
                AgenticSearchSpec(
                    source=source,
                    query="MB06-5747",
                    intent=SearchIntent.DISCOVERY,
                    strategy=SearchStrategy.OBJECT_QUERY,
                )
                for source in ("CROSSREF", "OPENALEX")
            ),
            "Search both",
        )


class NamedSource(Source):
    def __init__(
        self,
        name: str,
        record_id: str,
        *,
        indexed_text: str | None = None,
    ) -> None:
        self.name = name
        self.record_id = record_id
        self.indexed_text = indexed_text
        self.authors: list[str | None] = []
        self.capabilities = replace(Source.capabilities, name=name)

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        self.authors.append(author)
        return [
            BibliographicRecord(
                source=self.name,
                source_record_id=self.record_id,
                title="The same DOI from another index",
                authors=("Another author",),
                publication_date="2025",
                abstract="Specimen MB06-5747 was examined.",
                url="https://example.test/article",
                doi="10.1/shared",
                raw_metadata_hash=f"hash-{self.record_id}",
                indexed_text=self.indexed_text,
                indexed_text_source="OPEN_ACCESS_FULL_TEXT"
                if self.indexed_text
                else None,
            )
        ]


class MalformedThenValidReasoner(Reasoner):
    async def assess(self, **kwargs: object) -> AssessmentResult:
        record = kwargs["record"]
        assert isinstance(record, BibliographicRecord)
        if record.source_record_id == "malformed":
            raise ValueError("invalid confidence")
        return await super().assess(**kwargs)


class TwoRecordSource(Source):
    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        return [
            BibliographicRecord(
                source=self.name,
                source_record_id=record_id,
                title=record_id,
                authors=(),
                publication_date="2025",
                abstract="MB06-5747",
                url=None,
                doi=f"10.1/{record_id}",
                raw_metadata_hash=record_id,
            )
            for record_id in ("malformed", "valid")
        ]


class FailingPlannerReasoner(Reasoner):
    async def plan(self, **kwargs: object) -> AgenticPlan:
        self.plans += 1
        raise ValueError("invalid planner contract")


class RepeatingReasoner(Reasoner):
    async def plan(self, **kwargs: object) -> AgenticPlan:
        self.plans += 1
        return AgenticPlan(
            (
                AgenticSearchSpec(
                    source="TEST",
                    query="repeat me",
                    intent=SearchIntent.DISCOVERY,
                    strategy=SearchStrategy.OBJECT_QUERY,
                ),
            ),
            "Repeat to prove application deduplication",
        )


class CountingSource(Source):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        self.calls.append((query, author))
        return await super().search(query, limit, author=author)


def setup_scientific_repository(
    object_count: int = 1,
) -> tuple[_Repository, ScientificReturnWatch]:
    repository = _Repository()
    snapshot = ScientificReturnProjectSnapshot(
        id=ScientificReturnSnapshotId("snapshot-1"),
        project_id="project-1",
        payload=ProjectSnapshotPayload(
            project_id="project-1",
            project_reference="PRJ-1",
            researcher="Researcher",
            consulted_objects=tuple(
                ConsultedObjectSnapshot(
                    id=f"object-{index}",
                    inventory_number=f"MUHNAC/MB06-00574{index}",
                    object_name=(
                        "Cynoscion regalis" if index == 1 else f"Taxon {index}"
                    ),
                )
                for index in range(1, object_count + 1)
            ),
        ),
        payload_hash="snapshot-hash",
        builder_version="v1",
        created_at=_NOW,
    )
    watch = ScientificReturnWatch(
        id=ScientificReturnWatchId("watch-1"),
        project_id="project-1",
        status=WatchStatus.ACTIVE,
        review_interval_days=90,
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
        next_run_at=_NOW,
        schedule_anchor_at=_NOW,
        project_snapshot_id=snapshot.id,
    )
    repository.snapshots[str(snapshot.id)] = snapshot
    repository.watches[str(watch.id)] = watch
    return repository, watch


class CircuitScientificRepository(_Repository):
    async def get_metrics(self) -> ScientificReturnMetrics:
        return ScientificReturnMetrics(
            active_watches=1,
            runs=0,
            failed_runs=0,
            pending_candidates=0,
            confirmed_candidates=0,
            dismissed_candidates=0,
            full_agentic_confirmed_candidates=1,
            full_agentic_dismissed_candidates=4,
        )


@pytest.mark.asyncio
async def test_circuit_breaker_uses_only_full_agentic_human_outcomes() -> None:
    scientific, watch = setup_scientific_repository()
    scientific.__class__ = CircuitScientificRepository
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
        circuit_min_decisions=5,
        circuit_min_precision=0.5,
    )

    with pytest.raises(FullAgenticCircuitOpen):
        await StartFullAgenticScientificReturn(
            scientific,
            FullRepository(),
            Dispatcher(),
            Uow(),
            Clock(),
            config,
        ).execute(
            StartFullAgenticInput(
                watch_id=watch.id,
                objective=InvestigationObjective.DISCOVER_CANDIDATE,
                candidate_id=None,
                idempotency_key="circuit-open",
                caller=Actor(PermissionId("permission-1"), GroupName.CURATORIAL),
            )
        )


@pytest.mark.asyncio
async def test_invalid_operational_source_configuration_fails_before_enqueue() -> None:
    scientific, watch = setup_scientific_repository()
    dispatcher = Dispatcher()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("EUROPE_PMC",),
        budget=AgenticBudget(1, 1, 1, 1, 2),
        operational_sources=("CROSSREF",),
        evidence_sources=(),
    )

    with pytest.raises(FullAgenticSourceConfigurationInvalid):
        await StartFullAgenticScientificReturn(
            scientific, FullRepository(), dispatcher, Uow(), Clock(), config
        ).execute(
            StartFullAgenticInput(
                watch.id,
                InvestigationObjective.DISCOVER_CANDIDATE,
                None,
                "invalid-sources",
                Actor(PermissionId("permission-1"), GroupName.CURATORIAL),
            )
        )

    assert dispatcher.ids == []
    diagnostics = config.source_diagnostics()
    assert diagnostics["configurationValid"] is False
    assert diagnostics["unavailableSources"] == ["EUROPE_PMC"]


@pytest.mark.asyncio
async def test_agent_presents_without_deterministic_gate() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    dispatcher = Dispatcher()
    uow = Uow()
    clock = Clock()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
    )
    actor = Actor(PermissionId("permission-1"), GroupName.CURATORIAL)
    investigation = await StartFullAgenticScientificReturn(
        scientific,
        repository,
        dispatcher,
        uow,
        clock,
        config,
    ).execute(
        StartFullAgenticInput(
            watch_id=watch.id,
            objective=InvestigationObjective.DISCOVER_CANDIDATE,
            candidate_id=None,
            idempotency_key="request-1",
            caller=actor,
        )
    )
    original_next_run = watch.next_run_at

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        Reasoner(),
        (Source(),),
        uow,
        clock,
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert completed.status is FullAgenticInvestigationStatus.COMPLETED
    assert len(scientific.candidates) == 1
    candidate = next(iter(scientific.candidates.values()))
    assert candidate.status is CandidateStatus.PENDING
    assert candidate.confirmed_publication_entry_id is None
    assert scientific.decisions == []
    assert candidate.evidences == []
    assert next(iter(scientific.runs.values())).run_kind is RunKind.FULL_AGENTIC
    assert scientific.queries[0].query_text == '"Cynoscion regalis"'
    assert repository.links[0].relation_kind.value == "CREATED"
    analysis = next(iter(scientific.agent_analyses.values()))
    assert analysis.prompt_version_id == "pver-sr-full-reader-v2"
    assert analysis.prompt_version == "scientific-return-full-agentic-reader-v2"
    # The claimed form is literally in the abstract the reader received.
    assert analysis.input_payload["inventoryEvidenceStatus"] == "VERIFIED"
    assert watch.next_run_at == original_next_run
    assert (
        next(iter(repository.tools.values())).status
        is AgenticToolExecutionStatus.COMPLETED
    )
    event_kinds = [event.kind for event in repository.events]
    for expected in (
        AgenticTrajectoryEventKind.PLAN_CREATED,
        AgenticTrajectoryEventKind.TOOL_STARTED,
        AgenticTrajectoryEventKind.ARTICLE_ASSESSED,
        AgenticTrajectoryEventKind.CANDIDATE_LINKED,
    ):
        assert expected in event_kinds


@pytest.mark.asyncio
async def test_same_doi_from_multiple_sources_is_linked_only_once() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    clock = Clock()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("CROSSREF", "OPENALEX"),
        budget=AgenticBudget(2, 4, 10, 3, 8),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-shared-doi"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="shared-doi",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        MultiSourceReasoner(),
        (NamedSource("CROSSREF", "crossref-1"), NamedSource("OPENALEX", "W1")),
        Uow(),
        clock,
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert completed.status is FullAgenticInvestigationStatus.COMPLETED
    assert len(scientific.candidates) == 1
    assert len(repository.links) == 1
    assert completed.usage.candidates == 1
    # Two floor attempts (author+object and the bare inventory code) plus the
    # two the planner asked for.
    assert completed.usage.queries == 4


@pytest.mark.asyncio
async def test_repeated_search_is_deduplicated_between_iterations() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    source = CountingSource()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(4, 6, 10, 3, 10),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-dedup"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="dedup",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        RepeatingReasoner(),
        (source,),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    # Both floor attempts plus the single execution of the repeated query.
    assert completed.usage.queries == 3
    assert [query for query, _ in source.calls].count("repeat me") == 1
    assert any(
        event.kind.value == "SEARCH_SKIPPED_DUPLICATE"
        for event in repository.events
    )


@pytest.mark.asyncio
async def test_started_but_incomplete_search_is_resumed() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    source = CountingSource()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 1, 5, 2, 3),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-resume-search"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="resume-search",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)
    invocation: dict[str, object] = {
        "contractVersion": "structured-search-v3",
        "source": "TEST",
        "query": '"Cynoscion regalis"',
        "author": "Researcher",
        "objectId": "object-1",
        "intent": "DISCOVERY",
        "strategy": "AUTHOR_OBJECT",
    }
    key = normalized_tool_idempotency_key(str(investigation.id), 0, invocation)
    await repository.add_tool_execution(
        AgenticToolExecution(
            id=AgenticToolExecutionId("tool-interrupted"),
            investigation_id=investigation.id,
            trajectory_sequence=1,
            idempotency_key=key,
            status=AgenticToolExecutionStatus.RUNNING,
            invocation=invocation,
            started_at=_NOW,
        )
    )
    await repository.append_event(
        AgenticTrajectoryEvent(
            id=AgenticTrajectoryEventId("event-started"),
            investigation_id=investigation.id,
            sequence=1,
            kind=AgenticTrajectoryEventKind.TOOL_STARTED,
            payload={
                key: value
                for key, value in invocation.items()
                if key != "contractVersion"
            },
            occurred_at=_NOW,
        )
    )

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        Reasoner(),
        (source,),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert completed.status is FullAgenticInvestigationStatus.COMPLETED
    assert source.calls == [('"Cynoscion regalis"', "Researcher")]
    assert repository.tools[key].attempts == 2


class MetadataOnlySource(Source):
    """An adapter that indexes bodies but returns none, like OpenAlex."""

    name = "OPENALEX"
    capabilities = BibliographicSourceCapabilities(
        name="OPENALEX",
        searches_metadata=True,
        searches_indexed_full_text=True,
        returns_abstract=True,
        returns_inspectable_full_text=False,
        supports_structured_author=True,
    )

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        return [
            BibliographicRecord(
                source=self.name,
                source_record_id="record-metadata",
                title="Cynoscion study",
                authors=("Researcher",),
                publication_date="2025",
                abstract="A revision without any catalogue number.",
                url="https://example.test/article",
                doi="10.1/metadata",
                raw_metadata_hash="hash",
            )
        ]


class NoFormReasoner(Reasoner):
    async def assess(self, **kwargs: object) -> AssessmentResult:
        return AssessmentResult(
            assessment=ArticleAssessment(
                relevant=True,
                confidence=AgentConfidence.MEDIUM,
                explanation="The taxon and the author match the project.",
                passages=("A revision without any catalogue number.",),
                inventory_forms=(),
                contradictions=(),
            ),
            prompt_version_id="pver-sr-full-reader-v2",
            prompt_version="scientific-return-full-agentic-reader-v2",
        )


@pytest.mark.asyncio
async def test_a_metadata_only_source_never_reports_inventory_as_not_observed() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("OPENALEX",),
        budget=AgenticBudget(1, 1, 5, 2, 3),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-metadata-only"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="metadata-only",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        NoFormReasoner(),
        (MetadataOnlySource(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    analysis = next(iter(scientific.agent_analyses.values()))
    assert analysis.input_payload["inventoryEvidenceStatus"] == "UNAVAILABLE"
    assert analysis.input_payload["discoveryBasis"] == "AUTHOR_OBJECT"
    assert len(scientific.candidates) == 1


class LimitRecordingSource(Source):
    """Records the per-query limit the executor asked this source for."""

    def __init__(self, name: str, *, searches_indexed_full_text: bool) -> None:
        self.name = name
        self.limits: list[int] = []
        self.capabilities = replace(
            Source.capabilities,
            name=name,
            searches_indexed_full_text=searches_indexed_full_text,
            returns_inspectable_full_text=searches_indexed_full_text,
        )

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        self.limits.append(limit)
        return []


@pytest.mark.asyncio
async def test_a_healthy_investigation_is_never_marked_degraded() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-healthy"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="healthy",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        Reasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert completed.status is FullAgenticInvestigationStatus.COMPLETED
    assert completed.degraded_reason is None


class CommitLog:
    """A unit of work that remembers what was durable at each commit."""

    def __init__(self, repository: FullRepository, investigation_id: str) -> None:
        self._repository = repository
        self._investigation_id = investigation_id
        self.snapshots: list[int] = []

    async def commit(self) -> None:
        item = self._repository.investigations.get(self._investigation_id)
        self.snapshots.append(item.usage.llm_calls if item else 0)

    async def rollback(self) -> None:
        pass


@pytest.mark.asyncio
async def test_every_model_call_is_charged_and_committed_before_it_starts() -> None:
    """The reservation must be durable before the call, not after it returns.

    Charging afterwards only records calls that came back, so a worker killed
    mid-call resumes with the budget untouched and repeats the same work at no
    cost — the shape that lets an investigation retry forever.
    """

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 2, 5, 2, 4),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-reserve"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="reserve",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)
    uow = CommitLog(repository, str(investigation.id))
    charged_when_called: list[int] = []

    class ObservingReasoner(Reasoner):
        async def assess(self, **kwargs: object) -> AssessmentResult:
            charged_when_called.append(uow.snapshots[-1] if uow.snapshots else 0)
            return await super().assess(**kwargs)

    await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        ObservingReasoner(),
        (Source(),),
        uow,
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert charged_when_called
    assert charged_when_called[0] >= 1
    starts = [
        event
        for event in repository.events
        if event.kind is AgenticTrajectoryEventKind.LLM_CALL_STARTED
    ]
    assert starts
    assert starts[0].payload["phase"] == "ARTICLE_ASSESSMENT"
    assert starts[0].payload["llmCalls"] == 1


@pytest.mark.asyncio
async def test_a_hard_death_leaves_the_reserved_call_spent() -> None:
    """Resuming after a kill must not rewind the budget the dead pass charged."""

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 2, 5, 2, 4),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-killed"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="killed",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    class KilledReasoner(Reasoner):
        async def assess(self, **kwargs: object) -> AssessmentResult:
            # A signal, not an exception the loop could absorb: this is what a
            # platform timeout or an out-of-memory kill looks like from here.
            raise KeyboardInterrupt("worker killed")

    with pytest.raises(KeyboardInterrupt):
        await ExecuteFullAgenticScientificReturn(
            scientific,
            repository,
            KilledReasoner(),
            (Source(),),
            Uow(),
            Clock(),
            config,
        ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    stored = repository.investigations[str(investigation.id)]
    assert stored.usage.llm_calls == 1
    assert stored.status is FullAgenticInvestigationStatus.RUNNING

    # The lease outlives the process, so the row becomes claimable only later.
    stored.lease_expires_at = _NOW - timedelta(seconds=1)

    resumed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        Reasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-2"))

    assert resumed.status is FullAgenticInvestigationStatus.COMPLETED
    assert resumed.usage.llm_calls == 2


@pytest.mark.asyncio
async def test_an_exhausted_budget_never_reaches_the_model() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 2, 5, 2, 1),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-no-budget"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="no-budget",
        budget=config.budget,
        usage=AgenticUsage(llm_calls=1),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    class RefusingReasoner(Reasoner):
        async def assess(self, **kwargs: object) -> AssessmentResult:
            raise AssertionError("The model must not be called without budget")

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        RefusingReasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert completed.status is FullAgenticInvestigationStatus.COMPLETED
    assert completed.usage.llm_calls == 1


class SpentDeadline:
    """A slice with nothing left, however long the operation asked for."""

    total_seconds = 1.0

    def remaining(self) -> float:
        return 0.0

    def allows(self, seconds: float) -> bool:
        return False


def _live_investigation(
    identifier: str, *, recovery_count: int = 0, created_at: datetime = _NOW
) -> FullAgenticInvestigation:
    return FullAgenticInvestigation(
        id=FullAgenticInvestigationId(identifier),
        watch_id=ScientificReturnWatchId("watch-1"),
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key=identifier,
        budget=AgenticBudget(3, 4, 10, 3, 8),
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=created_at,
        recovery_count=recovery_count,
    )


@pytest.mark.asyncio
async def test_the_worker_hands_the_slice_back_instead_of_being_killed() -> None:
    """Stopping early keeps the work; being killed by the platform loses it."""

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
    )
    investigation = _live_investigation("investigation-slice")
    investigation.watch_id = watch.id
    await repository.add_investigation(investigation)

    class RefusingReasoner(Reasoner):
        async def assess(self, **kwargs: object) -> AssessmentResult:
            raise AssertionError("A spent slice must not start a model call")

    yielded = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        RefusingReasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
        SpentDeadline(),
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert yielded.status is FullAgenticInvestigationStatus.QUEUED
    assert yielded.lease_owner is None
    assert yielded.lease_expires_at is None
    assert any(
        event.kind is AgenticTrajectoryEventKind.EXECUTION_SLICE_EXHAUSTED
        for event in repository.events
    )


@pytest.mark.asyncio
async def test_a_yielded_slice_is_not_charged_as_a_recovery() -> None:
    """Otherwise healthy long work spends its recovery allowance and is killed."""

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
    )
    investigation = _live_investigation("investigation-yield-twice")
    investigation.watch_id = watch.id
    await repository.add_investigation(investigation)

    for _ in range(3):
        await ExecuteFullAgenticScientificReturn(
            scientific,
            repository,
            Reasoner(),
            (Source(),),
            Uow(),
            Clock(),
            config,
            SpentDeadline(),
        ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert repository.investigations[str(investigation.id)].recovery_count == 0


@pytest.mark.asyncio
async def test_a_repeatedly_recovered_investigation_is_terminated() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
        max_recoveries=2,
    )
    investigation = _live_investigation("investigation-poisoned", recovery_count=3)
    investigation.watch_id = watch.id
    investigation.status = FullAgenticInvestigationStatus.RUNNING
    investigation.lease_expires_at = _NOW - timedelta(seconds=1)
    await repository.add_investigation(investigation)

    class RefusingReasoner(Reasoner):
        async def assess(self, **kwargs: object) -> AssessmentResult:
            raise AssertionError("An exhausted investigation must not run again")

    terminated = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        RefusingReasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert terminated.status is FullAgenticInvestigationStatus.FAILED
    assert terminated.lease_owner is None
    assert any(
        event.kind is AgenticTrajectoryEventKind.RECOVERY_LIMIT_EXHAUSTED
        for event in repository.events
    )


@pytest.mark.asyncio
async def test_the_reaper_closes_only_investigations_past_their_age() -> None:
    """A live row blocks its target, so one that cannot finish must stop being live."""

    repository = FullRepository()
    old = _live_investigation("investigation-old", created_at=_NOW - timedelta(days=2))
    old.status = FullAgenticInvestigationStatus.RUNNING
    recent = _live_investigation("investigation-recent", created_at=_NOW)
    cancelling = _live_investigation(
        "investigation-cancelling", created_at=_NOW - timedelta(days=2)
    )
    cancelling.status = FullAgenticInvestigationStatus.CANCEL_REQUESTED
    for item in (old, recent, cancelling):
        await repository.add_investigation(item)

    scientific, _ = setup_scientific_repository()
    closed = await CloseAbandonedFullAgenticInvestigations(
        repository, scientific, Uow(), Clock(), timedelta(days=1)
    ).execute(limit=25)

    assert closed == 2
    assert old.status is FullAgenticInvestigationStatus.FAILED
    assert cancelling.status is FullAgenticInvestigationStatus.CANCELLED
    assert recent.status is FullAgenticInvestigationStatus.QUEUED
    assert [
        event.kind
        for event in repository.events
        if event.kind is AgenticTrajectoryEventKind.ABANDONED
    ] == [AgenticTrajectoryEventKind.ABANDONED] * 2


@pytest.mark.asyncio
async def test_plan_events_record_the_prompt_version_that_ran() -> None:
    """The trajectory must name the planner prompt, not a literal in the code.

    The floor produces its plan without a prompt, so it is named for what it
    is; only a model-produced plan carries a published version label.
    """

    class VersionedReasoner(Reasoner):
        async def plan(self, **kwargs: object) -> AgenticPlan:
            plan = await super().plan(**kwargs)
            return replace(
                plan,
                prompt_version_id="pver-sr-full-plan-v2",
                prompt_version="scientific-return-full-agentic-plan-v2",
            )

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-plan-version"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="plan-version",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        VersionedReasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    plans = [
        event.payload
        for event in repository.events
        if event.kind is AgenticTrajectoryEventKind.PLAN_CREATED
    ]
    assert plans
    assert plans[0]["contractVersion"] == "deterministic-floor"
    assert plans[0]["promptVersionId"] is None
    planned = [item for item in plans[1:] if item["promptVersionId"] is not None]
    assert planned
    assert all(
        item["contractVersion"] == "scientific-return-full-agentic-plan-v2"
        and item["promptVersionId"] == "pver-sr-full-plan-v2"
        for item in planned
    )


@pytest.mark.asyncio
async def test_a_metadata_only_source_is_given_fewer_results_to_spend() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    metadata_only = LimitRecordingSource("TEST", searches_indexed_full_text=False)
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 2, 40, 2, 3),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-result-limit"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="result-limit",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        Reasoner(),
        (metadata_only,),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    # Without the capability rule every query would have asked for 20.
    assert metadata_only.limits
    assert set(metadata_only.limits) == {10}


@pytest.mark.asyncio
async def test_discovery_floor_never_spends_the_whole_query_budget() -> None:
    scientific, watch = setup_scientific_repository(object_count=6)
    repository = FullRepository()
    source = CountingSource()
    reasoner = Reasoner()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 20, 3, 8),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-floor-budget"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="floor-budget",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        reasoner,
        (source,),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    # max_queries=4 reserves 2 for the floor, so six consulted objects cannot
    # starve the planner, and both strategies stay represented.
    author_calls = [query for query, author in source.calls if author == "Researcher"]
    # The bare code of the first object, without the institution prefix.
    inventory_calls = [
        query for query, _ in source.calls if query == '"MB06-005741"'
    ]
    assert len(author_calls) == 1
    assert len(inventory_calls) == 1
    assert reasoner.plans >= 1
    assert completed.usage.queries <= config.budget.max_queries


@pytest.mark.asyncio
async def test_planner_failure_degrades_after_discovery_floor() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(2, 2, 5, 2, 4),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-planner-failure"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="planner-failure",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        FailingPlannerReasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert completed.status is FullAgenticInvestigationStatus.COMPLETED
    assert any(event.kind.value == "PLANNER_ERROR" for event in repository.events)
    assert any(event.kind.value == "PLANNER_FALLBACK" for event in repository.events)
    # COMPLETED alone would read as "searched fully and found nothing".
    assert completed.degraded_reason is not None
    assert "deterministic floor" in completed.degraded_reason


@pytest.mark.asyncio
async def test_search_routes_floor_author_and_encrypts_bounded_replay_text() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    source = NamedSource("OPENALEX", "W1", indexed_text="full text must stay transient")
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("OPENALEX",),
        budget=AgenticBudget(1, 1, 2, 1, 3),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-openalex"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="openalex",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        MultiSourceReasoner(),
        (source,),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert source.authors == ["Researcher"]
    assert next(iter(scientific.runs.values())).source_count == 1
    tool_execution = next(iter(repository.tools.values()))
    assert tool_execution.invocation["contractVersion"] == "structured-search-v3"
    cached = tool_execution.result
    assert cached is not None
    records = cached["records"]
    assert isinstance(records, list)
    assert records[0]["indexed_text"] == "full text must stay transient"
    assert records[0]["indexed_text_hash"]

    search = AgenticSearchSpec(
        source="OPENALEX",
        query='"Cynoscion regalis"',
        author="Researcher",
        object_id="object-1",
        intent=SearchIntent.DISCOVERY,
        strategy=SearchStrategy.AUTHOR_OBJECT,
    )
    replayed = ExecuteFullAgenticScientificReturn._records_from_result(
        cached, search
    )
    assert replayed[0][0].indexed_text == "full text must stay transient"


@pytest.mark.asyncio
async def test_malformed_reader_result_does_not_abort_later_articles() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 1, 5, 2, 4),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-malformed-reader"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="malformed-reader",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)

    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        MalformedThenValidReasoner(),
        (TwoRecordSource(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert completed.status is FullAgenticInvestigationStatus.COMPLETED
    assert len(scientific.candidates) == 1
    assert any(
        event.kind.value == "ERROR"
        and event.payload.get("phase") == "ARTICLE_ASSESSMENT"
        for event in repository.events
    )


@pytest.mark.asyncio
async def test_idempotency_key_cannot_be_reused_for_another_target() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 1, 1, 1, 2),
    )
    starter = StartFullAgenticScientificReturn(
        scientific, repository, Dispatcher(), Uow(), Clock(), config
    )
    actor = Actor(PermissionId("permission-1"), GroupName.CURATORIAL)
    await starter.execute(
        StartFullAgenticInput(
            watch.id,
            InvestigationObjective.DISCOVER_CANDIDATE,
            None,
            "same-key",
            actor,
        )
    )

    with pytest.raises(ValueError, match="another full-agentic target"):
        await starter.execute(
            StartFullAgenticInput(
                ScientificReturnWatchId("another-watch"),
                InvestigationObjective.DISCOVER_CANDIDATE,
                None,
                "same-key",
                actor,
            )
        )


@pytest.mark.asyncio
async def test_enrich_candidate_is_rejected_until_implemented() -> None:
    scientific, watch = setup_scientific_repository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 1, 1, 1, 2),
    )

    with pytest.raises(ValueError, match="only DISCOVER_CANDIDATE"):
        await StartFullAgenticScientificReturn(
            scientific, FullRepository(), Dispatcher(), Uow(), Clock(), config
        ).execute(
            StartFullAgenticInput(
                watch.id,
                InvestigationObjective.ENRICH_CANDIDATE,
                CandidatePublicationId("candidate-1"),
                "enrich",
                Actor(PermissionId("permission-1"), GroupName.CURATORIAL),
            )
        )


@pytest.mark.asyncio
async def test_second_worker_cannot_take_a_live_lease() -> None:
    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(1, 1, 1, 1, 2),
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-leased"),
        watch_id=watch.id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="leased",
        budget=config.budget,
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )
    await repository.add_investigation(investigation)
    claimed = await repository.claim_investigation(
        investigation.id,
        "worker-1",
        _NOW,
        _NOW + timedelta(minutes=15),
    )
    assert claimed is not None
    reasoner = Reasoner()

    returned = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        reasoner,
        (Source(),),
        Uow(),
        Clock(),
        config,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-2"))

    assert returned.status is FullAgenticInvestigationStatus.RUNNING
    assert returned.lease_owner == "worker-1"
    assert reasoner.plans == 0


def test_repeated_cancel_request_is_idempotent() -> None:
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-cancel"),
        watch_id=ScientificReturnWatchId("watch-1"),
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.RUNNING,
        idempotency_key="cancel",
        budget=AgenticBudget(1, 1, 1, 1, 2),
        usage=AgenticUsage(),
        created_by=PermissionId("permission-1"),
        created_at=_NOW,
    )

    investigation.request_cancel(PermissionId("permission-1"), _NOW)
    investigation.request_cancel(PermissionId("permission-1"), _NOW)

    assert investigation.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED


@pytest.mark.asyncio
async def test_no_failure_mode_keeps_an_investigation_alive_forever() -> None:
    """The acceptance criterion of the whole hardening, stated as one test.

    A model that never answers, a source that asks to be waited for beyond the
    ceiling, and a worker killed outright: none of them may leave the same
    investigation live run after run. Each pass must either finish it or spend
    something that brings its end closer.
    """

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(2, 2, 4, 2, 3),
        max_recoveries=2,
    )
    investigation = _live_investigation("investigation-poison")
    investigation.watch_id = watch.id
    await repository.add_investigation(investigation)

    class HostileReasoner(Reasoner):
        async def assess(self, **kwargs: object) -> AssessmentResult:
            raise AgentReasonerTimeout("never answers")

    for _ in range(10):
        stored = repository.investigations[str(investigation.id)]
        if stored.status.is_terminal:
            break
        # Each run starts where the last one died: the lease has gone cold.
        stored.lease_expires_at = _NOW - timedelta(seconds=1)
        await ExecuteFullAgenticScientificReturn(
            scientific,
            repository,
            HostileReasoner(),
            (Source(),),
            Uow(),
            Clock(),
            config,
        ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    stored = repository.investigations[str(investigation.id)]
    assert stored.status.is_terminal
    assert stored.usage.llm_calls <= config.budget.max_llm_calls
    timeouts = [
        event
        for event in repository.events
        if event.kind is AgenticTrajectoryEventKind.LLM_CALL_TIMED_OUT
    ]
    assert timeouts, "a timed-out call must be distinguishable in the trajectory"


@pytest.mark.asyncio
async def test_a_terminated_investigation_never_leaves_its_run_open() -> None:
    """The envelope is only completed on the happy path, so the others must close it.

    A run left RUNNING for good is a lie in the project's history: it reads as
    work still in progress long after the investigation stopped existing.
    """

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
        max_recoveries=0,
    )
    investigation = _live_investigation("investigation-envelope")
    investigation.watch_id = watch.id
    await repository.add_investigation(investigation)

    # One healthy pass opens the envelope and completes normally.
    await ExecuteFullAgenticScientificReturn(
        scientific, repository, Reasoner(), (Source(),), Uow(), Clock(), config
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    stored = repository.investigations[str(investigation.id)]
    run_id = stored.search_run_id
    assert run_id is not None

    # Force it back into a live, recovered state past the ceiling.
    stored.status = FullAgenticInvestigationStatus.RUNNING
    stored.completed_at = None
    stored.recovery_count = 1
    stored.lease_expires_at = _NOW - timedelta(seconds=1)
    run = await scientific.get_run(run_id)
    assert run is not None
    run.status = RunStatus.RUNNING
    run.completed_at = None
    await scientific.save_run(run)

    terminated = await ExecuteFullAgenticScientificReturn(
        scientific, repository, Reasoner(), (Source(),), Uow(), Clock(), config
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-2"))

    assert terminated.status is FullAgenticInvestigationStatus.FAILED
    closed = await scientific.get_run(run_id)
    assert closed is not None
    assert closed.status is RunStatus.FAILED
    assert closed.completed_at is not None
    assert closed.error_message


@pytest.mark.asyncio
async def test_a_handed_back_slice_is_announced_to_a_push_queue() -> None:
    """Under Cloud Tasks the finished task is the last one unless we say otherwise.

    The database dispatcher needs no announcement — a poller finds the queued
    row — but a push queue would simply never create the next task.
    """

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    dispatcher = Dispatcher()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
    )
    investigation = _live_investigation("investigation-announce")
    investigation.watch_id = watch.id
    await repository.add_investigation(investigation)

    yielded = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        Reasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
        SpentDeadline(),
        dispatcher,
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert yielded.status is FullAgenticInvestigationStatus.QUEUED
    assert dispatcher.ids == [str(investigation.id)]


@pytest.mark.asyncio
async def test_a_failed_announcement_still_leaves_the_work_queued() -> None:
    """The durable row is the queue; the announcement is only a notification."""

    scientific, watch = setup_scientific_repository()
    repository = FullRepository()
    config = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("TEST",),
        budget=AgenticBudget(3, 4, 10, 3, 8),
    )
    investigation = _live_investigation("investigation-announce-fails")
    investigation.watch_id = watch.id
    await repository.add_investigation(investigation)

    class BrokenDispatcher:
        async def enqueue(self, investigation_id: FullAgenticInvestigationId) -> None:
            raise RuntimeError("the queue is unreachable")

    yielded = await ExecuteFullAgenticScientificReturn(
        scientific,
        repository,
        Reasoner(),
        (Source(),),
        Uow(),
        Clock(),
        config,
        SpentDeadline(),
        BrokenDispatcher(),
    ).execute(ExecuteFullAgenticInput(investigation.id, "worker-1"))

    assert yielded.status is FullAgenticInvestigationStatus.QUEUED
