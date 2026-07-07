"""Anti-corruption adapter over the Museum Questions published language.

Implements ``MuseumQuestionPort`` by calling ``app.museum_questions.public``
and mapping its DTO into this context's own ``QuestionView`` — the domain
never imports another bounded context's types directly.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_question_triage.domain.models import QuestionView
from app.museum_questions.public import get_question_summary


class MuseumQuestionAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_summary(self, question_id: str) -> QuestionView | None:
        summary = await get_question_summary(self._session, question_id)
        if summary is None:
            return None
        return QuestionView(
            id=summary.id,
            subject=summary.subject,
            message=summary.message,
            requester_email=summary.requester_email,
            status=summary.status,
        )
