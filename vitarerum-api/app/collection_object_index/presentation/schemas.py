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
    areaId: str
    areaName: str
    name: str
    curators: list[CuratorResponse]
    documentCount: int
    manageable: bool


class CreateCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    areaId: str


class UpdateCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MoveCollectionToAreaRequest(BaseModel):
    areaId: str


class CollectionAreaResponse(BaseModel):
    id: str
    name: str
    collectionCount: int


class CreateCollectionAreaRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateCollectionAreaRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CuratorCandidateResponse(BaseModel):
    permissionId: str
    name: str
    email: str


class SourceDocumentObjectMappingResponse(BaseModel):
    inventoryNumberColumn: str
    displayTitleColumn: str
    displayTitleColumns: list[str] = Field(default_factory=list)
    objectNameColumn: str | None = None
    descriptionColumns: list[str] = Field(default_factory=list)
    searchableColumns: list[str] = Field(default_factory=list)


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
    contentMatchesSearchableColumns: bool = True
    objectMapping: SourceDocumentObjectMappingResponse | None = None


class UpdateSourceDocumentObjectMappingRequest(BaseModel):
    inventoryNumberColumn: str = Field(min_length=1, max_length=255)
    displayTitleColumn: str | None = Field(default=None, min_length=1, max_length=255)
    displayTitleColumns: list[str] = Field(default_factory=list)
    objectNameColumn: str | None = Field(default=None, max_length=255)
    descriptionColumns: list[str] = Field(default_factory=list)
    searchableColumns: list[str] = Field(default_factory=list)


class SourceDocumentColumnsResponse(BaseModel):
    columns: list[str]


class AssignCuratorRequest(BaseModel):
    permissionId: str


class SearchableCollectionResponse(BaseModel):
    id: str
    name: str
    searchableColumns: list[str] = Field(default_factory=list)
    searchableColumnsTotal: int = 0


class ObjectSearchSnapshotResponse(BaseModel):
    inventoryNumber: str
    displayTitle: str
    objectName: str
    briefDescriptionSnapshot: str | None = None
    category: str


class SearchMatchReasonResponse(BaseModel):
    method: str
    label: str
    columns: list[str] = Field(default_factory=list)


class SearchHitResponse(BaseModel):
    collectionId: str
    collectionName: str
    sourceDocumentId: str
    fileName: str
    sheet: str
    rowNumber: int
    cells: dict[str, str]
    highlight: str
    objectSnapshot: ObjectSearchSnapshotResponse | None = None
    matchReasons: list[SearchMatchReasonResponse] = Field(default_factory=list)


class SearchResultResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[SearchHitResponse]
