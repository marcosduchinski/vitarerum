from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from httpx import ASGITransport, AsyncClient

from app.cidoc_crm.in_situ_visit_mapping.application.ports import (
    ExportObject,
    ProjectExportData,
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


def _export(use_type: UseType = UseType.IN_SITU_VISIT) -> ProjectExportData:
    return ProjectExportData(
        reference_number="CUP-ABCD1234",
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        use_type=use_type,
        visitor_name="Maria do Rosário",
        requested_objects=[ExportObject("INV-1", "lupus", 0)],
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
    assert body["placeName"] == _INSTITUTION
    assert body["visitorName"] == "Maria do Rosário"
    assert [ro["sourceId"] for ro in body["requestedObjects"]] == ["INV-1"]


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
