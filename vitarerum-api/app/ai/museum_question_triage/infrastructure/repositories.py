"""SQLAlchemy repository for the message-triage aggregate.

``add`` creates a new run; ``update`` persists in-place revisions to an
already-stored run (staff verdict override, reconciled search terms) — see
the mutability policy documented in ``domain/models.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_question_triage.domain.models import (
    ClassificationId,
    ClassificationOutcome,
    ClassificationQuality,
    ClassificationScoreSource,
    ClassificationStatus,
    ClassifierKind,
    MentionedObject,
    MentionedObjectOrigin,
    MessageClassification,
    MessageTriage,
    ObjectHitView,
    ObjectTriageMatch,
    TriageId,
    TriageVerdict,
    UseCategory,
    UseCategoryScore,
)
from app.ai.museum_question_triage.infrastructure.models import (
    MessageClassificationOrm,
    MessageTriageOrm,
)


def _mentioned_objects_to_json(
    items: list[MentionedObject],
) -> list[dict[str, Any]]:
    return [
        {
            "english": item.english,
            "portuguese": item.portuguese,
            "origin": item.origin.value,
        }
        for item in items
    ]


def _mentioned_objects_from_json(
    raw: list[dict[str, Any]],
) -> list[MentionedObject]:
    # Rows written before the refinements plan have no "origin" key — default
    # to AI, since every term up to that point came from the model.
    return [
        MentionedObject(
            english=item["english"],
            portuguese=item["portuguese"],
            origin=MentionedObjectOrigin(
                item.get("origin", MentionedObjectOrigin.AI.value)
            ),
        )
        for item in raw
    ]


def _object_matches_to_json(
    matches: list[ObjectTriageMatch],
) -> list[dict[str, Any]]:
    return [
        {
            "english": match.english,
            "portuguese": match.portuguese,
            "hits": [
                {
                    "collection_id": hit.collection_id,
                    "collection_name": hit.collection_name,
                    "file_name": hit.file_name,
                    "highlight": hit.highlight,
                }
                for hit in match.hits
            ],
            "languages_searched": list(match.languages_searched),
        }
        for match in matches
    ]


def _object_matches_from_json(
    raw: list[dict[str, Any]],
) -> list[ObjectTriageMatch]:
    # Rows written before the refinements plan have no "languages_searched"
    # key — "pt" is the conservative default, since Portuguese is always the
    # primary/first language searched.
    return [
        ObjectTriageMatch(
            english=item["english"],
            portuguese=item["portuguese"],
            hits=[ObjectHitView(**hit) for hit in item["hits"]],
            languages_searched=item.get("languages_searched", ["pt"]),
        )
        for item in raw
    ]


def triage_to_orm(triage: MessageTriage) -> MessageTriageOrm:
    return MessageTriageOrm(
        id=triage.id,
        question_id=triage.question_id,
        verdict=triage.verdict.value,
        is_visit_related=triage.is_visit_related,
        mentioned_objects=_mentioned_objects_to_json(triage.mentioned_objects),
        object_matches=_object_matches_to_json(triage.object_matches),
        suggested_reply=triage.suggested_reply,
        llm_model=triage.llm_model,
        created_at=triage.created_at,
        staff_override_verdict=(
            triage.staff_override_verdict.value
            if triage.staff_override_verdict
            else None
        ),
        staff_override_at=triage.staff_override_at,
        staff_override_by=triage.staff_override_by,
    )


def triage_to_domain(orm: MessageTriageOrm) -> MessageTriage:
    return MessageTriage(
        id=TriageId(orm.id),
        question_id=orm.question_id,
        verdict=TriageVerdict(orm.verdict),
        is_visit_related=orm.is_visit_related,
        mentioned_objects=_mentioned_objects_from_json(orm.mentioned_objects),
        object_matches=_object_matches_from_json(orm.object_matches),
        suggested_reply=orm.suggested_reply,
        llm_model=orm.llm_model,
        created_at=orm.created_at,
        staff_override_verdict=(
            TriageVerdict(orm.staff_override_verdict)
            if orm.staff_override_verdict
            else None
        ),
        staff_override_at=orm.staff_override_at,
        staff_override_by=orm.staff_override_by,
    )


def _scores_to_json(scores: list[UseCategoryScore]) -> list[dict[str, Any]]:
    return [
        {
            "category": score.category.value,
            "confidence": score.confidence,
            "source": score.source.value,
        }
        for score in scores
    ]


def _scores_from_json(raw: list[dict[str, Any]]) -> list[UseCategoryScore]:
    return [
        UseCategoryScore(
            category=UseCategory(item["category"]),
            confidence=float(item["confidence"]),
            source=ClassificationScoreSource(item["source"]),
        )
        for item in raw
    ]


def classification_to_orm(
    classification: MessageClassification,
) -> MessageClassificationOrm:
    return MessageClassificationOrm(
        id=classification.id,
        triage_id=classification.triage_id,
        classifier_kind=classification.classifier_kind.value,
        classifier_model=classification.classifier_model,
        classifier_version=classification.classifier_version,
        run_number=classification.run_number,
        superseded_at=classification.superseded_at,
        status=classification.status.value,
        outcome=classification.outcome.value if classification.outcome else None,
        quality=classification.quality.value if classification.quality else None,
        category_scores=_scores_to_json(classification.category_scores),
        assigned_categories=_scores_to_json(classification.assigned_categories),
        error=classification.error,
        metadata_json=dict(classification.metadata),
        classified_at=classification.classified_at,
        created_at=classification.created_at,
    )


def classification_to_domain(
    orm: MessageClassificationOrm,
) -> MessageClassification:
    return MessageClassification(
        id=ClassificationId(orm.id),
        triage_id=TriageId(orm.triage_id),
        classifier_kind=ClassifierKind(orm.classifier_kind),
        classifier_model=orm.classifier_model,
        classifier_version=orm.classifier_version,
        run_number=orm.run_number,
        superseded_at=orm.superseded_at,
        status=ClassificationStatus(orm.status),
        outcome=ClassificationOutcome(orm.outcome) if orm.outcome else None,
        quality=ClassificationQuality(orm.quality) if orm.quality else None,
        category_scores=_scores_from_json(orm.category_scores),
        assigned_categories=_scores_from_json(orm.assigned_categories),
        error=orm.error,
        metadata=dict(orm.metadata_json),
        classified_at=orm.classified_at,
        created_at=orm.created_at,
    )


class SqlAlchemyTriageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, triage: MessageTriage) -> None:
        self._session.add(triage_to_orm(triage))
        await self._session.flush()

    async def get_by_id(self, triage_id: TriageId) -> MessageTriage | None:
        orm = await self._session.get(MessageTriageOrm, triage_id)
        return triage_to_domain(orm) if orm else None

    async def get_latest_by_question(self, question_id: str) -> MessageTriage | None:
        stmt = (
            select(MessageTriageOrm)
            .where(MessageTriageOrm.question_id == question_id)
            .order_by(MessageTriageOrm.created_at.desc())
            .limit(1)
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return triage_to_domain(orm) if orm else None

    async def update(self, triage: MessageTriage) -> None:
        orm = await self._session.get(MessageTriageOrm, triage.id)
        # update() is only ever called with a triage just loaded from this
        # same repository, so the row is guaranteed to still exist.
        assert orm is not None, f"No stored triage with id {triage.id!r} to update"
        orm.mentioned_objects = _mentioned_objects_to_json(triage.mentioned_objects)
        orm.object_matches = _object_matches_to_json(triage.object_matches)
        orm.suggested_reply = triage.suggested_reply
        orm.staff_override_verdict = (
            triage.staff_override_verdict.value
            if triage.staff_override_verdict
            else None
        )
        orm.staff_override_at = triage.staff_override_at
        orm.staff_override_by = triage.staff_override_by
        await self._session.flush()


def _copy_classification_to_orm(
    classification: MessageClassification, orm: MessageClassificationOrm
) -> None:
    orm.classifier_kind = classification.classifier_kind.value
    orm.classifier_model = classification.classifier_model
    orm.classifier_version = classification.classifier_version
    orm.run_number = classification.run_number
    orm.superseded_at = classification.superseded_at
    orm.status = classification.status.value
    orm.outcome = classification.outcome.value if classification.outcome else None
    orm.quality = classification.quality.value if classification.quality else None
    orm.category_scores = _scores_to_json(classification.category_scores)
    orm.assigned_categories = _scores_to_json(classification.assigned_categories)
    orm.error = classification.error
    orm.metadata_json = dict(classification.metadata)
    orm.classified_at = classification.classified_at
    orm.created_at = classification.created_at


class SqlAlchemyMessageClassificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, classification: MessageClassification) -> None:
        self._session.add(classification_to_orm(classification))
        await self._session.flush()

    async def get_by_id(
        self, classification_id: ClassificationId
    ) -> MessageClassification | None:
        orm = await self._session.get(MessageClassificationOrm, classification_id)
        return classification_to_domain(orm) if orm else None

    async def get_current_by_triage(
        self, triage_id: TriageId, classifier_kind: ClassifierKind
    ) -> MessageClassification | None:
        stmt = (
            select(MessageClassificationOrm)
            .where(
                MessageClassificationOrm.triage_id == triage_id,
                MessageClassificationOrm.classifier_kind == classifier_kind.value,
                MessageClassificationOrm.superseded_at.is_(None),
            )
            .order_by(MessageClassificationOrm.run_number.desc())
            .limit(1)
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return classification_to_domain(orm) if orm else None

    async def supersede_current(
        self,
        triage_id: TriageId,
        classifier_kind: ClassifierKind,
        superseded_at: datetime,
    ) -> None:
        stmt = (
            select(MessageClassificationOrm)
            .where(
                MessageClassificationOrm.triage_id == triage_id,
                MessageClassificationOrm.classifier_kind == classifier_kind.value,
                MessageClassificationOrm.superseded_at.is_(None),
            )
            .order_by(MessageClassificationOrm.run_number.desc())
            .limit(1)
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        if orm is not None:
            orm.superseded_at = superseded_at
            await self._session.flush()

    async def update(self, classification: MessageClassification) -> None:
        orm = await self._session.get(MessageClassificationOrm, classification.id)
        assert (
            orm is not None
        ), f"No stored classification with id {classification.id!r} to update"
        _copy_classification_to_orm(classification, orm)
        await self._session.flush()
