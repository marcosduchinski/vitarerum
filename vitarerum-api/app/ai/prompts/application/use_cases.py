from __future__ import annotations

from dataclasses import dataclass

from app.ai.prompts.domain.models import (
    PromptPurpose,
    PromptStatus,
    PromptTemplate,
    PromptTemplateId,
    PromptTemplateVersion,
    PromptTemplateVersionId,
)
from app.ai.prompts.domain.ports import PromptTemplateRepository


class PromptTemplateNotFound(Exception):
    pass


class PromptVersionNotFound(Exception):
    pass


class ActivePromptNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreatePromptDraftInput:
    template_id: str
    version_label: str
    content: str
    default_temperature: float
    created_by: str
    source_version_id: str | None = None


class ListPromptTemplates:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        purpose: PromptPurpose | None = None,
        status: PromptStatus | None = None,
    ) -> list[PromptTemplate]:
        return await self._repository.list_templates(purpose=purpose, status=status)


class ListPromptVersions:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def execute(self, template_id: str) -> list[PromptTemplateVersion]:
        template = await self._repository.get_template_by_id(
            PromptTemplateId(template_id)
        )
        if template is None:
            raise PromptTemplateNotFound(template_id)
        return await self._repository.list_versions(template.id)


class GetPromptTemplate:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def execute(self, *, purpose: PromptPurpose, key: str) -> PromptTemplate:
        template = await self._repository.get_template(purpose, key)
        if template is None:
            raise PromptTemplateNotFound(f"{purpose.value}/{key}")
        return template


class GetPromptVersion:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def execute(self, version_id: str) -> PromptTemplateVersion:
        version = await self._repository.get_version(
            PromptTemplateVersionId(version_id)
        )
        if version is None:
            raise PromptVersionNotFound(version_id)
        return version


class GetPublishedPrompt:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, purpose: PromptPurpose, key: str
    ) -> PromptTemplateVersion:
        version = await self._repository.get_published_version(purpose, key)
        if version is None:
            raise ActivePromptNotFound(f"{purpose.value}/{key}")
        return version


class CreatePromptDraft:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def execute(self, data: CreatePromptDraftInput) -> PromptTemplateVersion:
        template_id = PromptTemplateId(data.template_id)
        template = await self._repository.get_template_by_id(template_id)
        if template is None:
            raise PromptTemplateNotFound(data.template_id)

        content = data.content
        default_temperature = data.default_temperature
        source = None
        if data.source_version_id is not None:
            source = await self._repository.get_version(
                PromptTemplateVersionId(data.source_version_id)
            )
            if source is None or source.template_id != template.id:
                raise PromptVersionNotFound(data.source_version_id)
            content = source.content
            default_temperature = source.default_temperature

        version_number = await self._repository.next_version_number(template.id)
        draft = (
            PromptTemplateVersion.copy_as_new_draft(
                source,
                version=version_number,
                version_label=data.version_label,
                created_by=data.created_by,
            )
            if source
            else PromptTemplateVersion.create_draft(
                template_id=template.id,
                version=version_number,
                version_label=data.version_label,
                content=content,
                default_temperature=default_temperature,
                created_by=data.created_by,
            )
        )
        await self._repository.add_version(draft)
        return draft


class PublishPromptVersion:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def execute(
        self, version_id: str, *, published_by: str
    ) -> PromptTemplateVersion:
        draft = await self._repository.get_version(PromptTemplateVersionId(version_id))
        if draft is None:
            raise PromptVersionNotFound(version_id)
        template = await self._repository.get_template_by_id_for_update(
            draft.template_id
        )
        if template is None:
            raise PromptTemplateNotFound(draft.template_id)
        current = await self._repository.get_published_version(
            template.purpose, template.key
        )
        if current is not None:
            await self._repository.save_version(current.archive_as_replaced())
        published = draft.publish(published_by=published_by)
        await self._repository.save_version(published)
        await self._repository.save_template(template.activate(published.id))
        return published


class ArchivePromptVersion:
    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    async def execute(self, version_id: str) -> PromptTemplateVersion:
        version = await self._repository.get_version(
            PromptTemplateVersionId(version_id)
        )
        if version is None:
            raise PromptVersionNotFound(version_id)
        archived = version.archive()
        await self._repository.save_version(archived)
        return archived
