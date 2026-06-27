"""Integration test for the OHS reader against a real (sqlite) schema.

Doubles as the "shared-kernel promotion left the schema untouched" check:
``Base.metadata.create_all`` builds the ``use_type`` enum and the Proposal /
Conversation mappings round-trip after UseType/IntendedUse moved to the kernel.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.shared.kernel import IntendedUse, UseType
from app.use_of_collections.application.context_views import (
    ConversationNotFound,
    MessageNotFound,
)
from app.use_of_collections.domain.enums import ProposalStatus
from app.use_of_collections.domain.models import (
    CollectionUseProjectId,
    Conversation,
    ConversationId,
    EmailAddress,
    Message,
    MessageId,
    Proposal,
    ProposalId,
    ReferenceNumber,
)
from app.use_of_collections.infrastructure.repositories import (
    SqlAlchemyConversationRepository,
    SqlAlchemyProposalContextReader,
    SqlAlchemyProposalRepository,
)


def _proposal() -> Proposal:
    return Proposal(
        id=ProposalId("prop-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Herbarium study",
        collection_use_project_id=CollectionUseProjectId("proj-1"),
        intended_use=IntendedUse(
            use_type=UseType.IN_SITU_VISIT, description="on site"
        ),
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.SUBMITTED,
        requested_by=ProposalId("permission-1"),  # any opaque id
        submitted_at=datetime(2026, 6, 1, tzinfo=UTC),
    )


def _conversation() -> Conversation:
    message = Message(
        id=MessageId("m1"),
        sent_at=datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        sender=EmailAddress("researcher@university.pt"),
        recipient=EmailAddress("collections@museum.pt"),
        subject="Visit request",
        body="Please let me examine the specimens on site.",
    )
    return Conversation.start(
        id=ConversationId("c1"),
        proposal_id=ProposalId("prop-1"),
        initial_message=message,
    )


async def _session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def test_reader_resolves_focus_message_through_conversation_root() -> None:
    session_factory = await _session()
    async with session_factory() as session:
        await SqlAlchemyProposalRepository(session).add(_proposal())
        await SqlAlchemyConversationRepository(session).add(_conversation())
        await session.commit()

        view = await SqlAlchemyProposalContextReader(session).load("c1", "m1")

    assert view.conversation_id == "c1"
    assert view.focus_message.message_id == "m1"
    assert view.focus_message.subject == "Visit request"
    assert view.proposal_id == "prop-1"
    assert view.reference_number == "VRP-20260601-0001"
    assert view.status is ProposalStatus.SUBMITTED
    assert view.intended_use.use_type is UseType.IN_SITU_VISIT
    assert view.intended_use.description == "on site"


async def test_reader_raises_for_unknown_conversation() -> None:
    session_factory = await _session()
    async with session_factory() as session:
        with pytest.raises(ConversationNotFound):
            await SqlAlchemyProposalContextReader(session).load("missing", "m1")


async def test_reader_raises_for_unknown_message() -> None:
    session_factory = await _session()
    async with session_factory() as session:
        await SqlAlchemyProposalRepository(session).add(_proposal())
        await SqlAlchemyConversationRepository(session).add(_conversation())
        await session.commit()
        with pytest.raises(MessageNotFound):
            await SqlAlchemyProposalContextReader(session).load("c1", "missing")
