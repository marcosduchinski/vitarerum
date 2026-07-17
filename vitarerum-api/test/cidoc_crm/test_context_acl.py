from datetime import UTC, date, datetime

from app.cidoc_crm.in_situ_visit_mapping.infrastructure.context_acl import (
    UseOfCollectionsExportAdapter,
)
from app.shared.kernel import PermissionId, UseType
from app.use_of_collections.public import (
    ApprovalView,
    ExportAttachmentView,
    ExportEntryView,
    ExportObjectView,
    ProjectExportView,
    VisitExecutionEvidenceView,
)


class _FakeReader:
    def __init__(self, view: ProjectExportView) -> None:
        self._view = view

    async def load(self, project_id: str) -> ProjectExportView | None:
        return self._view


def _view() -> ProjectExportView:
    return ProjectExportView(
        project_id="p1",
        reference_number="CUP-ABCD1234",
        title="Wolf study",
        purpose="Study collection objects in situ",
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        intended_use=UseType.IN_SITU_VISIT,
        visitor_name="Maria do Rosário",
        visit_execution_evidence=VisitExecutionEvidenceView(
            occurred=True,
            evidence_type="project_completed_event",
            occurred_at=datetime(2026, 6, 3, 17, 0, tzinfo=UTC),
            recorded_by=PermissionId("perm-staff"),
        ),
        approval=ApprovalView(
            approved_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
            approved_by=PermissionId("perm-director"),
            approval_note="Approved for in-situ handling.",
        ),
        requested_objects=[
            ExportObjectView(
                "INV-1",
                "lupus",
                0,
                display_title="Iberian wolf",
                object_name="Canis lupus signatus",
                brief_description_snapshot="Mounted specimen",
            )
        ],
        in_situ_occurrences=[
            ExportEntryView(
                "occ-1",
                "an occurrence",
                0,
                attachments=[
                    ExportAttachmentView("att-1", "a photo", "photo.jpg", 0, "IMAGE")
                ],
                object_source_id="INV-1",
                number_of_objects=1,
                occurrence_date=datetime(2026, 6, 2, 10, 0, tzinfo=UTC),
                location="Gallery A",
                reported_by=PermissionId("perm-reporter"),
                testimonial="Observed during handling.",
                occurrence_log_date_conclusion=datetime(
                    2026, 6, 2, 18, 0, tzinfo=UTC
                ),
                occurrence_log_curator=PermissionId("perm-curator"),
            )
        ],
        in_situ_logs=[
            ExportEntryView(
                "log-1",
                "observed",
                0,
                number_of_objects=1,
                added_at=datetime(2026, 6, 2, 11, 0, tzinfo=UTC),
                added_by=PermissionId("perm-log"),
                access_log_date_conclusion=datetime(2026, 6, 2, 19, 0, tzinfo=UTC),
                access_log_curator=PermissionId("perm-access-curator"),
            )
        ],
        in_situ_publications=[
            ExportEntryView(
                "pub-1",
                "a paper",
                0,
                object_source_id="INV-1",
                added_at=datetime(2026, 6, 3, 9, 0, tzinfo=UTC),
                added_by=PermissionId("perm-pub"),
            )
        ],
    )


async def test_acl_translates_object_source_id_into_related_object_source_id() -> None:
    adapter = UseOfCollectionsExportAdapter(_FakeReader(_view()))

    data = await adapter.load("p1")

    assert data is not None
    assert data.title == "Wolf study"
    assert data.purpose == "Study collection objects in situ"
    assert data.approval is not None
    assert data.approval.approved_by == "perm-director"
    assert data.approval.approval_note == "Approved for in-situ handling."
    assert data.requested_objects[0].display_title == "Iberian wolf"
    assert data.requested_objects[0].object_name == "Canis lupus signatus"
    assert data.requested_objects[0].brief_description_snapshot == "Mounted specimen"
    assert data.in_situ_occurrences[0].related_object_source_id == "INV-1"
    assert data.in_situ_occurrences[0].number_of_objects == 1
    assert data.in_situ_occurrences[0].location == "Gallery A"
    assert data.in_situ_occurrences[0].reported_by == "perm-reporter"
    assert data.in_situ_occurrences[0].testimonial == "Observed during handling."
    assert data.in_situ_occurrences[0].attachments[0].media_type == "IMAGE"
    assert data.in_situ_occurrences[0].occurrence_log_curator == "perm-curator"
    # Log entry has no object_source_id in the view → stays None, not "None".
    assert data.in_situ_logs[0].related_object_source_id is None
    assert data.in_situ_logs[0].added_by == "perm-log"
    assert data.in_situ_logs[0].access_log_curator == "perm-access-curator"
    assert data.in_situ_publications[0].related_object_source_id == "INV-1"
    assert data.in_situ_publications[0].added_by == "perm-pub"
    assert data.visit_execution_evidence.occurred is True
    assert data.visit_execution_evidence.evidence_type == "project_completed_event"
