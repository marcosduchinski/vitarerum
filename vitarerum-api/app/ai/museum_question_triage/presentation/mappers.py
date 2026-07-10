"""Domain → DTO mapping for the museum-question triage endpoints."""

from __future__ import annotations

from app.ai.museum_question_triage.application.search_strategy import (
    SEARCH_STRATEGY_DESCRIPTION,
)
from app.ai.museum_question_triage.domain.models import MessageTriage, TriageVerdict
from app.ai.museum_question_triage.presentation.schemas import (
    MentionedObjectResponse,
    ObjectHitResponse,
    ObjectTriageMatchResponse,
    TriageResponse,
)


def triage_response(triage: MessageTriage) -> TriageResponse:
    return TriageResponse(
        id=triage.id,
        questionId=triage.question_id,
        verdict=triage.verdict.value,
        effectiveVerdict=triage.effective_verdict.value,
        staffOverrideVerdict=(
            triage.staff_override_verdict.value
            if triage.staff_override_verdict
            else None
        ),
        isVisitRelated=triage.is_visit_related,
        mentionedObjects=[
            MentionedObjectResponse(
                english=obj.english, portuguese=obj.portuguese, origin=obj.origin.value
            )
            for obj in triage.mentioned_objects
        ],
        objectMatches=[
            ObjectTriageMatchResponse(
                english=match.english,
                portuguese=match.portuguese,
                hits=[
                    ObjectHitResponse(
                        collectionId=hit.collection_id,
                        collectionName=hit.collection_name,
                        fileName=hit.file_name,
                        highlight=hit.highlight,
                    )
                    for hit in match.hits
                ],
                languagesSearched=list(match.languages_searched),
            )
            for match in triage.object_matches
        ],
        suggestedReply=triage.suggested_reply,
        searchStrategy=(
            SEARCH_STRATEGY_DESCRIPTION
            if triage.effective_verdict is TriageVerdict.IN_SCOPE
            else None
        ),
        modelName=triage.llm_model,
        createdAt=triage.created_at,
    )
