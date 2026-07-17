from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from httpx import ASGITransport, AsyncClient

from app.cidoc_crm.in_situ_visit_mapping.application.cidoc.engine import (
    map_record_to_cidoc,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    ChildData,
    InSituVisitRecord,
)
from app.cidoc_crm.in_situ_visit_mapping.presentation.dependencies import (
    get_cidoc_use_case,
)
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)


def _doc() -> dict:
    record = InSituVisitRecord.create(
        code="VS-1",
        visit_begin_date=date(2026, 1, 1),
        visit_end_date=date(2026, 1, 2),
        visitor_name="Ana",
        place_name="Museu",
        requested_objects=[ChildData("XL01", "lupus", 1)],
    )
    return map_record_to_cidoc(record)


def _invalid_doc() -> dict:
    doc = _doc()
    visit = next(n for n in doc["@graph"] if n["@id"].startswith("ex:visit/"))
    visit["crm:P14_carried_out_by"] = {"@id": "ex:place/museu"}
    return doc


class _FakeCidocUseCase:
    def __init__(self, doc: dict | None = None) -> None:
        self._doc = doc or _doc()

    async def execute(self, data):  # noqa: ANN001
        return self._doc


@asynccontextmanager
async def _client(doc: dict | None = None) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_caller_permission] = lambda: _STAFF
    app.dependency_overrides[get_cidoc_use_case] = lambda: _FakeCidocUseCase(doc)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_get_cidoc_crm_validates_by_default() -> None:
    async with _client() as client:
        response = await client.get(
            "/api/v1/cidoc-mapping/in-situ-visit/record-1/cidoc-crm"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["@context"]["crm"] == "http://www.cidoc-crm.org/cidoc-crm/"
    assert body["@graph"]


async def test_get_cidoc_crm_returns_422_when_default_validation_fails() -> None:
    async with _client(_invalid_doc()) as client:
        response = await client.get(
            "/api/v1/cidoc-mapping/in-situ-visit/record-1/cidoc-crm"
        )

    assert response.status_code == 422
    assert response.json()["error"] == "SEMANTIC_VALIDATION_FAILED"


async def test_get_cidoc_crm_can_skip_validation_explicitly() -> None:
    async with _client(_invalid_doc()) as client:
        response = await client.get(
            "/api/v1/cidoc-mapping/in-situ-visit/record-1/cidoc-crm?validate=false"
        )

    assert response.status_code == 200
    assert response.json()["@graph"]
