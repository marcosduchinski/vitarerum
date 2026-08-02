"""Ports for the In-Situ Visit Report context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Protocol

from app.reports.in_situ_visit.domain.models import (
    InSituVisitReport,
    InSituVisitReportId,
)
from app.shared.kernel import PermissionId

if TYPE_CHECKING:
    from app.ai.museum_narrative.presentation.schemas import (
        PaginatedNarrativeRevisionsResponse,
        StoredNarrativeResponse,
    )
    from app.cidoc_crm.in_situ_visit_mapping.presentation.schemas import (
        InSituVisitRecordResponse,
    )


@dataclass(frozen=True, slots=True)
class InSituVisitReportFilters:
    search: str | None = None
    generated_from: datetime | None = None
    generated_to: datetime | None = None
    visit_from: date | None = None
    visit_to: date | None = None
    narrative_type: str | None = None


class InSituVisitReportRepository(Protocol):
    async def add(self, report: InSituVisitReport) -> None: ...

    async def get_by_id(
        self, report_id: InSituVisitReportId
    ) -> InSituVisitReport | None: ...

    async def list_by_project(
        self, project_id: str, page: int, size: int
    ) -> tuple[list[InSituVisitReport], int]: ...

    async def list_all(
        self, page: int, size: int, filters: InSituVisitReportFilters | None = None
    ) -> tuple[list[InSituVisitReport], int]: ...

    async def delete(self, report_id: InSituVisitReportId) -> bool: ...


class InSituVisitRecordExporter(Protocol):
    """Exports a collection-use project into the CIDOC-CRM record read model."""

    async def export(self, project_id: str) -> InSituVisitRecordResponse: ...


class NarrativeGenerator(Protocol):
    """Generates and stores a narrative for an exported CIDOC-CRM record."""

    async def generate(
        self,
        record_id: str,
        *,
        narrative_type: str | None,
        target_language: str,
        creativity_temperature: float,
    ) -> StoredNarrativeResponse: ...


class InSituVisitRecordReader(Protocol):
    """Reads the exported record's presentation DTO from the CIDOC-CRM context
    (via ``app.cidoc_crm.public``)."""

    async def get(self, record_id: str) -> InSituVisitRecordResponse | None: ...


class NarrativeReader(Protocol):
    """Reads a generated narrative's presentation DTO from the museum-narrative
    context (via ``app.ai.museum_narrative.public``)."""

    async def get(
        self, record_id: str, narrative_id: str
    ) -> StoredNarrativeResponse | None: ...


class NarrativeDeleter(Protocol):
    """Deletes a generated narrative through the museum-narrative context."""

    async def delete(self, record_id: str, narrative_id: str) -> bool: ...


class ExternalPublicationRevoker(Protocol):
    """Revokes external publications that expose a generated report."""

    async def revoke_for_report(
        self, report_id: str, revoked_by: PermissionId
    ) -> int: ...


class NarrativeRevisionReader(Protocol):
    """Reads editorial revisions from the museum-narrative context."""

    async def list(
        self, record_id: str, narrative_id: str, page: int, size: int
    ) -> PaginatedNarrativeRevisionsResponse | None: ...
