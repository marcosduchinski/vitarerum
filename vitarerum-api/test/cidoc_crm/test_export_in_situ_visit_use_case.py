from datetime import UTC, date, datetime

import pytest

from app.cidoc_crm.in_situ_visit_mapping.application.ports import (
    ExportAttachment,
    ExportEntry,
    ExportObject,
    ProjectExportData,
    VisitExecutionEvidence,
)
from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    ExportInSituVisitFromProject,
    ExportInSituVisitInput,
    NotInSituVisit,
    ProjectNotFound,
    VisitNotEvidenced,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    InSituVisitId,
    InSituVisitRecord,
)
from app.shared.kernel import PermissionId, UseType

_INSTITUTION = "Museu de História Natural"
_COMPLETED_AT = datetime(2026, 6, 3, 17, 0, tzinfo=UTC)
_COMPLETED_BY = PermissionId("perm-staff")


def _evidenced() -> VisitExecutionEvidence:
    return VisitExecutionEvidence(
        occurred=True,
        evidence_type="project_completed_event",
        occurred_at=_COMPLETED_AT,
        recorded_by=_COMPLETED_BY,
    )


def _not_evidenced(*gaps: str) -> VisitExecutionEvidence:
    return VisitExecutionEvidence(
        occurred=False,
        evidence_type="insufficient_operational_evidence",
        gaps=list(gaps),
    )


def _export(
    use_type: UseType = UseType.IN_SITU_VISIT,
    evidence: VisitExecutionEvidence | None = None,
) -> ProjectExportData:
    return ProjectExportData(
        project_id="p1",
        reference_number="CUP-ABCD1234",
        title="Wolf study",
        purpose="Study collection objects in situ",
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        use_type=use_type,
        visitor_name="Maria do Rosário",
        visit_execution_evidence=evidence or _evidenced(),
        requested_objects=[
            ExportObject(
                "INV-1",
                "lupus",
                0,
                display_title="Iberian wolf",
                object_name="Canis lupus signatus",
                brief_description_snapshot="Mounted specimen",
            )
        ],
        in_situ_occurrences=[
            ExportEntry(
                "occ-1",
                "an occurrence",
                0,
                [ExportAttachment("att-1", "a photo", "photo.jpg", 0, "IMAGE")],
                number_of_objects=1,
                occurrence_date=datetime(2026, 6, 2, 10, 0, tzinfo=UTC),
                location="Gallery A",
                reported_by=PermissionId("perm-reporter"),
                testimonial="Observed during handling.",
            )
        ],
        in_situ_logs=[
            ExportEntry(
                "log-1",
                "observed",
                0,
                number_of_objects=1,
                added_at=datetime(2026, 6, 2, 11, 0, tzinfo=UTC),
                added_by=PermissionId("perm-log"),
            )
        ],
        in_situ_publications=[
            ExportEntry(
                "pub-1",
                "a paper",
                0,
                added_at=datetime(2026, 6, 3, 9, 0, tzinfo=UTC),
                added_by=PermissionId("perm-pub"),
            )
        ],
    )


class _FakePort:
    def __init__(self, data: ProjectExportData | None) -> None:
        self._data = data
        self.seen: str | None = None

    async def load(self, project_id: str) -> ProjectExportData | None:
        self.seen = project_id
        return self._data


class _CapturingRepo:
    def __init__(self) -> None:
        self.added: InSituVisitRecord | None = None

    async def add(self, record: InSituVisitRecord) -> None:
        self.added = record

    async def get_by_id(  # pragma: no cover
        self, record_id: InSituVisitId
    ) -> InSituVisitRecord | None:
        return None

    async def list(self, page: int, size: int):  # pragma: no cover
        raise NotImplementedError


def _use_case(
    data: ProjectExportData | None,
) -> tuple[ExportInSituVisitFromProject, _CapturingRepo]:
    repo = _CapturingRepo()
    return ExportInSituVisitFromProject(_FakePort(data), repo, _INSTITUTION), repo


async def test_export_maps_project_into_record_and_persists() -> None:
    use_case, repo = _use_case(_export())

    record = await use_case.execute(ExportInSituVisitInput(project_id="p1"))

    assert repo.added is record
    assert record.code == "CUP-ABCD1234"
    assert record.record_schema_version == 2
    assert record.mapping_version == "0.7.0"
    assert record.crm_version == "7.1.3"
    assert record.source_project_id == "p1"
    assert record.visit_begin_date == date(2026, 6, 1)
    assert record.visit_end_date == date(2026, 6, 3)
    assert record.planned_begin_date == date(2026, 6, 1)
    assert record.planned_end_date == date(2026, 6, 3)
    assert record.execution_evidence_type == "project_completed_event"
    assert record.execution_occurred_at == _COMPLETED_AT
    assert record.execution_recorded_by == "perm-staff"
    assert record.execution_evidence_gaps == []
    assert record.visitor_name == "Maria do Rosário"
    # place_name comes from the configured institution, not the project.
    assert record.place_name == _INSTITUTION
    # The producing institution is captured on the snapshot, so regenerating
    # the CIDOC graph later does not depend on the configuration of that day.
    assert record.institution_name == _INSTITUTION
    assert [ro.source_id for ro in record.requested_objects] == ["INV-1"]
    assert record.project_title == "Wolf study"
    assert record.project_purpose == "Study collection objects in situ"
    assert record.requested_objects[0].display_title == "Iberian wolf"
    assert record.requested_objects[0].object_name == "Canis lupus signatus"
    assert record.requested_objects[0].brief_description_snapshot == "Mounted specimen"
    assert len(record.in_situ_occurrences) == 1
    assert record.in_situ_occurrences[0].attachments[0].reference == "photo.jpg"
    assert record.in_situ_occurrences[0].attachments[0].media_type == "IMAGE"
    assert record.in_situ_occurrences[0].number_of_objects == 1
    assert record.in_situ_occurrences[0].occurrence_date == datetime(
        2026, 6, 2, 10, 0, tzinfo=UTC
    )
    assert record.in_situ_occurrences[0].location == "Gallery A"
    assert record.in_situ_occurrences[0].reported_by == "perm-reporter"
    assert record.in_situ_occurrences[0].testimonial == "Observed during handling."
    assert len(record.in_situ_logs) == 1
    assert record.in_situ_logs[0].number_of_objects == 1
    assert record.in_situ_logs[0].added_at == datetime(2026, 6, 2, 11, 0, tzinfo=UTC)
    assert record.in_situ_logs[0].added_by == "perm-log"
    assert len(record.in_situ_publications) == 1
    assert record.in_situ_publications[0].added_at == datetime(
        2026, 6, 3, 9, 0, tzinfo=UTC
    )
    assert record.in_situ_publications[0].added_by == "perm-pub"


async def test_export_propagates_related_object_source_id() -> None:
    data = _export()
    export_with_link = ProjectExportData(
        project_id=data.project_id,
        reference_number=data.reference_number,
        title=data.title,
        purpose=data.purpose,
        begin_date=data.begin_date,
        end_date=data.end_date,
        use_type=data.use_type,
        visitor_name=data.visitor_name,
        visit_execution_evidence=data.visit_execution_evidence,
        requested_objects=data.requested_objects,
        in_situ_occurrences=[
            ExportEntry("occ-1", "an occurrence", 0, related_object_source_id="INV-1")
        ],
        in_situ_logs=[ExportEntry("log-1", "observed", 0)],
        in_situ_publications=[
            ExportEntry("pub-1", "a paper", 0, related_object_source_id="INV-1")
        ],
    )
    use_case, repo = _use_case(export_with_link)

    record = await use_case.execute(ExportInSituVisitInput(project_id="p1"))

    assert repo.added is record
    assert record.in_situ_occurrences[0].related_object_source_id == "INV-1"
    assert record.in_situ_logs[0].related_object_source_id is None
    assert record.in_situ_publications[0].related_object_source_id == "INV-1"


async def test_export_raises_when_project_missing() -> None:
    use_case, _ = _use_case(None)
    with pytest.raises(ProjectNotFound):
        await use_case.execute(ExportInSituVisitInput(project_id="missing"))


async def test_export_rejects_non_in_situ_visit_use_type() -> None:
    use_case, repo = _use_case(_export(use_type=UseType.EXHIBITION))
    with pytest.raises(NotInSituVisit):
        await use_case.execute(ExportInSituVisitInput(project_id="p1"))
    assert repo.added is None


async def test_export_rejects_in_situ_visit_without_execution_evidence() -> None:
    use_case, repo = _use_case(
        _export(evidence=_not_evidenced("project_status_not_completed"))
    )

    with pytest.raises(VisitNotEvidenced):
        await use_case.execute(ExportInSituVisitInput(project_id="p1"))

    assert repo.added is None
