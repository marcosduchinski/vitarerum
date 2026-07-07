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


class MentionedObjectResponse(BaseModel):
    english: str
    portuguese: str


class ObjectTriageMatchResponse(BaseModel):
    english: str
    portuguese: str
    hits: list[ObjectHitResponse]


class TriageResponse(BaseModel):
    id: str
    questionId: str
    verdict: TriageVerdictValue
    isVisitRelated: bool
    mentionedObjects: list[MentionedObjectResponse]
    objectMatches: list[ObjectTriageMatchResponse]
    suggestedReply: str | None
    modelName: str
    createdAt: datetime
