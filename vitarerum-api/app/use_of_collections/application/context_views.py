"""Published read models for the Use of Collections export context (Open Host
Service).

These are plain application DTOs (no ORM, no Pydantic) handed to downstream
contexts — currently the CIDOC-CRM mapping — so they never receive Use of
Collections aggregates directly (Anti-Corruption Layer rule). Re-exported,
together with the composition factory, from ``app.use_of_collections.public``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.shared.kernel import IntendedUse

# ── Project export read-view (consumed by the CIDOC-CRM mapping context) ───────


@dataclass(frozen=True, slots=True)
class ExportAttachmentView:
    """One file attachment hanging off a journal entry."""

    source_id: str
    description: str
    reference: str
    position: int


@dataclass(frozen=True, slots=True)
class ExportObjectView:
    """A requested object on the proposal (carries no attachments)."""

    source_id: str
    description: str
    position: int


@dataclass(frozen=True, slots=True)
class ExportEntryView:
    """A journal entry (occurrence / access log / publication) with attachments."""

    source_id: str
    description: str
    position: int
    attachments: list[ExportAttachmentView] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProjectExportView:
    """A read-only projection of a CollectionUseProject and its journals, handed
    to the CIDOC-CRM mapping context to build an in-situ visit snapshot."""

    project_id: str
    reference_number: str
    begin_date: date
    end_date: date
    intended_use: IntendedUse
    visitor_name: str
    requested_objects: list[ExportObjectView] = field(default_factory=list)
    in_situ_occurrences: list[ExportEntryView] = field(default_factory=list)
    in_situ_logs: list[ExportEntryView] = field(default_factory=list)
    in_situ_publications: list[ExportEntryView] = field(default_factory=list)


class ProjectExportReader(Protocol):
    """Published read port (OHS): assembles a project + its journals into a
    translated, read-only export view. Returns ``None`` when the project does
    not exist."""

    async def load(self, project_id: str) -> ProjectExportView | None: ...
