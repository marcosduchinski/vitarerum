"""Application ports for the In Situ Visit CEDOC mapping context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    InSituVisitId,
    InSituVisitRecord,
)
from app.shared.kernel import UseType


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


@dataclass(frozen=True, slots=True)
class ExportObject:
    source_id: str
    description: str
    position: int


@dataclass(frozen=True, slots=True)
class ExportEntry:
    source_id: str
    description: str
    position: int
    attachments: list[ExportAttachment] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProjectExportData:
    """The mapping context's own view of a collection-use project, ready to be
    turned into an :class:`InSituVisitRecord`."""

    reference_number: str
    begin_date: date
    end_date: date
    use_type: UseType
    visitor_name: str
    requested_objects: list[ExportObject] = field(default_factory=list)
    in_situ_occurrences: list[ExportEntry] = field(default_factory=list)
    in_situ_logs: list[ExportEntry] = field(default_factory=list)
    in_situ_publications: list[ExportEntry] = field(default_factory=list)


class ProjectExportPort(Protocol):
    """Reads a collection-use project's export data. Returns ``None`` when the
    project does not exist."""

    async def load(self, project_id: str) -> ProjectExportData | None: ...
