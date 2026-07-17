from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime

from httpx import ASGITransport, AsyncClient

from app.cidoc_crm.in_situ_visit_mapping.application.ports import (
    ExportAttachment,
    ExportEntry,
    ExportObject,
    ProjectExportData,
    VisitExecutionEvidence,
)
from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    ExportInSituVisitFromProject,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    InSituVisitId,
    InSituVisitRecord,
)
from app.cidoc_crm.in_situ_visit_mapping.presentation.dependencies import (
    get_export_use_case,
)
from app.database import get_async_session
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission
from app.shared.kernel import UseType

_MISSING = object()

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="r@uni.pt"
)
_INSTITUTION = "Test Museum"
_COMPLETED_AT = datetime(2026, 6, 3, 17, 0, tzinfo=UTC)


def _evidenced() -> VisitExecutionEvidence:
    return VisitExecutionEvidence(
        occurred=True,
        evidence_type="project_completed_event",
        occurred_at=_COMPLETED_AT,
        recorded_by=PermissionId("perm-staff"),
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
                related_object_source_id="INV-1",
                number_of_objects=1,
                occurrence_date=datetime(2026, 6, 2, 10, 0, tzinfo=UTC),
                location="Gallery A",
                reported_by=PermissionId("perm-reporter"),
                testimonial="Observed during handling.",
            )
        ],
    )


class _FakePort:
    def __init__(self, data: ProjectExportData | None) -> None:
        self._data = data

    async def load(self, project_id: str) -> ProjectExportData | None:
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


class _FakeSession:
    async def commit(self) -> None:
        self.committed = True


@asynccontextmanager
async def _client(
    *,
    caller: Actor = _STAFF,
    data: ProjectExportData | None | object = _MISSING,
) -> AsyncIterator[AsyncClient]:
    resolved = _export() if data is _MISSING else data
    repo = _CapturingRepo()
    use_case = ExportInSituVisitFromProject(
        _FakePort(resolved), repo, _INSTITUTION  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_export_use_case] = lambda: use_case
    app.dependency_overrides[get_async_session] = lambda: _FakeSession()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


_URL = "/api/v1/collection-use-projects/p1/export-in-situ-visit-record"


async def test_export_happy_path_returns_201_with_mapped_record() -> None:
    async with _client() as client:
        resp = await client.post(_URL)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "CUP-ABCD1234"
    assert body["recordSchemaVersion"] == 2
    assert body["sourceProjectId"] == "p1"
    assert body["sourceProjectTitle"] == "Wolf study"
    assert body["sourceProjectPurpose"] == "Study collection objects in situ"
    assert body["plannedBeginDate"] == "2026-06-01"
    assert body["plannedEndDate"] == "2026-06-03"
    assert body["executionEvidenceType"] == "project_completed_event"
    assert body["executionRecordedBy"] == "perm-staff"
    assert body["placeName"] == _INSTITUTION
    assert body["visitorName"] == "Maria do Rosário"
    assert [ro["sourceId"] for ro in body["requestedObjects"]] == ["INV-1"]
    assert body["requestedObjects"][0]["displayTitle"] == "Iberian wolf"
    assert body["requestedObjects"][0]["objectName"] == "Canis lupus signatus"
    assert body["inSituOccurrences"][0]["relatedObjectSourceId"] == "INV-1"
    assert body["inSituOccurrences"][0]["numberOfObjects"] == 1
    assert body["inSituOccurrences"][0]["location"] == "Gallery A"
    assert body["inSituOccurrences"][0]["reportedBy"] == "perm-reporter"
    assert body["inSituOccurrences"][0]["attachments"][0]["mediaType"] == "IMAGE"


async def test_export_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 403


async def test_export_project_not_found_404() -> None:
    async with _client(data=None) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 404
    assert resp.json()["error"] == "PROJECT_NOT_FOUND"


async def test_export_wrong_use_type_409() -> None:
    async with _client(data=_export(use_type=UseType.EXHIBITION)) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_USE_TYPE"


async def test_export_without_execution_evidence_409() -> None:
    async with _client(
        data=_export(evidence=_not_evidenced("project_status_not_completed"))
    ) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 409
    assert resp.json()["error"] == "VISIT_NOT_EVIDENCED"
