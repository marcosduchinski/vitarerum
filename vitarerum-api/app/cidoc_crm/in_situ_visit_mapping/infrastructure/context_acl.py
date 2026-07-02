"""Anti-corruption layer over the Use of Collections context.

The ONLY place in the In Situ Visit mapping context that knows about
``use_of_collections``. It reads through the published OHS
(``use_of_collections.public``) and translates the project export view into this
context's own ``ProjectExportData`` language.
"""

from __future__ import annotations

from app.cidoc_crm.in_situ_visit_mapping.application.ports import (
    ExportAttachment,
    ExportEntry,
    ExportObject,
    ProjectExportData,
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
        reference_number=view.reference_number,
        begin_date=view.begin_date,
        end_date=view.end_date,
        use_type=view.intended_use,
        visitor_name=view.visitor_name,
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
    )


def _entry(view: ExportEntryView) -> ExportEntry:
    return ExportEntry(
        source_id=view.source_id,
        description=view.description,
        position=view.position,
        attachments=[
            ExportAttachment(
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
            )
            for att in view.attachments
        ],
    )
