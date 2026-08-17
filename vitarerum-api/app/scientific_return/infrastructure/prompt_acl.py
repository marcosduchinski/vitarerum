from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.scientific_return.application.ports import (
    AgentPromptUnavailable,
    PublishedAgentPrompt,
)


class AiPromptRegistryAdapter:
    """Reads published prompts by key under the scientific-return purpose.

    The cycle uses several prompts — shadow analysis, planning, reflection — that
    share one purpose and differ by key, so no new ``PromptPurpose`` is needed
    and prompt administration stays as it is.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_published(self, key: str) -> PublishedAgentPrompt:
        from app.ai.prompts.public import (
            ActivePromptNotFound,
            PromptPurpose,
            get_published_prompt,
        )

        try:
            prompt = await get_published_prompt(
                self._session,
                PromptPurpose.SCIENTIFIC_RETURN_ANALYSIS,
                key,
            )
        except ActivePromptNotFound as exc:
            raise AgentPromptUnavailable(
                f"No published prompt is available for '{key}'"
            ) from exc
        return PublishedAgentPrompt(
            version_id=prompt.id,
            version_label=prompt.version_label,
            content=prompt.content,
            temperature=prompt.default_temperature,
        )
