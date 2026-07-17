"""Application ports for the In Situ Visit CIDOC mapping context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    InSituVisitId,
    InSituVisitRecord,
)
from app.shared.kernel import PermissionId, UseType


class InSituVisitRecordRepository(Protocol):
    async def add(self, record: InSituVisitRecord) -> None: ...

    async def get_by_id(self, record_id: InSituVisitId) -> InSituVisitRecord | None: ...

    async def list(
        self, page: int, size: int
    ) -> tuple[list[InSituVisitRecord], int]: ...


# ── Project export source (translated from use_of_collections via the ACL) ─────


@dataclass(frozen=True, slots=True)
class ExportAttachment:
    source_id: str
    description: str
    reference: str
    position: int
    media_type: str | None = None


@dataclass(frozen=True, slots=True)
class ExportObject:
    source_id: str
    description: str
    position: int
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None


@dataclass(frozen=True, slots=True)
class ExportEntry:
    source_id: str
    description: str
    position: int
    attachments: list[ExportAttachment] = field(default_factory=list)
    related_object_source_id: str | None = None
    number_of_objects: int | None = None
    occurrence_date: datetime | None = None
    location: str | None = None
    reported_by: PermissionId | None = None
    testimonial: str | None = None
    added_at: datetime | None = None
    added_by: PermissionId | None = None
    access_log_date_conclusion: datetime | None = None
    access_log_curator: PermissionId | None = None
    occurrence_log_date_conclusion: datetime | None = None
    occurrence_log_curator: PermissionId | None = None


@dataclass(frozen=True, slots=True)
class ApprovalData:
    approved_at: datetime
    approved_by: PermissionId | None
    approval_note: str | None = None


@dataclass(frozen=True, slots=True)
class VisitExecutionEvidence:
    occurred: bool
    evidence_type: str
    occurred_at: datetime | None = None
    recorded_by: PermissionId | None = None
    gaps: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProjectExportData:
    """The mapping context's own view of a collection-use project, ready to be
    turned into an :class:`InSituVisitRecord`."""

    project_id: str
    reference_number: str
    title: str
    purpose: str
    begin_date: date
    end_date: date
    use_type: UseType
    visitor_name: str
    visit_execution_evidence: VisitExecutionEvidence
    approval: ApprovalData | None = None
    requested_objects: list[ExportObject] = field(default_factory=list)
    in_situ_occurrences: list[ExportEntry] = field(default_factory=list)
    in_situ_logs: list[ExportEntry] = field(default_factory=list)
    in_situ_publications: list[ExportEntry] = field(default_factory=list)


class ProjectExportPort(Protocol):
    """Reads a collection-use project's export data. Returns ``None`` when the
    project does not exist."""

    async def load(self, project_id: str) -> ProjectExportData | None: ...
