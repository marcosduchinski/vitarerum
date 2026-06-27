"""Local LLM adapter implementing ``NarrativeModelPort`` via Ollama.

Mirrors ``app/ai/proposalchat/infrastructure/model_ollama.py``: heavy imports
(langchain-ollama / httpx) are loaded lazily inside :meth:`generate` so the
module imports without the model stack and unit tests can substitute a fake port.

Failure mapping:
- connection failures        → ModelUnavailable  (503)
- timeouts / slow responses  → ModelTimeout      (504)
"""

from __future__ import annotations

from app.ai.museum_narrative.domain.ports import ModelTimeout, ModelUnavailable


class OllamaNarrativeAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        api_key: str = "",
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key

    async def generate(
        self, *, system_prompt: str, user_prompt: str, temperature: float
    ) -> str:
        import httpx
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        client_kwargs: dict[str, object] = {"timeout": self._timeout_seconds}
        if self._api_key:
            # Ollama Cloud authenticates via a bearer token on every request.
            client_kwargs["headers"] = {"Authorization": f"Bearer {self._api_key}"}

        chat = ChatOllama(
            base_url=self._base_url,
            model=self._model,
            temperature=temperature,
            client_kwargs=client_kwargs,
        )
        try:
            response = await chat.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ModelTimeout("The language model did not respond in time") from exc
        except (httpx.ConnectError, httpx.HTTPError, ConnectionError, OSError) as exc:
            raise ModelUnavailable(
                "The language model is currently unavailable"
            ) from exc
        return str(response.content)
