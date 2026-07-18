from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.ai.prompts.domain.models import (
    PromptPurpose,
    PromptStatus,
    PromptTemplate,
    PromptTemplateVersion,
)


class PromptTemplateResponse(BaseModel):
    id: str
    purpose: PromptPurpose
    key: str
    name: str
    description: str
    variablesSchemaJson: str
    activeVersionId: str | None
    createdAt: datetime


class PromptTemplateVersionResponse(BaseModel):
    id: str
    templateId: str
    version: int
    versionLabel: str
    status: PromptStatus
    content: str
    defaultTemperature: float
    createdBy: str
    createdAt: datetime
    publishedBy: str | None
    publishedAt: datetime | None
    archivedAt: datetime | None


class CreatePromptDraftRequest(BaseModel):
    version_label: str = Field(min_length=1)
    content: str = Field(min_length=1)
    default_temperature: float = Field(ge=0.0, le=1.0)
    source_version_id: str | None = None

    @field_validator("version_label", "content")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty.")
        return stripped


def prompt_template_response(template: PromptTemplate) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=template.id,
        purpose=template.purpose,
        key=template.key,
        name=template.name,
        description=template.description,
        variablesSchemaJson=template.variables_schema_json,
        activeVersionId=template.active_version_id,
        createdAt=template.created_at,
    )


def prompt_version_response(
    version: PromptTemplateVersion,
) -> PromptTemplateVersionResponse:
    return PromptTemplateVersionResponse(
        id=version.id,
        templateId=version.template_id,
        version=version.version,
        versionLabel=version.version_label,
        status=version.status,
        content=version.content,
        defaultTemperature=version.default_temperature,
        createdBy=version.created_by,
        createdAt=version.created_at,
        publishedBy=version.published_by,
        publishedAt=version.published_at,
        archivedAt=version.archived_at,
    )
