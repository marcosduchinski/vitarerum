from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.scientific_return.application.ports import (
    AgentPromptUnavailable,
    PublishedAgentPrompt,
)

_PROMPT_KEY = "candidate_shadow_analysis"


class AiPromptRegistryAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_published(self) -> PublishedAgentPrompt:
        from app.ai.prompts.public import (
            ActivePromptNotFound,
            PromptPurpose,
            get_published_prompt,
        )

        try:
            prompt = await get_published_prompt(
                self._session,
                PromptPurpose.SCIENTIFIC_RETURN_ANALYSIS,
                _PROMPT_KEY,
            )
        except ActivePromptNotFound as exc:
            raise AgentPromptUnavailable(
                "No published prompt is available for scientific-return analysis"
            ) from exc
        return PublishedAgentPrompt(
            version_id=prompt.id,
            version_label=prompt.version_label,
            content=prompt.content,
            temperature=prompt.default_temperature,
        )
