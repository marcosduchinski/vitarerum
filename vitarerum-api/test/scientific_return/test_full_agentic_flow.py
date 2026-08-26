from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.identity.public import Actor, GroupName
from app.scientific_return.application.agent_tools import (
    normalized_tool_idempotency_key,
)
from app.scientific_return.application.full_agentic import (
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
        item.lease_owner = worker_id
        item.lease_expires_at = lease_expires_at
        item.version += 1
        return item

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
