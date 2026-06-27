"""ProposalChat application services (framework-free).

Triage is ephemeral and advisory: the service loads context through the ACL,
calls the model, and returns a suggestion. Nothing is persisted and no
``ProposalEvent`` is emitted.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.proposalchat.domain.models import (
    ConversationContext,
    EmptyMessageBody,
    IntendedUseSuggestion,
)
from app.ai.proposalchat.domain.ports import (
    IntendedUseSuggestionPort,
    ProposalContextPort,
)


@dataclass(frozen=True, slots=True)
class SuggestIntendedUseCommand:
    conversation_id: str
    message_id: str


class GetTriageContext:
    """Read service backing ``GET /proposalchat/context`` — a translated,
    stateless read across the context boundary."""

    def __init__(self, context: ProposalContextPort) -> None:
        self._context = context

    async def execute(
        self, conversation_id: str, message_id: str
    ) -> ConversationContext:
        return await self._context.load(conversation_id, message_id)


class SuggestIntendedUseService:
    """Runs triage: load context → guard empty body → ask the model."""

    def __init__(
        self,
        context: ProposalContextPort,
        model: IntendedUseSuggestionPort,
    ) -> None:
        self._context = context
        self._model = model

    async def handle(
        self, command: SuggestIntendedUseCommand
    ) -> IntendedUseSuggestion:
        context = await self._context.load(
            command.conversation_id, command.message_id
        )
        if not context.focus.body.strip():
            raise EmptyMessageBody("The focus message has no analysable content")
        return await self._model.suggest(context)
