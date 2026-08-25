from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSourceCapabilities,
)


class _HttpxSecretFilter(logging.Filter):
    def __init__(self, secret: str) -> None:
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        def redact(value: object) -> object:
            rendered = str(value)
            return (
                rendered.replace(self._secret, "[REDACTED]")
                if self._secret in rendered
                else value
            )

        record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(item) for item in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: redact(value) for key, value in record.args.items()}
        return True


def _without_author(query: str, author: str | None) -> str:
    """Drop the author phrase from the free-text terms.

    Exact removal of the phrase the planner put there, never a guess about
    which quoted fragment is a person.
    """
    if not author:
        return query.strip()
    remaining = query.replace(f'"{author}"', " ").replace(author, " ")
    return " ".join(remaining.split())


class OpenAlexBibliographicSource:
    """OpenAlex discovery adapter, enabled only when an API key is configured."""

    name = "OPENALEX"
    capabilities = BibliographicSourceCapabilities(
        name=name,
        searches_metadata=True,
        searches_indexed_full_text=True,
        returns_abstract=True,
        returns_inspectable_full_text=False,
        supports_structured_author=True,
        normalizes_inventory_separators=True,
    )
    _TRANSIENT_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAlex requires a non-empty API key")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        logging.getLogger("httpx").addFilter(_HttpxSecretFilter(api_key))
        self._timeout = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._retry_base_seconds = max(0.0, retry_base_seconds)
        self._transport = transport
        self._sleep = sleep

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        """Search OpenAlex, routing the author to the field that indexes it.

        ``search`` covers title, abstract and full text, never authorship, so a
        name left inside it matches nothing and drags the whole conjunction to
        zero results. Measured against the live API: the taxon alone returns the
        expected work, the taxon with the author returns none, and the taxon
        with the author moved to ``raw_author_name.search`` returns it again.
        """
        terms = _without_author(query, author)
        params: dict[str, str | int] = {
            "per-page": limit,
            "api_key": self._api_key,
        }
        if terms:
            params["search"] = terms
        if author:
            params["filter"] = f"raw_author_name.search:{author}"
        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": "Vitarerum/0.1 (scientific-return monitoring)"},
            transport=self._transport,
        ) as client:
            response = await self._get_with_retry(client, params)
        return [
            self._to_record(item)
            for item in response.json().get("results", [])
            if item.get("title")
        ]

    async def _get_with_retry(
        self, client: httpx.AsyncClient, params: dict[str, str | int]
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            response = await client.get(f"{self._base_url}/works", params=params)
            if (
                response.status_code not in self._TRANSIENT_STATUSES
                or attempt == self._max_retries
            ):
                response.raise_for_status()
                return response
            retry_after = response.headers.get("Retry-After", "").strip()
            try:
                delay = float(retry_after)
            except ValueError:
                delay = self._retry_base_seconds * float(2**attempt)
            await self._sleep(max(0.0, delay))
        raise RuntimeError("OpenAlex retry loop ended unexpectedly")

    def _to_record(self, item: dict[str, Any]) -> BibliographicRecord:
        doi = self._doi(item)
        source_id = str(item.get("id", "")).strip() or doi or str(item["title"])
        authors = tuple(
            str(authorship.get("author", {}).get("display_name", "")).strip()
            for authorship in item.get("authorships", [])
        )
        raw_hash = hashlib.sha256(
            json.dumps(item, sort_keys=True, default=str).encode()
        ).hexdigest()
        locations = item.get("best_oa_location") or item.get("primary_location") or {}
        return BibliographicRecord(
            source=self.name,
            source_record_id=source_id,
            title=str(item["title"]).strip(),
            authors=tuple(author for author in authors if author),
            publication_date=str(item.get("publication_date", "")).strip() or None,
            abstract=self._abstract(item.get("abstract_inverted_index")),
            url=str(locations.get("landing_page_url", "")).strip() or doi,
            doi=doi.removeprefix("https://doi.org/") if doi else None,
            raw_metadata_hash=raw_hash,
        )

    @staticmethod
    def _doi(item: dict[str, Any]) -> str | None:
        doi = str(item.get("doi", "")).strip()
        if doi:
            return doi
        ids = item.get("ids") or {}
        return str(ids.get("doi", "")).strip() or None

    @staticmethod
    def _abstract(value: object) -> str | None:
        if not isinstance(value, dict):
            return None
        positioned: list[tuple[int, str]] = []
        for word, positions in value.items():
            if not isinstance(word, str) or not isinstance(positions, list):
                continue
            positioned.extend(
                (position, word) for position in positions if isinstance(position, int)
            )
        return " ".join(word for _, word in sorted(positioned)) or None
