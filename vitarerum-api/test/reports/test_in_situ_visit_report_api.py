"""Integration tests for the in-situ visit report endpoint.

The endpoint orchestrates two other contexts (CIDOC-CRM export + KG-RAG
narrative). These tests override ``get_report_use_case`` with a real
``GenerateInSituVisitReport`` composed of in-memory fakes for those two steps,
so the route → orchestrator → response path (and its error mapping) is exercised
without a database or a live LLM.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient

from app.ai.museum_narrative.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
    SemanticValidationFailed,
    UnsupportedNarrativeType,
)
from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    NotInSituVisit,
    ProjectNotFound,
)
from app.database import get_async_session
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.reports.in_situ_visit.application.use_cases import GenerateInSituVisitReport
from app.reports.in_situ_visit.domain.models import InSituVisitReport
from app.reports.in_situ_visit.presentation.dependencies import get_report_use_case
from app.shared.dependencies import get_caller_permission

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="r@uni.pt"
)

_URL = "/api/v1/reports/collection-use/p1/in_situ_visit"


class _FakeExport:
    def __init__(self, *, record=None, error: Exception | None = None) -> None:
        self._record = record or SimpleNamespace(id="rec-1")
        self._error = error

    async def execute(self, data):  # noqa: ANN001
        if self._error is not None:
            raise self._error
        return self._record


class _FakeNarrative:
    def __init__(self, *, narrative=None, error: Exception | None = None) -> None:
        self._narrative = narrative or SimpleNamespace(id="nar-1")
        self._error = error

    async def execute(self, data):  # noqa: ANN001
        if self._error is not None:
            raise self._error
        return self._narrative


class _CapturingRepo:
    def __init__(self) -> None:
        self.added: InSituVisitReport | None = None

    async def add(self, report: InSituVisitReport) -> None:
        self.added = report


class _FakeSession:
    async def commit(self) -> None:
        self.committed = True


@asynccontextmanager
async def _client(
    *,
    caller: Actor = _STAFF,
    export_error: Exception | None = None,
    narrative_error: Exception | None = None,
) -> AsyncIterator[tuple[AsyncClient, _CapturingRepo]]:
    repo = _CapturingRepo()
    use_case = GenerateInSituVisitReport(
        _FakeExport(error=export_error),  # type: ignore[arg-type]
        _FakeNarrative(error=narrative_error),  # type: ignore[arg-type]
        repo,
    )
    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_report_use_case] = lambda: use_case
    app.dependency_overrides[get_async_session] = lambda: _FakeSession()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, repo
    finally:
        app.dependency_overrides.clear()


async def test_happy_path_returns_201_linking_record_and_narrative() -> None:
    async with _client() as (client, repo):
        resp = await client.post(_URL, json={})
    assert resp.status_code == 201
    body = resp.json()
    assert body["projectId"] == "p1"
    assert body["createdBy"] == "perm-staff"
    assert body["inSituVisitRecordId"] == "rec-1"
    assert body["narrativeId"] == "nar-1"
    assert body["id"] and body["createdAt"]
    # The report aggregate was persisted with the same linkage.
    assert repo.added is not None
    assert repo.added.in_situ_visit_record_id == "rec-1"
    assert repo.added.narrative_id == "nar-1"


async def test_forbidden_for_external_caller() -> None:
    async with _client(caller=_EXTERNAL) as (client, repo):
        resp = await client.post(_URL, json={})
    assert resp.status_code == 403
    assert repo.added is None


async def test_project_not_found_maps_to_404() -> None:
    async with _client(export_error=ProjectNotFound("nope")) as (client, repo):
        resp = await client.post(_URL, json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "PROJECT_NOT_FOUND"
    assert repo.added is None


async def test_wrong_use_type_maps_to_409() -> None:
    async with _client(export_error=NotInSituVisit("wrong")) as (client, repo):
        resp = await client.post(_URL, json={})
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_USE_TYPE"
    assert repo.added is None


async def test_unsupported_narrative_type_maps_to_400() -> None:
    async with _client(narrative_error=UnsupportedNarrativeType("bad style")) as (
        client,
        repo,
    ):
        resp = await client.post(_URL, json={"narrative_type": "marketing"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_NARRATIVE_TYPE"
    assert repo.added is None


async def test_temperature_above_one_is_422() -> None:
    async with _client() as (client, repo):
        resp = await client.post(_URL, json={"creativity_temperature": 1.01})
    assert resp.status_code == 422
    assert repo.added is None


async def test_semantic_validation_failure_maps_to_422() -> None:
    async with _client(narrative_error=SemanticValidationFailed()) as (client, repo):
        resp = await client.post(_URL, json={})
    assert resp.status_code == 422
    assert resp.json()["error"] == "SEMANTIC_VALIDATION_FAILED"
    assert repo.added is None


async def test_model_unavailable_maps_to_503() -> None:
    async with _client(narrative_error=ModelUnavailable("down")) as (client, repo):
        resp = await client.post(_URL, json={})
    assert resp.status_code == 503
    assert resp.json()["error"] == "MODEL_UNAVAILABLE"


async def test_model_timeout_maps_to_504() -> None:
    async with _client(narrative_error=ModelTimeout("slow")) as (client, repo):
        resp = await client.post(_URL, json={})
    assert resp.status_code == 504
    assert resp.json()["error"] == "MODEL_TIMEOUT"
