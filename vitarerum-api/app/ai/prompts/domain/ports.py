from __future__ import annotations

from typing import Protocol

from app.ai.prompts.domain.models import (
    PromptPurpose,
    PromptStatus,
    PromptTemplate,
    PromptTemplateId,
    PromptTemplateVersion,
    PromptTemplateVersionId,
)


class PromptPublicationConflict(Exception):
    pass


class PromptTemplateRepository(Protocol):
    async def get_template(
        self, purpose: PromptPurpose, key: str
    ) -> PromptTemplate | None: ...
    async def get_template_by_id(
        self, template_id: PromptTemplateId
    ) -> PromptTemplate | None: ...
    async def get_template_by_id_for_update(
        self, template_id: PromptTemplateId
    ) -> PromptTemplate | None: ...
    async def list_templates(
        self,
        *,
        purpose: PromptPurpose | None = None,
        status: PromptStatus | None = None,
    ) -> list[PromptTemplate]: ...
    async def get_version(
        self, version_id: PromptTemplateVersionId
    ) -> PromptTemplateVersion | None: ...
    async def get_published_version(
        self, purpose: PromptPurpose, key: str
    ) -> PromptTemplateVersion | None: ...
    async def list_versions(
        self, template_id: PromptTemplateId
    ) -> list[PromptTemplateVersion]: ...
    async def add_template(self, template: PromptTemplate) -> None: ...
    async def add_version(self, version: PromptTemplateVersion) -> None: ...
    async def save_template(self, template: PromptTemplate) -> None: ...
    async def save_version(self, version: PromptTemplateVersion) -> None: ...
    async def next_version_number(self, template_id: PromptTemplateId) -> int: ...
