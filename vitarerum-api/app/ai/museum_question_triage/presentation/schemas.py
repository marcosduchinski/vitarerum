"""Pydantic response shapes for the museum-question triage endpoints, in
camelCase to match the frontend's ``MuseumQuestionTriage`` model directly."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

TriageVerdictValue = Literal["IN_SCOPE", "OUT_OF_SCOPE"]
ClassificationStatusValue = Literal["NOT_REQUESTED", "PENDING", "COMPLETED", "FAILED"]
ClassificationOutcomeValue = Literal["CATEGORIZED", "UNCLEAR"]
ClassificationQualityValue = Literal["FULL", "DEGRADED"]
ClassifierKindValue = Literal["LLM", "EMBEDDING", "CASCADE"]
ClassificationScoreSourceValue = Literal["LLM", "EMBEDDING"]
EmbeddingPrototypeAggregationValue = Literal["MEAN", "MAX_EXAMPLE", "HYBRID"]
UseCategoryValue = Literal[
    "EXHIBITION",
    "PUBLISHING_IMAGES",
    "LEARNING_EVENTS",
    "ANSWERING_ENQUIRIES",
    "RESEARCH_PROJECTS",
    "OPERATING_MACHINERY",
    "PLAYING_INSTRUMENTS",
    "FILMING",
    "INSPIRING_NEW_WORK",
]


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


class UseCategoryScoreResponse(BaseModel):
    category: str
    confidence: float
    source: ClassificationScoreSourceValue


class UseCategoryClassificationResponse(BaseModel):
    status: ClassificationStatusValue
    outcome: ClassificationOutcomeValue | None
    quality: ClassificationQualityValue | None
    classifierKind: ClassifierKindValue | None
    classifierModel: str | None
    classifierVersion: str | None
    assignedCategories: list[UseCategoryScoreResponse]
    categoryScores: list[UseCategoryScoreResponse]
    classifiedAt: datetime | None
    error: str | None


class UseCategoryClassificationAuditResponse(UseCategoryClassificationResponse):
    id: str
    triageId: str
    runNumber: int
    supersededAt: datetime | None
    metadata: dict[str, Any]
    createdAt: datetime


class UseCategoryClassificationAuditListResponse(BaseModel):
    triageId: str
    classifications: list[UseCategoryClassificationAuditResponse]


class EmbeddingPrototypeVersionResponse(BaseModel):
    id: str
    version: str
    embeddingModel: str
    aggregationMethod: EmbeddingPrototypeAggregationValue
    thresholdProfile: dict[str, Any]
    exampleIds: list[str]
    prototypes: dict[str, list[list[float]]]
    metrics: dict[str, Any]
    createdAt: datetime
    promotedAt: datetime | None
    retiredAt: datetime | None


class GenerateEmbeddingPrototypeVersionRequest(BaseModel):
    version: str
    aggregationMethod: EmbeddingPrototypeAggregationValue = "MAX_EXAMPLE"
    promote: bool = False


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
    useCategoryClassification: UseCategoryClassificationResponse


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


class UseCategoryCorrectionRequest(BaseModel):
    categories: list[UseCategoryValue]
    humanOutcome: ClassificationOutcomeValue
