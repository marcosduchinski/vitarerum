from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.ai.museum_narrative.domain.facts import (
    CanonicalVisitFacts,
    MissingFact,
    PersonFact,
)
from app.ai.museum_narrative.domain.models import (
    GeneratedNarrative,
    GeneratedNarrativeRevision,
    NarrativeFactSnapshot,
    NarrativeFactSnapshotId,
    NarrativeId,
)
from app.ai.museum_narrative.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
    RecordNotFound,
    SemanticValidationFailed,
)
from app.ai.museum_narrative.presentation.dependencies import (
    get_facts_port,
    get_model_port,
    get_narrative_repository,
)
from app.database import get_async_session
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="r@uni.pt"
)


class _FakeFacts:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    async def prepare(self, record_id: str) -> CanonicalVisitFacts:
        if self._error is not None:
            raise self._error
        return CanonicalVisitFacts(
            report_subject="In-situ visit CUP-1",
            project_reference="CUP-1",
            project_title=None,
            project_purpose=None,
            planned_begin_date=None,
            planned_end_date=None,
            requester=PersonFact(name="Dr. Ana Ribeiro"),
            approval=MissingFact(reason="No approval was recorded."),
            execution=MissingFact(reason="No execution evidence was recorded."),
            source_snapshot_id=record_id,
            source_version="2",
        )


class _FakeModel:
    def __init__(self, *, text: str = "narrative text", error=None) -> None:
        self._text = text
        self._error = error

    async def generate(self, *, system_prompt, user_prompt, temperature) -> str:
        if self._error is not None:
            raise self._error
        return self._text


class _FakeRepo:
    def __init__(self) -> None:
        self.stored: list[GeneratedNarrative] = []
        self.snapshots: list[NarrativeFactSnapshot] = []
        self.revisions: list[GeneratedNarrativeRevision] = []

    async def add_facts_snapshot(self, snapshot: NarrativeFactSnapshot) -> None:
        self.snapshots.append(snapshot)

    async def get_facts_snapshot(
        self, snapshot_id: NarrativeFactSnapshotId
    ) -> NarrativeFactSnapshot | None:
        return next((s for s in self.snapshots if s.id == snapshot_id), None)

    async def add(self, narrative: GeneratedNarrative) -> None:
        self.stored.append(narrative)

    async def save(self, narrative: GeneratedNarrative) -> None:
        self.stored = [narrative if n.id == narrative.id else n for n in self.stored]

    async def add_revision(self, revision: GeneratedNarrativeRevision) -> None:
        self.revisions.append(revision)

    async def get_by_id(
        self, narrative_id: NarrativeId
    ) -> GeneratedNarrative | None:
        return next((n for n in self.stored if n.id == narrative_id), None)

    async def list_by_record(
        self, record_id: str, page: int, size: int
    ) -> tuple[list[GeneratedNarrative], int]:
        matches = [n for n in self.stored if n.record_id == record_id]
        matches.sort(key=lambda n: n.generated_at, reverse=True)
        total = len(matches)
        return matches[page * size : page * size + size], total


class _FakeSession:
    async def commit(self) -> None:
        return None


@asynccontextmanager
async def _client(
    *, caller: Actor = _STAFF, facts=None, model=None, repo: _FakeRepo | None = None
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_facts_port] = lambda: facts or _FakeFacts()
    app.dependency_overrides[get_model_port] = lambda: model or _FakeModel()
    app.dependency_overrides[get_narrative_repository] = lambda: repo or _FakeRepo()
    app.dependency_overrides[get_async_session] = lambda: _FakeSession()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


_URL = "/api/v1/cidoc-mapping/in-situ-visit/r1/narrative"


async def test_default_type_returns_institutional() -> None:
    async with _client() as client:
        resp = await client.post(_URL, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["record_id"] == "r1"
    assert body["meta"]["resolved_narrative_type"] == "institutional"
    assert body["meta"]["resolution_source"] == "default"
    assert body["meta"]["facts_snapshot_id"]
    assert body["meta"]["prompt_version"]
    assert body["meta"]["model_response_hash"]
    assert body["meta"]["validation_conforms"] is True
    assert body["meta"]["validation_findings"] == []
    assert body["facts_snapshot"]["id"] == body["meta"]["facts_snapshot_id"]
    assert "CUP-1" in body["facts_snapshot"]["payload_json"]
    assert body["data"]["narrative"] == "narrative text"


async def test_explicit_type_echoed_in_meta() -> None:
    async with _client() as client:
        resp = await client.post(_URL, json={"narrative_type": "social_media"})
    assert resp.status_code == 200
    assert resp.json()["meta"]["resolved_narrative_type"] == "social_media"
    assert resp.json()["meta"]["resolution_source"] == "request_body"


async def test_invalid_type_is_400() -> None:
    async with _client() as client:
        resp = await client.post(_URL, json={"narrative_type": "marketing_sales"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_NARRATIVE_TYPE"


async def test_temperature_above_one_is_422() -> None:
    async with _client() as client:
        resp = await client.post(_URL, json={"creativity_temperature": 1.01})
    assert resp.status_code == 422


async def test_missing_record_is_404() -> None:
    facts = _FakeFacts(error=RecordNotFound("nope"))
    async with _client(facts=facts) as client:
        resp = await client.post(_URL, json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "IN_SITU_VISIT_NOT_FOUND"


async def test_semantic_failure_is_422() -> None:
    facts = _FakeFacts(error=SemanticValidationFailed("bad graph"))
    async with _client(facts=facts) as client:
        resp = await client.post(_URL, json={})
    assert resp.status_code == 422
    assert resp.json()["error"] == "SEMANTIC_VALIDATION_FAILED"


async def test_model_unavailable_is_503() -> None:
    model = _FakeModel(error=ModelUnavailable("down"))
    async with _client(model=model) as client:
        resp = await client.post(_URL, json={})
    assert resp.status_code == 503
    assert resp.json()["error"] == "MODEL_UNAVAILABLE"


async def test_model_timeout_is_504() -> None:
    model = _FakeModel(error=ModelTimeout("slow"))
    async with _client(model=model) as client:
        resp = await client.post(_URL, json={})
    assert resp.status_code == 504
    assert resp.json()["error"] == "MODEL_TIMEOUT"


async def test_external_caller_is_403() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.post(_URL, json={})
    assert resp.status_code == 403


# ── persistence ──────────────────────────────────────────────────────────────-

_LIST_URL = "/api/v1/cidoc-mapping/in-situ-visit/r1/narratives"


async def test_post_persists_and_returns_identifiers() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        resp = await client.post(_URL, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["narrative_id"]
    assert body["generated_at"]
    assert len(repo.stored) == 1
    assert repo.stored[0].id == body["narrative_id"]


async def test_listed_newest_first_after_two_generations() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        await client.post(_URL, json={"narrative_type": "institutional"})
        await client.post(_URL, json={"narrative_type": "social_media"})
        resp = await client.get(_LIST_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_elements"] == 2
    # newest first
    assert body["content"][0]["meta"]["resolved_narrative_type"] == "social_media"


async def test_get_stored_narrative_by_id() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        created = (await client.post(_URL, json={})).json()
        narrative_id = created["narrative_id"]
        resp = await client.get(f"{_LIST_URL}/{narrative_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["narrative_id"] == narrative_id
    assert body["data"]["narrative"] == "narrative text"
    assert body["facts_snapshot"]["id"] == created["facts_snapshot"]["id"]
    assert (
        body["facts_snapshot"]["payload_json"]
        == created["facts_snapshot"]["payload_json"]
    )


async def test_get_unknown_narrative_is_404() -> None:
    async with _client() as client:
        resp = await client.get(f"{_LIST_URL}/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"] == "NARRATIVE_NOT_FOUND"


async def test_list_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.get(_LIST_URL)
    assert resp.status_code == 403


async def test_patch_updates_narrative_text() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        narrative_id = (await client.post(_URL, json={})).json()["narrative_id"]
        resp = await client.patch(
            f"{_LIST_URL}/{narrative_id}", json={"narrative": "edited text"}
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["narrative"] == "edited text"
    assert repo.stored[0].narrative == "edited text"
    assert repo.revisions[0].previous_narrative == "narrative text"
    assert repo.revisions[0].revised_narrative == "edited text"


async def test_patch_unknown_narrative_is_404() -> None:
    async with _client() as client:
        resp = await client.patch(
            f"{_LIST_URL}/does-not-exist", json={"narrative": "x"}
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "NARRATIVE_NOT_FOUND"


async def test_get_under_wrong_record_is_404() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        narrative_id = (await client.post(_URL, json={})).json()["narrative_id"]
        # same narrative id, but addressed under a different visit record
        resp = await client.get(
            f"/api/v1/cidoc-mapping/in-situ-visit/other/narratives/{narrative_id}"
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "NARRATIVE_NOT_FOUND"


async def test_patch_under_wrong_record_is_404() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        narrative_id = (await client.post(_URL, json={})).json()["narrative_id"]
        resp = await client.patch(
            f"/api/v1/cidoc-mapping/in-situ-visit/other/narratives/{narrative_id}",
            json={"narrative": "edited"},
        )
    assert resp.status_code == 404
    assert repo.stored[0].narrative != "edited"


async def test_patch_empty_narrative_is_422() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        narrative_id = (await client.post(_URL, json={})).json()["narrative_id"]
        resp = await client.patch(
            f"{_LIST_URL}/{narrative_id}", json={"narrative": ""}
        )
    assert resp.status_code == 422


async def test_patch_whitespace_narrative_is_422() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        narrative_id = (await client.post(_URL, json={})).json()["narrative_id"]
        resp = await client.patch(
            f"{_LIST_URL}/{narrative_id}", json={"narrative": "   "}
        )
    assert resp.status_code == 422
    assert repo.stored[0].narrative == "narrative text"  # unchanged


async def test_blank_model_output_is_503() -> None:
    async with _client(model=_FakeModel(text="   ")) as client:
        resp = await client.post(_URL, json={})
    assert resp.status_code == 503
    assert resp.json()["error"] == "MODEL_UNAVAILABLE"


async def test_patch_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.patch(
            f"{_LIST_URL}/whatever", json={"narrative": "x"}
        )
    assert resp.status_code == 403
