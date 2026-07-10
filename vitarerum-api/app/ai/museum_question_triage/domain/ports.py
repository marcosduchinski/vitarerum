"""Driven ports (hexagonal) and error vocabulary for the museum-question
triage context.

``TriageModelPort`` is implemented by the local Ollama adapter;
``MuseumQuestionPort`` by an ACL over ``app.museum_questions.public``;
``ObjectSearchPort`` by an ACL over the Collection Object Index's
``SearchCollectionObjects`` use case. The application depends only on these
Protocols.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.ai.museum_question_triage.domain.models import (
        MessageTriage,
        ObjectHitView,
        QuestionView,
        TriageClassification,
    )
    from app.identity.public import Actor


class QuestionNotFound(Exception):
    """No museum question matches the requested id."""


class ModelUnavailable(Exception):
    """The triage model could not be reached."""


class ModelTimeout(Exception):
    """The triage model did not respond in time."""


class TriageNotFound(Exception):
    """No triage run exists yet for the requested question."""


class TriageNotInScope(Exception):
    """The requested action requires the triage's effective verdict to be
    IN_SCOPE (e.g. editing search terms while OUT_OF_SCOPE)."""


class TriageTermValidationError(Exception):
    """A staff-submitted search-term list violates a validation rule (a
    field too long, or too many terms)."""


class TriageModelPort(Protocol):
    """Run the local LLM. Raises :class:`ModelUnavailable` / :class:`ModelTimeout`."""

    async def classify(self, message: str) -> TriageClassification: ...

    async def draft_out_of_scope_reply(self, message: str) -> str: ...


class MuseumQuestionPort(Protocol):
    """Reads a museum question through the published language ACL."""

    async def get_summary(self, question_id: str) -> QuestionView | None: ...


class ObjectSearchPort(Protocol):
    """Searches the collection catalogue through the Collection Object Index
    ACL. ``limit`` bounds how many hits are returned per query term."""

    async def search(
        self, caller: Actor, query: str, limit: int
    ) -> list[ObjectHitView]: ...


class TriageRepository(Protocol):
    """Persists and reads back triage runs."""

    async def add(self, triage: MessageTriage) -> None: ...

    async def get_latest_by_question(
        self, question_id: str
    ) -> MessageTriage | None: ...

    async def update(self, triage: MessageTriage) -> None:
        """Persist in-place revisions to an already-stored triage run (staff
        override of the verdict, or a reconciled search-term list) — as
        opposed to ``add``, which only creates a brand new run. Last-write-
        wins: no optimistic-concurrency check (accepted MVP limitation)."""
        ...
