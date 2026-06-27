from datetime import UTC, datetime

import pytest

from app.ai.proposalchat.application.use_cases import (
    SuggestIntendedUseCommand,
    SuggestIntendedUseService,
)
from app.ai.proposalchat.domain.models import (
    Confidence,
    ConversationContext,
    EmptyMessageBody,
    FocusMessage,
    IntendedUseSuggestion,
    ProposalSummary,
)
from app.ai.proposalchat.domain.ports import (
    ConversationNotFoundError,
    MessageNotFoundError,
)
from app.ai.proposalchat.infrastructure.context_acl import UserRequestContextAdapter
from app.shared.kernel import IntendedUse, UseType
from app.use_of_collections.application.context_views import (
    ConversationNotFound,
    FocusMessageView,
    MessageNotFound,
    ProposalContextView,
)
from app.use_of_collections.domain.enums import ProposalStatus


def _context(
    body: str = "Please let me examine the herbarium on site.",
) -> ConversationContext:
    return ConversationContext(
        conversation_id="c1",
        focus=FocusMessage(
            message_id="m1",
            subject="Visit request",
            body=body,
            sender="researcher@university.pt",
            sent_at=datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        ),
        proposal=ProposalSummary(
            proposal_id="prop-1",
            reference_number="VRP-20260601-0001",
            title="Herbarium study",
            status="SUBMITTED",
            intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT, description=""),
        ),
    )


def test_confidence_rejects_out_of_range() -> None:
    Confidence(0.0)
    Confidence(1.0)
    with pytest.raises(ValueError):
        Confidence(1.01)
    with pytest.raises(ValueError):
        Confidence(-0.1)


def test_suggestion_maps_to_shared_intended_use() -> None:
    suggestion = IntendedUseSuggestion(
        use_type=UseType.EXHIBITION,
        description="Loan for a temporary exhibition.",
        confidence=Confidence(0.8),
        rationale="Mentions display to the public.",
        source_conversation_id="c1",
        source_message_id="m1",
    )
    intended = suggestion.to_intended_use()
    assert isinstance(intended, IntendedUse)
    assert intended.use_type is UseType.EXHIBITION
    assert intended.description == "Loan for a temporary exhibition."


class _FixedContextPort:
    def __init__(self, context: ConversationContext) -> None:
        self._context = context

    async def load(self, conversation_id: str, message_id: str) -> ConversationContext:
        return self._context


class _FixedModelPort:
    async def suggest(self, context: ConversationContext) -> IntendedUseSuggestion:
        return IntendedUseSuggestion(
            use_type=UseType.IN_SITU_VISIT,
            description="On-site consultation.",
            confidence=Confidence(0.9),
            rationale="Asks to examine specimens on site.",
            source_conversation_id="c1",
            source_message_id="m1",
        )


async def test_service_rejects_empty_body() -> None:
    service = SuggestIntendedUseService(
        _FixedContextPort(_context(body="   ")), _FixedModelPort()
    )
    with pytest.raises(EmptyMessageBody):
        await service.handle(SuggestIntendedUseCommand("c1", "m1"))


async def test_service_returns_suggestion_for_real_body() -> None:
    service = SuggestIntendedUseService(
        _FixedContextPort(_context()), _FixedModelPort()
    )
    suggestion = await service.handle(SuggestIntendedUseCommand("c1", "m1"))
    assert suggestion.use_type is UseType.IN_SITU_VISIT


# ── ACL translation ─────────────────────────────────────────────────────────--


class _FakeReader:
    def __init__(self, *, view=None, error=None) -> None:
        self._view = view
        self._error = error

    async def load(self, conversation_id: str, message_id: str) -> ProposalContextView:
        if self._error is not None:
            raise self._error
        assert self._view is not None
        return self._view


def _view() -> ProposalContextView:
    return ProposalContextView(
        conversation_id="c1",
        focus_message=FocusMessageView(
            message_id="m1",
            sent_at=datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
            sender="researcher@university.pt",
            subject="Visit request",
            body="On-site consultation please.",
        ),
        proposal_id="prop-1",
        reference_number="VRP-20260601-0001",
        title="Herbarium study",
        status=ProposalStatus.SUBMITTED,
        intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT, description="x"),
    )


async def test_acl_translates_view_into_context() -> None:
    adapter = UserRequestContextAdapter(_FakeReader(view=_view()))
    context = await adapter.load("c1", "m1")
    assert context.focus.subject == "Visit request"
    assert context.proposal.proposal_id == "prop-1"
    assert context.proposal.status == "SUBMITTED"
    assert context.proposal.intended_use.use_type is UseType.IN_SITU_VISIT


async def test_acl_maps_conversation_not_found() -> None:
    adapter = UserRequestContextAdapter(_FakeReader(error=ConversationNotFound("c1")))
    with pytest.raises(ConversationNotFoundError):
        await adapter.load("c1", "m1")


async def test_acl_maps_message_not_found() -> None:
    adapter = UserRequestContextAdapter(_FakeReader(error=MessageNotFound("m1")))
    with pytest.raises(MessageNotFoundError):
        await adapter.load("c1", "m1")
