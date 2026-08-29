"""The Ollama adapter for every scientific-return reasoner.

Two properties matter here and neither is free.

Each call owns its client and closes it. LangChain builds a pair of httpx
clients whenever a ``ChatOllama`` is instantiated and closes neither, so a
per-call client leaks unless someone closes it — but a client shared across
calls is worse: abandoning one timed-out call has to close the connection to
free the model slot on the server, and closing a shared pool would break every
other call in flight. Owning one per call and closing it in ``finally`` gives
both, and pooling buys nothing for an exchange measured in minutes.

The call has a total deadline. ``ChatOllama`` streams even through
``ainvoke``, and httpx's timeout on a stream bounds the gap between chunks, not
the whole exchange: a model stuck in a repetition loop keeps the connection
busy forever without ever tripping it. ``num_predict`` caps the generation and
the deadline caps the exchange, so a degenerate response becomes a timeout the
agentic loop already knows how to absorb.
"""

from __future__ import annotations

import asyncio
import logging

from app.scientific_return.application.ports import (
    AgentReasonerTimeout,
    AgentReasonerUnavailable,
)

logger = logging.getLogger(__name__)


def _is_ollama_response_error(exc: BaseException) -> bool:
    exc_type = type(exc)
    return (
        exc_type.__name__ == "ResponseError"
        and exc_type.__module__.split(".", maxsplit=1)[0] == "ollama"
    )


class OllamaScientificReturnReasoner:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        api_key: str = "",
        total_timeout_seconds: float | None = None,
        num_predict: int | None = None,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key
        # The read timeout bounds one chunk; this bounds the whole call. It is
        # never below the per-chunk timeout, or a healthy first token would be
        # reported as a hang.
        self._total_timeout_seconds = max(
            timeout_seconds, total_timeout_seconds or timeout_seconds
        )
        self._num_predict = num_predict

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def total_timeout_seconds(self) -> float:
        return self._total_timeout_seconds

    def _client(self) -> object:
        from langchain_ollama import ChatOllama

        client_kwargs: dict[str, object] = {"timeout": self._timeout_seconds}
        if self._api_key:
            client_kwargs["headers"] = {"Authorization": f"Bearer {self._api_key}"}
        return ChatOllama(
            base_url=self._base_url,
            model=self._model,
            format="json",
            num_predict=self._num_predict,
            client_kwargs=client_kwargs,
            async_client_kwargs=client_kwargs,
        )

    async def _close(self, chat: object) -> None:
        """Release this call's httpx clients, and any stream still attached.

        On a timeout the stream is still open: cancelling the task unwinds the
        generator only when the event loop gets round to finalising it, so the
        model slot is freed here instead, deterministically.
        """
        for attribute in ("_async_client", "_client"):
            client = getattr(chat, attribute, None)
            closer = getattr(client, "close", None)
            if closer is None:
                continue
            try:
                result = closer()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.debug("Could not close the Ollama %s.", attribute)

    async def generate(
        self, *, system_prompt: str, user_prompt: str, temperature: float
    ) -> str:
        import httpx
        from langchain_core.messages import HumanMessage, SystemMessage

        chat = self._client()
        # Per-call settings travel as Ollama options. A bare ``temperature=``
        # keyword would land at the top level of the chat payload, outside
        # ``options``, where the server ignores it.
        options: dict[str, object] = {"temperature": temperature}
        if self._num_predict is not None:
            options["num_predict"] = self._num_predict
        try:
            async with asyncio.timeout(self._total_timeout_seconds):
                response = await chat.ainvoke(  # type: ignore[attr-defined]
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt),
                    ],
                    options=options,
                )
        except (TimeoutError, httpx.TimeoutException) as exc:
            # Two ways to run out of time: the whole exchange outlived the total
            # deadline, or the gap between chunks outlived the read timeout.
            raise AgentReasonerTimeout(
                "The scientific-return reasoner did not respond in time"
            ) from exc
        except (httpx.ConnectError, httpx.HTTPError, ConnectionError, OSError) as exc:
            raise AgentReasonerUnavailable(
                "The scientific-return reasoner is unavailable"
            ) from exc
        except Exception as exc:
            if _is_ollama_response_error(exc):
                raise AgentReasonerUnavailable(
                    "The scientific-return reasoner is unavailable"
                ) from exc
            raise
        finally:
            await self._close(chat)
        return str(response.content)
