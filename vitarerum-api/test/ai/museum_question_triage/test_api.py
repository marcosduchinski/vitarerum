import csv
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import StringIO

from httpx import ASGITransport, AsyncClient

from app.ai.museum_question_triage.domain.models import (
    ClassificationId,
    ClassificationOutcome,
    ClassificationQuality,
    ClassificationScoreSource,
    ClassificationStatus,
    ClassifierKind,
    MentionedObject,
    MessageClassification,
    MessageTriage,
    ObjectHitView,
    QuestionView,
    TriageClassification,
    TriageId,
    UseCategory,
    UseCategoryScore,
)
from app.ai.museum_question_triage.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
)
from app.ai.museum_question_triage.presentation import routes as triage_routes
from app.ai.museum_question_triage.presentation.dependencies import (
    get_classification_repository,
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


def _use_category_score() -> UseCategoryScore:
    return UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.91,
        source=ClassificationScoreSource.LLM,
    )


def _completed_classification(triage_id: TriageId) -> MessageClassification:
    score = _use_category_score()
    return MessageClassification(
        id=ClassificationId("classification-completed"),
        triage_id=triage_id,
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
        run_number=1,
        superseded_at=None,
        status=ClassificationStatus.COMPLETED,
        outcome=ClassificationOutcome.CATEGORIZED,
        quality=ClassificationQuality.FULL,
        category_scores=[score],
        assigned_categories=[score],
        error=None,
        metadata={},
        classified_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 10, 11, 59, tzinfo=UTC),
    )


def _failed_classification(triage_id: TriageId) -> MessageClassification:
    return MessageClassification(
        id=ClassificationId("classification-failed"),
        triage_id=triage_id,
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
        run_number=1,
        superseded_at=None,
        status=ClassificationStatus.FAILED,
        outcome=None,
        quality=None,
        category_scores=[],
        assigned_categories=[],
        error="model unavailable",
        metadata={},
        classified_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 7, 10, 11, 59, tzinfo=UTC),
    )


def _completed_embedding_classification(triage_id: TriageId) -> MessageClassification:
    score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.86,
        source=ClassificationScoreSource.EMBEDDING,
    )
    return MessageClassification(
        id=ClassificationId("classification-embedding-completed"),
        triage_id=triage_id,
        classifier_kind=ClassifierKind.EMBEDDING,
        classifier_model="nomic-embed-text",
        classifier_version="embedding-prototypes-v1",
        run_number=1,
        superseded_at=None,
        status=ClassificationStatus.COMPLETED,
        outcome=ClassificationOutcome.CATEGORIZED,
        quality=ClassificationQuality.FULL,
        category_scores=[score],
        assigned_categories=[score],
        error=None,
        metadata={
            "threshold_profile": "embedding-prototypes-v1",
            "would_escalate_due_to_length": False,
        },
        classified_at=datetime(2026, 7, 10, 12, 1, tzinfo=UTC),
        created_at=datetime(2026, 7, 10, 11, 59, tzinfo=UTC),
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

    async def classify_use_categories(self, message: str):
        raise AssertionError(
            "Background use-category classification is mocked in API tests"
        )


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

    async def get_by_id(self, triage_id: TriageId) -> MessageTriage | None:
        return next((triage for triage in self.stored if triage.id == triage_id), None)

    async def get_latest_by_question(self, question_id: str) -> MessageTriage | None:
        matches = [t for t in self.stored if t.question_id == question_id]
        matches.sort(key=lambda t: t.created_at, reverse=True)
        return matches[0] if matches else None

    async def list_latest(self, *, limit: int) -> list[MessageTriage]:
        matches = sorted(self.stored, key=lambda t: t.created_at, reverse=True)
        return matches[:limit]

    async def update(self, triage: MessageTriage) -> None:
        for index, existing in enumerate(self.stored):
            if existing.id == triage.id:
                self.stored[index] = triage
                return


class _FakeClassificationRepo:
    def __init__(
        self,
        events: list[tuple[str, str]] | None = None,
        stored: list[MessageClassification] | None = None,
    ) -> None:
        self.events = events
        self.stored: list[MessageClassification] = stored or []

    async def add(self, classification: MessageClassification) -> None:
        self.stored.append(classification)
        if self.events is not None:
            self.events.append(("pending", classification.id))

    async def get_by_id(
        self, classification_id: ClassificationId
    ) -> MessageClassification | None:
        return next(
            (
                classification
                for classification in self.stored
                if classification.id == classification_id
            ),
            None,
        )

    async def get_current_by_triage(
        self, triage_id: TriageId, classifier_kind: ClassifierKind
    ) -> MessageClassification | None:
        matches = [
            classification
            for classification in self.stored
            if classification.triage_id == triage_id
            and classification.classifier_kind is classifier_kind
            and classification.superseded_at is None
        ]
        matches.sort(key=lambda classification: classification.run_number, reverse=True)
        return matches[0] if matches else None

    async def list_current_by_triage(
        self, triage_id: TriageId
    ) -> list[MessageClassification]:
        return [
            classification
            for classification in self.stored
            if classification.triage_id == triage_id
            and classification.superseded_at is None
        ]

    async def supersede_current(
        self,
        triage_id: TriageId,
        classifier_kind: ClassifierKind,
        superseded_at: datetime,
    ) -> None:
        current = await self.get_current_by_triage(triage_id, classifier_kind)
        if current is None:
            return
        index = self.stored.index(current)
        self.stored[index] = MessageClassification(
            id=current.id,
            triage_id=current.triage_id,
            classifier_kind=current.classifier_kind,
            classifier_model=current.classifier_model,
            classifier_version=current.classifier_version,
            run_number=current.run_number,
            superseded_at=superseded_at,
            status=current.status,
            outcome=current.outcome,
            quality=current.quality,
            category_scores=list(current.category_scores),
            assigned_categories=list(current.assigned_categories),
            error=current.error,
            metadata=dict(current.metadata),
            classified_at=current.classified_at,
            created_at=current.created_at,
        )

    async def update(self, classification: MessageClassification) -> None:
        for index, existing in enumerate(self.stored):
            if existing.id == classification.id:
                self.stored[index] = classification
                return
        self.stored.append(classification)


class _FakeSession:
    def __init__(self, events: list[tuple[str, str]] | None = None) -> None:
        self.events = events

    async def commit(self) -> None:
        if self.events is not None:
            self.events.append(("commit", "session"))
        return None

    async def rollback(self) -> None:
        if self.events is not None:
            self.events.append(("rollback", "session"))
        return None


@asynccontextmanager
async def _client(
    *,
    caller: Actor = _STAFF,
    museum_question: _FakeMuseumQuestion | None = None,
    model: _FakeModel | None = None,
    object_search: _FakeObjectSearch | None = None,
    repo: _FakeRepo | None = None,
    classification_repo: _FakeClassificationRepo | None = None,
    events: list[tuple[str, str]] | None = None,
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_museum_question_port] = lambda: (
        museum_question or _FakeMuseumQuestion()
    )
    app.dependency_overrides[get_triage_model_port] = lambda: model or _FakeModel()
    app.dependency_overrides[get_object_search_port] = lambda: (
        object_search or _FakeObjectSearch()
    )
    app.dependency_overrides[get_triage_repository] = lambda: repo or _FakeRepo()
    app.dependency_overrides[get_classification_repository] = lambda: (
        classification_repo or _FakeClassificationRepo(events)
    )
    app.dependency_overrides[get_async_session] = lambda: _FakeSession(events)
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
    assert body["useCategoryClassification"] == {
        "status": "NOT_REQUESTED",
        "outcome": None,
        "quality": None,
        "classifierKind": None,
        "classifierModel": None,
        "classifierVersion": None,
        "assignedCategories": [],
        "categoryScores": [],
        "classifiedAt": None,
        "error": None,
    }


async def test_post_triage_creates_pending_classification_before_background(
    monkeypatch,
) -> None:
    events: list[tuple[str, str]] = []
    classification_repo = _FakeClassificationRepo(events)

    async def fake_background(classification_id: str) -> None:
        events.append(("background", classification_id))

    monkeypatch.setattr(
        triage_routes.settings, "use_category_classification_enabled", True
    )
    monkeypatch.setattr(
        triage_routes, "_classify_use_categories_background", fake_background
    )

    async with _client(
        classification_repo=classification_repo, events=events
    ) as client:
        resp = await client.post(_URL)

    assert resp.status_code == 200
    assert len(classification_repo.stored) == 1
    pending_id = classification_repo.stored[0].id
    assert events == [
        ("pending", pending_id),
        ("commit", "session"),
        ("background", pending_id),
    ]


async def test_post_triage_creates_embedding_shadow_classification(
    monkeypatch,
) -> None:
    events: list[tuple[str, str]] = []
    classification_repo = _FakeClassificationRepo(events)

    async def fake_llm_background(classification_id: str) -> None:
        events.append(("llm-background", classification_id))

    async def fake_embedding_background(classification_id: str) -> None:
        events.append(("embedding-background", classification_id))

    async def fake_cascade_background(classification_id: str) -> None:
        events.append(("cascade-background", classification_id))

    monkeypatch.setattr(
        triage_routes.settings, "use_category_classification_enabled", True
    )
    monkeypatch.setattr(
        triage_routes.settings, "use_category_embedding_shadow_enabled", True
    )
    monkeypatch.setattr(triage_routes.settings, "use_category_cascade_enabled", True)
    monkeypatch.setattr(
        triage_routes, "_classify_use_categories_background", fake_llm_background
    )
    monkeypatch.setattr(
        triage_routes,
        "_classify_embedding_use_categories_background",
        fake_embedding_background,
    )
    monkeypatch.setattr(
        triage_routes,
        "_classify_cascade_use_categories_background",
        fake_cascade_background,
    )

    async with _client(
        classification_repo=classification_repo, events=events
    ) as client:
        resp = await client.post(_URL)

    assert resp.status_code == 200
    assert [item.classifier_kind for item in classification_repo.stored] == [
        ClassifierKind.LLM,
        ClassifierKind.EMBEDDING,
        ClassifierKind.CASCADE,
    ]
    llm_id = classification_repo.stored[0].id
    embedding_id = classification_repo.stored[1].id
    cascade_id = classification_repo.stored[2].id
    assert events == [
        ("pending", llm_id),
        ("pending", embedding_id),
        ("pending", cascade_id),
        ("commit", "session"),
        ("llm-background", llm_id),
        ("embedding-background", embedding_id),
        ("cascade-background", cascade_id),
    ]


async def test_background_failure_marks_pending_classification_failed(
    monkeypatch,
) -> None:
    events: list[tuple[str, str]] = []
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.CASCADE,
        classifier_model="llama3.1:8b",
        classifier_version="cascade-use-category-v1",
    )
    classification_repo = _FakeClassificationRepo(events, stored=[pending])

    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[_FakeSession]:
        yield _FakeSession(events)

    monkeypatch.setattr(triage_routes, "async_session_factory", fake_session_factory)
    monkeypatch.setattr(
        triage_routes,
        "SqlAlchemyMessageClassificationRepository",
        lambda session: classification_repo,
    )

    await triage_routes._mark_background_classification_failed(
        pending.id, RuntimeError("classification exploded")
    )

    failed = classification_repo.stored[0]
    assert failed.status is ClassificationStatus.FAILED
    assert failed.error == "classification exploded"
    assert failed.classified_at is not None
    assert failed.category_scores == []
    assert failed.assigned_categories == []
    assert events == [("commit", "session")]


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
    assert body["effectiveVerdict"] == "IN_SCOPE"
    assert body["staffOverrideVerdict"] is None
    assert body["suggestedReply"] is None
    assert body["searchStrategy"]
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
            "languagesSearched": ["pt"],
        }
    ]
    assert body["mentionedObjects"] == [
        {"english": "Allende", "portuguese": "Allende", "origin": "AI"}
    ]


async def test_missing_question_is_404() -> None:
    async with _client(museum_question=_FakeMuseumQuestion(question=None)) as client:
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


async def test_get_returns_pending_use_category_classification() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        posted = (await client.post(_URL)).json()

    pending = MessageClassification.pending(
        triage_id=TriageId(posted["id"]),
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
    )
    classification_repo = _FakeClassificationRepo(stored=[pending])

    async with _client(repo=repo, classification_repo=classification_repo) as client:
        resp = await client.get(_URL)

    assert resp.status_code == 200
    assert resp.json()["useCategoryClassification"]["status"] == "PENDING"
    assert resp.json()["useCategoryClassification"]["classifierKind"] == "LLM"


async def test_get_returns_completed_use_category_classification() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        posted = (await client.post(_URL)).json()

    classification_repo = _FakeClassificationRepo(
        stored=[_completed_classification(TriageId(posted["id"]))]
    )

    async with _client(repo=repo, classification_repo=classification_repo) as client:
        resp = await client.get(_URL)

    assert resp.status_code == 200
    classification = resp.json()["useCategoryClassification"]
    assert classification["status"] == "COMPLETED"
    assert classification["outcome"] == "CATEGORIZED"
    assert classification["quality"] == "FULL"
    assert classification["assignedCategories"] == [
        {"category": "RESEARCH_PROJECTS", "confidence": 0.91, "source": "LLM"}
    ]
    assert classification["categoryScores"] == classification["assignedCategories"]


async def test_get_returns_failed_use_category_classification() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        posted = (await client.post(_URL)).json()

    classification_repo = _FakeClassificationRepo(
        stored=[_failed_classification(TriageId(posted["id"]))]
    )

    async with _client(repo=repo, classification_repo=classification_repo) as client:
        resp = await client.get(_URL)

    assert resp.status_code == 200
    classification = resp.json()["useCategoryClassification"]
    assert classification["status"] == "FAILED"
    assert classification["error"] == "model unavailable"
    assert classification["assignedCategories"] == []


async def test_list_triage_classifications_returns_current_classifier_runs() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        posted = (await client.post(_URL)).json()

    triage_id = TriageId(posted["id"])
    classification_repo = _FakeClassificationRepo(
        stored=[
            _completed_classification(triage_id),
            _completed_embedding_classification(triage_id),
        ]
    )

    async with _client(repo=repo, classification_repo=classification_repo) as client:
        resp = await client.get(f"{_URL}/classifications")

    assert resp.status_code == 200
    body = resp.json()
    assert body["triageId"] == posted["id"]
    assert [item["classifierKind"] for item in body["classifications"]] == [
        "LLM",
        "EMBEDDING",
    ]
    embedding = body["classifications"][1]
    assert embedding["id"] == "classification-embedding-completed"
    assert embedding["runNumber"] == 1
    assert embedding["metadata"]["threshold_profile"] == "embedding-prototypes-v1"
    assert embedding["assignedCategories"] == [
        {"category": "RESEARCH_PROJECTS", "confidence": 0.86, "source": "EMBEDDING"}
    ]


async def test_list_triage_classifications_requires_existing_triage() -> None:
    async with _client(repo=_FakeRepo()) as client:
        resp = await client.get(f"{_URL}/classifications")

    assert resp.status_code == 404
    assert resp.json()["error"] == "TRIAGE_NOT_FOUND"


async def test_sync_use_categories_creates_staff_reviewed_cascade() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        posted = (await client.post(_URL)).json()

    triage_id = TriageId(posted["id"])
    classification_repo = _FakeClassificationRepo(
        stored=[_completed_embedding_classification(triage_id)]
    )

    async with _client(repo=repo, classification_repo=classification_repo) as client:
        resp = await client.put(
            f"{_URL}/use-categories",
            json={"categories": ["ANSWERING_ENQUIRIES", "RESEARCH_PROJECTS"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["triageId"] == posted["id"]
    cascade = body["classifications"][-1]
    assert cascade["classifierKind"] == "CASCADE"
    assert cascade["classifierVersion"] == "staff-reviewed-v1"
    assert cascade["runNumber"] == 1
    assert cascade["outcome"] == "CATEGORIZED"
    assert cascade["metadata"]["staff_reviewed"] is True
    assert cascade["metadata"]["reviewed_by"] == _STAFF.email
    assert cascade["assignedCategories"] == [
        {"category": "ANSWERING_ENQUIRIES", "confidence": 1.0, "source": "LLM"},
        {"category": "RESEARCH_PROJECTS", "confidence": 1.0, "source": "LLM"},
    ]


async def test_sync_use_categories_can_mark_unclear() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        posted = (await client.post(_URL)).json()

    async with _client(repo=repo) as client:
        resp = await client.put(f"{_URL}/use-categories", json={"categories": []})

    assert resp.status_code == 200
    cascade = resp.json()["classifications"][0]
    assert cascade["triageId"] == posted["id"]
    assert cascade["classifierKind"] == "CASCADE"
    assert cascade["outcome"] == "UNCLEAR"
    assert cascade["assignedCategories"] == []


async def test_export_use_category_calibration_csv() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo) as client:
        posted = (await client.post(_URL)).json()

    triage_id = TriageId(posted["id"])
    classification_repo = _FakeClassificationRepo(
        stored=[
            _completed_classification(triage_id),
            _completed_embedding_classification(triage_id),
        ]
    )

    async with _client(repo=repo, classification_repo=classification_repo) as client:
        resp = await client.get(
            "/api/v1/museum-questions/triage/classifications/calibration.csv"
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(StringIO(resp.text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["triage_id"] == posted["id"]
    assert row["question_id"] == "q1"
    assert row["message_hash_sha256"]
    assert "RESEARCH_PROJECTS" in row["llm_assigned_categories"]
    assert "RESEARCH_PROJECTS" in row["embedding_assigned_categories"]
    assert _QUESTION.message not in resp.text
    assert _QUESTION.requester_email not in resp.text


async def test_get_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.get(_URL)
    assert resp.status_code == 403


_VERDICT_URL = "/api/v1/museum-questions/q1/triage/verdict"
_SEARCH_TERMS_URL = "/api/v1/museum-questions/q1/triage/search-terms"


async def test_override_verdict_flips_effective_verdict() -> None:
    repo = _FakeRepo()
    async with _client(
        repo=repo,
        model=_FakeModel(is_visit_related=True),
    ) as client:
        await client.post(_URL)
        resp = await client.patch(_VERDICT_URL, json={"verdict": "OUT_OF_SCOPE"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "IN_SCOPE"
    assert body["effectiveVerdict"] == "OUT_OF_SCOPE"
    assert body["staffOverrideVerdict"] == "OUT_OF_SCOPE"
    assert body["suggestedReply"]  # lazily drafted since it flipped OUT_OF_SCOPE


async def test_override_verdict_404_when_no_triage_yet() -> None:
    async with _client() as client:
        resp = await client.patch(_VERDICT_URL, json={"verdict": "OUT_OF_SCOPE"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "TRIAGE_NOT_FOUND"


async def test_override_verdict_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.patch(_VERDICT_URL, json={"verdict": "OUT_OF_SCOPE"})
    assert resp.status_code == 403


async def test_sync_search_terms_adds_and_searches() -> None:
    hit = ObjectHitView(
        collection_id="c1",
        collection_name="Zoology",
        file_name="zoology.xlsx",
        highlight="<b>Vulpes vulpes</b>",
    )
    repo = _FakeRepo()
    async with _client(
        repo=repo,
        model=_FakeModel(is_visit_related=True),
        object_search=_FakeObjectSearch({"Vulpes vulpes": [hit]}),
    ) as client:
        await client.post(_URL)
        resp = await client.put(
            _SEARCH_TERMS_URL,
            json={
                "terms": [{"english": "Vulpes vulpes", "portuguese": "Vulpes vulpes"}]
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mentionedObjects"] == [
        {"english": "Vulpes vulpes", "portuguese": "Vulpes vulpes", "origin": "STAFF"}
    ]
    assert body["objectMatches"][0]["hits"] == [
        {
            "collectionId": "c1",
            "collectionName": "Zoology",
            "fileName": "zoology.xlsx",
            "highlight": "<b>Vulpes vulpes</b>",
        }
    ]


async def test_sync_search_terms_409_when_out_of_scope() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo, model=_FakeModel(is_visit_related=False)) as client:
        await client.post(_URL)
        resp = await client.put(_SEARCH_TERMS_URL, json={"terms": []})

    assert resp.status_code == 409
    assert resp.json()["error"] == "TRIAGE_NOT_IN_SCOPE"


async def test_sync_search_terms_422_when_too_many_terms() -> None:
    repo = _FakeRepo()
    async with _client(repo=repo, model=_FakeModel(is_visit_related=True)) as client:
        await client.post(_URL)
        resp = await client.put(
            _SEARCH_TERMS_URL,
            json={
                "terms": [
                    {"english": f"term{i}", "portuguese": f"termo{i}"}
                    for i in range(11)
                ]
            },
        )

    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_SEARCH_TERMS"


async def test_sync_search_terms_404_when_no_triage_yet() -> None:
    async with _client() as client:
        resp = await client.put(_SEARCH_TERMS_URL, json={"terms": []})
    assert resp.status_code == 404
    assert resp.json()["error"] == "TRIAGE_NOT_FOUND"


async def test_sync_search_terms_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.put(_SEARCH_TERMS_URL, json={"terms": []})
    assert resp.status_code == 403
