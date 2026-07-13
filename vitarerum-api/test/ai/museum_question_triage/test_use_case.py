import csv
import hashlib
from datetime import UTC, datetime
from io import StringIO

import pytest

from app.ai.museum_question_triage.application.embedding_classifier import (
    EmbeddingClassificationResult,
)
from app.ai.museum_question_triage.application.use_cases import (
    MAX_STAFF_SEARCH_TERMS,
    SEARCH_FETCH_LIMIT_PER_LANGUAGE,
    ClassifyPendingCascadeUseCategory,
    ClassifyPendingCascadeUseCategoryInput,
    ClassifyPendingEmbeddingUseCategory,
    ClassifyPendingEmbeddingUseCategoryInput,
    ClassifyPendingUseCategory,
    ClassifyPendingUseCategoryInput,
    CreatePendingCascadeUseCategoryClassification,
    CreatePendingCascadeUseCategoryClassificationInput,
    CreatePendingEmbeddingUseCategoryClassification,
    CreatePendingEmbeddingUseCategoryClassificationInput,
    CreatePendingUseCategoryClassification,
    CreatePendingUseCategoryClassificationInput,
    ExportUseCategoryCalibrationCsv,
    ExportUseCategoryCalibrationInput,
    GenerateEmbeddingPrototypeVersion,
    GenerateEmbeddingPrototypeVersionInput,
    GetLatestTriage,
    GetLatestTriageInput,
    NotEnoughTrainingExamples,
    OverrideTriageVerdict,
    OverrideTriageVerdictInput,
    SyncTriageSearchTerms,
    SyncTriageSearchTermsInput,
    SyncUseCategories,
    SyncUseCategoriesInput,
    TriageMuseumQuestion,
    TriageMuseumQuestionInput,
)
from app.ai.museum_question_triage.domain.models import (
    ClassificationId,
    ClassificationOutcome,
    ClassificationQuality,
    ClassificationScoreSource,
    ClassificationStatus,
    ClassifierKind,
    EmbeddingPrototypeAggregation,
    EmbeddingPrototypeVersion,
    HumanCategoryOutcome,
    MentionedObject,
    MentionedObjectOrigin,
    MessageClassification,
    MessageTriage,
    ObjectHitView,
    ObjectTriageMatch,
    QuestionView,
    TrainingExampleId,
    TrainingExampleSource,
    TriageClassification,
    TriageId,
    TriageVerdict,
    UseCategory,
    UseCategoryClassification,
    UseCategoryScore,
    UseCategoryTrainingExample,
)
from app.ai.museum_question_triage.domain.ports import (
    ModelUnavailable,
    QuestionNotFound,
    TriageNotFound,
    TriageNotInScope,
    TriageTermValidationError,
)
from app.identity.public import Actor, GroupName, PermissionId

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)

_QUESTION = QuestionView(
    id="q1",
    subject="Visit request",
    message="I would like to visit and study the meteorite collection.",
    requester_email="researcher@uni.pt",
    status="SUBMITTED",
)


class _FakeMuseumQuestion:
    def __init__(self, question: QuestionView | None = _QUESTION) -> None:
        self._question = question

    async def get_summary(self, question_id: str) -> QuestionView | None:
        return self._question


class _FakeModel:
    def __init__(
        self,
        *,
        is_visit_related: bool = True,
        mentioned_objects: list[MentionedObject] | None = None,
        reply: str = "Thanks, but this is out of scope.",
        classify_error: Exception | None = None,
        use_category_error: Exception | None = None,
        use_category_result: UseCategoryClassification | None = None,
    ) -> None:
        self._is_visit_related = is_visit_related
        self._mentioned_objects = mentioned_objects or []
        self._reply = reply
        self._classify_error = classify_error
        self._use_category_error = use_category_error
        self._use_category_result = use_category_result
        self.classify_calls: list[str] = []
        self.use_category_calls: list[str] = []
        self.reply_calls: list[str] = []

    async def classify(self, message: str) -> TriageClassification:
        self.classify_calls.append(message)
        if self._classify_error is not None:
            raise self._classify_error
        return TriageClassification(
            is_visit_related=self._is_visit_related,
            mentioned_objects=self._mentioned_objects,
        )

    async def draft_out_of_scope_reply(self, message: str) -> str:
        self.reply_calls.append(message)
        return self._reply

    async def classify_use_categories(self, message: str) -> UseCategoryClassification:
        self.use_category_calls.append(message)
        if self._use_category_error is not None:
            raise self._use_category_error
        if self._use_category_result is not None:
            return self._use_category_result
        score = UseCategoryScore(
            category=UseCategory.RESEARCH_PROJECTS,
            confidence=0.91,
            source=ClassificationScoreSource.LLM,
        )
        return UseCategoryClassification(
            outcome=ClassificationOutcome.CATEGORIZED,
            category_scores=[score],
            assigned_categories=[score],
        )


class _FakeEmbeddingClassifier:
    def __init__(
        self,
        error: Exception | None = None,
        *,
        scores: list[UseCategoryScore] | None = None,
        assigned: list[UseCategoryScore] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._error = error
        default_score = UseCategoryScore(
            category=UseCategory.RESEARCH_PROJECTS,
            confidence=0.86,
            source=ClassificationScoreSource.EMBEDDING,
        )
        self._scores = scores or [default_score]
        self._assigned = assigned if assigned is not None else [default_score]
        self._metadata = metadata or {
            "threshold_profile": "embedding-test",
            "would_escalate_due_to_length": False,
        }
        self.calls: list[str] = []

    async def classify(self, message: str) -> EmbeddingClassificationResult:
        self.calls.append(message)
        if self._error is not None:
            raise self._error
        outcome = (
            ClassificationOutcome.CATEGORIZED
            if self._assigned
            else ClassificationOutcome.UNCLEAR
        )
        return EmbeddingClassificationResult(
            classification=UseCategoryClassification(
                outcome=outcome,
                category_scores=list(self._scores),
                assigned_categories=list(self._assigned),
            ),
            metadata=dict(self._metadata),
        )


class _FakeEmbedding:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[list[str]] = []

    async def embed(self, text: str) -> list[float]:
        return self._vectors[text]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self._vectors[text] for text in texts]


class _FakeObjectSearch:
    def __init__(
        self, hits_by_query: dict[str, list[ObjectHitView]] | None = None
    ) -> None:
        self._hits_by_query = hits_by_query or {}
        self.calls: list[tuple[Actor, str, int]] = []

    async def search(
        self, caller: Actor, query: str, limit: int
    ) -> list[ObjectHitView]:
        self.calls.append((caller, query, limit))
        return self._hits_by_query.get(query, [])


class _FakeRepo:
    def __init__(self) -> None:
        self.stored: list[MessageTriage] = []
        self.update_calls: list[MessageTriage] = []

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
        self.update_calls.append(triage)


class _FakeClassificationRepo:
    def __init__(self) -> None:
        self.stored: list[MessageClassification] = []
        self.update_calls: list[MessageClassification] = []
        self.supersede_calls: list[tuple[TriageId, ClassifierKind, datetime]] = []

    async def add(self, classification: MessageClassification) -> None:
        self.stored.append(classification)

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
        self.supersede_calls.append((triage_id, classifier_kind, superseded_at))
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
        self.update_calls.append(classification)
        for index, existing in enumerate(self.stored):
            if existing.id == classification.id:
                self.stored[index] = classification
                return


class _FakeTrainingExampleRepo:
    def __init__(self) -> None:
        self.stored: list[UseCategoryTrainingExample] = []
        self.supersede_calls: list[tuple[TriageId, datetime, TrainingExampleId]] = []

    async def add(self, example: UseCategoryTrainingExample) -> None:
        self.stored.append(example)

    async def get_current_by_triage(
        self, triage_id: TriageId
    ) -> UseCategoryTrainingExample | None:
        matches = [
            example
            for example in self.stored
            if example.triage_id == triage_id and example.superseded_at is None
        ]
        matches.sort(key=lambda example: example.run_number, reverse=True)
        return matches[0] if matches else None

    async def supersede_current(
        self,
        triage_id: TriageId,
        superseded_at: datetime,
        superseded_by_example_id: TrainingExampleId,
    ) -> None:
        self.supersede_calls.append(
            (triage_id, superseded_at, superseded_by_example_id)
        )
        current = await self.get_current_by_triage(triage_id)
        if current is None:
            return
        index = self.stored.index(current)
        self.stored[index] = UseCategoryTrainingExample(
            id=current.id,
            triage_id=current.triage_id,
            question_id=current.question_id,
            run_number=current.run_number,
            superseded_at=superseded_at,
            superseded_by_example_id=superseded_by_example_id,
            human_outcome=current.human_outcome,
            human_categories=list(current.human_categories),
            llm_categories=list(current.llm_categories),
            embedding_categories=list(current.embedding_categories),
            source=current.source,
            reviewed_by=current.reviewed_by,
            reviewed_at=current.reviewed_at,
            message_hash=current.message_hash,
            active=current.active,
            notes=current.notes,
            created_at=current.created_at,
        )

    async def list_active_current(self) -> list[UseCategoryTrainingExample]:
        return [
            example
            for example in self.stored
            if example.active and example.superseded_at is None
        ]


class _FakePrototypeVersionRepo:
    def __init__(self) -> None:
        self.stored: list[EmbeddingPrototypeVersion] = []
        self.promote_calls: list[tuple[str, datetime]] = []

    async def add(self, version: EmbeddingPrototypeVersion) -> None:
        self.stored.append(version)

    async def get_by_version(
        self, version: str
    ) -> EmbeddingPrototypeVersion | None:
        return next(
            (item for item in self.stored if item.version == version),
            None,
        )

    async def get_promoted(self) -> EmbeddingPrototypeVersion | None:
        return next(
            (
                item
                for item in self.stored
                if item.promoted_at is not None and item.retired_at is None
            ),
            None,
        )

    async def list(self) -> list[EmbeddingPrototypeVersion]:
        return list(self.stored)

    async def promote(self, version: str, promoted_at: datetime) -> None:
        self.promote_calls.append((version, promoted_at))
        for item in self.stored:
            if item.promoted_at is not None and item.retired_at is None:
                item.retired_at = promoted_at
            if item.version == version:
                item.promoted_at = promoted_at
                item.retired_at = None


class _FailingTrainingExampleRepo(_FakeTrainingExampleRepo):
    async def add(self, example: UseCategoryTrainingExample) -> None:
        raise RuntimeError("training example store failed")


def _use_case(
    *,
    museum_question: _FakeMuseumQuestion | None = None,
    model: _FakeModel | None = None,
    object_search: _FakeObjectSearch | None = None,
    repo: _FakeRepo | None = None,
) -> tuple[TriageMuseumQuestion, _FakeModel, _FakeObjectSearch, _FakeRepo]:
    mq = museum_question or _FakeMuseumQuestion()
    model_ = model or _FakeModel()
    search = object_search or _FakeObjectSearch()
    repository = repo or _FakeRepo()
    return (
        TriageMuseumQuestion(mq, model_, search, repository, "llama3.1:8b"),
        model_,
        search,
        repository,
    )


def _stored_use_category_triage(question_id: str = "q1") -> MessageTriage:
    return MessageTriage(
        id=TriageId("triage-1"),
        question_id=question_id,
        verdict=TriageVerdict.IN_SCOPE,
        is_visit_related=True,
        mentioned_objects=[],
        object_matches=[],
        suggested_reply=None,
        llm_model="llama3.1:8b",
        created_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
    )


def _training_example(
    *,
    id_: str = "example-1",
    question_id: str = "q1",
    categories: list[UseCategory] | None = None,
    outcome: HumanCategoryOutcome = HumanCategoryOutcome.CATEGORIZED,
    message: str = _QUESTION.message,
) -> UseCategoryTrainingExample:
    human_categories = (
        [UseCategory.RESEARCH_PROJECTS] if categories is None else categories
    )
    return UseCategoryTrainingExample.create(
        triage_id=TriageId(f"triage-{id_}"),
        question_id=question_id,
        run_number=1,
        human_outcome=outcome,
        human_categories=human_categories,
        llm_categories=[],
        embedding_categories=[],
        source=TrainingExampleSource.HUMAN_CREATED,
        reviewed_by=_STAFF.email,
        reviewed_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
        message_hash=(
            "unclear-hash"
            if outcome is HumanCategoryOutcome.UNCLEAR
            else hashlib.sha256(
                " ".join(message.strip().casefold().split()).encode("utf-8")
            ).hexdigest()
        ),
    )


async def test_create_pending_use_category_classification() -> None:
    repo = _FakeClassificationRepo()
    use_case = CreatePendingUseCategoryClassification(repo, "llama3.1:8b")

    result = await use_case.execute(
        CreatePendingUseCategoryClassificationInput(triage_id="triage-1")
    )

    assert result.status is ClassificationStatus.PENDING
    assert result.triage_id == "triage-1"
    assert result.classifier_kind is ClassifierKind.LLM
    assert result.classifier_model == "llama3.1:8b"
    assert result.classifier_version == "llm-use-category-v1"
    assert result.run_number == 1
    assert repo.stored == [result]


async def test_create_pending_supersedes_current_line_and_increments_run() -> None:
    repo = _FakeClassificationRepo()
    current = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
    )
    repo.stored.append(current)
    use_case = CreatePendingUseCategoryClassification(repo, "llama3.1:8b")

    result = await use_case.execute(
        CreatePendingUseCategoryClassificationInput(triage_id="triage-1")
    )

    assert result.run_number == 2
    assert repo.stored[0].superseded_at is not None
    assert repo.stored[1] == result


async def test_classify_pending_use_category_completes_classification() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
    )
    classification_repo.stored.append(pending)
    model = _FakeModel()
    use_case = ClassifyPendingUseCategory(
        _FakeMuseumQuestion(), model, triage_repo, classification_repo
    )

    result = await use_case.execute(
        ClassifyPendingUseCategoryInput(classification_id=pending.id)
    )

    assert result.status is ClassificationStatus.COMPLETED
    assert result.outcome is ClassificationOutcome.CATEGORIZED
    assert result.quality is ClassificationQuality.FULL
    assert result.assigned_categories[0].category is UseCategory.RESEARCH_PROJECTS
    assert result.error is None
    assert result.classified_at is not None
    assert model.use_category_calls == [_QUESTION.message]
    assert classification_repo.update_calls == [result]


async def test_classify_pending_use_category_marks_model_failure() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
    )
    classification_repo.stored.append(pending)
    use_case = ClassifyPendingUseCategory(
        _FakeMuseumQuestion(),
        _FakeModel(use_category_error=ModelUnavailable("down")),
        triage_repo,
        classification_repo,
    )

    result = await use_case.execute(
        ClassifyPendingUseCategoryInput(classification_id=pending.id)
    )

    assert result.status is ClassificationStatus.FAILED
    assert result.outcome is None
    assert result.quality is None
    assert result.error == "down"
    assert result.classified_at is not None
    assert classification_repo.update_calls == [result]


async def test_create_pending_embedding_use_category_classification() -> None:
    repo = _FakeClassificationRepo()
    use_case = CreatePendingEmbeddingUseCategoryClassification(
        repo, "nomic-embed-text", "embedding-test"
    )

    result = await use_case.execute(
        CreatePendingEmbeddingUseCategoryClassificationInput(triage_id="triage-1")
    )

    assert result.status is ClassificationStatus.PENDING
    assert result.triage_id == "triage-1"
    assert result.classifier_kind is ClassifierKind.EMBEDDING
    assert result.classifier_model == "nomic-embed-text"
    assert result.classifier_version == "embedding-test"
    assert result.run_number == 1
    assert repo.stored == [result]


async def test_classify_pending_embedding_completes_classification() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.EMBEDDING,
        classifier_model="nomic-embed-text",
        classifier_version="embedding-test",
    )
    classification_repo.stored.append(pending)
    classifier = _FakeEmbeddingClassifier()
    use_case = ClassifyPendingEmbeddingUseCategory(
        _FakeMuseumQuestion(), classifier, triage_repo, classification_repo
    )

    result = await use_case.execute(
        ClassifyPendingEmbeddingUseCategoryInput(classification_id=pending.id)
    )

    assert result.status is ClassificationStatus.COMPLETED
    assert result.outcome is ClassificationOutcome.CATEGORIZED
    assert result.quality is ClassificationQuality.FULL
    assert result.assigned_categories[0].source is ClassificationScoreSource.EMBEDDING
    assert result.metadata["threshold_profile"] == "embedding-test"
    assert classifier.calls == [_QUESTION.message]
    assert classification_repo.update_calls == [result]


async def test_classify_pending_embedding_use_category_marks_model_failure() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.EMBEDDING,
        classifier_model="nomic-embed-text",
        classifier_version="embedding-test",
    )
    classification_repo.stored.append(pending)
    use_case = ClassifyPendingEmbeddingUseCategory(
        _FakeMuseumQuestion(),
        _FakeEmbeddingClassifier(error=ModelUnavailable("embedding down")),
        triage_repo,
        classification_repo,
    )

    result = await use_case.execute(
        ClassifyPendingEmbeddingUseCategoryInput(classification_id=pending.id)
    )

    assert result.status is ClassificationStatus.FAILED
    assert result.outcome is None
    assert result.error == "embedding down"
    assert result.classified_at is not None
    assert classification_repo.update_calls == [result]


async def test_create_pending_cascade_use_category_classification() -> None:
    repo = _FakeClassificationRepo()
    use_case = CreatePendingCascadeUseCategoryClassification(
        repo, "nomic-embed-text", "cascade-test"
    )

    result = await use_case.execute(
        CreatePendingCascadeUseCategoryClassificationInput(triage_id="triage-1")
    )

    assert result.status is ClassificationStatus.PENDING
    assert result.triage_id == "triage-1"
    assert result.classifier_kind is ClassifierKind.CASCADE
    assert result.classifier_model == "nomic-embed-text"
    assert result.classifier_version == "cascade-test"
    assert result.run_number == 1
    assert repo.stored == [result]


async def test_classify_pending_cascade_uses_embedding_when_confident() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.CASCADE,
        classifier_model="nomic-embed-text",
        classifier_version="cascade-test",
    )
    classification_repo.stored.append(pending)
    embedding = _FakeEmbeddingClassifier()
    model = _FakeModel()
    use_case = ClassifyPendingCascadeUseCategory(
        _FakeMuseumQuestion(),
        embedding,
        model,
        triage_repo,
        classification_repo,
        high_threshold=0.74,
        margin_delta=0.08,
    )

    result = await use_case.execute(
        ClassifyPendingCascadeUseCategoryInput(classification_id=pending.id)
    )

    assert result.status is ClassificationStatus.COMPLETED
    assert result.quality is ClassificationQuality.FULL
    assert result.assigned_categories[0].source is ClassificationScoreSource.EMBEDDING
    assert result.metadata["tier2_llm_used"] is False
    assert result.metadata["escalation_reasons"] == []
    assert embedding.calls == [_QUESTION.message]
    assert model.use_category_calls == []


async def test_classify_pending_cascade_escalates_low_confidence_to_llm() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.CASCADE,
        classifier_model="nomic-embed-text",
        classifier_version="cascade-test",
    )
    classification_repo.stored.append(pending)
    low_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.62,
        source=ClassificationScoreSource.EMBEDDING,
    )
    embedding = _FakeEmbeddingClassifier(scores=[low_score], assigned=[])
    model = _FakeModel()
    use_case = ClassifyPendingCascadeUseCategory(
        _FakeMuseumQuestion(),
        embedding,
        model,
        triage_repo,
        classification_repo,
        high_threshold=0.74,
        margin_delta=0.08,
    )

    result = await use_case.execute(
        ClassifyPendingCascadeUseCategoryInput(classification_id=pending.id)
    )

    assert result.status is ClassificationStatus.COMPLETED
    assert result.quality is ClassificationQuality.FULL
    assert result.assigned_categories[0].source is ClassificationScoreSource.LLM
    assert result.metadata["tier2_llm_used"] is True
    assert "low_confidence" in result.metadata["escalation_reasons"]
    assert model.use_category_calls == [_QUESTION.message]


async def test_classify_pending_cascade_keeps_tier1_assigned_score_consistent() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.CASCADE,
        classifier_model="nomic-embed-text",
        classifier_version="cascade-test",
    )
    classification_repo.stored.append(pending)
    embedding_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.9,
        source=ClassificationScoreSource.EMBEDDING,
    )
    llm_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.55,
        source=ClassificationScoreSource.LLM,
    )
    embedding = _FakeEmbeddingClassifier(
        scores=[embedding_score],
        assigned=[embedding_score],
        metadata={
            "threshold_profile": "embedding-test",
            "would_escalate_due_to_length": True,
        },
    )
    model = _FakeModel(
        use_category_result=UseCategoryClassification(
            outcome=ClassificationOutcome.UNCLEAR,
            category_scores=[llm_score],
            assigned_categories=[],
        )
    )
    use_case = ClassifyPendingCascadeUseCategory(
        _FakeMuseumQuestion(),
        embedding,
        model,
        triage_repo,
        classification_repo,
        high_threshold=0.74,
        margin_delta=0.08,
    )

    result = await use_case.execute(
        ClassifyPendingCascadeUseCategoryInput(classification_id=pending.id)
    )

    assert result.status is ClassificationStatus.COMPLETED
    assert result.outcome is ClassificationOutcome.CATEGORIZED
    assert result.assigned_categories == [embedding_score]
    assert result.category_scores == [embedding_score]
    assert result.metadata["tier2_llm_used"] is True
    assert "long_message" in result.metadata["escalation_reasons"]


async def test_classify_pending_cascade_degrades_when_tier2_fails() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    pending = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.CASCADE,
        classifier_model="nomic-embed-text",
        classifier_version="cascade-test",
    )
    classification_repo.stored.append(pending)
    low_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.62,
        source=ClassificationScoreSource.EMBEDDING,
    )
    embedding = _FakeEmbeddingClassifier(scores=[low_score], assigned=[])
    use_case = ClassifyPendingCascadeUseCategory(
        _FakeMuseumQuestion(),
        embedding,
        _FakeModel(use_category_error=ModelUnavailable("llm down")),
        triage_repo,
        classification_repo,
        high_threshold=0.74,
        margin_delta=0.08,
    )

    result = await use_case.execute(
        ClassifyPendingCascadeUseCategoryInput(classification_id=pending.id)
    )

    assert result.status is ClassificationStatus.COMPLETED
    assert result.quality is ClassificationQuality.DEGRADED
    assert result.outcome is ClassificationOutcome.UNCLEAR
    assert result.assigned_categories == []
    assert result.metadata["tier2_llm_used"] is True
    assert result.metadata["fallback_reason"] == "llm down"


async def test_sync_use_categories_creates_staff_reviewed_cascade_line() -> None:
    triage_repo = _FakeRepo()
    triage = _stored_use_category_triage()
    triage_repo.stored.append(triage)
    classification_repo = _FakeClassificationRepo()
    current_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.86,
        source=ClassificationScoreSource.EMBEDDING,
    )
    classification_repo.stored.append(
        MessageClassification(
            id=ClassificationId("classification-cascade-1"),
            triage_id=triage.id,
            classifier_kind=ClassifierKind.CASCADE,
            classifier_model="nomic-embed-text",
            classifier_version="cascade-test",
            run_number=1,
            superseded_at=None,
            status=ClassificationStatus.COMPLETED,
            outcome=ClassificationOutcome.CATEGORIZED,
            quality=ClassificationQuality.FULL,
            category_scores=[current_score],
            assigned_categories=[current_score],
            error=None,
            metadata={},
            classified_at=datetime(2026, 7, 10, 12, 1, tzinfo=UTC),
            created_at=datetime(2026, 7, 10, 12, 1, tzinfo=UTC),
        )
    )
    training_repo = _FakeTrainingExampleRepo()
    use_case = SyncUseCategories(
        _FakeMuseumQuestion(), triage_repo, classification_repo, training_repo
    )

    result = await use_case.execute(
        SyncUseCategoriesInput(
            question_id="q1",
            categories=[
                UseCategory.ANSWERING_ENQUIRIES,
                UseCategory.ANSWERING_ENQUIRIES,
                UseCategory.PUBLISHING_IMAGES,
            ],
            human_outcome=HumanCategoryOutcome.CATEGORIZED,
            caller=_STAFF,
        )
    )

    assert result.classifier_kind is ClassifierKind.CASCADE
    assert result.classifier_version == "staff-reviewed-v1"
    assert result.run_number == 2
    assert result.status is ClassificationStatus.COMPLETED
    assert result.outcome is ClassificationOutcome.CATEGORIZED
    assert result.quality is ClassificationQuality.FULL
    assert [score.category for score in result.assigned_categories] == [
        UseCategory.ANSWERING_ENQUIRIES,
        UseCategory.PUBLISHING_IMAGES,
    ]
    assert all(score.confidence == 1.0 for score in result.assigned_categories)
    assert result.metadata["staff_reviewed"] is True
    assert result.metadata["reviewed_by"] == _STAFF.email
    assert result.metadata["human_outcome"] == "CATEGORIZED"
    assert classification_repo.stored[0].superseded_at is not None
    assert classification_repo.stored[1] == result
    example = training_repo.stored[-1]
    assert result.metadata["training_example_id"] == example.id
    assert example.triage_id == triage.id
    assert example.question_id == "q1"
    assert example.run_number == 1
    assert example.human_outcome is HumanCategoryOutcome.CATEGORIZED
    assert example.human_categories == [
        UseCategory.ANSWERING_ENQUIRIES,
        UseCategory.PUBLISHING_IMAGES,
    ]
    assert example.embedding_categories == []
    assert example.source is TrainingExampleSource.HUMAN_CREATED
    assert example.reviewed_by == _STAFF.email
    assert example.message_hash
    assert example.active is True
    assert triage.effective_verdict is TriageVerdict.IN_SCOPE


async def test_sync_use_categories_training_failure_does_not_add_cascade_line() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    use_case = SyncUseCategories(
        _FakeMuseumQuestion(),
        triage_repo,
        classification_repo,
        _FailingTrainingExampleRepo(),
    )

    with pytest.raises(RuntimeError, match="training example store failed"):
        await use_case.execute(
            SyncUseCategoriesInput(
                question_id="q1",
                categories=[UseCategory.RESEARCH_PROJECTS],
                human_outcome=HumanCategoryOutcome.CATEGORIZED,
                caller=_STAFF,
            )
        )

    assert classification_repo.stored == []
    assert classification_repo.supersede_calls == []


async def test_sync_use_categories_can_mark_unclear() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    training_repo = _FakeTrainingExampleRepo()
    use_case = SyncUseCategories(
        _FakeMuseumQuestion(), triage_repo, classification_repo, training_repo
    )

    result = await use_case.execute(
        SyncUseCategoriesInput(
            question_id="q1",
            categories=[],
            human_outcome=HumanCategoryOutcome.UNCLEAR,
            caller=_STAFF,
        )
    )

    assert result.outcome is ClassificationOutcome.UNCLEAR
    assert result.assigned_categories == []
    assert result.category_scores == []
    assert training_repo.stored[0].human_outcome is HumanCategoryOutcome.UNCLEAR
    assert training_repo.stored[0].human_categories == []


async def test_generate_embedding_prototype_version_from_human_examples() -> None:
    message = _QUESTION.message
    training_repo = _FakeTrainingExampleRepo()
    positive = _training_example(
        categories=[UseCategory.RESEARCH_PROJECTS, UseCategory.ANSWERING_ENQUIRIES],
        message=message,
    )
    unclear = _training_example(
        id_="unclear",
        categories=[],
        outcome=HumanCategoryOutcome.UNCLEAR,
    )
    training_repo.stored.extend([positive, unclear])
    prototype_repo = _FakePrototypeVersionRepo()
    embedding = _FakeEmbedding({message: [0.9, 0.1]})
    use_case = GenerateEmbeddingPrototypeVersion(
        _FakeMuseumQuestion(), embedding, training_repo, prototype_repo
    )

    result = await use_case.execute(
        GenerateEmbeddingPrototypeVersionInput(
            version="embedding-prototypes-2026-07-13-v1",
            embedding_model="nomic-embed-text",
            threshold_profile={"profile_version": "test-thresholds"},
            promote=True,
        )
    )

    assert result.version == "embedding-prototypes-2026-07-13-v1"
    assert result.embedding_model == "nomic-embed-text"
    assert result.aggregation_method is EmbeddingPrototypeAggregation.MAX_EXAMPLE
    assert result.promoted_at is not None
    assert result.example_ids == [positive.id, unclear.id]
    assert result.prototypes == {
        UseCategory.ANSWERING_ENQUIRIES: [[0.9, 0.1]],
        UseCategory.RESEARCH_PROJECTS: [[0.9, 0.1]],
    }
    assert result.metrics["training_examples_count"] == 2
    assert result.metrics["unclear_examples_count"] == 1
    assert result.metrics["positive_examples_count"] == 2
    assert prototype_repo.stored == [result]
    assert prototype_repo.promote_calls[0][0] == result.version
    assert embedding.calls == [[message]]


async def test_generate_embedding_prototype_version_requires_examples() -> None:
    training_repo = _FakeTrainingExampleRepo()
    training_repo.stored.append(
        _training_example(categories=[], outcome=HumanCategoryOutcome.UNCLEAR)
    )
    use_case = GenerateEmbeddingPrototypeVersion(
        _FakeMuseumQuestion(),
        _FakeEmbedding({}),
        training_repo,
        _FakePrototypeVersionRepo(),
    )

    with pytest.raises(NotEnoughTrainingExamples):
        await use_case.execute(
            GenerateEmbeddingPrototypeVersionInput(
                version="embedding-prototypes-empty",
                embedding_model="nomic-embed-text",
                threshold_profile={},
            )
        )


async def test_export_use_category_calibration_csv_excludes_message_text() -> None:
    triage_repo = _FakeRepo()
    triage_repo.stored.append(_stored_use_category_triage())
    classification_repo = _FakeClassificationRepo()
    llm_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.91,
        source=ClassificationScoreSource.LLM,
    )
    embedding_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.86,
        source=ClassificationScoreSource.EMBEDDING,
    )
    classification_repo.stored.extend(
        [
            MessageClassification(
                id=ClassificationId("llm-1"),
                triage_id=TriageId("triage-1"),
                classifier_kind=ClassifierKind.LLM,
                classifier_model="llama3.1:8b",
                classifier_version="llm-use-category-v1",
                run_number=1,
                superseded_at=None,
                status=ClassificationStatus.COMPLETED,
                outcome=ClassificationOutcome.CATEGORIZED,
                quality=ClassificationQuality.FULL,
                category_scores=[llm_score],
                assigned_categories=[llm_score],
                error=None,
                metadata={},
                classified_at=datetime(2026, 7, 10, 12, 1, tzinfo=UTC),
                created_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
            ),
            MessageClassification(
                id=ClassificationId("embedding-1"),
                triage_id=TriageId("triage-1"),
                classifier_kind=ClassifierKind.EMBEDDING,
                classifier_model="nomic-embed-text",
                classifier_version="embedding-prototypes-v1",
                run_number=1,
                superseded_at=None,
                status=ClassificationStatus.COMPLETED,
                outcome=ClassificationOutcome.CATEGORIZED,
                quality=ClassificationQuality.FULL,
                category_scores=[embedding_score],
                assigned_categories=[embedding_score],
                error=None,
                metadata={"threshold_profile": "embedding-prototypes-v1"},
                classified_at=datetime(2026, 7, 10, 12, 2, tzinfo=UTC),
                created_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
            ),
        ]
    )
    use_case = ExportUseCategoryCalibrationCsv(
        _FakeMuseumQuestion(), triage_repo, classification_repo
    )

    content = await use_case.execute(ExportUseCategoryCalibrationInput(limit=100))
    rows = list(csv.DictReader(StringIO(content)))

    assert len(rows) == 1
    row = rows[0]
    assert row["triage_id"] == "triage-1"
    assert row["question_id"] == "q1"
    assert row["internal_link"] == "/p/museum-questions/q1"
    assert row["question_status"] == "SUBMITTED"
    assert row["message_hash_sha256"]
    assert row["human_categories"] == ""
    assert "RESEARCH_PROJECTS" in row["llm_assigned_categories"]
    assert "RESEARCH_PROJECTS" in row["embedding_assigned_categories"]
    assert _QUESTION.message not in content
    assert _QUESTION.requester_email not in content


async def test_out_of_scope_drafts_reply_and_skips_search() -> None:
    use_case, model, object_search, repo = _use_case(
        model=_FakeModel(is_visit_related=False)
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.verdict is TriageVerdict.OUT_OF_SCOPE
    assert result.suggested_reply == "Thanks, but this is out of scope."
    assert result.object_matches == []
    assert object_search.calls == []
    assert model.reply_calls == [_QUESTION.message]
    assert repo.stored == [result]


async def test_in_scope_with_objects_searches_each_language() -> None:
    pt_hit = ObjectHitView(
        collection_id="c1",
        collection_name="Meteorites",
        file_name="rows.xlsx",
        highlight="<b>Allende</b>",
    )
    use_case, _model, object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(
                    english="Allende meteorite", portuguese="Meteorito Allende"
                ),
                MentionedObject(english="Ghost object", portuguese="Objeto fantasma"),
            ],
        ),
        object_search=_FakeObjectSearch({"Meteorito Allende": [pt_hit]}),
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.verdict is TriageVerdict.IN_SCOPE
    assert result.suggested_reply is None
    assert [(m.english, m.portuguese) for m in result.object_matches] == [
        ("Allende meteorite", "Meteorito Allende"),
        ("Ghost object", "Objeto fantasma"),
    ]
    assert result.object_matches[0].hits == [pt_hit]
    assert result.object_matches[1].hits == []  # not found in catalogue

    # Portuguese searched first, then English, for each of the two objects.
    assert object_search.calls == [
        (_STAFF, "Meteorito Allende", SEARCH_FETCH_LIMIT_PER_LANGUAGE),
        (_STAFF, "Allende meteorite", SEARCH_FETCH_LIMIT_PER_LANGUAGE),
        (_STAFF, "Objeto fantasma", SEARCH_FETCH_LIMIT_PER_LANGUAGE),
        (_STAFF, "Ghost object", SEARCH_FETCH_LIMIT_PER_LANGUAGE),
    ]


async def test_search_skips_english_when_identical_to_portuguese() -> None:
    use_case, _model, object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english="Allende", portuguese="Allende"),
            ],
        )
    )
    await use_case.execute(TriageMuseumQuestionInput(question_id="q1", caller=_STAFF))
    assert object_search.calls == [(_STAFF, "Allende", SEARCH_FETCH_LIMIT_PER_LANGUAGE)]


async def test_hits_from_both_languages_are_merged_and_deduplicated() -> None:
    shared_hit = ObjectHitView(
        collection_id="c1",
        collection_name="Meteorites",
        file_name="rows.xlsx",
        highlight="<b>Allende</b>",
    )
    english_only_hit = ObjectHitView(
        collection_id="c2",
        collection_name="Meteorites",
        file_name="other.xlsx",
        highlight="<b>Allende</b> chondrite",
    )
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(
                    english="Allende meteorite", portuguese="Meteorito Allende"
                ),
            ],
        ),
        object_search=_FakeObjectSearch(
            {
                "Meteorito Allende": [shared_hit],
                "Allende meteorite": [shared_hit, english_only_hit],
            }
        ),
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.object_matches[0].hits == [shared_hit, english_only_hit]


async def test_distinct_rows_in_the_same_file_are_not_deduplicated_away() -> None:
    # Two different rows of the same spreadsheet: the Portuguese search
    # finds one, the English search finds another. Same collection_id/
    # file_name, but different highlight — both must be kept.
    row_five = ObjectHitView(
        collection_id="c1",
        collection_name="Zoology",
        file_name="zoology.xlsx",
        highlight="row 5: <b>baleia</b> azul",
    )
    row_twelve = ObjectHitView(
        collection_id="c1",
        collection_name="Zoology",
        file_name="zoology.xlsx",
        highlight="row 12: blue <b>whale</b>",
    )
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english="Blue whale", portuguese="Baleia azul"),
            ],
        ),
        object_search=_FakeObjectSearch(
            {"Baleia azul": [row_five], "Blue whale": [row_twelve]}
        ),
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.object_matches[0].hits == [row_five, row_twelve]


async def test_merged_hits_are_not_truncated_to_a_small_display_cap() -> None:
    # Regression: hits used to be capped to 5 for display. The cap is gone —
    # the full merged/deduplicated list is persisted, and the UI paginates
    # over it client-side.
    hits = [
        ObjectHitView(
            collection_id="c1",
            collection_name="Zoology",
            file_name="zoology.xlsx",
            highlight=f"row {i}: <b>lagarto</b>",
        )
        for i in range(8)
    ]
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english="Lizard", portuguese="Lagarto"),
            ],
        ),
        object_search=_FakeObjectSearch({"Lagarto": hits}),
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.object_matches[0].hits == hits


async def test_mentioned_objects_are_trimmed_deduplicated_and_blanks_dropped() -> None:
    use_case, _model, object_search, repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(
                    english="  Allende meteorite ", portuguese="  Meteorito Allende "
                ),
                MentionedObject(
                    english="Allende meteorite", portuguese="Meteorito Allende"
                ),
                MentionedObject(
                    english="ALLENDE METEORITE", portuguese="METEORITO ALLENDE"
                ),
                MentionedObject(english="", portuguese=""),
                MentionedObject(english="   ", portuguese="   "),
                MentionedObject(english="Ghost object", portuguese="Ghost object"),
            ],
        )
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.mentioned_objects == [
        MentionedObject(english="Allende meteorite", portuguese="Meteorito Allende"),
        MentionedObject(english="Ghost object", portuguese="Ghost object"),
    ]
    assert [(m.english, m.portuguese) for m in result.object_matches] == [
        ("Allende meteorite", "Meteorito Allende"),
        ("Ghost object", "Ghost object"),
    ]
    # first object: 2 searches (distinct pt/en); second: 1 (identical pt/en)
    assert len(object_search.calls) == 3
    assert repo.stored[0].mentioned_objects == result.mentioned_objects


async def test_same_portuguese_but_different_english_are_kept_distinct() -> None:
    # An imprecise translation could give two different objects the same
    # Portuguese name — deduping on Portuguese alone would silently drop one.
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english="Blue whale", portuguese="Baleia"),
                MentionedObject(english="Right whale", portuguese="Baleia"),
            ],
        )
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.mentioned_objects == [
        MentionedObject(english="Blue whale", portuguese="Baleia"),
        MentionedObject(english="Right whale", portuguese="Baleia"),
    ]


async def test_blank_language_falls_back_to_the_other() -> None:
    use_case, _model, _object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[MentionedObject(english="", portuguese="Baleia")],
        )
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.mentioned_objects == [
        MentionedObject(english="Baleia", portuguese="Baleia")
    ]


async def test_in_scope_without_objects_skips_search() -> None:
    use_case, _model, object_search, _repo = _use_case(
        model=_FakeModel(is_visit_related=True, mentioned_objects=[])
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert result.verdict is TriageVerdict.IN_SCOPE
    assert result.object_matches == []
    assert object_search.calls == []


async def test_object_queries_are_capped_at_three() -> None:
    use_case, _model, object_search, _repo = _use_case(
        model=_FakeModel(
            is_visit_related=True,
            mentioned_objects=[
                MentionedObject(english=x, portuguese=x) for x in ["a", "b", "c", "d"]
            ],
        )
    )
    result = await use_case.execute(
        TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
    )
    assert len(result.object_matches) == 3
    assert len(object_search.calls) == 3  # english == portuguese, 1 search each


async def test_missing_question_raises() -> None:
    use_case, *_ = _use_case(museum_question=_FakeMuseumQuestion(question=None))
    with pytest.raises(QuestionNotFound):
        await use_case.execute(
            TriageMuseumQuestionInput(question_id="missing", caller=_STAFF)
        )


async def test_model_unavailable_propagates() -> None:
    use_case, *_ = _use_case(model=_FakeModel(classify_error=ModelUnavailable("down")))
    with pytest.raises(ModelUnavailable):
        await use_case.execute(
            TriageMuseumQuestionInput(question_id="q1", caller=_STAFF)
        )


async def test_get_latest_triage_returns_none_when_never_run() -> None:
    result = await GetLatestTriage(_FakeRepo()).execute(
        GetLatestTriageInput(question_id="q1")
    )
    assert result is None


async def test_get_latest_triage_returns_most_recent() -> None:
    repo = _FakeRepo()
    older = MessageTriage(
        id=TriageId("t1"),
        question_id="q1",
        verdict=TriageVerdict.IN_SCOPE,
        is_visit_related=True,
        mentioned_objects=[],
        object_matches=[],
        suggested_reply=None,
        llm_model="llama3.1:8b",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = MessageTriage(
        id=TriageId("t2"),
        question_id="q1",
        verdict=TriageVerdict.OUT_OF_SCOPE,
        is_visit_related=False,
        mentioned_objects=[],
        object_matches=[],
        suggested_reply="reply",
        llm_model="llama3.1:8b",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    await repo.add(older)
    await repo.add(newer)
    latest = await GetLatestTriage(repo).execute(GetLatestTriageInput(question_id="q1"))
    assert latest == newer


def _stored_triage(
    *,
    verdict: TriageVerdict = TriageVerdict.IN_SCOPE,
    is_visit_related: bool = True,
    mentioned_objects: list[MentionedObject] | None = None,
    object_matches: list[ObjectTriageMatch] | None = None,
    suggested_reply: str | None = None,
) -> MessageTriage:
    return MessageTriage(
        id=TriageId("t1"),
        question_id="q1",
        verdict=verdict,
        is_visit_related=is_visit_related,
        mentioned_objects=mentioned_objects or [],
        object_matches=object_matches or [],
        suggested_reply=suggested_reply,
        llm_model="llama3.1:8b",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_override_verdict_sets_effective_verdict_ai_verdict_unchanged() -> None:
    repo = _FakeRepo()
    await repo.add(_stored_triage(verdict=TriageVerdict.IN_SCOPE))
    use_case = OverrideTriageVerdict(_FakeMuseumQuestion(), _FakeModel(), repo)

    result = await use_case.execute(
        OverrideTriageVerdictInput(
            question_id="q1", verdict=TriageVerdict.OUT_OF_SCOPE, caller=_STAFF
        )
    )

    assert result.verdict is TriageVerdict.IN_SCOPE  # AI's original, untouched
    assert result.staff_override_verdict is TriageVerdict.OUT_OF_SCOPE
    assert result.effective_verdict is TriageVerdict.OUT_OF_SCOPE
    assert result.staff_override_by == _STAFF.email
    assert result.staff_override_at is not None
    assert repo.update_calls == [result]


async def test_override_to_out_of_scope_drafts_reply_if_missing() -> None:
    repo = _FakeRepo()
    await repo.add(_stored_triage(verdict=TriageVerdict.IN_SCOPE, suggested_reply=None))
    model = _FakeModel(reply="Sorry, out of scope.")
    use_case = OverrideTriageVerdict(_FakeMuseumQuestion(), model, repo)

    result = await use_case.execute(
        OverrideTriageVerdictInput(
            question_id="q1", verdict=TriageVerdict.OUT_OF_SCOPE, caller=_STAFF
        )
    )

    assert result.suggested_reply == "Sorry, out of scope."
    assert model.reply_calls == [_QUESTION.message]


async def test_override_does_not_regenerate_an_existing_reply() -> None:
    repo = _FakeRepo()
    await repo.add(
        _stored_triage(
            verdict=TriageVerdict.OUT_OF_SCOPE, suggested_reply="Original reply."
        )
    )
    model = _FakeModel(reply="Would overwrite.")
    use_case = OverrideTriageVerdict(_FakeMuseumQuestion(), model, repo)

    # Flip to IN_SCOPE and back to OUT_OF_SCOPE — the original reply must
    # survive, and the model must not be called again since it was never
    # cleared.
    await use_case.execute(
        OverrideTriageVerdictInput(
            question_id="q1", verdict=TriageVerdict.IN_SCOPE, caller=_STAFF
        )
    )
    result = await use_case.execute(
        OverrideTriageVerdictInput(
            question_id="q1", verdict=TriageVerdict.OUT_OF_SCOPE, caller=_STAFF
        )
    )

    assert result.suggested_reply == "Original reply."
    assert model.reply_calls == []


async def test_override_raises_when_no_triage_exists() -> None:
    use_case = OverrideTriageVerdict(_FakeMuseumQuestion(), _FakeModel(), _FakeRepo())
    with pytest.raises(TriageNotFound):
        await use_case.execute(
            OverrideTriageVerdictInput(
                question_id="missing", verdict=TriageVerdict.OUT_OF_SCOPE, caller=_STAFF
            )
        )


async def test_sync_search_terms_adds_new_term_and_searches_it() -> None:
    repo = _FakeRepo()
    await repo.add(_stored_triage())
    hit = ObjectHitView(
        collection_id="c1",
        collection_name="Zoology",
        file_name="zoology.xlsx",
        highlight="<b>Vulpes vulpes</b>",
    )
    object_search = _FakeObjectSearch({"Vulpes vulpes": [hit]})
    use_case = SyncTriageSearchTerms(object_search, repo)

    result = await use_case.execute(
        SyncTriageSearchTermsInput(
            question_id="q1",
            terms=[("Vulpes vulpes", "Vulpes vulpes")],
            caller=_STAFF,
        )
    )

    assert result.mentioned_objects == [
        MentionedObject(
            english="Vulpes vulpes",
            portuguese="Vulpes vulpes",
            origin=MentionedObjectOrigin.STAFF,
        )
    ]
    assert result.object_matches[0].hits == [hit]
    assert result.object_matches[0].languages_searched == ["pt"]
    assert object_search.calls == [
        (_STAFF, "Vulpes vulpes", SEARCH_FETCH_LIMIT_PER_LANGUAGE)
    ]


async def test_sync_search_terms_removes_term_no_longer_present() -> None:
    kept_match = ObjectTriageMatch(
        english="Blue whale",
        portuguese="Baleia azul",
        hits=[],
        languages_searched=["pt", "en"],
    )
    removed_match = ObjectTriageMatch(
        english="Fox", portuguese="Raposa", hits=[], languages_searched=["pt", "en"]
    )
    repo = _FakeRepo()
    await repo.add(
        _stored_triage(
            mentioned_objects=[
                MentionedObject(english="Blue whale", portuguese="Baleia azul"),
                MentionedObject(english="Fox", portuguese="Raposa"),
            ],
            object_matches=[kept_match, removed_match],
        )
    )
    use_case = SyncTriageSearchTerms(_FakeObjectSearch(), repo)

    result = await use_case.execute(
        SyncTriageSearchTermsInput(
            question_id="q1", terms=[("Blue whale", "Baleia azul")], caller=_STAFF
        )
    )

    assert result.mentioned_objects == [
        MentionedObject(english="Blue whale", portuguese="Baleia azul")
    ]
    assert result.object_matches == [kept_match]


async def test_sync_search_terms_keeps_unchanged_term_without_re_searching() -> None:
    existing_match = ObjectTriageMatch(
        english="Blue whale",
        portuguese="Baleia azul",
        hits=[],
        languages_searched=["pt", "en"],
    )
    repo = _FakeRepo()
    await repo.add(
        _stored_triage(
            mentioned_objects=[
                MentionedObject(english="Blue whale", portuguese="Baleia azul")
            ],
            object_matches=[existing_match],
        )
    )
    object_search = _FakeObjectSearch()
    use_case = SyncTriageSearchTerms(object_search, repo)

    result = await use_case.execute(
        SyncTriageSearchTermsInput(
            question_id="q1", terms=[("Blue whale", "Baleia azul")], caller=_STAFF
        )
    )

    assert result.object_matches == [existing_match]
    assert object_search.calls == []


async def test_sync_search_terms_edited_term_is_drop_and_add_not_correlated() -> None:
    # Editing "raposa"/"fox" into "Vulpes vulpes" changes the (portuguese,
    # english) key entirely — the diff must treat it as drop-the-old,
    # search-the-new, not try to detect "this is the same item, edited".
    old_match = ObjectTriageMatch(
        english="Fox", portuguese="Raposa", hits=[], languages_searched=["pt", "en"]
    )
    repo = _FakeRepo()
    await repo.add(
        _stored_triage(
            mentioned_objects=[MentionedObject(english="Fox", portuguese="Raposa")],
            object_matches=[old_match],
        )
    )
    new_hit = ObjectHitView(
        collection_id="c1",
        collection_name="Zoology",
        file_name="zoology.xlsx",
        highlight="<b>Vulpes vulpes</b>",
    )
    object_search = _FakeObjectSearch({"Vulpes vulpes": [new_hit]})
    use_case = SyncTriageSearchTerms(object_search, repo)

    result = await use_case.execute(
        SyncTriageSearchTermsInput(
            question_id="q1",
            terms=[("Vulpes vulpes", "Vulpes vulpes")],
            caller=_STAFF,
        )
    )

    assert result.mentioned_objects == [
        MentionedObject(
            english="Vulpes vulpes",
            portuguese="Vulpes vulpes",
            origin=MentionedObjectOrigin.STAFF,
        )
    ]
    assert result.object_matches[0].hits == [new_hit]


async def test_sync_search_terms_rejects_when_out_of_scope() -> None:
    repo = _FakeRepo()
    await repo.add(_stored_triage(verdict=TriageVerdict.OUT_OF_SCOPE))
    use_case = SyncTriageSearchTerms(_FakeObjectSearch(), repo)

    with pytest.raises(TriageNotInScope):
        await use_case.execute(
            SyncTriageSearchTermsInput(
                question_id="q1", terms=[("Fox", "Raposa")], caller=_STAFF
            )
        )


async def test_sync_search_terms_rejects_too_many_terms() -> None:
    repo = _FakeRepo()
    await repo.add(_stored_triage())
    use_case = SyncTriageSearchTerms(_FakeObjectSearch(), repo)

    too_many = [(f"term{i}", f"termo{i}") for i in range(MAX_STAFF_SEARCH_TERMS + 1)]
    with pytest.raises(TriageTermValidationError):
        await use_case.execute(
            SyncTriageSearchTermsInput(question_id="q1", terms=too_many, caller=_STAFF)
        )


async def test_sync_search_terms_rejects_field_too_long() -> None:
    repo = _FakeRepo()
    await repo.add(_stored_triage())
    use_case = SyncTriageSearchTerms(_FakeObjectSearch(), repo)

    with pytest.raises(TriageTermValidationError):
        await use_case.execute(
            SyncTriageSearchTermsInput(
                question_id="q1", terms=[("x" * 201, "y")], caller=_STAFF
            )
        )


async def test_sync_search_terms_length_checked_after_trimming() -> None:
    # A field that only exceeds the limit because of surrounding whitespace
    # must not be rejected — the check applies to the trimmed value, matching
    # the documented order (normalize, then validate).
    repo = _FakeRepo()
    await repo.add(_stored_triage())
    object_search = _FakeObjectSearch({"x": []})
    use_case = SyncTriageSearchTerms(object_search, repo)

    padded = f"{'  ' * 5}x{'  ' * 5}"  # 21 chars raw, 1 char trimmed
    result = await use_case.execute(
        SyncTriageSearchTermsInput(
            question_id="q1", terms=[(padded, padded)], caller=_STAFF
        )
    )

    assert result.mentioned_objects == [
        MentionedObject(english="x", portuguese="x", origin=MentionedObjectOrigin.STAFF)
    ]


async def test_sync_search_terms_empty_list_is_valid_and_clears_matches() -> None:
    repo = _FakeRepo()
    await repo.add(
        _stored_triage(
            mentioned_objects=[MentionedObject(english="Fox", portuguese="Raposa")],
            object_matches=[
                ObjectTriageMatch(english="Fox", portuguese="Raposa", hits=[])
            ],
        )
    )
    use_case = SyncTriageSearchTerms(_FakeObjectSearch(), repo)

    result = await use_case.execute(
        SyncTriageSearchTermsInput(question_id="q1", terms=[], caller=_STAFF)
    )

    assert result.mentioned_objects == []
    assert result.object_matches == []


async def test_sync_search_terms_raises_when_no_triage_exists() -> None:
    use_case = SyncTriageSearchTerms(_FakeObjectSearch(), _FakeRepo())
    with pytest.raises(TriageNotFound):
        await use_case.execute(
            SyncTriageSearchTermsInput(
                question_id="missing", terms=[("Fox", "Raposa")], caller=_STAFF
            )
        )
