"""The reasoner must end, whether the backend is silent or endlessly chatty."""

from __future__ import annotations

import asyncio

import pytest

from app.scientific_return.application.ports import AgentReasonerTimeout
from app.scientific_return.infrastructure.reasoner_ollama import (
    OllamaScientificReturnReasoner,
)

_NEVER_ANSWERS_MODEL = "streams-forever"


class _FakeHttpClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeChat:
    """Stands in for ChatOllama, recording what the adapter asked of it."""

    instances: list[_FakeChat] = []
    behaviour_for_new = "answer"

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls: list[dict[str, object]] = []
        # Keyed on the model so concurrent calls can behave differently, which
        # a shared class flag could not express.
        self.behaviour = (
            "never_answers"
            if kwargs.get("model") == _NEVER_ANSWERS_MODEL
            else _FakeChat.behaviour_for_new
        )
        self._async_client = _FakeHttpClient()
        _FakeChat.instances.append(self)

    async def ainvoke(self, messages: object, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.behaviour == "never_answers":
            # A backend that streams forever: no chunk gap ever elapses, so only
            # a total deadline can end this.
            await asyncio.Event().wait()
        return type("Response", (), {"content": '{"ok":true}'})()


@pytest.fixture(autouse=True)
def _fake_chat_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    import langchain_ollama

    _FakeChat.instances.clear()
    _FakeChat.behaviour_for_new = "answer"
    monkeypatch.setattr(langchain_ollama, "ChatOllama", _FakeChat)


def _reasoner(**overrides: object) -> OllamaScientificReturnReasoner:
    options: dict[str, object] = {
        "base_url": "http://ollama.test",
        "model": "test-model",
        "timeout_seconds": 0.05,
        "total_timeout_seconds": 0.05,
        "num_predict": 4096,
    }
    options.update(overrides)
    return OllamaScientificReturnReasoner(**options)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_backend_that_never_stops_streaming_becomes_a_timeout() -> None:
    _FakeChat.behaviour_for_new = "never_answers"

    with pytest.raises(AgentReasonerTimeout):
        await _reasoner().generate(
            system_prompt="system", user_prompt="user", temperature=0.1
        )


@pytest.mark.asyncio
async def test_a_timed_out_call_closes_its_own_client() -> None:
    """Otherwise the abandoned stream keeps holding a model slot."""

    _FakeChat.behaviour_for_new = "never_answers"

    with pytest.raises(AgentReasonerTimeout):
        await _reasoner().generate(
            system_prompt="system", user_prompt="user", temperature=0.1
        )

    assert _FakeChat.instances[0]._async_client.closed is True


@pytest.mark.asyncio
async def test_one_call_timing_out_never_disturbs_a_concurrent_call() -> None:
    """The reason each call owns its client instead of sharing one.

    Closing a shared pool to free the model slot of an abandoned call would
    break every other call in flight, turning one slow answer into a cascade
    that also spends budget.
    """

    slow = _reasoner(model=_NEVER_ANSWERS_MODEL)
    healthy = _reasoner(timeout_seconds=5.0, total_timeout_seconds=5.0)

    async def call_slow() -> str:
        return await slow.generate(
            system_prompt="s", user_prompt="u", temperature=0.1
        )

    async def call_healthy() -> str:
        # Starts while the slow call is still streaming, and must outlive it.
        await asyncio.sleep(0.01)
        return await healthy.generate(
            system_prompt="s", user_prompt="u", temperature=0.1
        )

    timed_out, answered = await asyncio.gather(
        call_slow(), call_healthy(), return_exceptions=True
    )

    assert isinstance(timed_out, AgentReasonerTimeout)
    assert answered == '{"ok":true}'


@pytest.mark.asyncio
async def test_the_generation_ceiling_and_temperature_travel_as_options() -> None:
    reasoner = _reasoner(total_timeout_seconds=5.0)

    await reasoner.generate(system_prompt="s", user_prompt="u", temperature=0.35)

    chat = _FakeChat.instances[0]
    assert chat.kwargs["num_predict"] == 4096
    assert chat.calls[0]["options"] == {"temperature": 0.35, "num_predict": 4096}


@pytest.mark.asyncio
async def test_every_call_closes_the_client_it_built() -> None:
    """A client nobody closes is a leak; a client everybody shares is a cascade."""

    reasoner = _reasoner(total_timeout_seconds=5.0)

    await reasoner.generate(system_prompt="s", user_prompt="u", temperature=0.1)
    await reasoner.generate(system_prompt="s", user_prompt="u", temperature=0.1)

    assert len(_FakeChat.instances) == 2
    assert all(chat._async_client.closed for chat in _FakeChat.instances)


@pytest.mark.asyncio
async def test_the_total_deadline_never_undercuts_the_chunk_timeout() -> None:
    reasoner = OllamaScientificReturnReasoner(
        base_url="http://ollama.test",
        model="test-model",
        timeout_seconds=300.0,
        total_timeout_seconds=30.0,
    )

    assert reasoner.total_timeout_seconds == 300.0
