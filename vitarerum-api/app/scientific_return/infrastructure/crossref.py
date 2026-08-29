from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSourceCapabilities,
)
from app.scientific_return.infrastructure.source_wait import (
    SourceDeadline,
    SourceWaitBudget,
)


class CrossrefBibliographicSource:
    name = "CROSSREF"
    capabilities = BibliographicSourceCapabilities(
        name=name,
        searches_metadata=True,
        searches_indexed_full_text=False,
        returns_abstract=True,
        returns_inspectable_full_text=False,
        supports_structured_author=False,
        normalizes_inventory_separators=True,
    )
    _TRANSIENT_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        mailto: str | None = None,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        min_interval_seconds: float = 0.25,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        wait_budget: SourceWaitBudget | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._mailto = mailto
        self._max_retries = max(0, max_retries)
        self._retry_base_seconds = max(0.0, retry_base_seconds)
        self._min_interval_seconds = max(0.0, min_interval_seconds)
        self._transport = transport
        self._sleep = sleep
        self._wait_budget = wait_budget or SourceWaitBudget(
            max_retry_after_seconds=60.0, total_timeout_seconds=120.0
        )
        self._request_lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        """Accepts ``author`` for protocol compatibility and ignores it.

        This source's free-text index covers author names, so the name stays
        inside ``query`` where the planner put it, and the audited text is
        exactly what is sent.
        """
        params: dict[str, str | int] = {
            "query": query,
            "rows": limit,
        }
        if self._mailto:
            params["mailto"] = self._mailto
        user_agent = "Vitarerum/0.1 (scientific-return monitoring)"
        if self._mailto:
            user_agent = f"Vitarerum/0.1 (mailto:{self._mailto})"
        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": user_agent},
            transport=self._transport,
        ) as client:
            response = await self._get_with_retry(
                client, params, self._wait_budget.start(self.name)
            )
        payload = response.json()
        items = payload.get("message", {}).get("items", [])
        return [self._to_record(item) for item in items if item.get("title")]

    async def _get_with_retry(
        self,
        client: httpx.AsyncClient,
        params: dict[str, str | int],
        deadline: SourceDeadline,
    ) -> httpx.Response:
        # The lock is taken before the budget is spent, so the wait for another
        # caller's minimum interval counts against this call's deadline too.
        async with self._request_lock:
            for attempt in range(self._max_retries + 1):
                await self._respect_minimum_interval()
                deadline.ensure(self._timeout)
                self._last_request_at = time.monotonic()
                response = await client.get(f"{self._base_url}/works", params=params)
                if (
                    response.status_code not in self._TRANSIENT_STATUSES
                    or attempt == self._max_retries
                ):
                    response.raise_for_status()
                    return response
                delay = self._wait_budget.retry_delay(
                    source=self.name,
                    retry_after_header=response.headers.get("Retry-After", ""),
                    attempt=attempt,
                    base_seconds=self._retry_base_seconds,
                )
                deadline.ensure(delay)
                await self._sleep(delay)
        raise RuntimeError("Crossref retry loop ended unexpectedly")

    async def _respect_minimum_interval(self) -> None:
        if self._last_request_at is None:
            return
        remaining = self._min_interval_seconds - (
            time.monotonic() - self._last_request_at
        )
        if remaining > 0:
            await self._sleep(remaining)

    def _to_record(self, item: dict[str, Any]) -> BibliographicRecord:
        title = self._clean_markup(str(item.get("title", [""])[0])) or ""
        authors = tuple(
            " ".join(
                part
                for part in (
                    str(author.get("given", "")).strip(),
                    str(author.get("family", "")).strip(),
                )
                if part
            )
            for author in item.get("author", [])
        )
        doi = str(item.get("DOI", "")).strip() or None
        source_id = doi or str(item.get("URL", "")).strip() or title
        raw_hash = hashlib.sha256(
            json.dumps(item, sort_keys=True, default=str).encode()
        ).hexdigest()
        return BibliographicRecord(
            source=self.name,
            source_record_id=source_id,
            title=title,
            authors=tuple(author for author in authors if author),
            publication_date=self._publication_date(item),
            abstract=self._clean_abstract(item.get("abstract")),
            url=str(item.get("URL", "")).strip() or None,
            doi=doi,
            raw_metadata_hash=raw_hash,
        )

    @staticmethod
    def _publication_date(item: dict[str, Any]) -> str | None:
        parts = item.get("published", {}).get("date-parts", [])
        if not parts or not parts[0]:
            return None
        values = [str(value) for value in parts[0][:3]]
        return "-".join(values)

    @staticmethod
    def _clean_abstract(value: object) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        return CrossrefBibliographicSource._clean_markup(value)

    @staticmethod
    def _clean_markup(value: str) -> str | None:
        if not value.strip():
            return None
        without_tags = re.sub(r"<[^>]+>", " ", value)
        return " ".join(html.unescape(without_tags).split())
