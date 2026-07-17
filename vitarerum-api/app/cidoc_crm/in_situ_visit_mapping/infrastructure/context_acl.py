"""Anti-corruption layer over the Use of Collections context.

The ONLY place in the In Situ Visit mapping context that knows about
``use_of_collections``. It reads through the published OHS
(``use_of_collections.public``) and translates the project export view into this
context's own ``ProjectExportData`` language.
"""

from __future__ import annotations

from app.cidoc_crm.in_situ_visit_mapping.application.ports import (
    ApprovalData,
    ExportAttachment,
    ExportEntry,
    ExportObject,
    ProjectExportData,
    VisitExecutionEvidence,
)
from app.use_of_collections.public import (
    ExportEntryView,
    ExportObjectView,
    ProjectExportReader,
    ProjectExportView,
)


class UseOfCollectionsExportAdapter:
    """Implements ``ProjectExportPort`` by reading the Use of Collections OHS."""

    def __init__(self, reader: ProjectExportReader) -> None:
        self._reader = reader

    async def load(self, project_id: str) -> ProjectExportData | None:
        view = await self._reader.load(project_id)
        if view is None:
            return None
        return _to_export_data(view)


def _to_export_data(view: ProjectExportView) -> ProjectExportData:
    return ProjectExportData(
        project_id=view.project_id,
        reference_number=view.reference_number,
        title=view.title,
        purpose=view.purpose,
        begin_date=view.begin_date,
        end_date=view.end_date,
        use_type=view.intended_use,
        visitor_name=view.visitor_name,
        visit_execution_evidence=VisitExecutionEvidence(
            occurred=view.visit_execution_evidence.occurred,
            evidence_type=view.visit_execution_evidence.evidence_type,
            occurred_at=view.visit_execution_evidence.occurred_at,
            recorded_by=view.visit_execution_evidence.recorded_by,
            gaps=view.visit_execution_evidence.gaps,
        ),
        approval=(
            ApprovalData(
                approved_at=view.approval.approved_at,
                approved_by=view.approval.approved_by,
                approval_note=view.approval.approval_note,
            )
            if view.approval is not None
            else None
        ),
        requested_objects=[_object(ro) for ro in view.requested_objects],
        in_situ_occurrences=[_entry(e) for e in view.in_situ_occurrences],
        in_situ_logs=[_entry(e) for e in view.in_situ_logs],
        in_situ_publications=[_entry(e) for e in view.in_situ_publications],
    )


def _object(view: ExportObjectView) -> ExportObject:
    return ExportObject(
        source_id=view.source_id,
        description=view.description,
        position=view.position,
        display_title=view.display_title,
        object_name=view.object_name,
        brief_description_snapshot=view.brief_description_snapshot,
    )


def _entry(view: ExportEntryView) -> ExportEntry:
    return ExportEntry(
        source_id=view.source_id,
        description=view.description,
        position=view.position,
        related_object_source_id=view.object_source_id,
        number_of_objects=view.number_of_objects,
        occurrence_date=view.occurrence_date,
        location=view.location,
        reported_by=view.reported_by,
        testimonial=view.testimonial,
        added_at=view.added_at,
        added_by=view.added_by,
        access_log_date_conclusion=view.access_log_date_conclusion,
        access_log_curator=view.access_log_curator,
        occurrence_log_date_conclusion=view.occurrence_log_date_conclusion,
        occurrence_log_curator=view.occurrence_log_curator,
        attachments=[
            ExportAttachment(
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
                media_type=att.media_type,
            )
            for att in view.attachments
        ],
    )
