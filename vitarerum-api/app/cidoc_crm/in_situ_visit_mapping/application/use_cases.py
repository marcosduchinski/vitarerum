"""Application services for the In Situ Visit CIDOC mapping context.

One use case per endpoint: ``RecordInSituVisit`` persists a freshly generated
aggregate (POST), ``ListInSituVisits`` returns a page of stored records (GET).
``execute`` takes an ``Input`` dataclass, matching the repo-wide convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.cidoc_crm.in_situ_visit_mapping.application.cidoc import (
    load_mapping_definition,
    map_record_to_cidoc,
)
from app.cidoc_crm.in_situ_visit_mapping.application.ports import (
    ExportEntry,
    ExportObject,
    InSituVisitRecordRepository,
    ProjectExportPort,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    AttachmentData,
    ChildData,
    InSituVisitId,
    InSituVisitRecord,
)
from app.shared.kernel import UseType


class InSituVisitRecordNotFound(Exception):
    """Raised when a requested in-situ visit record does not exist."""


class ProjectNotFound(Exception):
    """Raised when the collection-use project to export does not exist."""


class NotInSituVisit(Exception):
    """Raised when the project's intended use is not IN_SITU_VISIT."""


class VisitNotEvidenced(Exception):
    """Raised when a project lacks evidence that the visit was executed."""


def _mapping_versions() -> tuple[str | None, str | None]:
    metadata = load_mapping_definition().get("metadata", {})
    mapping_version = metadata.get("mapping_version")
    crm_version = metadata.get("crm_version")
    return (
        mapping_version if isinstance(mapping_version, str) else None,
        crm_version if isinstance(crm_version, str) else None,
    )


@dataclass(frozen=True, slots=True)
class RecordInSituVisitInput:
    code: str
    visit_begin_date: date
    visit_end_date: date
    visitor_name: str
    place_name: str
    requested_objects: list[ChildData] = field(default_factory=list)
    in_situ_occurrences: list[ChildData] = field(default_factory=list)
    in_situ_logs: list[ChildData] = field(default_factory=list)
    in_situ_publications: list[ChildData] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ListInSituVisitsInput:
    page: int = 0
    size: int = 20


@dataclass(frozen=True, slots=True)
class BuildInSituVisitCidocInput:
    record_id: str


@dataclass(frozen=True, slots=True)
class ExportInSituVisitInput:
    project_id: str


class RecordInSituVisit:
    """Persist a new in-situ visit mapping record (the aggregate)."""

    def __init__(self, repository: InSituVisitRecordRepository) -> None:
        self._repository = repository
        self._mapping_version, self._crm_version = _mapping_versions()

    async def execute(self, data: RecordInSituVisitInput) -> InSituVisitRecord:
        record = InSituVisitRecord.create(
            code=data.code,
            visit_begin_date=data.visit_begin_date,
            visit_end_date=data.visit_end_date,
            visitor_name=data.visitor_name,
            place_name=data.place_name,
            mapping_version=self._mapping_version,
            crm_version=self._crm_version,
            requested_objects=data.requested_objects,
            in_situ_occurrences=data.in_situ_occurrences,
            in_situ_logs=data.in_situ_logs,
            in_situ_publications=data.in_situ_publications,
        )
        await self._repository.add(record)
        return record


class ListInSituVisits:
    """Return a page of stored in-situ visit mapping records."""

    def __init__(self, repository: InSituVisitRecordRepository) -> None:
        self._repository = repository

    async def execute(
        self, data: ListInSituVisitsInput
    ) -> tuple[list[InSituVisitRecord], int]:
        return await self._repository.list(data.page, data.size)


class BuildInSituVisitCidoc:
    """Build the CIDOC-CRM JSON-LD representation of a stored visit record."""

    def __init__(self, repository: InSituVisitRecordRepository) -> None:
        self._repository = repository
        # The mapping definition is static; load it once per use-case instance.
        self._mapping = load_mapping_definition()

    async def execute(self, data: BuildInSituVisitCidocInput) -> dict[str, Any]:
        record = await self._repository.get_by_id(InSituVisitId(data.record_id))
        if record is None:
            raise InSituVisitRecordNotFound(
                f"No in-situ visit record found with id {data.record_id}"
            )
        return map_record_to_cidoc(record, self._mapping)


def _object_to_child(obj: ExportObject) -> ChildData:
    return ChildData(
        source_id=obj.source_id,
        description=obj.description,
        position=obj.position,
        display_title=obj.display_title,
        object_name=obj.object_name,
        brief_description_snapshot=obj.brief_description_snapshot,
    )


def _entry_to_child(entry: ExportEntry) -> ChildData:
    return ChildData(
        source_id=entry.source_id,
        description=entry.description,
        position=entry.position,
        related_object_source_id=entry.related_object_source_id,
        attachments=[
            AttachmentData(
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
                media_type=att.media_type,
            )
            for att in entry.attachments
        ],
        number_of_objects=entry.number_of_objects,
        occurrence_date=entry.occurrence_date,
        location=entry.location,
        reported_by=str(entry.reported_by) if entry.reported_by else None,
        testimonial=entry.testimonial,
        added_at=entry.added_at,
        added_by=str(entry.added_by) if entry.added_by else None,
        access_log_date_conclusion=entry.access_log_date_conclusion,
        access_log_curator=(
            str(entry.access_log_curator) if entry.access_log_curator else None
        ),
        occurrence_log_date_conclusion=entry.occurrence_log_date_conclusion,
        occurrence_log_curator=(
            str(entry.occurrence_log_curator)
            if entry.occurrence_log_curator
            else None
        ),
    )


class ExportInSituVisitFromProject:
    """Generate and persist an in-situ visit record from a collection-use project.

    Only projects whose intended use is ``IN_SITU_VISIT`` can be exported; the
    project reference number becomes the record code, and the configured
    institution name is captured both as the visit's place and as the producer
    of the snapshot (the CIDOC graph's ``dcterms:creator``).
    """

    def __init__(
        self,
        export_port: ProjectExportPort,
        repository: InSituVisitRecordRepository,
        institution_name: str,
    ) -> None:
        self._export_port = export_port
        self._repository = repository
        self._institution_name = institution_name
        self._mapping_version, self._crm_version = _mapping_versions()

    async def execute(self, data: ExportInSituVisitInput) -> InSituVisitRecord:
        export = await self._export_port.load(data.project_id)
        if export is None:
            raise ProjectNotFound(
                f"No collection-use project found with id {data.project_id}"
            )
        if export.use_type != UseType.IN_SITU_VISIT:
            raise NotInSituVisit(
                "Project intended use must be IN_SITU_VISIT to export an "
                "in-situ visit record"
            )
        if not export.visit_execution_evidence.occurred:
            gaps = ", ".join(export.visit_execution_evidence.gaps) or "unknown"
            raise VisitNotEvidenced(
                "Project lacks minimum operational evidence that the in-situ "
                f"visit was executed: {gaps}"
            )

        record = InSituVisitRecord.create(
            code=export.reference_number,
            visit_begin_date=export.begin_date,
            visit_end_date=export.end_date,
            visitor_name=export.visitor_name,
            place_name=self._institution_name,
            institution_name=self._institution_name,
            mapping_version=self._mapping_version,
            crm_version=self._crm_version,
            source_project_id=export.project_id,
            project_title=export.title,
            project_purpose=export.purpose,
            planned_begin_date=export.begin_date,
            planned_end_date=export.end_date,
            execution_evidence_type=export.visit_execution_evidence.evidence_type,
            execution_occurred_at=export.visit_execution_evidence.occurred_at,
            execution_recorded_by=(
                str(export.visit_execution_evidence.recorded_by)
                if export.visit_execution_evidence.recorded_by
                else None
            ),
            execution_evidence_gaps=export.visit_execution_evidence.gaps,
            approved_at=export.approval.approved_at if export.approval else None,
            approved_by=(
                str(export.approval.approved_by)
                if export.approval and export.approval.approved_by
                else None
            ),
            approval_note=export.approval.approval_note if export.approval else None,
            requested_objects=[_object_to_child(ro) for ro in export.requested_objects],
            in_situ_occurrences=[
                _entry_to_child(e) for e in export.in_situ_occurrences
            ],
            in_situ_logs=[_entry_to_child(e) for e in export.in_situ_logs],
            in_situ_publications=[
                _entry_to_child(e) for e in export.in_situ_publications
            ],
        )
        await self._repository.add(record)
        return record
