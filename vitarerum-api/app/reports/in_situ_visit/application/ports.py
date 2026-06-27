"""Ports for the In-Situ Visit Report context."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.reports.in_situ_visit.domain.models import (
    InSituVisitReport,
    InSituVisitReportId,
)

if TYPE_CHECKING:
    from app.ai.museum_narrative.presentation.schemas import StoredNarrativeResponse
    from app.cidoc_crm.in_situ_visit_mapping.presentation.schemas import (
        InSituVisitRecordResponse,
    )


class InSituVisitReportRepository(Protocol):
    async def add(self, report: InSituVisitReport) -> None: ...

    async def get_by_id(
        self, report_id: InSituVisitReportId
    ) -> InSituVisitReport | None: ...

    async def list_by_project(
        self, project_id: str, page: int, size: int
    ) -> tuple[list[InSituVisitReport], int]: ...

    async def list_all(
        self, page: int, size: int
    ) -> tuple[list[InSituVisitReport], int]: ...


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
