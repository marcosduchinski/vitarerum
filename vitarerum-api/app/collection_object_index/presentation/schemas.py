"""Pydantic schemas for the Collection Data Sources management API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CuratorResponse(BaseModel):
    permissionId: str
    name: str | None = None
    email: str | None = None
    assignedAt: datetime


class CollectionResponse(BaseModel):
    id: str
    name: str
    active: bool
    curators: list[CuratorResponse]
    documentCount: int
    manageable: bool


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
