"""Anti-corruption layer over the User Request context.

The ONLY place in ProposalChat that knows about ``use_of_collections``. It reads
through the published OHS (``use_of_collections.public``) and translates the
User Request view + its read errors into ProposalChat's own domain language.
"""

from __future__ import annotations

from app.ai.proposalchat.domain.models import (
    ConversationContext,
    FocusMessage,
    ProposalSummary,
)
from app.ai.proposalchat.domain.ports import (
    ConversationNotFoundError,
    MessageNotFoundError,
)
from app.use_of_collections.public import (
    ConversationNotFound,
    MessageNotFound,
    ProposalContextReader,
)


class UserRequestContextAdapter:
    """Implements ``ProposalContextPort`` by reading the User Request OHS."""

    def __init__(self, reader: ProposalContextReader) -> None:
        self._reader = reader

    async def load(
        self, conversation_id: str, message_id: str
    ) -> ConversationContext:
        try:
            view = await self._reader.load(conversation_id, message_id)
        except ConversationNotFound as exc:
            raise ConversationNotFoundError(conversation_id) from exc
        except MessageNotFound as exc:
            raise MessageNotFoundError(message_id) from exc

        return ConversationContext(
            conversation_id=view.conversation_id,
            focus=FocusMessage(
                message_id=view.focus_message.message_id,
                subject=view.focus_message.subject,
                body=view.focus_message.body,
                sender=view.focus_message.sender,
                sent_at=view.focus_message.sent_at,
            ),
            proposal=ProposalSummary(
                proposal_id=view.proposal_id,
                reference_number=view.reference_number,
                title=view.title,
                status=str(view.status),
                intended_use=view.intended_use,
            ),
        )
