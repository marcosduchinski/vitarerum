"""In-Situ Visit Report ingestion — a cross-context inbound orchestrator.

It composes two existing use cases — ``ExportInSituVisitFromProject`` (CIDOC-CRM
mapping) and ``GenerateNarrative`` (KG-RAG) — and persists the linkage as an
``InSituVisitReport``. As a cross-context inbound orchestrator it owns only its
own aggregate and never touches another context's aggregates directly.

The whole chain runs under a single transaction (the route commits once at the
end), so a narrative failure leaves no orphaned record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from app.ai.museum_narrative.application.use_cases import (
    GenerateNarrative,
    GenerateNarrativeInput,
)
from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    ExportInSituVisitFromProject,
    ExportInSituVisitInput,
)
from app.reports.in_situ_visit.application.ports import (
    InSituVisitRecordReader,
    InSituVisitReportRepository,
    NarrativeReader,
)
from app.reports.in_situ_visit.domain.models import (
    InSituVisitReport,
    InSituVisitReportId,
)
from app.shared.kernel import PermissionId

if TYPE_CHECKING:
    from app.ai.museum_narrative.presentation.schemas import StoredNarrativeResponse
    from app.cidoc_crm.in_situ_visit_mapping.presentation.schemas import (
        InSituVisitRecordResponse,
    )

_DEFAULT_TEMPERATURE = 0.3
_DEFAULT_LANGUAGE = "pt"


class InSituVisitReportNotFound(Exception):
    """Raised when a requested in-situ visit report does not exist."""


@dataclass(frozen=True, slots=True)
class GenerateInSituVisitReportInput:
    project_id: str
    created_by: PermissionId
    narrative_type: str | None = None
    target_language: str = _DEFAULT_LANGUAGE
    creativity_temperature: float = _DEFAULT_TEMPERATURE


class GenerateInSituVisitReport:
    def __init__(
        self,
        export_use_case: ExportInSituVisitFromProject,
        narrative_use_case: GenerateNarrative,
        report_repository: InSituVisitReportRepository,
    ) -> None:
        self._export = export_use_case
        self._narrative = narrative_use_case
        self._report_repo = report_repository

    async def execute(self, data: GenerateInSituVisitReportInput) -> InSituVisitReport:
        # 1. Export the project to a fresh CIDOC-CRM record (404 / 409 bubble up).
        record = await self._export.execute(
            ExportInSituVisitInput(project_id=data.project_id)
        )

        # 2. Generate a narrative from that record (400 / 422 / 503 / 504 bubble up).
        narrative = await self._narrative.execute(
            GenerateNarrativeInput(
                record_id=record.id,
                narrative_type=data.narrative_type,
                target_language=data.target_language,
                creativity_temperature=data.creativity_temperature,
            )
        )

        # 3. Persist the linkage. Commit happens in the route (single transaction).
        report = InSituVisitReport.create(
            created_by=data.created_by,
            project_id=data.project_id,
            narrative_id=narrative.id,
            in_situ_visit_record_id=record.id,
        )
        await self._report_repo.add(report)
        return report


@dataclass(frozen=True, slots=True)
class GetInSituVisitReportInput:
    project_id: str
    report_id: str


@dataclass(frozen=True, slots=True)
class ListInSituVisitReportsInput:
    project_id: str
    page: int = 0
    size: int = 20


@dataclass(frozen=True, slots=True)
class ListAllInSituVisitReportsInput:
    page: int = 0
    size: int = 20


class GetInSituVisitReport:
    """Return one stored report by id, or raise ``InSituVisitReportNotFound``."""

    def __init__(self, repository: InSituVisitReportRepository) -> None:
        self._repository = repository

    async def execute(self, data: GetInSituVisitReportInput) -> InSituVisitReport:
        report = await self._repository.get_by_id(InSituVisitReportId(data.report_id))
        # The report must belong to the project in the path.
        if report is None or report.project_id != data.project_id:
            raise InSituVisitReportNotFound(
                f"No report found with id {data.report_id} "
                f"for project {data.project_id}"
            )
        return report


class ListInSituVisitReports:
    """Return a page of stored reports for one project, newest first."""

    def __init__(self, repository: InSituVisitReportRepository) -> None:
        self._repository = repository

    async def execute(
        self, data: ListInSituVisitReportsInput
    ) -> tuple[list[InSituVisitReport], int]:
        return await self._repository.list_by_project(
            data.project_id, data.page, data.size
        )


@dataclass(frozen=True, slots=True)
class InSituVisitReportSummary:
    """A list row: the report's linkage ids plus a few human-readable fields
    pulled from its CIDOC-CRM record (for rendering a list without a per-row
    drill-down). The record fields are ``None`` if the record can't be read."""

    report: InSituVisitReport
    code: str | None
    visitor_name: str | None
    place_name: str | None
    visit_begin_date: date | None
    visit_end_date: date | None


class ListAllInSituVisitReportSummaries:
    """List reports across all projects (newest first) enriched, per row, with
    display fields read from the record through the CIDOC-CRM published language.

    Read-only assembly — touches no schema. It costs one record read per row in
    the page (page size is capped), which is acceptable for a list view."""

    def __init__(
        self,
        repository: InSituVisitReportRepository,
        record_reader: InSituVisitRecordReader,
    ) -> None:
        self._repository = repository
        self._record_reader = record_reader

    async def execute(
        self, data: ListAllInSituVisitReportsInput
    ) -> tuple[list[InSituVisitReportSummary], int]:
        reports, total = await self._repository.list_all(data.page, data.size)
        summaries: list[InSituVisitReportSummary] = []
        for report in reports:
            record = await self._record_reader.get(report.in_situ_visit_record_id)
            summaries.append(
                InSituVisitReportSummary(
                    report=report,
                    code=record.code if record else None,
                    visitor_name=record.visitorName if record else None,
                    place_name=record.placeName if record else None,
                    visit_begin_date=record.visitBeginDate if record else None,
                    visit_end_date=record.visitEndDate if record else None,
                )
            )
        return summaries, total


@dataclass(frozen=True, slots=True)
class InSituVisitReportDetail:
    """The assembled detail view: the report plus the embedded record and
    narrative DTOs read back from their own contexts."""

    report: InSituVisitReport
    record: InSituVisitRecordResponse | None
    narrative: StoredNarrativeResponse | None


class GetInSituVisitReportDetail:
    """Assemble a report's full detail by fanning out to the CIDOC-CRM record and
    the generated narrative through their published languages."""

    def __init__(
        self,
        repository: InSituVisitReportRepository,
        record_reader: InSituVisitRecordReader,
        narrative_reader: NarrativeReader,
    ) -> None:
        self._repository = repository
        self._record_reader = record_reader
        self._narrative_reader = narrative_reader

    async def execute(self, data: GetInSituVisitReportInput) -> InSituVisitReportDetail:
        report = await self._repository.get_by_id(InSituVisitReportId(data.report_id))
        # The report must belong to the project in the path.
        if report is None or report.project_id != data.project_id:
            raise InSituVisitReportNotFound(
                f"No report found with id {data.report_id} "
                f"for project {data.project_id}"
            )
        record = await self._record_reader.get(report.in_situ_visit_record_id)
        narrative = await self._narrative_reader.get(
            report.in_situ_visit_record_id, report.narrative_id
        )
        return InSituVisitReportDetail(
            report=report, record=record, narrative=narrative
        )
