from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType

PromptTemplateId = NewType("PromptTemplateId", str)
PromptTemplateVersionId = NewType("PromptTemplateVersionId", str)


class PromptPurpose(StrEnum):
    IN_SITU_NARRATIVE = "in_situ_narrative"
    MUSEUM_QUESTION_TRIAGE = "museum_question_triage"
    PROPOSAL_ASSISTANCE = "proposal_assistance"
    PROJECT_ASSISTANCE = "project_assistance"


class PromptStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PromptInvariantError(ValueError):
    pass


class PublishedPromptRequired(PromptInvariantError):
    pass


def _validate_variables_schema(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("variables_schema_json must be valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("variables_schema_json must be a JSON object.")
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    id: PromptTemplateId
    purpose: PromptPurpose
    key: str
    name: str
    description: str
    variables_schema_json: str
    created_at: datetime
    active_version_id: PromptTemplateVersionId | None = None

    @classmethod
    def create(
        cls,
        *,
        purpose: PromptPurpose,
        key: str,
        name: str,
        description: str,
        variables_schema_json: str,
    ) -> PromptTemplate:
        return cls(
            id=PromptTemplateId(str(uuid.uuid4())),
            purpose=purpose,
            key=key,
            name=name.strip(),
            description=description.strip(),
            variables_schema_json=_validate_variables_schema(variables_schema_json),
            created_at=datetime.now(UTC),
        )

    def activate(self, version_id: PromptTemplateVersionId) -> PromptTemplate:
        return PromptTemplate(
            id=self.id,
            purpose=self.purpose,
            key=self.key,
            name=self.name,
            description=self.description,
            variables_schema_json=self.variables_schema_json,
            created_at=self.created_at,
            active_version_id=version_id,
        )


@dataclass(frozen=True, slots=True)
class PromptTemplateVersion:
    id: PromptTemplateVersionId
    template_id: PromptTemplateId
    version: int
    version_label: str
    status: PromptStatus
    content: str
    default_temperature: float
    created_by: str
    created_at: datetime
    published_by: str | None = None
    published_at: datetime | None = None
    archived_at: datetime | None = None

    @classmethod
    def create_draft(
        cls,
        *,
        template_id: PromptTemplateId,
        version: int,
        version_label: str,
        content: str,
        default_temperature: float,
        created_by: str,
    ) -> PromptTemplateVersion:
        if not content.strip():
            raise ValueError("content must not be empty.")
        if not version_label.strip():
            raise ValueError("version_label must not be empty.")
        if version < 1:
            raise ValueError("version must be positive.")
        return cls(
            id=PromptTemplateVersionId(str(uuid.uuid4())),
            template_id=template_id,
            version=version,
            version_label=version_label.strip(),
            status=PromptStatus.DRAFT,
            content=content.strip(),
            default_temperature=default_temperature,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )

    @classmethod
    def copy_as_new_draft(
        cls,
        source: PromptTemplateVersion,
        *,
        version: int,
        version_label: str,
        created_by: str,
    ) -> PromptTemplateVersion:
        return cls.create_draft(
            template_id=source.template_id,
            version=version,
            version_label=version_label,
            content=source.content,
            default_temperature=source.default_temperature,
            created_by=created_by,
        )

    def publish(self, *, published_by: str) -> PromptTemplateVersion:
        if self.status is not PromptStatus.DRAFT:
            raise PromptInvariantError("only draft prompt versions can be published.")
        return PromptTemplateVersion(
            id=self.id,
            template_id=self.template_id,
            version=self.version,
            version_label=self.version_label,
            status=PromptStatus.PUBLISHED,
            content=self.content,
            default_temperature=self.default_temperature,
            created_by=self.created_by,
            created_at=self.created_at,
            published_by=published_by,
            published_at=datetime.now(UTC),
            archived_at=None,
        )

    def archive(self) -> PromptTemplateVersion:
        if self.status is PromptStatus.PUBLISHED:
            raise PublishedPromptRequired(
                "published prompt versions are archived only by publishing "
                "a replacement."
            )
        return PromptTemplateVersion(
            id=self.id,
            template_id=self.template_id,
            version=self.version,
            version_label=self.version_label,
            status=PromptStatus.ARCHIVED,
            content=self.content,
            default_temperature=self.default_temperature,
            created_by=self.created_by,
            created_at=self.created_at,
            published_by=self.published_by,
            published_at=self.published_at,
            archived_at=datetime.now(UTC),
        )

    def archive_as_replaced(self) -> PromptTemplateVersion:
        if self.status is not PromptStatus.PUBLISHED:
            return self.archive()
        return PromptTemplateVersion(
            id=self.id,
            template_id=self.template_id,
            version=self.version,
            version_label=self.version_label,
            status=PromptStatus.ARCHIVED,
            content=self.content,
            default_temperature=self.default_temperature,
            created_by=self.created_by,
            created_at=self.created_at,
            published_by=self.published_by,
            published_at=self.published_at,
            archived_at=datetime.now(UTC),
        )
