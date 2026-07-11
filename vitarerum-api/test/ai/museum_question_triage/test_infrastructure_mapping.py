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
    MessageClassification,
    TriageId,
    UseCategory,
    UseCategoryScore,
)
from app.ai.museum_question_triage.infrastructure.repositories import (
    SqlAlchemyMessageClassificationRepository,
    classification_to_domain,
    classification_to_orm,
)
from app.database import Base

_NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


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
