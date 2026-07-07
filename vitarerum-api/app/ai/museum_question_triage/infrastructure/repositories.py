"""SQLAlchemy repository for the message-triage aggregate.

Append-only: each run is one row, read back as the latest run for a question
(newest first).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_question_triage.domain.models import (
    MentionedObject,
    MessageTriage,
    ObjectHitView,
    ObjectTriageMatch,
    TriageId,
    TriageVerdict,
)
from app.ai.museum_question_triage.infrastructure.models import MessageTriageOrm


def _mentioned_objects_to_json(
    items: list[MentionedObject],
) -> list[dict[str, Any]]:
    return [{"english": item.english, "portuguese": item.portuguese} for item in items]


def _mentioned_objects_from_json(
    raw: list[dict[str, Any]],
) -> list[MentionedObject]:
    return [MentionedObject(**item) for item in raw]


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
        }
        for match in matches
    ]


def _object_matches_from_json(
    raw: list[dict[str, Any]],
) -> list[ObjectTriageMatch]:
    return [
        ObjectTriageMatch(
            english=item["english"],
            portuguese=item["portuguese"],
            hits=[ObjectHitView(**hit) for hit in item["hits"]],
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
    )


class SqlAlchemyTriageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, triage: MessageTriage) -> None:
        self._session.add(triage_to_orm(triage))
        await self._session.flush()

    async def get_latest_by_question(
        self, question_id: str
    ) -> MessageTriage | None:
        stmt = (
            select(MessageTriageOrm)
            .where(MessageTriageOrm.question_id == question_id)
            .order_by(MessageTriageOrm.created_at.desc())
            .limit(1)
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return triage_to_domain(orm) if orm else None
