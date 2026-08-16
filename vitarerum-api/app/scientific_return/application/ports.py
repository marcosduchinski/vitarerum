from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.identity.public import Actor
from app.scientific_return.domain.enums import CandidateStatus, EvidenceStrength
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateDecision,
    CandidatePublication,
    CandidatePublicationId,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnQuery,
    ScientificReturnSearchRun,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)


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
    async def get_published(self) -> PublishedAgentPrompt: ...


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


class BibliographicSource(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[BibliographicRecord]: ...


@dataclass(frozen=True, slots=True)
class ScientificReturnMetrics:
    active_watches: int
    runs: int
    failed_runs: int
    pending_candidates: int
    confirmed_candidates: int
    dismissed_candidates: int


@dataclass(frozen=True, slots=True)
class CandidateReviewItem:
    project_id: str
    candidate: CandidatePublication


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
