"""Adapters that run the production autonomous-search use case for a bench item.

The adapters deliberately keep production side effects in memory.  The test bench
therefore exercises the exact planner/search/reader/grounding/candidate pipeline
without creating watches, runs, candidates, notifications, or learning records in
the operational scientific-return tables.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.scientific_return.application.full_agentic import (
    ExecuteFullAgenticInput,
    ExecuteFullAgenticScientificReturn,
    FullAgenticConfiguration,
)
from app.scientific_return.application.full_agentic_ports import (
    AgenticPlan,
    AssessmentResult,
    FullAgenticReasoner,
    LearningProposal,
)
from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSourceCapabilities,
    CandidateReviewItem,
    ScientificReturnMetrics,
)
from app.scientific_return.domain.bench_models import TestSubject
from app.scientific_return.domain.enums import (
    AgentConfidence,
    CandidateStatus,
    EvidenceStrength,
    FullAgenticInvestigationStatus,
    InvestigationObjective,
    WatchStatus,
)
from app.scientific_return.domain.full_agentic_models import (
    AgenticBudget,
    AgenticCandidateLink,
    AgenticToolExecution,
    AgenticTrajectoryEvent,
    AgenticUsage,
    ArticleAssessment,
    FullAgenticInvestigation,
    FullAgenticInvestigationId,
    KnowledgeItemId,
    ScientificReturnKnowledgeItem,
)
from app.scientific_return.domain.inventory_variants import (
    generate_inventory_query_variants,
)
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateDecision,
    CandidateEvidence,
    CandidatePublication,
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnQuery,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnSnapshotId,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)
from app.shared.kernel import PermissionId

LOCAL_CORPUS_SOURCE = "TEST_KNOWLEDGE_BASE"
BENCH_SCORE_VERSION = "full-agentic-evidence-score-v1"


@dataclass(frozen=True, slots=True)
class LocalCorpusDocument:
    source_id: str
    revision_id: str
    name: str
    revision: int
    locator: str | None
    authors: tuple[str, ...]
    content: str
    content_hash: str


def _terms(value: str) -> set[str]:
    return set(re.findall(r"\w{3,}", value.casefold()))


def _canonical_inventory(value: str) -> str:
    return re.sub(r"\W", "", value.casefold())


def _excerpt(content: str, query: str, maximum: int = 16_000) -> str:
    """Return the same bounded, inspectable body contract used by production."""
    if len(content) <= maximum:
        return content
    folded = content.casefold()
    positions = [folded.find(term) for term in _terms(query)]
    position = min((item for item in positions if item >= 0), default=0)
    start = max(0, position - maximum // 3)
    return content[start : start + maximum]


class LocalCorpusSource:
    """Search adapter over the immutable knowledge-base snapshot of one batch."""

    name = LOCAL_CORPUS_SOURCE
    capabilities = BibliographicSourceCapabilities(
        name=LOCAL_CORPUS_SOURCE,
        searches_metadata=True,
        searches_indexed_full_text=True,
        returns_abstract=False,
        returns_inspectable_full_text=True,
        supports_structured_author=True,
        normalizes_inventory_separators=True,
    )

    def __init__(self, documents: tuple[LocalCorpusDocument, ...]) -> None:
        self.documents = documents

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        query_terms = _terms(query)
        normalized_query = _canonical_inventory(query)
        author_terms = _terms(author or "")
        ranked: list[tuple[Decimal, LocalCorpusDocument]] = []
        for document in self.documents:
            searchable = " ".join((document.name, *document.authors, document.content))
            searchable_terms = _terms(searchable)
            term_coverage = (
                Decimal(len(query_terms & searchable_terms)) / Decimal(len(query_terms))
                if query_terms
                else Decimal("0")
            )
            author_coverage = (
                Decimal(len(author_terms & searchable_terms))
                / Decimal(len(author_terms))
                if author_terms
                else Decimal("0")
            )
            inventory_match = bool(
                normalized_query
                and len(normalized_query) >= 5
                and normalized_query in _canonical_inventory(searchable)
            )
            score = term_coverage + author_coverage + Decimal(inventory_match)
            if score > 0:
                ranked.append((score, document))
        ranked.sort(key=lambda item: (-item[0], item[1].revision_id))
        return [
            BibliographicRecord(
                source=self.name,
                source_record_id=document.revision_id,
                title=document.name,
                authors=document.authors,
                publication_date=None,
                abstract=None,
                url=document.locator,
                doi=None,
                raw_metadata_hash=document.content_hash,
                indexed_text=document.content,
                indexed_text_source=(
                    f"test-source:{document.source_id}:revision:"
                    f"{document.revision}:content"
                ),
            )
            for _, document in ranked[:limit]
        ]


class DeterministicBenchReasoner:
    """Test-only fallback; execution still traverses the production engine."""

    model_name = "deterministic"

    async def plan(self, **_: object) -> AgenticPlan:
        return AgenticPlan((), "The deterministic discovery floor is complete", True)

    async def assess(self, **kwargs: object) -> AssessmentResult:
        record = kwargs["record"]
        context = kwargs["trusted_context"]
        if not isinstance(record, BibliographicRecord) or not isinstance(context, dict):
            raise TypeError("Invalid deterministic reader input")
        content = record.indexed_text or record.abstract or ""
        objects = context.get("objects", [])
        first_object = objects[0] if isinstance(objects, list) and objects else {}
        inventory = (
            str(first_object.get("inventoryNumber", ""))
            if isinstance(first_object, dict)
            else ""
        )
        observed: str | None = None
        for variant in generate_inventory_query_variants(inventory):
            position = content.casefold().find(variant.text.casefold())
            if position >= 0:
                observed = content[position : position + len(variant.text)]
                break
        evidence = _excerpt(content, inventory, maximum=320)
        return AssessmentResult(
            assessment=ArticleAssessment(
                relevant=True,
                confidence=AgentConfidence.HIGH,
                explanation="The local source matches the autonomous discovery query.",
                passages=(evidence,) if evidence else (),
                inventory_forms=(observed,) if observed else (),
                contradictions=(),
            ),
            prompt_version_id="pver-sr-test-deterministic-v1",
            prompt_version="scientific-return-test-deterministic-v1",
        )

    async def learn(self, **_: object) -> LearningProposal:
        raise NotImplementedError("The isolated test runtime never learns")


class _Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class _UnitOfWork:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class TransientFullAgenticRepository:
    """In-memory adapter for the production engine's operational persistence."""

    def __init__(
        self,
        investigation: FullAgenticInvestigation,
        knowledge: tuple[ScientificReturnKnowledgeItem, ...] = (),
    ) -> None:
        self.investigation = investigation
        self.knowledge = {str(item.id): item for item in knowledge}
        self.events: list[AgenticTrajectoryEvent] = []
        self.tools: dict[str, AgenticToolExecution] = {}
        self.links: list[AgenticCandidateLink] = []

    async def add_knowledge(self, item: ScientificReturnKnowledgeItem) -> None:
        return None

    async def save_knowledge(self, item: ScientificReturnKnowledgeItem) -> None:
        return None

    async def get_knowledge(
        self, item_id: KnowledgeItemId
    ) -> ScientificReturnKnowledgeItem | None:
        return self.knowledge.get(str(item_id))

    async def list_knowledge(
        self, *, active_only: bool, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        return list(self.knowledge.values())[:limit]

    async def find_knowledge_exact(
        self, registered_number: str, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        normalized = registered_number.casefold().strip()
        return [
            item
            for item in self.knowledge.values()
            if (item.registered_number or "").casefold().strip() == normalized
        ][:limit]

    async def add_investigation(self, investigation: FullAgenticInvestigation) -> None:
        self.investigation = investigation

    async def save_investigation(self, investigation: FullAgenticInvestigation) -> None:
        investigation.version += 1
        self.investigation = investigation

    async def claim_investigation(
        self,
        investigation_id: FullAgenticInvestigationId,
        worker_id: str,
        claimed_at: datetime,
        lease_expires_at: datetime,
    ) -> FullAgenticInvestigation | None:
        item = self.investigation
        if item.id != investigation_id or item.status.is_terminal:
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
        item = self.investigation
        if item.id != investigation_id or item.lease_owner != worker_id:
            return None
        item.heartbeat_at = heartbeat_at
        item.lease_expires_at = lease_expires_at
        item.version += 1
        return item.version

    async def get_investigation(
        self, investigation_id: FullAgenticInvestigationId
    ) -> FullAgenticInvestigation | None:
        return self.investigation if self.investigation.id == investigation_id else None

    async def get_by_idempotency_key(self, key: str) -> FullAgenticInvestigation | None:
        return self.investigation if self.investigation.idempotency_key == key else None

    async def find_live_target(
        self, watch_id: str, objective: str, candidate_id: str | None
    ) -> FullAgenticInvestigation | None:
        return self.investigation if not self.investigation.status.is_terminal else None

    async def list_investigations(
        self, watch_id: str, limit: int
    ) -> list[FullAgenticInvestigation]:
        return [self.investigation][:limit]

    async def append_event(self, event: AgenticTrajectoryEvent) -> None:
        self.events.append(event)

    async def list_events(
        self, investigation_id: FullAgenticInvestigationId
    ) -> list[AgenticTrajectoryEvent]:
        return [
            item for item in self.events if item.investigation_id == investigation_id
        ]

    async def next_event_sequence(
        self, investigation_id: FullAgenticInvestigationId
    ) -> int:
        return (
            max(
                (
                    item.sequence
                    for item in self.events
                    if item.investigation_id == investigation_id
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
        return None

    async def link_candidate(self, link: AgenticCandidateLink) -> bool:
        if any(item.candidate_id == link.candidate_id for item in self.links):
            return False
        self.links.append(link)
        return True

    async def add_tool_execution(self, execution: AgenticToolExecution) -> None:
        self.tools[execution.idempotency_key] = execution

    async def save_tool_execution(self, execution: AgenticToolExecution) -> None:
        self.tools[execution.idempotency_key] = execution

    async def get_tool_execution(self, key: str) -> AgenticToolExecution | None:
        return self.tools.get(key)


class TransientScientificReturnRepository:
    """In-memory adapter that captures domain outputs for the bench projection."""

    def __init__(
        self, watch: ScientificReturnWatch, snapshot: ScientificReturnProjectSnapshot
    ) -> None:
        self.watch = watch
        self.snapshot = snapshot
        self.runs: dict[str, ScientificReturnSearchRun] = {}
        self.queries: list[ScientificReturnQuery] = []
        self.candidates: dict[str, CandidatePublication] = {}
        self.analyses: dict[str, CandidateAgentAnalysis] = {}

    async def add_watch(self, watch: ScientificReturnWatch) -> None:
        self.watch = watch

    async def save_watch(self, watch: ScientificReturnWatch) -> None:
        self.watch = watch

    async def get_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnWatch | None:
        return self.watch if self.watch.id == watch_id else None

    async def get_watch_by_project(
        self, project_id: str
    ) -> ScientificReturnWatch | None:
        return self.watch if self.watch.project_id == project_id else None

    async def list_due_watches(
        self, now: datetime, limit: int
    ) -> list[ScientificReturnWatch]:
        return []

    async def add_snapshot(self, snapshot: ScientificReturnProjectSnapshot) -> None:
        self.snapshot = snapshot

    async def get_snapshot_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnProjectSnapshot | None:
        return self.snapshot if self.watch.id == watch_id else None

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
        items = [item for item in self.runs.values() if item.watch_id == watch_id]
        return items[page * size : (page + 1) * size], len(items)

    async def add_query(self, query: ScientificReturnQuery) -> None:
        self.queries.append(query)

    async def list_queries(self, run_id: str) -> list[ScientificReturnQuery]:
        return [item for item in self.queries if str(item.run_id) == run_id]

    async def get_candidate(
        self, candidate_id: CandidatePublicationId
    ) -> CandidatePublication | None:
        return self.candidates.get(str(candidate_id))

    async def get_candidate_by_key(
        self, watch_id: ScientificReturnWatchId, key: str
    ) -> CandidatePublication | None:
        return next(
            (
                item
                for item in self.candidates.values()
                if item.watch_id == watch_id and item.deduplication_key == key
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
        items = list(self.candidates.values())
        return items[page * size : (page + 1) * size], len(items)

    async def list_candidate_queue(
        self,
        status: CandidateStatus | None,
        project_id: str | None,
        source: str | None,
        evidence_strength: EvidenceStrength | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidateReviewItem], int]:
        return [], 0

    async def add_decision(self, decision: CandidateDecision) -> None:
        return None

    async def list_decisions(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateDecision]:
        return []

    async def get_metrics(self) -> ScientificReturnMetrics:
        return ScientificReturnMetrics(1, len(self.runs), 0, len(self.candidates), 0, 0)

    async def add_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None:
        self.analyses[str(analysis.id)] = analysis

    async def save_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None:
        self.analyses[str(analysis.id)] = analysis

    async def get_agent_analysis(
        self, analysis_id: CandidateAgentAnalysisId
    ) -> CandidateAgentAnalysis | None:
        return self.analyses.get(str(analysis_id))

    async def list_agent_analyses(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateAgentAnalysis]:
        return [
            item for item in self.analyses.values() if item.candidate_id == candidate_id
        ]

    async def list_queries_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> list[ScientificReturnQuery]:
        return list(self.queries)

    async def append_candidate_evidences(
        self,
        candidate_id: CandidatePublicationId,
        evidences: tuple[CandidateEvidence, ...],
    ) -> tuple[CandidateEvidence, ...]:
        candidate = self.candidates[str(candidate_id)]
        candidate.evidences.extend(evidences)
        return evidences


@dataclass(frozen=True, slots=True)
class BenchAgenticOutcome:
    investigation: FullAgenticInvestigation
    scientific: TransientScientificReturnRepository
    operations: TransientFullAgenticRepository


async def execute_bench_agentic(
    *,
    item_id: str,
    attempt_number: int,
    created_by: str,
    subject: TestSubject,
    documents: tuple[LocalCorpusDocument, ...],
    reasoner: FullAgenticReasoner | None,
    budget: AgenticBudget,
    worker_id: str,
    knowledge: tuple[ScientificReturnKnowledgeItem, ...] = (),
) -> BenchAgenticOutcome:
    """Run one batch item through the production autonomous-search use case."""
    now = datetime.now(UTC)
    watch_id = ScientificReturnWatchId(f"bench-watch:{item_id}")
    snapshot_id = ScientificReturnSnapshotId(f"bench-snapshot:{item_id}")
    snapshot = ScientificReturnProjectSnapshot(
        id=snapshot_id,
        project_id=f"bench-project:{item_id}",
        payload=ProjectSnapshotPayload(
            project_id=f"bench-project:{item_id}",
            project_reference=f"scientific-return-test:{item_id}",
            researcher=subject.author,
            consulted_objects=(
                ConsultedObjectSnapshot(
                    id=item_id,
                    inventory_number=subject.inventory_number,
                    object_name=subject.object_name,
                ),
            ),
        ),
        payload_hash=hashlib.sha256(repr(subject).encode()).hexdigest(),
        builder_version="scientific-return-test-snapshot-v2",
        created_at=now,
    )
    watch = ScientificReturnWatch(
        id=watch_id,
        project_id=snapshot.project_id,
        status=WatchStatus.ACTIVE,
        review_interval_days=1,
        created_by=PermissionId(created_by),
        created_at=now,
        next_run_at=now,
        project_snapshot_id=snapshot_id,
    )
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId(str(uuid4())),
        watch_id=watch_id,
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key=f"bench:{item_id}:{attempt_number}",
        budget=budget,
        usage=AgenticUsage(),
        created_by=PermissionId(created_by),
        created_at=now,
    )
    scientific = TransientScientificReturnRepository(watch, snapshot)
    operations = TransientFullAgenticRepository(investigation, knowledge)
    source = LocalCorpusSource(documents)
    configuration = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=(source.name,),
        budget=budget,
        operational_sources=(source.name,),
        evidence_sources=(source.name,),
    )
    completed = await ExecuteFullAgenticScientificReturn(
        scientific,
        operations,
        reasoner or DeterministicBenchReasoner(),
        (source,),
        _UnitOfWork(),
        _Clock(),
        configuration,
    ).execute(ExecuteFullAgenticInput(investigation.id, worker_id))
    return BenchAgenticOutcome(completed, scientific, operations)


def evidence_score(analysis: CandidateAgentAnalysis) -> Decimal:
    """Stable report projection; rank itself remains the production engine rank."""
    confidence = analysis.result.confidence if analysis.result else AgentConfidence.LOW
    base = {
        AgentConfidence.HIGH: Decimal("0.90000"),
        AgentConfidence.MEDIUM: Decimal("0.60000"),
        AgentConfidence.LOW: Decimal("0.30000"),
    }[confidence]
    if analysis.input_payload.get("inventoryEvidenceStatus") == "VERIFIED":
        base += Decimal("0.10000")
    return min(base, Decimal("1.00000")).quantize(Decimal("0.00001"))
