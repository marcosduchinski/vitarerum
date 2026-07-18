from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_narrative.domain.models import NarrativeType
from app.ai.museum_narrative.domain.ports import (
    NarrativePromptUnavailable,
    NarrativePromptVersionMismatch,
    NarrativePromptVersionNotFound,
)

PROMPT_KEYS: dict[NarrativeType, str] = {
    NarrativeType.INSTITUTIONAL: "system_institutional",
    NarrativeType.SCIENTIFIC: "system_scientific",
    NarrativeType.AUDIOGUIDE_ADULT: "system_audioguide_adult",
    NarrativeType.AUDIOGUIDE_CHILD: "system_audioguide_child",
    NarrativeType.SOCIAL_MEDIA: "system_social_media",
}


@dataclass(frozen=True, slots=True)
class PublishedPromptView:
    version_id: str
    version_label: str
    status: str
    content: str


class AiPromptRegistryAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_published(self, narrative_type: NarrativeType) -> PublishedPromptView:
        from app.ai.prompts.public import (
            ActivePromptNotFound,
            PromptPurpose,
            get_published_prompt,
        )

        key = PROMPT_KEYS[narrative_type]
        try:
            prompt = await get_published_prompt(
                self._session, PromptPurpose.IN_SITU_NARRATIVE, key
            )
        except ActivePromptNotFound as exc:
            raise NarrativePromptUnavailable(
                f"No published AI prompt found for in-situ narrative key '{key}'."
            ) from exc
        return PublishedPromptView(
            version_id=prompt.id,
            version_label=prompt.version_label,
            status=prompt.status.value,
            content=prompt.content,
        )

    async def get_version(
        self, version_id: str, narrative_type: NarrativeType
    ) -> PublishedPromptView:
        from app.ai.prompts.public import (
            PromptPurpose,
            PromptTemplateNotFound,
            PromptVersionNotFound,
            get_prompt_template,
            get_prompt_version,
        )

        try:
            prompt = await get_prompt_version(self._session, version_id)
        except PromptVersionNotFound as exc:
            raise NarrativePromptVersionNotFound(version_id) from exc
        key = PROMPT_KEYS[narrative_type]
        try:
            template = await get_prompt_template(
                self._session, PromptPurpose.IN_SITU_NARRATIVE, key
            )
        except PromptTemplateNotFound as exc:
            raise NarrativePromptUnavailable(
                f"No AI prompt template found for in-situ narrative key '{key}'."
            ) from exc
        if prompt.template_id != template.id:
            raise NarrativePromptVersionMismatch(
                f"Prompt version '{version_id}' does not belong to "
                f"narrative type '{narrative_type.value}'."
            )
        return PublishedPromptView(
            version_id=prompt.id,
            version_label=prompt.version_label,
            status=prompt.status.value,
            content=prompt.content,
        )
