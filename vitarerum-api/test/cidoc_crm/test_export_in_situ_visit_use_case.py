from datetime import date

import pytest

from app.cidoc_crm.in_situ_visit_mapping.application.ports import (
    ExportAttachment,
    ExportEntry,
    ExportObject,
    ProjectExportData,
)
from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    ExportInSituVisitFromProject,
    ExportInSituVisitInput,
    NotInSituVisit,
    ProjectNotFound,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    InSituVisitId,
    InSituVisitRecord,
)
from app.shared.kernel import UseType

_INSTITUTION = "Museu de História Natural"


def _export(use_type: UseType = UseType.IN_SITU_VISIT) -> ProjectExportData:
    return ProjectExportData(
        reference_number="CUP-ABCD1234",
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        use_type=use_type,
        visitor_name="Maria do Rosário",
        requested_objects=[ExportObject("INV-1", "lupus", 0)],
        in_situ_occurrences=[
            ExportEntry(
                "occ-1",
                "an occurrence",
                0,
                [ExportAttachment("att-1", "a photo", "photo.jpg", 0)],
            )
        ],
        in_situ_logs=[ExportEntry("log-1", "observed", 0)],
        in_situ_publications=[ExportEntry("pub-1", "a paper", 0)],
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
    assert record.visit_begin_date == date(2026, 6, 1)
    assert record.visit_end_date == date(2026, 6, 3)
    assert record.visitor_name == "Maria do Rosário"
    # place_name comes from the configured institution, not the project.
    assert record.place_name == _INSTITUTION
    assert [ro.source_id for ro in record.requested_objects] == ["INV-1"]
    assert len(record.in_situ_occurrences) == 1
    assert record.in_situ_occurrences[0].attachments[0].reference == "photo.jpg"
    assert len(record.in_situ_logs) == 1
    assert len(record.in_situ_publications) == 1


async def test_export_raises_when_project_missing() -> None:
    use_case, _ = _use_case(None)
    with pytest.raises(ProjectNotFound):
        await use_case.execute(ExportInSituVisitInput(project_id="missing"))


async def test_export_rejects_non_in_situ_visit_use_type() -> None:
    use_case, repo = _use_case(_export(use_type=UseType.EXHIBITION))
    with pytest.raises(NotInSituVisit):
        await use_case.execute(ExportInSituVisitInput(project_id="p1"))
    assert repo.added is None
