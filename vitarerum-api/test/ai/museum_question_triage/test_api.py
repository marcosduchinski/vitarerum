from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.ai.museum_question_triage.domain.models import (
    MentionedObject,
    MessageTriage,
    ObjectHitView,
    QuestionView,
    TriageClassification,
)
from app.ai.museum_question_triage.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
)
from app.ai.museum_question_triage.presentation.dependencies import (
    get_museum_question_port,
    get_object_search_port,
    get_triage_model_port,
    get_triage_repository,
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

_QUESTION = QuestionView(
    id="q1",
    subject="Visit request",
    message="I would like to visit and study the meteorite collection.",
    requester_email="researcher@uni.pt",
    status="SUBMITTED",
)


class _FakeMuseumQuestion:
    def __init__(self, *, question: QuestionView | None = _QUESTION) -> None:
        self._question = question

    async def get_summary(self, question_id: str) -> QuestionView | None:
        return self._question


class _FakeModel:
    def __init__(
        self,
        *,
        is_visit_related: bool = True,
        mentioned_objects: list[MentionedObject] | None = None,
        reply: str = "This is out of scope.",
        error: Exception | None = None,
    ) -> None:
        self._is_visit_related = is_visit_related
        self._mentioned_objects = mentioned_objects or []
        self._reply = reply
        self._error = error

    async def classify(self, message: str) -> TriageClassification:
        if self._error is not None:
            raise self._error
        return TriageClassification(
            is_visit_related=self._is_visit_related,
            mentioned_objects=self._mentioned_objects,
        )

    async def draft_out_of_scope_reply(self, message: str) -> str:
        return self._reply


class _FakeObjectSearch:
    def __init__(
        self, hits_by_query: dict[str, list[ObjectHitView]] | None = None
    ) -> None:
        self._hits_by_query = hits_by_query or {}

    async def search(
        self, caller: Actor, query: str, limit: int
    ) -> list[ObjectHitView]:
        return self._hits_by_query.get(query, [])


class _FakeRepo:
    def __init__(self) -> None:
        self.stored: list[MessageTriage] = []

    async def add(self, triage: MessageTriage) -> None:
        self.stored.append(triage)

    async def get_latest_by_question(
        self, question_id: str
    ) -> MessageTriage | None:
        matches = [t for t in self.stored if t.question_id == question_id]
        matches.sort(key=lambda t: t.created_at, reverse=True)
        return matches[0] if matches else None


class _FakeSession:
    async def commit(self) -> None:
        return None


@asynccontextmanager
async def _client(
    *,
    caller: Actor = _STAFF,
    museum_question: _FakeMuseumQuestion | None = None,
    model: _FakeModel | None = None,
    object_search: _FakeObjectSearch | None = None,
    repo: _FakeRepo | None = None,
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_museum_question_port] = (
        lambda: museum_question or _FakeMuseumQuestion()
    )
    app.dependency_overrides[get_triage_model_port] = lambda: model or _FakeModel()
    app.dependency_overrides[get_object_search_port] = (
        lambda: object_search or _FakeObjectSearch()
    )
    app.dependency_overrides[get_triage_repository] = lambda: repo or _FakeRepo()
    app.dependency_overrides[get_async_session] = lambda: _FakeSession()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


_URL = "/api/v1/museum-questions/q1/triage"


async def test_out_of_scope_returns_suggested_reply() -> None:
    async with _client(model=_FakeModel(is_visit_related=False)) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "OUT_OF_SCOPE"
    assert body["suggestedReply"] == "This is out of scope."
    assert body["objectMatches"] == []


async def test_in_scope_with_object_returns_search_hits() -> None:
    hit = ObjectHitView(
        collection_id="c1",
        collection_name="Meteorites",
        file_name="rows.xlsx",
        highlight="<b>Allende</b>",
    )
    async with _client(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english="Allende", portuguese="Allende")
            ],
        ),
        object_search=_FakeObjectSearch({"Allende": [hit]}),
    ) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "IN_SCOPE"
    assert body["suggestedReply"] is None
    assert body["objectMatches"] == [
        {
            "english": "Allende",
            "portuguese": "Allende",
            "hits": [
                {
                    "collectionId": "c1",
                    "collectionName": "Meteorites",
                    "fileName": "rows.xlsx",
                    "highlight": "<b>Allende</b>",
                }
            ],
        }
    ]


async def test_missing_question_is_404() -> None:
    async with _client(
        museum_question=_FakeMuseumQuestion(question=None)
    ) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 404
    assert resp.json()["error"] == "MUSEUM_QUESTION_NOT_FOUND"


async def test_model_unavailable_is_503() -> None:
    async with _client(model=_FakeModel(error=ModelUnavailable("down"))) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 503
    assert resp.json()["error"] == "MODEL_UNAVAILABLE"


async def test_model_timeout_is_504() -> None:
    async with _client(model=_FakeModel(error=ModelTimeout("slow"))) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 504
    assert resp.json()["error"] == "MODEL_TIMEOUT"


async def test_external_caller_is_403() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.post(_URL)
    assert resp.status_code == 403


async def test_get_returns_404_when_never_run() -> None:
    async with _client() as client:
        resp = await client.get(_URL)
    assert resp.status_code == 404
    assert resp.json()["error"] == "TRIAGE_NOT_FOUND"


async def test_get_returns_latest_stored_triage() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        posted = (await client.post(_URL)).json()
        resp = await client.get(_URL)
    assert resp.status_code == 200
    assert resp.json()["id"] == posted["id"]


async def test_get_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.get(_URL)
    assert resp.status_code == 403
