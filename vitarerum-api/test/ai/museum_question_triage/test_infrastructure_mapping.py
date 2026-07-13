from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.museum_question_triage.domain.models import (
    ClassificationId,
    ClassificationOutcome,
    ClassificationQuality,
    ClassificationScoreSource,
    ClassificationStatus,
    ClassifierKind,
    EmbeddingPrototypeAggregation,
    EmbeddingPrototypeVersion,
    EmbeddingPrototypeVersionId,
    HumanCategoryOutcome,
    MessageClassification,
    MessageTriage,
    TrainingExampleId,
    TrainingExampleSource,
    TriageId,
    TriageVerdict,
    UseCategory,
    UseCategoryScore,
    UseCategoryTrainingExample,
)
from app.ai.museum_question_triage.infrastructure.repositories import (
    SqlAlchemyEmbeddingPrototypeVersionRepository,
    SqlAlchemyMessageClassificationRepository,
    SqlAlchemyTriageRepository,
    SqlAlchemyUseCategoryTrainingExampleRepository,
    classification_to_domain,
    classification_to_orm,
    embedding_prototype_version_to_domain,
    embedding_prototype_version_to_orm,
    training_example_to_domain,
    training_example_to_orm,
)
from app.database import Base

_NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _triage(
    *,
    id_: str = "triage-1",
    question_id: str = "q1",
    created_at: datetime = _NOW,
) -> MessageTriage:
    return MessageTriage(
        id=TriageId(id_),
        question_id=question_id,
        verdict=TriageVerdict.IN_SCOPE,
        is_visit_related=True,
        mentioned_objects=[],
        object_matches=[],
        suggested_reply=None,
        llm_model="llama3.1:8b",
        created_at=created_at,
    )


def _score(
    category: UseCategory = UseCategory.RESEARCH_PROJECTS,
    confidence: float = 0.91,
) -> UseCategoryScore:
    return UseCategoryScore(
        category=category,
        confidence=confidence,
        source=ClassificationScoreSource.LLM,
    )


def _classification(
    *,
    id_: str = "classification-1",
    run_number: int = 1,
    superseded_at: datetime | None = None,
) -> MessageClassification:
    score = _score()
    return MessageClassification(
        id=ClassificationId(id_),
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
        run_number=run_number,
        superseded_at=superseded_at,
        status=ClassificationStatus.COMPLETED,
        outcome=ClassificationOutcome.CATEGORIZED,
        quality=ClassificationQuality.FULL,
        category_scores=[score],
        assigned_categories=[score],
        error=None,
        metadata={"prompt": "v1"},
        classified_at=_NOW,
        created_at=_NOW,
    )


def _training_example(
    *,
    id_: str = "example-1",
    triage_id: str = "triage-1",
    question_id: str = "q1",
    run_number: int = 1,
    active: bool = True,
) -> UseCategoryTrainingExample:
    return UseCategoryTrainingExample(
        id=TrainingExampleId(id_),
        triage_id=TriageId(triage_id),
        question_id=question_id,
        run_number=run_number,
        superseded_at=None,
        superseded_by_example_id=None,
        human_outcome=HumanCategoryOutcome.CATEGORIZED,
        human_categories=[UseCategory.RESEARCH_PROJECTS],
        llm_categories=[UseCategory.RESEARCH_PROJECTS],
        embedding_categories=[],
        source=TrainingExampleSource.LLM_ACCEPTED,
        reviewed_by="s@museum.pt",
        reviewed_at=_NOW,
        message_hash="a" * 64,
        active=active,
        notes=None,
        created_at=_NOW,
    )


def _prototype_version(
    *,
    id_: str = "prototype-1",
    version: str = "embedding-prototypes-test-v1",
    promoted_at: datetime | None = None,
    retired_at: datetime | None = None,
) -> EmbeddingPrototypeVersion:
    return EmbeddingPrototypeVersion(
        id=EmbeddingPrototypeVersionId(id_),
        version=version,
        embedding_model="nomic-embed-text",
        aggregation_method=EmbeddingPrototypeAggregation.MAX_EXAMPLE,
        threshold_profile={"profile_version": "test"},
        example_ids=[TrainingExampleId("example-1")],
        prototypes={UseCategory.RESEARCH_PROJECTS: [[0.9, 0.1]]},
        metrics={"training_examples_count": 1},
        created_at=_NOW,
        promoted_at=promoted_at,
        retired_at=retired_at,
    )


async def _session_factory() -> async_sessionmaker:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def test_classification_roundtrip_preserves_key_data() -> None:
    classification = _classification()

    rebuilt = classification_to_domain(classification_to_orm(classification))

    assert rebuilt.id == classification.id
    assert rebuilt.triage_id == classification.triage_id
    assert rebuilt.classifier_kind is ClassifierKind.LLM
    assert rebuilt.classifier_model == "llama3.1:8b"
    assert rebuilt.classifier_version == "llm-use-category-v1"
    assert rebuilt.run_number == 1
    assert rebuilt.status is ClassificationStatus.COMPLETED
    assert rebuilt.outcome is ClassificationOutcome.CATEGORIZED
    assert rebuilt.quality is ClassificationQuality.FULL
    assert rebuilt.category_scores == classification.category_scores
    assert rebuilt.assigned_categories == classification.assigned_categories
    assert rebuilt.metadata == {"prompt": "v1"}
    assert rebuilt.classified_at == _NOW


def test_training_example_roundtrip_preserves_key_data() -> None:
    example = _training_example()

    rebuilt = training_example_to_domain(training_example_to_orm(example))

    assert rebuilt.id == example.id
    assert rebuilt.triage_id == example.triage_id
    assert rebuilt.question_id == "q1"
    assert rebuilt.human_outcome is HumanCategoryOutcome.CATEGORIZED
    assert rebuilt.human_categories == [UseCategory.RESEARCH_PROJECTS]
    assert rebuilt.llm_categories == [UseCategory.RESEARCH_PROJECTS]
    assert rebuilt.source is TrainingExampleSource.LLM_ACCEPTED
    assert rebuilt.reviewed_by == "s@museum.pt"
    assert rebuilt.message_hash == "a" * 64
    assert rebuilt.active is True


def test_embedding_prototype_version_roundtrip_preserves_key_data() -> None:
    version = _prototype_version()

    rebuilt = embedding_prototype_version_to_domain(
        embedding_prototype_version_to_orm(version)
    )

    assert rebuilt.id == version.id
    assert rebuilt.version == "embedding-prototypes-test-v1"
    assert rebuilt.embedding_model == "nomic-embed-text"
    assert rebuilt.aggregation_method is EmbeddingPrototypeAggregation.MAX_EXAMPLE
    assert rebuilt.threshold_profile == {"profile_version": "test"}
    assert rebuilt.example_ids == [TrainingExampleId("example-1")]
    assert rebuilt.prototypes == {UseCategory.RESEARCH_PROJECTS: [[0.9, 0.1]]}
    assert rebuilt.metrics == {"training_examples_count": 1}


async def test_repository_returns_current_unsuperseded_highest_run() -> None:
    factory = await _session_factory()
    superseded_at = datetime(2026, 7, 10, 13, 0, tzinfo=UTC)

    async with factory() as session:
        repo = SqlAlchemyMessageClassificationRepository(session)
        await repo.add(
            _classification(
                id_="classification-1",
                run_number=1,
                superseded_at=superseded_at,
            )
        )
        await repo.add(_classification(id_="classification-2", run_number=2))
        await session.commit()

        current = await repo.get_current_by_triage(
            TriageId("triage-1"), ClassifierKind.LLM
        )

    assert current is not None
    assert current.id == "classification-2"
    assert current.run_number == 2


async def test_repository_supersedes_current_line() -> None:
    factory = await _session_factory()
    superseded_at = datetime(2026, 7, 10, 13, 0, tzinfo=UTC)

    async with factory() as session:
        repo = SqlAlchemyMessageClassificationRepository(session)
        await repo.add(_classification(id_="classification-1", run_number=1))
        await session.commit()

        await repo.supersede_current(
            TriageId("triage-1"), ClassifierKind.LLM, superseded_at
        )
        await session.commit()

        current = await repo.get_current_by_triage(
            TriageId("triage-1"), ClassifierKind.LLM
        )
        superseded = await repo.get_by_id(ClassificationId("classification-1"))

    assert current is None
    assert superseded is not None
    assert superseded.superseded_at == superseded_at.replace(tzinfo=None)


async def test_training_example_repository_supersedes_and_filters_active() -> None:
    factory = await _session_factory()
    superseded_at = datetime(2026, 7, 10, 13, 0, tzinfo=UTC)

    async with factory() as session:
        triage_repo = SqlAlchemyTriageRepository(session)
        repo = SqlAlchemyUseCategoryTrainingExampleRepository(session)
        await triage_repo.add(
            _triage(id_="triage-old", created_at=datetime(2026, 7, 9, tzinfo=UTC))
        )
        await triage_repo.add(_triage(id_="triage-1", created_at=_NOW))
        await repo.add(
            _training_example(id_="other-triage", triage_id="triage-old", run_number=1)
        )
        await repo.add(_training_example(id_="old", run_number=1))
        await session.commit()

        await repo.supersede_current(
            TriageId("triage-1"), superseded_at, TrainingExampleId("new")
        )
        await repo.add(_training_example(id_="new", run_number=2))
        await session.commit()

        active = await repo.list_active_current()
        current = await repo.get_current_by_triage(TriageId("triage-1"))

    assert [example.id for example in active] == ["new"]
    assert current is not None
    assert current.id == "new"


async def test_embedding_prototype_repository_promotes_and_retires_previous() -> None:
    factory = await _session_factory()
    promoted_at = datetime(2026, 7, 10, 13, 0, tzinfo=UTC)

    async with factory() as session:
        repo = SqlAlchemyEmbeddingPrototypeVersionRepository(session)
        await repo.add(
            _prototype_version(
                id_="old",
                version="embedding-prototypes-old",
                promoted_at=_NOW,
            )
        )
        await repo.add(
            _prototype_version(id_="new", version="embedding-prototypes-new")
        )
        await session.commit()

        await repo.promote("embedding-prototypes-new", promoted_at)
        await session.commit()

        promoted = await repo.get_promoted()
        old = await repo.get_by_version("embedding-prototypes-old")

    assert promoted is not None
    assert promoted.version == "embedding-prototypes-new"
    assert promoted.promoted_at == promoted_at.replace(tzinfo=None)
    assert old is not None
    assert old.retired_at == promoted_at.replace(tzinfo=None)
