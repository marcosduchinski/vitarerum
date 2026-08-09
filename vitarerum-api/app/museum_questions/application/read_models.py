"""Application read models for Museum Questions.

Plain DTOs used by query use cases. They are not ORM or Pydantic models.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.public import PermissionView
from app.museum_questions.domain.models import MuseumQuestion


@dataclass(frozen=True, slots=True)
class MuseumQuestionListItem:
    question: MuseumQuestion
    attachment_count: int
    assigned_to: PermissionView | None = None
