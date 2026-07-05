"""SQLAlchemy adapter for the Museum Questions repository port."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.museum_questions.domain.models import MuseumQuestion
from app.museum_questions.infrastructure.models import MuseumQuestionRecord


class SqlAlchemyMuseumQuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, question: MuseumQuestion) -> None:
        self._session.add(
            MuseumQuestionRecord(
                id=question.id,
                requester_name=question.requester_name,
                requester_email=question.requester_email,
                subject=question.subject,
                message=question.message,
                status=question.status.value,
                created_at=question.created_at,
                answered_at=question.answered_at,
                answered_by=question.answered_by,
                answer_body=question.answer_body,
                answer_sent_at=question.answer_sent_at,
                out_of_scope_at=question.out_of_scope_at,
                out_of_scope_by=question.out_of_scope_by,
                out_of_scope_reason=question.out_of_scope_reason,
                out_of_scope_email_sent_at=question.out_of_scope_email_sent_at,
                closed_at=question.closed_at,
                closed_by=question.closed_by,
            )
        )
        await self._session.flush()
