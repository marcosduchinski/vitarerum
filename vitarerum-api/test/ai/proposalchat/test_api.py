from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.ai.proposalchat.domain.models import (
    Confidence,
    ConversationContext,
    FocusMessage,
    IntendedUseSuggestion,
    ProposalSummary,
)
from app.ai.proposalchat.domain.ports import (
    ConversationNotFoundError,
    MessageNotFoundError,
    ModelTimeout,
    ModelUnavailable,
)
from app.ai.proposalchat.presentation.dependencies import (
    get_context_port,
    get_model_port,
)
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission
from app.shared.kernel import IntendedUse, UseType

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="r@uni.pt"
)


def _context(
    body: str = "Please let me examine specimens on site.",
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


class _FakeContextPort:
    def __init__(self, *, context=None, error=None) -> None:
        self._context = context
        self._error = error

    async def load(self, conversation_id: str, message_id: str) -> ConversationContext:
        if self._error is not None:
            raise self._error
        return self._context if self._context is not None else _context()


class _FakeModelPort:
    def __init__(self, *, suggestion=None, error=None) -> None:
        self._suggestion = suggestion
        self._error = error

    async def suggest(self, context: ConversationContext) -> IntendedUseSuggestion:
        if self._error is not None:
            raise self._error
        return self._suggestion or IntendedUseSuggestion(
            use_type=UseType.IN_SITU_VISIT,
            description="On-site consultation of specimens.",
            confidence=Confidence(0.91),
            rationale="Asks to examine physical specimens on site.",
            # Provenance mirrors the real adapter: derived from the context.
            source_conversation_id=context.conversation_id,
            source_message_id=context.focus.message_id,
        )


@asynccontextmanager
async def _client(
    *,
    caller: Actor = _STAFF,
    context_port: object | None = None,
    model_port: object | None = None,
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_context_port] = (
        lambda: context_port or _FakeContextPort()
    )
    app.dependency_overrides[get_model_port] = lambda: model_port or _FakeModelPort()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ── GET /context ─────────────────────────────────────────────────────────────-


async def test_get_context_returns_focus_and_proposal() -> None:
    async with _client() as client:
        resp = await client.get(
            "/api/v1/proposalchat/context",
            params={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversationId"] == "c1"
    assert body["focusMessage"]["messageId"] == "m1"
    assert body["focusMessage"]["subject"] == "Visit request"
    assert body["proposal"]["referenceNumber"] == "VRP-20260601-0001"
    assert body["proposal"]["intendedUse"]["useType"] == "IN_SITU_VISIT"


async def test_get_context_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.get(
            "/api/v1/proposalchat/context",
            params={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 403
    assert resp.json()["error"] == "ACCESS_DENIED"


async def test_get_context_conversation_not_found() -> None:
    port = _FakeContextPort(error=ConversationNotFoundError("c1"))
    async with _client(context_port=port) as client:
        resp = await client.get(
            "/api/v1/proposalchat/context",
            params={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "CONVERSATION_NOT_FOUND"


async def test_get_context_message_not_found() -> None:
    port = _FakeContextPort(error=MessageNotFoundError("m1"))
    async with _client(context_port=port) as client:
        resp = await client.get(
            "/api/v1/proposalchat/context",
            params={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "MESSAGE_NOT_FOUND"


# ── POST /intended-use-suggestions ───────────────────────────────────────────-


async def test_suggestion_happy_path() -> None:
    async with _client() as client:
        resp = await client.post(
            "/api/v1/proposalchat/intended-use-suggestions",
            json={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 200
    body = resp.json()["suggestion"]
    assert body["intendedUse"]["useType"] == "IN_SITU_VISIT"
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["source"] == {"conversationId": "c1", "messageId": "m1"}


async def test_suggestion_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as client:
        resp = await client.post(
            "/api/v1/proposalchat/intended-use-suggestions",
            json={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 403
    assert resp.json()["error"] == "ACCESS_DENIED"


async def test_suggestion_empty_body_422() -> None:
    port = _FakeContextPort(context=_context(body="   "))
    async with _client(context_port=port) as client:
        resp = await client.post(
            "/api/v1/proposalchat/intended-use-suggestions",
            json={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 422
    assert resp.json()["error"] == "EMPTY_MESSAGE_BODY"


async def test_suggestion_model_unavailable_503() -> None:
    model = _FakeModelPort(error=ModelUnavailable("down"))
    async with _client(model_port=model) as client:
        resp = await client.post(
            "/api/v1/proposalchat/intended-use-suggestions",
            json={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 503
    assert resp.json()["error"] == "MODEL_UNAVAILABLE"


async def test_suggestion_model_timeout_504() -> None:
    model = _FakeModelPort(error=ModelTimeout("slow"))
    async with _client(model_port=model) as client:
        resp = await client.post(
            "/api/v1/proposalchat/intended-use-suggestions",
            json={"conversationId": "c1", "messageId": "m1"},
        )
    assert resp.status_code == 504
    assert resp.json()["error"] == "MODEL_TIMEOUT"
