from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.identity.public import Actor
from app.scientific_return.domain.agent_policies import AuthorizedExecution
from app.scientific_return.domain.enums import (
    AgentRecommendedAction,
    CandidateStatus,
    EvidenceStrength,
    InvestigationMode,
    InvestigationObjective,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentObservation,
    AgentPlan,
    AgentReflection,
    ReflectionContext,
)
from app.scientific_return.domain.investigation_models import (
    InvestigationId,
    ScientificReturnInvestigation,
    ToolExecutionId,
)
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateDecision,
    CandidateEvidence,
    CandidatePublication,
    CandidatePublicationId,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnQuery,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)


class InvestigationConcurrencyConflict(RuntimeError):
    """Another writer moved the investigation while this one held it.

    Shared by both engines: each keeps a version on the aggregate, and a stored
    version that is not the expected one means the row was changed underneath —
    typically by the sweep's reaper closing what it judged abandoned.
    """


class AgentReasonerUnavailable(RuntimeError):
    pass


class AgentReasonerTimeout(RuntimeError):
    pass


class AgentPromptUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PublishedAgentPrompt:
    version_id: str
    version_label: str
    content: str
    temperature: float


class ScientificReturnReasoner(Protocol):
    @property
    def model_name(self) -> str: ...

    async def generate(
        self, *, system_prompt: str, user_prompt: str, temperature: float
    ) -> str: ...


class AgentPromptProvider(Protocol):
    async def get_published(self, key: str) -> PublishedAgentPrompt: ...


AGENT_PLAN_PROMPT_KEY = "scientific_return_agent_plan"
AGENT_REFLECTION_PROMPT_KEY = "scientific_return_agent_reflection"

# Registry identifier prefix of every published full-agentic reader version.
# Analyses are discriminated by it instead of by a version label: the label
# spelling changed between v1 and v2, so a label match would silently lose the
# archived v1 rows if that version were ever republished as a rollback.
FULL_AGENTIC_READER_PROMPT_ID_PREFIX = "pver-sr-full-reader"


@dataclass(frozen=True, slots=True)
class ReasonerCall:
    """Telemetry of one model call, kept beside whatever it produced.

    Recorded per iteration so a reviewer can see which model and which published
    prompt produced a plan, and so cost and latency are attributable.
    """

    model: str
    prompt_version_id: str
    prompt_version: str
    latency_ms: int
    response_hash: str


@dataclass(frozen=True, slots=True)
class PlanResult:
    plan: AgentPlan
    call: ReasonerCall


@dataclass(frozen=True, slots=True)
class ReflectionResult:
    reflection: AgentReflection
    call: ReasonerCall


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Everything a tool needs beyond the execution the policy authorised.

    The snapshot is passed rather than fetched so the tool stays pure with
    respect to storage and can be tested against fake sources alone.
    """

    objective: InvestigationObjective
    snapshot: ProjectSnapshotPayload
    now: datetime
    candidate: CandidatePublication | None = None


@dataclass(frozen=True, slots=True)
class ToolQueryOutcome:
    """One query sent to one source, recorded whether it worked or not."""

    query: str
    variant_kind: str
    source: str
    result_count: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredRecord:
    """A normalised bibliographic record with its evidence already computed.

    The evidence comes from the same deterministic rules the scheduled pipeline
    uses. The tool does not persist anything; it reports what the rules found so
    the caller can decide what to write.
    """

    candidate_id: CandidatePublicationId
    record: BibliographicRecord
    deduplication_key: str
    evidences: tuple[CandidateEvidence, ...]
    is_actionable: bool
    matches_candidate: bool = False


@dataclass(frozen=True, slots=True)
class AgentToolOutcome:
    action: AgentRecommendedAction
    queries: tuple[ToolQueryOutcome, ...]
    records: tuple[DiscoveredRecord, ...]
    total_results: int
    result_hash: str
    unavailable: bool = False
    error: str | None = None
    duplicates_avoided: int = 0

    @property
    def actionable_records(self) -> tuple[DiscoveredRecord, ...]:
        return tuple(item for item in self.records if item.is_actionable)


class AgentTool(Protocol):
    """A capability the cycle may execute, resolved from a typed action."""

    @property
    def action(self) -> AgentRecommendedAction: ...

    async def execute(
        self, execution: AuthorizedExecution, context: ToolExecutionContext
    ) -> AgentToolOutcome: ...


class UnknownAgentTool(LookupError):
    """No tool is registered for the requested action."""


class InvestigationUnitOfWork(Protocol):
    """Commits one step of the cycle.

    The cycle persists between external calls rather than wrapping them, so no
    transaction is ever open while a model is thinking or a source is answering.
    The port exists because that commit belongs to the use case, and the use case
    may not reach for a session.
    """

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class InvestigationLock(Protocol):
    """Held for the whole cycle, not for one transaction.

    The cycle commits between steps, so a transaction-scoped lock would be
    released before the first external call and guard nothing.
    """

    async def acquire(self, key: str) -> None: ...

    async def release(self) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class AgentToolRegistry(Protocol):
    def resolve(self, action: AgentRecommendedAction) -> AgentTool: ...


class InvestigationReasoner(Protocol):
    """The reasoning core of the cycle, in the cycle's own vocabulary.

    Separate operations rather than one generic ``generate`` call: planning and
    reflecting use different prompts, different schemas and different failure
    handling. An invalid plan stops the investigation; an invalid reflection
    falls back to the deterministic one.
    """

    @property
    def model_name(self) -> str: ...

    async def plan(
        self, observation: AgentObservation, mode: InvestigationMode
    ) -> PlanResult: ...

    async def reflect(self, context: ReflectionContext) -> ReflectionResult: ...


@dataclass(frozen=True, slots=True)
class BibliographicRecord:
    source: str
    source_record_id: str
    title: str
    authors: tuple[str, ...]
    publication_date: str | None
    abstract: str | None
    url: str | None
    doi: str | None
    raw_metadata_hash: str
    indexed_text: str | None = None
    indexed_text_source: str | None = None


@dataclass(frozen=True, slots=True)
class BibliographicSourceCapabilities:
    name: str
    searches_metadata: bool
    searches_indexed_full_text: bool
    returns_abstract: bool
    returns_inspectable_full_text: bool
    supports_structured_author: bool
    normalizes_inventory_separators: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip().upper())
        if not self.name:
            raise ValueError("Bibliographic source name is required")

    def as_prompt_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "searchesMetadata": self.searches_metadata,
            "searchesIndexedFullText": self.searches_indexed_full_text,
            "returnsAbstract": self.returns_abstract,
            "returnsInspectableFullText": self.returns_inspectable_full_text,
            "supportsStructuredAuthor": self.supports_structured_author,
            "normalizesInventorySeparators": self.normalizes_inventory_separators,
        }


class BibliographicSource(Protocol):
    name: str

    @property
    def capabilities(self) -> BibliographicSourceCapabilities: ...

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        """Search the source.

        ``query`` is the audited query text, sent verbatim by sources whose
        free-text index covers author names. ``author`` repeats the researcher
        for sources that index authors in a separate field and therefore cannot
        match the name through free text: measured against the live OpenAlex
        API, ``search="Diogo Parrinha" "Rhoptropus nivimontanus"`` returns
        nothing while the taxon alone returns the expected work, because
        ``search`` covers title, abstract and full text but not authorship.
        """
        ...


@dataclass(frozen=True, slots=True)
class ScientificReturnMetrics:
    active_watches: int
    runs: int
    failed_runs: int
    pending_candidates: int
    confirmed_candidates: int
    dismissed_candidates: int
    full_agentic_runs: int = 0
    full_agentic_failed_runs: int = 0
    full_agentic_pending_candidates: int = 0
    full_agentic_confirmed_candidates: int = 0
    full_agentic_dismissed_candidates: int = 0


@dataclass(frozen=True, slots=True)
class CandidateReviewItem:
    project_id: str
    candidate: CandidatePublication
    discovery_basis: str | None = None
    search_intent: str | None = None
    search_strategy: str | None = None
    inventory_evidence_status: str | None = None
    grounded_inventory_forms: tuple[dict[str, str | None], ...] = ()
    grounded_passages: tuple[str, ...] = ()
    rejected_passage_count: int = 0
    rejected_inventory_form_count: int = 0


class ProjectSnapshotProvider(Protocol):
    async def get_completed_project(
        self, project_id: str
    ) -> ProjectSnapshotPayload | None: ...


class ConfirmedPublicationWriter(Protocol):
    async def add_confirmed_publication(
        self,
        project_id: str,
        caller: Actor,
        candidate: CandidatePublication,
    ) -> str: ...


class ScientificReturnRepository(Protocol):
    async def add_watch(self, watch: ScientificReturnWatch) -> None: ...

    async def save_watch(self, watch: ScientificReturnWatch) -> None: ...

    async def get_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnWatch | None: ...

    async def get_watch_by_project(
        self, project_id: str
    ) -> ScientificReturnWatch | None: ...

    async def list_due_watches(
        self, now: datetime, limit: int
    ) -> list[ScientificReturnWatch]: ...

    async def add_snapshot(self, snapshot: ScientificReturnProjectSnapshot) -> None: ...

    async def get_snapshot_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnProjectSnapshot | None: ...

    async def add_run(self, run: ScientificReturnSearchRun) -> None: ...

    async def save_run(self, run: ScientificReturnSearchRun) -> None: ...

    async def get_run(
        self, run_id: ScientificReturnRunId
    ) -> ScientificReturnSearchRun | None: ...

    async def list_runs(
        self, watch_id: ScientificReturnWatchId, page: int, size: int
    ) -> tuple[list[ScientificReturnSearchRun], int]: ...

    async def add_query(self, query: ScientificReturnQuery) -> None: ...

    async def list_queries(self, run_id: str) -> list[ScientificReturnQuery]: ...

    async def get_candidate(
        self, candidate_id: CandidatePublicationId
    ) -> CandidatePublication | None: ...

    async def get_candidate_by_key(
        self, watch_id: ScientificReturnWatchId, key: str
    ) -> CandidatePublication | None: ...

    async def add_candidate(self, candidate: CandidatePublication) -> None: ...

    async def save_candidate(self, candidate: CandidatePublication) -> None: ...

    async def list_candidates(
        self,
        project_id: str,
        status: CandidateStatus | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidatePublication], int]: ...

    async def list_candidates_needing_inventory_proof(
        self, watch_id: ScientificReturnWatchId, limit: int
    ) -> list[CandidatePublication]:
        """Pending candidates with no evidence tying them to an inventory number.

        These are the ones a semantic search can produce and a deterministic
        rule cannot support: plausible by taxon and author, unproven against the
        specimen. They are exactly what an enrichment cycle exists to settle.
        """
        ...

    async def list_candidate_queue(
        self,
        status: CandidateStatus | None,
        project_id: str | None,
        source: str | None,
        evidence_strength: EvidenceStrength | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidateReviewItem], int]: ...

    async def add_decision(self, decision: CandidateDecision) -> None: ...

    async def list_decisions(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateDecision]: ...

    async def get_metrics(self) -> ScientificReturnMetrics: ...

    async def add_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None: ...

    async def save_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None: ...

    async def get_agent_analysis(
        self, analysis_id: CandidateAgentAnalysisId
    ) -> CandidateAgentAnalysis | None: ...

    async def list_agent_analyses(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateAgentAnalysis]: ...

    async def list_queries_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> list[ScientificReturnQuery]:
        """Every query ever issued for a watch, across all runs.

        The agentic cycle refuses to repeat a query, and repetition is a
        property of the watch rather than of one run, so per-run listing is not
        enough.
        """
        ...

    async def append_candidate_evidences(
        self,
        candidate_id: CandidatePublicationId,
        evidences: tuple[CandidateEvidence, ...],
    ) -> tuple[CandidateEvidence, ...]:
        """Add verified evidence to an existing candidate, idempotently.

        Returns only what was actually written. Evidence already present is left
        alone rather than rewritten, so the provenance of the original finding
        survives and a replayed execution cannot inflate the delta.
        """
        ...


class ScientificReturnInvestigationRepository(Protocol):
    """Persists the investigation aggregate and its tool executions."""

    async def add(self, investigation: ScientificReturnInvestigation) -> None: ...

    async def save(self, investigation: ScientificReturnInvestigation) -> None: ...

    async def get(
        self, investigation_id: InvestigationId
    ) -> ScientificReturnInvestigation | None: ...

    async def list_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> list[ScientificReturnInvestigation]: ...

    async def list_for_candidate(
        self, candidate_id: CandidatePublicationId
    ) -> list[ScientificReturnInvestigation]: ...

    async def list_abandoned(
        self, stale_before: datetime, limit: int
    ) -> list[ScientificReturnInvestigation]:
        """Non-terminal investigations that stopped reporting progress.

        A supervised cycle is synchronous and bounded, so one that has not moved
        since ``stale_before`` is not slow, it is gone: its process died before
        it could close itself.
        """
        ...

    async def find_live(
        self,
        watch_id: ScientificReturnWatchId,
        objective: InvestigationObjective,
        candidate_id: CandidatePublicationId | None,
    ) -> ScientificReturnInvestigation | None:
        """The non-terminal investigation for this target, if one exists.

        Used to refuse starting a second investigation over the same target
        rather than relying on the database constraint to raise.
        """
        ...

    async def find_by_idempotency_key(
        self, key: str
    ) -> ScientificReturnInvestigation | None:
        """The investigation a previous call with this client key produced."""
        ...

    async def find_tool_execution(
        self, idempotency_key: str
    ) -> ToolExecutionRecord | None: ...

    async def add_tool_execution(self, execution: ToolExecutionRecord) -> None: ...

    async def save_tool_execution(self, execution: ToolExecutionRecord) -> None: ...


@dataclass(slots=True)
class ToolExecutionRecord:
    """One external execution, claimed by its idempotency key before it runs.

    Written before the call and updated after, so a crash in between leaves a
    row saying an attempt was made. A replay finds that row instead of calling
    the source again.
    """

    id: ToolExecutionId
    investigation_id: InvestigationId
    iteration_id: str
    idempotency_key: str
    action: AgentRecommendedAction
    started_at: datetime
    queries: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    total_results: int = 0
    created_candidate_ids: tuple[str, ...] = ()
    added_evidence_ids: tuple[str, ...] = ()
    result_hash: str | None = None
    succeeded: bool = False
    error_message: str | None = None
    attempts: int = 1
    completed_at: datetime | None = None
