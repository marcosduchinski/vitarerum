"""ProposalChat driven ports (hexagonal) and their error vocabulary.

Both ports are implemented by infrastructure adapters: ``ProposalContextPort`` by
the User Request ACL, ``IntendedUseSuggestionPort`` by the LangGraph/Ollama model
adapter. The application depends only on these Protocols.
"""

from __future__ import annotations

from typing import Protocol

from app.ai.proposalchat.domain.models import (
    ConversationContext,
    IntendedUseSuggestion,
)


class ConversationNotFoundError(Exception):
    """The referenced conversation does not exist (translated by the ACL)."""


class MessageNotFoundError(Exception):
    """The conversation has no message with the referenced id (via the ACL)."""


class ModelUnavailable(Exception):
    """The suggestion model could not be reached."""


class ModelTimeout(Exception):
    """The suggestion model did not respond in time."""


class ProposalContextPort(Protocol):
    """Driven port: load the triage context for a focus message through the
    User Request anti-corruption layer. Resolves the focus message via the
    conversation root, never by reaching into ``Message`` directly."""

    async def load(
        self, conversation_id: str, message_id: str
    ) -> ConversationContext: ...


class IntendedUseSuggestionPort(Protocol):
    """Driven port: analyse a triage context and return a suggested intended
    use. Raises :class:`ModelUnavailable` / :class:`ModelTimeout` on adapter
    failure."""

    async def suggest(self, context: ConversationContext) -> IntendedUseSuggestion: ...
