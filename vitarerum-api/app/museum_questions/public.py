"""Museum Questions published language (Open Host Service).

The ONLY ``museum_questions`` module other bounded contexts may import —
enforced by import-linter. Exposes a deliberately narrow read-only view of a
question for future downstream contexts without allowing access to internals.
Mirrors the ``app.ai.museum_narrative.public`` pattern (lazy infra import inside
the function body).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class QuestionSummaryView:
    id: str
    subject: str
    message: str
    requester_email: str
    status: str


async def get_question_summary(
    session: AsyncSession, question_id: str
) -> QuestionSummaryView | None:
    """Return a read-only summary of a museum question, or ``None`` if no
    question with ``question_id`` exists."""
    from app.config import settings
    from app.museum_questions.infrastructure.repositories import (
        SqlAlchemyMuseumQuestionRepository,
    )
    from app.shared.field_encryption import FieldEncryptor

    encryptor = FieldEncryptor.from_base64(settings.db_field_encryption_key)
    question = await SqlAlchemyMuseumQuestionRepository(session, encryptor).get_by_id(
        question_id
    )
    if question is None:
        return None
    return QuestionSummaryView(
        id=question.id,
        subject=question.subject,
        message=question.message,
        requester_email=question.requester_email,
        status=question.status.value,
    )


__all__ = ["QuestionSummaryView", "get_question_summary"]
