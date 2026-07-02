"""Request/response schemas for the Document Templates endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.shared.kernel import UseType


class PublicDocumentTemplateResponse(BaseModel):
    """Shape exposed to the public submission screen."""

    id: str
    title: str
    description: str
    mandatory: bool


class DocumentTemplateResponse(BaseModel):
    """Full shape for the staff management area."""

    id: str
    useType: UseType
    title: str
    description: str
    mandatory: bool
    active: bool
    displayOrder: int
    fileName: str
    uploadedAt: datetime


class UpdateDocumentTemplateRequest(BaseModel):
    """Full replace of the editable metadata (the management form sends all)."""

    title: str
    description: str = ""
    mandatory: bool = False
    active: bool = True
    displayOrder: int = 0
