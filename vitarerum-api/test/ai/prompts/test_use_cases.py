import pytest

from app.ai.prompts.application.use_cases import (
    ActivePromptNotFound,
    ArchivePromptVersion,
    CreatePromptDraft,
    CreatePromptDraftInput,
    GetPublishedPrompt,
    PublishPromptVersion,
)
from app.ai.prompts.domain.models import (
    PromptPurpose,
    PromptStatus,
    PromptTemplate,
    PromptTemplateId,
    PromptTemplateVersion,
    PromptTemplateVersionId,
    PublishedPromptRequired,
)

SCHEMA = '{"type":"object"}'


class _FakeRepo:
    def __init__(self) -> None:
        self.templates: dict[PromptTemplateId, PromptTemplate] = {}
        self.versions: dict[PromptTemplateVersionId, PromptTemplateVersion] = {}
        self.save_order: list[str] = []
        self.locked_template_ids: list[PromptTemplateId] = []

    async def get_template(
        self, purpose: PromptPurpose, key: str
    ) -> PromptTemplate | None:
        return next(
            (
                template
                for template in self.templates.values()
                if template.purpose == purpose and template.key == key
            ),
            None,
        )

    async def get_template_by_id(
        self, template_id: PromptTemplateId
    ) -> PromptTemplate | None:
        return self.templates.get(template_id)

    async def get_template_by_id_for_update(
        self, template_id: PromptTemplateId
    ) -> PromptTemplate | None:
        self.locked_template_ids.append(template_id)
        return self.templates.get(template_id)

    async def list_templates(
        self,
        *,
        purpose: PromptPurpose | None = None,
        status: PromptStatus | None = None,
    ) -> list[PromptTemplate]:
        templates = list(self.templates.values())
        if purpose is not None:
            templates = [
                template for template in templates if template.purpose == purpose
            ]
        if status is not None:
            templates = [
                template
                for template in templates
                if template.active_version_id
                and self.versions[template.active_version_id].status == status
            ]
        return templates

    async def get_version(
        self, version_id: PromptTemplateVersionId
    ) -> PromptTemplateVersion | None:
        return self.versions.get(version_id)

    async def get_published_version(
        self, purpose: PromptPurpose, key: str
    ) -> PromptTemplateVersion | None:
        template = await self.get_template(purpose, key)
        if template is None:
            return None
        return next(
            (
                version
                for version in self.versions.values()
                if version.template_id == template.id
                and version.status is PromptStatus.PUBLISHED
            ),
            None,
        )

    async def list_versions(
        self, template_id: PromptTemplateId
    ) -> list[PromptTemplateVersion]:
        return [
            version
            for version in sorted(self.versions.values(), key=lambda item: item.version)
            if version.template_id == template_id
        ]

    async def add_template(self, template: PromptTemplate) -> None:
        self.templates[template.id] = template

    async def add_version(self, version: PromptTemplateVersion) -> None:
        self.versions[version.id] = version

    async def save_template(self, template: PromptTemplate) -> None:
        self.save_order.append(f"template:{template.id}")
        self.templates[template.id] = template

    async def save_version(self, version: PromptTemplateVersion) -> None:
        self.save_order.append(f"version:{version.id}")
        self.versions[version.id] = version

    async def next_version_number(self, template_id: PromptTemplateId) -> int:
        versions = [
            version.version
            for version in self.versions.values()
            if version.template_id == template_id
        ]
        return (max(versions) if versions else 0) + 1


def _template() -> PromptTemplate:
    return PromptTemplate.create(
        purpose=PromptPurpose.IN_SITU_NARRATIVE,
        key="system_institutional",
        name="Institutional narrative",
        description="Prompt for institutional narratives.",
        variables_schema_json=SCHEMA,
    )


async def test_get_published_prompt_raises_operational_error_when_missing() -> None:
    repo = _FakeRepo()

    with pytest.raises(ActivePromptNotFound):
        await GetPublishedPrompt(repo).execute(
            purpose=PromptPurpose.IN_SITU_NARRATIVE,
            key="system_institutional",
        )


async def test_publish_archives_current_version_and_updates_active_cache() -> None:
    repo = _FakeRepo()
    template = _template()
    await repo.add_template(template)
    current = PromptTemplateVersion.create_draft(
        template_id=template.id,
        version=1,
        version_label="museum-narrative-institutional-v1",
        content="Original prompt.",
        default_temperature=0.3,
        created_by="system",
    ).publish(published_by="system")
    await repo.add_version(current)
    await repo.save_template(template.activate(current.id))
    draft = await CreatePromptDraft(repo).execute(
        CreatePromptDraftInput(
            template_id=template.id,
            version_label="museum-narrative-institutional-v2",
            content="Revised prompt.",
            default_temperature=0.3,
            created_by="staff-1",
        )
    )

    published = await PublishPromptVersion(repo).execute(
        draft.id, published_by="staff-1"
    )

    assert repo.versions[current.id].status is PromptStatus.ARCHIVED
    assert published.status is PromptStatus.PUBLISHED
    assert repo.templates[template.id].active_version_id == published.id
    assert repo.locked_template_ids == [template.id]
    assert repo.save_order[-2:] == [
        f"version:{published.id}",
        f"template:{template.id}",
    ]


async def test_archive_rejects_isolated_archive_of_published_version() -> None:
    repo = _FakeRepo()
    template = _template()
    await repo.add_template(template)
    version = PromptTemplateVersion.create_draft(
        template_id=template.id,
        version=1,
        version_label="museum-narrative-institutional-v1",
        content="Original prompt.",
        default_temperature=0.3,
        created_by="system",
    ).publish(published_by="system")
    await repo.add_version(version)

    with pytest.raises(PublishedPromptRequired):
        await ArchivePromptVersion(repo).execute(version.id)


async def test_copy_as_new_draft_preserves_source_content() -> None:
    repo = _FakeRepo()
    template = _template()
    await repo.add_template(template)
    source = PromptTemplateVersion.create_draft(
        template_id=template.id,
        version=1,
        version_label="museum-narrative-institutional-v1",
        content="Previous prompt.",
        default_temperature=0.3,
        created_by="system",
    ).publish(published_by="system")
    await repo.add_version(source)

    draft = await CreatePromptDraft(repo).execute(
        CreatePromptDraftInput(
            template_id=template.id,
            source_version_id=source.id,
            version_label="museum-narrative-institutional-v2",
            content="Ignored because source is provided.",
            default_temperature=0.7,
            created_by="staff-1",
        )
    )

    assert draft.content == source.content
    assert draft.default_temperature == source.default_temperature
    assert draft.version == 2
    assert draft.status is PromptStatus.DRAFT
