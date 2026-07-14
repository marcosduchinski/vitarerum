from datetime import date

from app.cidoc_crm.in_situ_visit_mapping.infrastructure.context_acl import (
    UseOfCollectionsExportAdapter,
)
from app.use_of_collections.public import ExportEntryView, ExportObjectView, ProjectExportView
from app.shared.kernel import UseType


class _FakeReader:
    def __init__(self, view: ProjectExportView) -> None:
        self._view = view

    async def load(self, project_id: str) -> ProjectExportView | None:
        return self._view


def _view() -> ProjectExportView:
    return ProjectExportView(
        project_id="p1",
        reference_number="CUP-ABCD1234",
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        intended_use=UseType.IN_SITU_VISIT,
        visitor_name="Maria do Rosário",
        requested_objects=[ExportObjectView("INV-1", "lupus", 0)],
        in_situ_occurrences=[
            ExportEntryView("occ-1", "an occurrence", 0, object_source_id="INV-1")
        ],
        in_situ_logs=[ExportEntryView("log-1", "observed", 0)],
        in_situ_publications=[
            ExportEntryView("pub-1", "a paper", 0, object_source_id="INV-1")
        ],
    )


async def test_acl_translates_object_source_id_into_related_object_source_id() -> None:
    adapter = UseOfCollectionsExportAdapter(_FakeReader(_view()))

    data = await adapter.load("p1")

    assert data is not None
    assert data.in_situ_occurrences[0].related_object_source_id == "INV-1"
    # Log entry has no object_source_id in the view → stays None, not "None".
    assert data.in_situ_logs[0].related_object_source_id is None
    assert data.in_situ_publications[0].related_object_source_id == "INV-1"
