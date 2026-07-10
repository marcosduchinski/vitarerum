"""Pydantic response shapes for the museum-question triage endpoints, in
camelCase to match the frontend's ``MuseumQuestionTriage`` model directly."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TriageVerdictValue = Literal["IN_SCOPE", "OUT_OF_SCOPE"]


class ObjectHitResponse(BaseModel):
    collectionId: str
    collectionName: str
    fileName: str
    highlight: str


MentionedObjectOriginValue = Literal["AI", "STAFF"]


class MentionedObjectResponse(BaseModel):
    english: str
    portuguese: str
    origin: MentionedObjectOriginValue


class ObjectTriageMatchResponse(BaseModel):
    english: str
    portuguese: str
    hits: list[ObjectHitResponse]
    languagesSearched: list[str]


class TriageResponse(BaseModel):
    id: str
    questionId: str
    verdict: TriageVerdictValue
    effectiveVerdict: TriageVerdictValue
    staffOverrideVerdict: TriageVerdictValue | None
    isVisitRelated: bool
    mentionedObjects: list[MentionedObjectResponse]
    objectMatches: list[ObjectTriageMatchResponse]
    suggestedReply: str | None
    searchStrategy: str | None
    modelName: str
    createdAt: datetime


class OverrideTriageVerdictRequest(BaseModel):
    verdict: TriageVerdictValue


class TriageSearchTermRequest(BaseModel):
    english: str
    portuguese: str


class TriageSearchTermsRequest(BaseModel):
    """Deliberately has no ``origin`` field — provenance is computed by the
    backend from the diff against what's persisted, never accepted as
    client input (a client could otherwise forge a term's origin)."""

    terms: list[TriageSearchTermRequest]
