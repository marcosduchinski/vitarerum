"""Published read models for the Use of Collections export context (Open Host
Service).

These are plain application DTOs (no ORM, no Pydantic) handed to downstream
contexts — currently the CIDOC-CRM mapping — so they never receive Use of
Collections aggregates directly (Anti-Corruption Layer rule). Re-exported,
together with the composition factory, from ``app.use_of_collections.public``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from app.shared.kernel import PermissionId, UseType
from app.use_of_collections.domain.enums import (
    ProposalEventType,
    UseEventType,
    UseStatus,
)
from app.use_of_collections.domain.models import CollectionUseProject, Proposal

# ── Project export read-view (consumed by the CIDOC-CRM mapping context) ───────


@dataclass(frozen=True, slots=True)
class ExportAttachmentView:
    """One file attachment hanging off a journal entry."""

    source_id: str
    description: str
    reference: str
    position: int
    media_type: str | None = None


@dataclass(frozen=True, slots=True)
class ExportObjectView:
    """A requested object on the proposal (carries no attachments)."""

    source_id: str
    description: str
    position: int
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None


@dataclass(frozen=True, slots=True)
class ExportEntryView:
    """A journal entry (occurrence / access log / publication) with attachments.

    ``object_source_id`` is the inventory number of the specific collection
    object the entry concerns (occurrences and access log entries always refer
    to one; publication entries have none, so it stays ``None``)."""

    source_id: str
    description: str
    position: int
    attachments: list[ExportAttachmentView] = field(default_factory=list)
    object_source_id: str | None = None
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
class ApprovalView:
    approved_at: datetime
    approved_by: PermissionId | None
    approval_note: str | None = None


@dataclass(frozen=True, slots=True)
class VisitExecutionEvidenceView:
    """Operational evidence that an in-situ visit has actually occurred."""

    occurred: bool
    evidence_type: str
    occurred_at: datetime | None = None
    recorded_by: PermissionId | None = None
    gaps: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProjectExportView:
    """A read-only projection of a CollectionUseProject and its journals, handed
    to the CIDOC-CRM mapping context to build an in-situ visit snapshot."""

    project_id: str
    reference_number: str
    title: str
    purpose: str
    begin_date: date
    end_date: date
    intended_use: UseType
    visitor_name: str
    visit_execution_evidence: VisitExecutionEvidenceView
    approval: ApprovalView | None = None
    requested_objects: list[ExportObjectView] = field(default_factory=list)
    in_situ_occurrences: list[ExportEntryView] = field(default_factory=list)
    in_situ_logs: list[ExportEntryView] = field(default_factory=list)
    in_situ_publications: list[ExportEntryView] = field(default_factory=list)


class ProjectExportReader(Protocol):
    """Published read port (OHS): assembles a project + its journals into a
    translated, read-only export view. Returns ``None`` when the project does
    not exist."""

    async def load(self, project_id: str) -> ProjectExportView | None: ...


def build_visit_execution_evidence(
    project: CollectionUseProject,
) -> VisitExecutionEvidenceView:
    """Derive the minimal operational evidence for treating a visit as executed."""
    completed_event = next(
        (
            event
            for event in reversed(project.events)
            if event.type == UseEventType.COMPLETED
        ),
        None,
    )
    gaps: list[str] = []
    if project.status != UseStatus.COMPLETED:
        gaps.append("project_status_not_completed")
    if completed_event is None:
        gaps.append("completed_event_missing")

    if project.status == UseStatus.COMPLETED and completed_event is not None:
        return VisitExecutionEvidenceView(
            occurred=True,
            evidence_type="project_completed_event",
            occurred_at=completed_event.occurred_at,
            recorded_by=completed_event.triggered_by,
            gaps=[],
        )
    return VisitExecutionEvidenceView(
        occurred=False,
        evidence_type="insufficient_operational_evidence",
        gaps=gaps,
    )


def build_approval_view(proposal: Proposal | None) -> ApprovalView | None:
    """Return the latest APPROVED proposal event, if the source has events."""
    if proposal is None:
        return None
    approved_event = next(
        (
            event
            for event in reversed(proposal.events)
            if event.type == ProposalEventType.APPROVED
        ),
        None,
    )
    if approved_event is None:
        return None
    return ApprovalView(
        approved_at=approved_event.occurred_at,
        approved_by=approved_event.triggered_by,
        approval_note=approved_event.note,
    )
