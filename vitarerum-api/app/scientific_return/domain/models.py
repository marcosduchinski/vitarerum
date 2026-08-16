from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import NewType

from app.scientific_return.domain.enums import (
    CandidateStatus,
    DecisionType,
    EvidenceStrength,
    EvidenceType,
    QueryStatus,
    QueryType,
    RunStatus,
    WatchStatus,
)
from app.shared.kernel import PermissionId

ScientificReturnWatchId = NewType("ScientificReturnWatchId", str)
ScientificReturnSnapshotId = NewType("ScientificReturnSnapshotId", str)
ScientificReturnRunId = NewType("ScientificReturnRunId", str)
ScientificReturnQueryId = NewType("ScientificReturnQueryId", str)
CandidatePublicationId = NewType("CandidatePublicationId", str)
CandidateEvidenceId = NewType("CandidateEvidenceId", str)
CandidateDecisionId = NewType("CandidateDecisionId", str)


@dataclass(frozen=True, slots=True)
class ConsultedObjectSnapshot:
    id: str
    inventory_number: str
    object_name: str


@dataclass(frozen=True, slots=True)
class ProjectSnapshotPayload:
    project_id: str
    project_reference: str
    researcher: str
    consulted_objects: tuple[ConsultedObjectSnapshot, ...]


@dataclass(slots=True)
class ScientificReturnProjectSnapshot:
    id: ScientificReturnSnapshotId
    project_id: str
    payload: ProjectSnapshotPayload
    payload_hash: str
    builder_version: str
    created_at: datetime


@dataclass(slots=True)
class ScientificReturnWatch:
    id: ScientificReturnWatchId
    project_id: str
    status: WatchStatus
    review_interval_days: int
    created_by: PermissionId
    created_at: datetime
    next_run_at: datetime
    project_snapshot_id: ScientificReturnSnapshotId
    last_run_at: datetime | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.review_interval_days <= 365:
            raise ValueError("reviewIntervalDays must be between 1 and 365")

    def change_status(self, status: WatchStatus) -> None:
        if self.status is WatchStatus.CLOSED and status is not WatchStatus.CLOSED:
            raise ValueError("A closed watch cannot be reopened")
        self.status = status

    def record_run(self, occurred_at: datetime, next_run_at: datetime) -> None:
        self.last_run_at = occurred_at
        self.next_run_at = next_run_at


@dataclass(slots=True)
class ScientificReturnSearchRun:
    id: ScientificReturnRunId
    watch_id: ScientificReturnWatchId
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    source_count: int = 0
    candidate_count: int = 0
    new_candidate_count: int = 0
    error_message: str | None = None


@dataclass(slots=True)
class ScientificReturnQuery:
    id: ScientificReturnQueryId
    run_id: ScientificReturnRunId
    source: str
    query_text: str
    query_type: QueryType
    sent_at: datetime
    result_count: int
    status: QueryStatus
    error_message: str | None = None


@dataclass(slots=True)
class CandidateEvidence:
    id: CandidateEvidenceId
    candidate_id: CandidatePublicationId
    type: EvidenceType
    strength: EvidenceStrength
    value: str
    source_field: str
    explanation: str
    created_at: datetime
    object_id: str | None = None


@dataclass(slots=True)
class CandidatePublication:
    id: CandidatePublicationId
    watch_id: ScientificReturnWatchId
    first_seen_run_id: ScientificReturnRunId
    source: str
    source_record_id: str
    deduplication_key: str
    title: str
    authors: tuple[str, ...]
    publication_date: str | None
    abstract: str | None
    url: str | None
    raw_metadata_hash: str
    created_at: datetime
    doi: str | None = None
    status: CandidateStatus = CandidateStatus.PENDING
    snoozed_until: datetime | None = None
    confirmed_publication_entry_id: str | None = None
    evidences: list[CandidateEvidence] = field(default_factory=list)

    def dismiss(self) -> None:
        self.status = CandidateStatus.DISMISSED
        self.snoozed_until = None

    def snooze(self, until: datetime, now: datetime) -> None:
        if until <= now:
            raise ValueError("snoozedUntil must be in the future")
        self.status = CandidateStatus.SNOOZED
        self.snoozed_until = until

    def confirm(self, publication_entry_id: str) -> None:
        self.status = CandidateStatus.CONFIRMED
        self.snoozed_until = None
        self.confirmed_publication_entry_id = publication_entry_id

    def make_pending_if_snooze_expired(self, now: datetime) -> None:
        if (
            self.status is CandidateStatus.SNOOZED
            and self.snoozed_until is not None
            and self.snoozed_until <= now
        ):
            self.status = CandidateStatus.PENDING
            self.snoozed_until = None


@dataclass(frozen=True, slots=True)
class CandidateCorrection:
    title: str | None = None
    doi: str | None = None
    url: str | None = None
    authors: tuple[str, ...] | None = None


@dataclass(slots=True)
class CandidateDecision:
    id: CandidateDecisionId
    candidate_id: CandidatePublicationId
    decision: DecisionType
    justification: str | None
    decided_by: PermissionId
    decided_at: datetime
    evidence_snapshot: tuple[dict[str, str], ...]
    correction: CandidateCorrection | None = None
