"""Museum-question triage application service.

Orchestrates the pipeline: load the question via the ACL → classify it
(in/out of scope + mentioned objects, each named in English and Portuguese) →
either draft an out-of-scope reply or search the catalogue in both languages
for each mentioned object → persist the run.
``execute`` takes an ``Input`` dataclass, per the repo-wide convention.
Authorization (``require_staff``) is enforced by the route handler, matching
``app.ai.museum_narrative``'s convention — not duplicated here.

Also hosts the two staff-review use cases added by the refinements plan
(docs/plans/museum-questions-ai-triage-refinements-plan.md):
``OverrideTriageVerdict`` (contest the scope verdict) and
``SyncTriageSearchTerms`` (edit/add/remove extracted search terms and
re-search only what changed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.ai.museum_question_triage.domain.models import (
    MentionedObject,
    MentionedObjectOrigin,
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
    TriageNotFound,
    TriageNotInScope,
    TriageRepository,
    TriageTermValidationError,
)

if TYPE_CHECKING:
    from app.identity.public import Actor

MAX_OBJECT_QUERIES = 3
# How many hits to fetch per language before merging — not a display cap (the
# UI paginates client-side over the full merged list); just a sane ceiling so
# a very common term can't pull in an unbounded number of rows.
SEARCH_FETCH_LIMIT_PER_LANGUAGE = 100
# Staff-edited search terms are a deliberate, explicit action per term, so
# MAX_OBJECT_QUERIES (which only bounds the AI's own automatic extraction)
# does not apply to them — but the whole list still needs a sanity ceiling so
# one request can't trigger dozens of catalogue searches at once.
MAX_STAFF_SEARCH_TERMS = 10
_MAX_TERM_FIELD_LENGTH = 200


def _normalize_object_terms(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Trim, drop blank pairs, and deduplicate (case-insensitively, by the
    ``(portuguese, english)`` pair — not just Portuguese alone, since an
    imprecise translation could otherwise collapse two genuinely different
    objects that happen to share a Portuguese name). If only one language
    came back non-blank, the other falls back to it rather than being stored
    empty. Shared by the AI's own extraction (``_normalize_mentioned_objects``)
    and by staff-submitted term lists (``SyncTriageSearchTerms``) — this
    function only deals in plain text pairs, callers decide provenance."""
    seen: set[tuple[str, str]] = set()
    normalized: list[tuple[str, str]] = []
    for english_raw, portuguese_raw in pairs:
        english = english_raw.strip()
        portuguese = portuguese_raw.strip()
        if not english and not portuguese:
            continue
        english = english or portuguese
        portuguese = portuguese or english
        key = (portuguese.casefold(), english.casefold())
        if key in seen:
            continue
        seen.add(key)
        normalized.append((english, portuguese))
    return normalized


def _normalize_mentioned_objects(
    items: list[MentionedObject],
) -> list[MentionedObject]:
    """Apply ``_normalize_object_terms`` to the AI's raw extraction. Untrusted
    LLM output may otherwise contain blank/whitespace-only entries or
    repeats, wasting catalogue searches and polluting the persisted record."""
    pairs = _normalize_object_terms([(item.english, item.portuguese) for item in items])
    return [
        MentionedObject(english=english, portuguese=portuguese)
        for english, portuguese in pairs
    ]


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


async def _search_both_languages(
    object_search: ObjectSearchPort, caller: Actor, *, english: str, portuguese: str
) -> tuple[list[ObjectHitView], list[str]]:
    """Search the catalogue in Portuguese (the primary language) and, if the
    English name differs, also in English — merging and deduplicating the
    results. Skips the second search when both names are identical (e.g. a
    proper noun the model didn't translate), to avoid a wasted query. Returns
    the merged hits alongside which language codes were actually searched
    (["pt"] or ["pt", "en"]), surfaced to staff as part of search-strategy
    transparency."""
    portuguese_hits = await object_search.search(
        caller, portuguese, SEARCH_FETCH_LIMIT_PER_LANGUAGE
    )
    if english.casefold() == portuguese.casefold():
        return portuguese_hits, ["pt"]
    english_hits = await object_search.search(
        caller, english, SEARCH_FETCH_LIMIT_PER_LANGUAGE
    )
    return _merge_hits(portuguese_hits, english_hits), ["pt", "en"]


@dataclass(frozen=True, slots=True)
class TriageMuseumQuestionInput:
    question_id: str
    caller: Actor


@dataclass(frozen=True, slots=True)
class GetLatestTriageInput:
    question_id: str


@dataclass(frozen=True, slots=True)
class OverrideTriageVerdictInput:
    question_id: str
    verdict: TriageVerdict
    caller: Actor


@dataclass(frozen=True, slots=True)
class SyncTriageSearchTermsInput:
    question_id: str
    terms: list[
        tuple[str, str]
    ]  # (english, portuguese) pairs, no origin — see routes.py
    caller: Actor


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
                f"No museum question found with id {data.question_id!r}"
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
                hits, languages_searched = await _search_both_languages(
                    self._object_search,
                    data.caller,
                    english=obj.english,
                    portuguese=obj.portuguese,
                )
                object_matches.append(
                    ObjectTriageMatch(
                        english=obj.english,
                        portuguese=obj.portuguese,
                        hits=hits,
                        languages_searched=languages_searched,
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


class GetLatestTriage:
    """Return the most recent stored triage for a question, or ``None`` if
    triage was never run."""

    def __init__(self, repository: TriageRepository) -> None:
        self._repository = repository

    async def execute(self, data: GetLatestTriageInput) -> MessageTriage | None:
        return await self._repository.get_latest_by_question(data.question_id)


class OverrideTriageVerdict:
    """Staff contesting the AI's scope verdict (checkpoint 1 of the
    refinements plan). Never rewrites ``verdict`` itself — only stamps
    ``staff_override_verdict``. If the effective verdict becomes
    OUT_OF_SCOPE and no reply was drafted yet (the AI's original run was
    IN_SCOPE, so it never ran ``draft_out_of_scope_reply``), one is generated
    now, lazily, and kept even if the staff flips back to IN_SCOPE later —
    the presentation layer decides whether to render it, not the domain."""

    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        model: TriageModelPort,
        repository: TriageRepository,
    ) -> None:
        self._museum_question = museum_question
        self._model = model
        self._repository = repository

    async def execute(self, data: OverrideTriageVerdictInput) -> MessageTriage:
        triage = await self._repository.get_latest_by_question(data.question_id)
        if triage is None:
            raise TriageNotFound(
                f"No triage has been run for question {data.question_id!r} yet."
            )

        triage.override_verdict(data.verdict, by=data.caller.email)

        if (
            triage.effective_verdict is TriageVerdict.OUT_OF_SCOPE
            and triage.suggested_reply is None
        ):
            question = await self._museum_question.get_summary(data.question_id)
            if question is None:
                raise QuestionNotFound(
                    f"No museum question found with id {data.question_id!r}"
                )
            triage.suggested_reply = await self._model.draft_out_of_scope_reply(
                question.message
            )

        await self._repository.update(triage)
        return triage


class SyncTriageSearchTerms:
    """Staff editing/adding/removing extracted search terms (checkpoint 2 of
    the refinements plan) — a full reconciliation of the term list, not one
    endpoint per term. Diffs by the ``(portuguese, english)`` key against
    what's persisted: a key missing after the edit is dropped, a key present
    only after the edit is searched fresh (this covers both a genuinely new
    term and an edited one — editing changes the key, so there is no third
    "in-place edit" case to detect), and a key present in both is left
    untouched (no redundant re-search)."""

    def __init__(
        self,
        object_search: ObjectSearchPort,
        repository: TriageRepository,
    ) -> None:
        self._object_search = object_search
        self._repository = repository

    async def execute(self, data: SyncTriageSearchTermsInput) -> MessageTriage:
        triage = await self._repository.get_latest_by_question(data.question_id)
        if triage is None:
            raise TriageNotFound(
                f"No triage has been run for question {data.question_id!r} yet."
            )
        if triage.effective_verdict is not TriageVerdict.IN_SCOPE:
            raise TriageNotInScope(
                "Search terms can only be edited while the triage is in scope."
            )

        # Normalize (trim/drop-blank/dedupe) before validating: a field with
        # surrounding whitespace that fits within the limit once trimmed must
        # not be rejected for its raw, untrimmed length.
        normalized_pairs = _normalize_object_terms(data.terms)
        for english, portuguese in normalized_pairs:
            if (
                len(english) > _MAX_TERM_FIELD_LENGTH
                or len(portuguese) > _MAX_TERM_FIELD_LENGTH
            ):
                raise TriageTermValidationError(
                    f"Search term fields cannot exceed {_MAX_TERM_FIELD_LENGTH} "
                    "characters."
                )
        if len(normalized_pairs) > MAX_STAFF_SEARCH_TERMS:
            raise TriageTermValidationError(
                f"No more than {MAX_STAFF_SEARCH_TERMS} search terms are allowed."
            )

        existing_terms_by_key = {
            (obj.portuguese.casefold(), obj.english.casefold()): obj
            for obj in triage.mentioned_objects
        }
        existing_matches_by_key = {
            (match.portuguese.casefold(), match.english.casefold()): match
            for match in triage.object_matches
        }

        new_terms: list[MentionedObject] = []
        new_matches: list[ObjectTriageMatch] = []
        for english, portuguese in normalized_pairs:
            key = (portuguese.casefold(), english.casefold())
            existing_term = existing_terms_by_key.get(key)
            if existing_term is not None:
                new_terms.append(existing_term)
                existing_match = existing_matches_by_key.get(key)
                if existing_match is not None:
                    new_matches.append(existing_match)
                continue

            new_terms.append(
                MentionedObject(
                    english=english,
                    portuguese=portuguese,
                    origin=MentionedObjectOrigin.STAFF,
                )
            )
            hits, languages_searched = await _search_both_languages(
                self._object_search, data.caller, english=english, portuguese=portuguese
            )
            new_matches.append(
                ObjectTriageMatch(
                    english=english,
                    portuguese=portuguese,
                    hits=hits,
                    languages_searched=languages_searched,
                )
            )

        triage.mentioned_objects = new_terms
        triage.object_matches = new_matches
        await self._repository.update(triage)
        return triage
