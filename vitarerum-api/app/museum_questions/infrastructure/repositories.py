"""SQLAlchemy adapter for the Museum Questions repository port."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.museum_questions.domain.models import MuseumQuestion, MuseumQuestionStatus
from app.museum_questions.infrastructure.models import MuseumQuestionRecord


def _to_domain(record: MuseumQuestionRecord) -> MuseumQuestion:
    return MuseumQuestion(
        id=record.id,
        requester_name=record.requester_name,
        requester_email=record.requester_email,
        subject=record.subject,
        message=record.message,
        created_at=record.created_at,
        status=MuseumQuestionStatus(record.status),
        answered_at=record.answered_at,
        answered_by=record.answered_by,
        answer_body=record.answer_body,
        answer_sent_at=record.answer_sent_at,
        out_of_scope_at=record.out_of_scope_at,
        out_of_scope_by=record.out_of_scope_by,
        out_of_scope_reason=record.out_of_scope_reason,
        out_of_scope_email_sent_at=record.out_of_scope_email_sent_at,
        closed_at=record.closed_at,
        closed_by=record.closed_by,
    )


def _apply(record: MuseumQuestionRecord, question: MuseumQuestion) -> None:
    record.requester_name = question.requester_name
    record.requester_email = question.requester_email
    record.subject = question.subject
    record.message = question.message
    record.status = question.status.value
    record.created_at = question.created_at
    record.answered_at = question.answered_at
    record.answered_by = question.answered_by
    record.answer_body = question.answer_body
    record.answer_sent_at = question.answer_sent_at
    record.out_of_scope_at = question.out_of_scope_at
    record.out_of_scope_by = question.out_of_scope_by
    record.out_of_scope_reason = question.out_of_scope_reason
    record.out_of_scope_email_sent_at = question.out_of_scope_email_sent_at
    record.closed_at = question.closed_at
    record.closed_by = question.closed_by


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

    async def get_by_id(self, question_id: str) -> MuseumQuestion | None:
        record = await self._session.get(MuseumQuestionRecord, question_id)
        return _to_domain(record) if record else None

    async def list(
        self,
        *,
        status: MuseumQuestionStatus | None,
        page: int,
        size: int,
    ) -> tuple[list[MuseumQuestion], int]:
        filters = []
        if status is not None:
            filters.append(MuseumQuestionRecord.status == status.value)

        total_stmt = select(func.count()).select_from(MuseumQuestionRecord)
        list_stmt = select(MuseumQuestionRecord)
        if filters:
            total_stmt = total_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = await self._session.scalar(total_stmt)
        result = await self._session.execute(
            list_stmt.order_by(MuseumQuestionRecord.created_at.asc())
            .offset(page * size)
            .limit(size)
        )
        return [_to_domain(r) for r in result.scalars()], int(total or 0)

    async def save(self, question: MuseumQuestion) -> None:
        record = await self._session.get(MuseumQuestionRecord, question.id)
        if record is None:
            raise LookupError(f"No museum question found with id {question.id}")
        _apply(record, question)
        await self._session.flush()
