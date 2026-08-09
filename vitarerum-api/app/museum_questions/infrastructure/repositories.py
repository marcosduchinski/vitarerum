"""SQLAlchemy adapter for the Museum Questions repository port."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.museum_questions.application.read_models import MuseumQuestionListItem
from app.museum_questions.domain.models import (
    MuseumQuestion,
    MuseumQuestionAttachment,
    MuseumQuestionStatus,
)
from app.museum_questions.infrastructure.models import (
    MuseumQuestionAttachmentRecord,
    MuseumQuestionRecord,
)
from app.shared.field_encryption import FieldEncryptor

_REQUESTER_NAME = "museum_questions.requester_name"
_REQUESTER_EMAIL = "museum_questions.requester_email"
_REQUESTER_EMAIL_HASH = "museum_questions.requester_email_hash"
_SUBJECT = "museum_questions.subject"
_MESSAGE = "museum_questions.message"
_ANSWER_BODY = "museum_questions.answer_body"
_OUT_OF_SCOPE_REASON = "museum_questions.out_of_scope_reason"
_ATTACHMENT_FILE_NAME = "museum_question_attachments.file_name"


def _to_domain(
    record: MuseumQuestionRecord,
    encryptor: FieldEncryptor,
    attachments: list[MuseumQuestionAttachmentRecord] | None = None,
) -> MuseumQuestion:
    attachment_records = attachments or []
    return MuseumQuestion(
        id=record.id,
        requester_name=encryptor.decrypt_text(record.requester_name, _REQUESTER_NAME)
        or "",
        requester_email=encryptor.decrypt_text(record.requester_email, _REQUESTER_EMAIL)
        or "",
        subject=encryptor.decrypt_text(record.subject, _SUBJECT) or "",
        message=encryptor.decrypt_text(record.message, _MESSAGE) or "",
        created_at=record.created_at,
        response_due_at=record.response_due_at,
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
        assigned_to=record.assigned_to,
        response_overdue_notified_at=record.response_overdue_notified_at,
        attachments=[
            MuseumQuestionAttachment(
                id=attachment.id,
                question_id=attachment.question_id,
                file_name=encryptor.decrypt_text(
                    attachment.file_name, _ATTACHMENT_FILE_NAME
                )
                or "",
                file_reference=attachment.file_reference,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                created_at=attachment.created_at,
                sort_order=attachment.sort_order,
            )
            for attachment in sorted(
                attachment_records,
                key=lambda item: (item.sort_order, item.created_at, item.id),
            )
        ],
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
    record.response_due_at = question.response_due_at
    record.response_overdue_notified_at = question.response_overdue_notified_at
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
    record.assigned_to = question.assigned_to
    record.attachments = [
        MuseumQuestionAttachmentRecord(
            id=attachment.id,
            question_id=attachment.question_id,
            file_name=encryptor.encrypt_required_text(
                attachment.file_name, _ATTACHMENT_FILE_NAME
            ),
            file_reference=attachment.file_reference,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
            created_at=attachment.created_at,
            sort_order=attachment.sort_order,
        )
        for attachment in question.attachments or []
    ]


class SqlAlchemyMuseumQuestionRepository:
    def __init__(self, session: AsyncSession, encryptor: FieldEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    async def add(self, question: MuseumQuestion) -> None:
        record = MuseumQuestionRecord(
            id=question.id,
            status=question.status.value,
            created_at=question.created_at,
            response_due_at=question.response_due_at,
            response_overdue_notified_at=question.response_overdue_notified_at,
            answered_at=question.answered_at,
            answered_by=question.answered_by,
            answer_sent_at=question.answer_sent_at,
            out_of_scope_at=question.out_of_scope_at,
            out_of_scope_by=question.out_of_scope_by,
            out_of_scope_email_sent_at=question.out_of_scope_email_sent_at,
            closed_at=question.closed_at,
            closed_by=question.closed_by,
            assigned_to=question.assigned_to,
        )
        _apply(record, question, self._encryptor)
        self._session.add(record)
        await self._session.flush()

    async def get_by_id(self, question_id: str) -> MuseumQuestion | None:
        result = await self._session.execute(
            select(MuseumQuestionRecord)
            .options(selectinload(MuseumQuestionRecord.attachments))
            .where(MuseumQuestionRecord.id == question_id)
        )
        record = result.scalar_one_or_none()
        return (
            _to_domain(record, self._encryptor, record.attachments) if record else None
        )

    async def list(
        self,
        *,
        status: MuseumQuestionStatus | None,
        requester_email: str | None,
        assigned_to: str | None,
        unassigned_only: bool,
        page: int,
        size: int,
    ) -> tuple[list[MuseumQuestionListItem], int]:
        filters = []
        if status is not None:
            filters.append(MuseumQuestionRecord.status == status.value)
        if requester_email:
            filters.append(
                MuseumQuestionRecord.requester_email_hash
                == self._encryptor.lookup_hash(requester_email, _REQUESTER_EMAIL_HASH)
            )
        if assigned_to:
            filters.append(MuseumQuestionRecord.assigned_to == assigned_to)
        if unassigned_only:
            filters.append(MuseumQuestionRecord.assigned_to.is_(None))

        total_stmt = select(func.count()).select_from(MuseumQuestionRecord)
        attachment_counts = (
            select(
                MuseumQuestionAttachmentRecord.question_id.label("question_id"),
                func.count(MuseumQuestionAttachmentRecord.id).label("attachment_count"),
            )
            .group_by(MuseumQuestionAttachmentRecord.question_id)
            .subquery()
        )
        list_stmt = select(
            MuseumQuestionRecord,
            func.coalesce(attachment_counts.c.attachment_count, 0),
        ).outerjoin(
            attachment_counts,
            MuseumQuestionRecord.id == attachment_counts.c.question_id,
        )
        if filters:
            total_stmt = total_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = await self._session.scalar(total_stmt)
        result = await self._session.execute(
            list_stmt.order_by(MuseumQuestionRecord.created_at.asc())
            .offset(page * size)
            .limit(size)
        )
        return [
            MuseumQuestionListItem(
                question=_to_domain(record, self._encryptor, []),
                attachment_count=int(attachment_count or 0),
            )
            for record, attachment_count in result.all()
        ], int(total or 0)

    async def list_unanswered_due_for_overdue_notification(
        self, *, now: datetime, limit: int
    ) -> Sequence[MuseumQuestion]:
        result = await self._session.execute(
            select(MuseumQuestionRecord)
            .where(
                MuseumQuestionRecord.status == MuseumQuestionStatus.SUBMITTED.value,
                MuseumQuestionRecord.answered_at.is_(None),
                MuseumQuestionRecord.response_due_at <= now,
                MuseumQuestionRecord.response_overdue_notified_at.is_(None),
            )
            .order_by(
                MuseumQuestionRecord.response_due_at.asc(),
                MuseumQuestionRecord.created_at.asc(),
                MuseumQuestionRecord.id.asc(),
            )
            .limit(limit)
        )
        return [_to_domain(record, self._encryptor, []) for record in result.scalars()]

    async def save(self, question: MuseumQuestion) -> None:
        result = await self._session.execute(
            select(MuseumQuestionRecord)
            .options(selectinload(MuseumQuestionRecord.attachments))
            .where(MuseumQuestionRecord.id == question.id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise LookupError(f"No museum question found with id {question.id}")
        _apply(record, question, self._encryptor)
        await self._session.flush()
