"""SQLAlchemy adapter for the Museum Questions repository port."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.museum_questions.domain.models import MuseumQuestion, MuseumQuestionStatus
from app.museum_questions.infrastructure.models import MuseumQuestionRecord
from app.shared.field_encryption import FieldEncryptor

_REQUESTER_NAME = "museum_questions.requester_name"
_REQUESTER_EMAIL = "museum_questions.requester_email"
_REQUESTER_EMAIL_HASH = "museum_questions.requester_email_hash"
_SUBJECT = "museum_questions.subject"
_MESSAGE = "museum_questions.message"
_ANSWER_BODY = "museum_questions.answer_body"
_OUT_OF_SCOPE_REASON = "museum_questions.out_of_scope_reason"


def _to_domain(
    record: MuseumQuestionRecord, encryptor: FieldEncryptor
) -> MuseumQuestion:
    return MuseumQuestion(
        id=record.id,
        requester_name=encryptor.decrypt_text(record.requester_name, _REQUESTER_NAME)
        or "",
        requester_email=encryptor.decrypt_text(
            record.requester_email, _REQUESTER_EMAIL
        )
        or "",
        subject=encryptor.decrypt_text(record.subject, _SUBJECT) or "",
        message=encryptor.decrypt_text(record.message, _MESSAGE) or "",
        created_at=record.created_at,
        status=MuseumQuestionStatus(record.status),
        answered_at=record.answered_at,
        answered_by=record.answered_by,
        answer_body=encryptor.decrypt_text(record.answer_body, _ANSWER_BODY),
        answer_sent_at=record.answer_sent_at,
        out_of_scope_at=record.out_of_scope_at,
        out_of_scope_by=record.out_of_scope_by,
        out_of_scope_reason=encryptor.decrypt_text(
            record.out_of_scope_reason, _OUT_OF_SCOPE_REASON
        ),
        out_of_scope_email_sent_at=record.out_of_scope_email_sent_at,
        closed_at=record.closed_at,
        closed_by=record.closed_by,
    )


def _apply(
    record: MuseumQuestionRecord, question: MuseumQuestion, encryptor: FieldEncryptor
) -> None:
    record.requester_name = encryptor.encrypt_required_text(
        question.requester_name, _REQUESTER_NAME
    )
    record.requester_email = encryptor.encrypt_required_text(
        question.requester_email, _REQUESTER_EMAIL
    )
    record.requester_email_hash = encryptor.lookup_required_hash(
        question.requester_email, _REQUESTER_EMAIL_HASH
    )
    record.subject = encryptor.encrypt_required_text(question.subject, _SUBJECT)
    record.message = encryptor.encrypt_required_text(question.message, _MESSAGE)
    record.status = question.status.value
    record.created_at = question.created_at
    record.answered_at = question.answered_at
    record.answered_by = question.answered_by
    record.answer_body = encryptor.encrypt_text(question.answer_body, _ANSWER_BODY)
    record.answer_sent_at = question.answer_sent_at
    record.out_of_scope_at = question.out_of_scope_at
    record.out_of_scope_by = question.out_of_scope_by
    record.out_of_scope_reason = encryptor.encrypt_text(
        question.out_of_scope_reason, _OUT_OF_SCOPE_REASON
    )
    record.out_of_scope_email_sent_at = question.out_of_scope_email_sent_at
    record.closed_at = question.closed_at
    record.closed_by = question.closed_by


class SqlAlchemyMuseumQuestionRepository:
    def __init__(self, session: AsyncSession, encryptor: FieldEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    async def add(self, question: MuseumQuestion) -> None:
        record = MuseumQuestionRecord(
            id=question.id,
            status=question.status.value,
            created_at=question.created_at,
            answered_at=question.answered_at,
            answered_by=question.answered_by,
            answer_sent_at=question.answer_sent_at,
            out_of_scope_at=question.out_of_scope_at,
            out_of_scope_by=question.out_of_scope_by,
            out_of_scope_email_sent_at=question.out_of_scope_email_sent_at,
            closed_at=question.closed_at,
            closed_by=question.closed_by,
        )
        _apply(record, question, self._encryptor)
        self._session.add(record)
        await self._session.flush()

    async def get_by_id(self, question_id: str) -> MuseumQuestion | None:
        record = await self._session.get(MuseumQuestionRecord, question_id)
        return _to_domain(record, self._encryptor) if record else None

    async def list(
        self,
        *,
        status: MuseumQuestionStatus | None,
        requester_email: str | None,
        page: int,
        size: int,
    ) -> tuple[list[MuseumQuestion], int]:
        filters = []
        if status is not None:
            filters.append(MuseumQuestionRecord.status == status.value)
        if requester_email:
            filters.append(
                MuseumQuestionRecord.requester_email_hash
                == self._encryptor.lookup_hash(requester_email, _REQUESTER_EMAIL_HASH)
            )

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
        return [_to_domain(r, self._encryptor) for r in result.scalars()], int(
            total or 0
        )

    async def save(self, question: MuseumQuestion) -> None:
        record = await self._session.get(MuseumQuestionRecord, question.id)
        if record is None:
            raise LookupError(f"No museum question found with id {question.id}")
        _apply(record, question, self._encryptor)
        await self._session.flush()
