"""Pydantic schemas for the Collection Data Sources management API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CuratorResponse(BaseModel):
    permissionId: str
    name: str | None = None
    email: str | None = None
    assignedAt: datetime


class CollectionResponse(BaseModel):
    id: str
    name: str
    curators: list[CuratorResponse]
    documentCount: int
    manageable: bool


class CreateCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CuratorCandidateResponse(BaseModel):
    permissionId: str
    name: str
    email: str


class SourceDocumentResponse(BaseModel):
    id: str
    collectionId: str
    fileName: str
    sourceKind: str
    status: str
    errorMessage: str | None = None
    rowCount: int | None = None
    uploadedAt: datetime
    indexedAt: datetime | None = None


class AssignCuratorRequest(BaseModel):
    permissionId: str


class SearchableCollectionResponse(BaseModel):
    id: str
    name: str


class SearchHitResponse(BaseModel):
    collectionId: str
    collectionName: str
    sourceDocumentId: str
    fileName: str
    sheet: str
    rowNumber: int
    cells: dict[str, str]
    highlight: str


class SearchResultResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[SearchHitResponse]
