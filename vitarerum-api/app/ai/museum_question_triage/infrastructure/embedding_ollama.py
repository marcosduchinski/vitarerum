"""Ollama embeddings adapter for the shadow use-category classifier."""

from __future__ import annotations

import asyncio
from typing import Any

from app.ai.museum_question_triage.domain.ports import ModelTimeout, ModelUnavailable


class OllamaEmbeddingAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        api_key: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_many([text]))[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        import httpx

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, headers=self._headers()
            ) as client:
                return await asyncio.gather(
                    *[self._embed_with_client(client, text) for text in texts]
                )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ModelTimeout("The embedding model did not respond in time") from exc
        except (httpx.ConnectError, httpx.HTTPError, ConnectionError, OSError) as exc:
            raise ModelUnavailable(
                "The embedding model is currently unavailable"
            ) from exc

    async def _embed_with_client(self, client: Any, text: str) -> list[float]:
        response = await client.post(
            f"{self._base_url}/api/embeddings",
            json={"model": self._model, "prompt": text},
        )
        response.raise_for_status()
        embedding = _extract_embedding(response.json())
        if embedding is None:
            raise ModelUnavailable("The embedding model returned an invalid response")
        return embedding


def _extract_embedding(payload: dict[str, Any]) -> list[float] | None:
    raw = payload.get("embedding")
    if raw is None:
        embeddings = payload.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            raw = embeddings[0]
    if not isinstance(raw, list) or not raw:
        return None
    try:
        return [float(value) for value in raw]
    except (TypeError, ValueError):
        return None
