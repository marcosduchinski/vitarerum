"""Museum-question triage application service.

Orchestrates the pipeline: load the question via the ACL → classify it
(in/out of scope + mentioned objects, each named in English and Portuguese) →
either draft an out-of-scope reply or search the catalogue in both languages
for each mentioned object → persist the run.
``execute`` takes an ``Input`` dataclass, per the repo-wide convention.
Authorization (``require_staff``) is enforced by the route handler, matching
``app.ai.museum_narrative``'s convention — not duplicated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.ai.museum_question_triage.domain.models import (
    MentionedObject,
    MessageTriage,
    ObjectHitView,
    ObjectTriageMatch,
    TriageVerdict,
)
from app.ai.museum_question_triage.domain.ports import (
    MuseumQuestionPort,
    ObjectSearchPort,
    QuestionNotFound,
    TriageModelPort,
    TriageRepository,
)

if TYPE_CHECKING:
    from app.identity.public import Actor

MAX_OBJECT_QUERIES = 3
# How many hits to fetch per language before merging — not a display cap (the
# UI paginates client-side over the full merged list); just a sane ceiling so
# a very common term can't pull in an unbounded number of rows.
SEARCH_FETCH_LIMIT_PER_LANGUAGE = 100


def _normalize_mentioned_objects(
    items: list[MentionedObject],
) -> list[MentionedObject]:
    """Trim, drop blank pairs, and deduplicate (case-insensitively, by the
    ``(portuguese, english)`` pair — not just Portuguese alone, since an
    imprecise translation could otherwise collapse two genuinely different
    objects that happen to share a Portuguese name) the objects the model
    extracted. Untrusted LLM output may otherwise contain blank/whitespace-
    only entries or repeats, wasting catalogue searches and polluting the
    persisted record. If only one language came back non-blank, the other
    falls back to it rather than being stored empty."""
    seen: set[tuple[str, str]] = set()
    normalized: list[MentionedObject] = []
    for raw in items:
        english = raw.english.strip()
        portuguese = raw.portuguese.strip()
        if not english and not portuguese:
            continue
        english = english or portuguese
        portuguese = portuguese or english
        key = (portuguese.casefold(), english.casefold())
        if key in seen:
            continue
        seen.add(key)
        normalized.append(MentionedObject(english=english, portuguese=portuguese))
    return normalized


def _merge_hits(
    primary: list[ObjectHitView], secondary: list[ObjectHitView]
) -> list[ObjectHitView]:
    """Merge two search result lists (Portuguese-first), dropping duplicates
    so a term matched by both languages isn't shown twice. Not truncated
    further here — each side is already bounded by
    ``SEARCH_FETCH_LIMIT_PER_LANGUAGE``, and the full merged list is what gets
    persisted; the UI paginates over it client-side. Keyed by collection +
    file + highlight (not just collection + file) so two distinct rows in the
    same source file — e.g. one matched by the Portuguese search, another by
    the English one — aren't mistaken for the same hit."""
    seen: set[tuple[str, str, str]] = set()
    merged: list[ObjectHitView] = []
    for hit in (*primary, *secondary):
        key = (hit.collection_id, hit.file_name, hit.highlight)
        if key in seen:
            continue
        seen.add(key)
        merged.append(hit)
    return merged


@dataclass(frozen=True, slots=True)
class TriageMuseumQuestionInput:
    question_id: str
    caller: Actor


@dataclass(frozen=True, slots=True)
class GetLatestTriageInput:
    question_id: str


class TriageMuseumQuestion:
    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        model: TriageModelPort,
        object_search: ObjectSearchPort,
        repository: TriageRepository,
        model_name: str,
    ) -> None:
        self._museum_question = museum_question
        self._model = model
        self._object_search = object_search
        self._repository = repository
        self._model_name = model_name

    async def execute(self, data: TriageMuseumQuestionInput) -> MessageTriage:
        question = await self._museum_question.get_summary(data.question_id)
        if question is None:
            raise QuestionNotFound(
                f"No museum question found with id {data.question_id}"
            )

        classification = await self._model.classify(question.message)
        verdict = (
            TriageVerdict.IN_SCOPE
            if classification.is_visit_related
            else TriageVerdict.OUT_OF_SCOPE
        )
        mentioned_objects = _normalize_mentioned_objects(
            classification.mentioned_objects
        )

        suggested_reply: str | None = None
        object_matches: list[ObjectTriageMatch] = []
        if verdict is TriageVerdict.OUT_OF_SCOPE:
            suggested_reply = await self._model.draft_out_of_scope_reply(
                question.message
            )
        else:
            for obj in mentioned_objects[:MAX_OBJECT_QUERIES]:
                hits = await self._search_both_languages(data.caller, obj)
                object_matches.append(
                    ObjectTriageMatch(
                        english=obj.english, portuguese=obj.portuguese, hits=hits
                    )
                )

        record = MessageTriage.create(
            question_id=data.question_id,
            verdict=verdict,
            is_visit_related=classification.is_visit_related,
            mentioned_objects=mentioned_objects,
            object_matches=object_matches,
            suggested_reply=suggested_reply,
            llm_model=self._model_name,
        )
        await self._repository.add(record)
        return record

    async def _search_both_languages(
        self, caller: Actor, obj: MentionedObject
    ) -> list[ObjectHitView]:
        """Search the catalogue in Portuguese (the primary language) and, if
        the English name differs, also in English — merging and deduplicating
        the results. Skips the second search when both names are identical
        (e.g. a proper noun the model didn't translate), to avoid a wasted
        query."""
        portuguese_hits = await self._object_search.search(
            caller, obj.portuguese, SEARCH_FETCH_LIMIT_PER_LANGUAGE
        )
        if obj.english.casefold() == obj.portuguese.casefold():
            return portuguese_hits
        english_hits = await self._object_search.search(
            caller, obj.english, SEARCH_FETCH_LIMIT_PER_LANGUAGE
        )
        return _merge_hits(portuguese_hits, english_hits)


class GetLatestTriage:
    """Return the most recent stored triage for a question, or ``None`` if
    triage was never run."""

    def __init__(self, repository: TriageRepository) -> None:
        self._repository = repository

    async def execute(self, data: GetLatestTriageInput) -> MessageTriage | None:
        return await self._repository.get_latest_by_question(data.question_id)
