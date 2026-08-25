from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any
from xml.etree import ElementTree

import httpx

from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSourceCapabilities,
)

logger = logging.getLogger(__name__)


class EuropePmcBibliographicSource:
    """Europe PMC adapter with transient, open-access full-text enrichment."""

    name = "EUROPE_PMC"
    capabilities = BibliographicSourceCapabilities(
        name=name,
        searches_metadata=True,
        searches_indexed_full_text=True,
        returns_abstract=True,
        returns_inspectable_full_text=True,
        supports_structured_author=False,
        normalizes_inventory_separators=True,
    )
    _TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
    _MAX_FULL_TEXT_BYTES = 15 * 1024 * 1024

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        full_text_result_limit: int = 10,
        email: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._retry_base_seconds = max(0.0, retry_base_seconds)
        self._full_text_result_limit = max(0, full_text_result_limit)
        self._email = email
        self._transport = transport
        self._sleep = sleep
        self._full_text_cache: dict[str, str | None] = {}

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
            "resultType": "core",
            "pageSize": limit,
            "format": "json",
        }
        if self._email:
            params["email"] = self._email
        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": "Vitarerum/0.1 (scientific-return evaluation)"},
            transport=self._transport,
        ) as client:
            response = await self._get_with_retry(client, "search", params=params)
            items = response.json().get("resultList", {}).get("result", [])
            records: list[BibliographicRecord] = []
            for index, item in enumerate(items):
                if not isinstance(item, dict) or not item.get("title"):
                    continue
                indexed_text = None
                pmcid = str(item.get("pmcid", "")).strip()
                if pmcid and index < self._full_text_result_limit:
                    indexed_text = await self._get_full_text(client, pmcid)
                records.append(self._to_record(item, indexed_text))
        return records

    async def _get_full_text(self, client: httpx.AsyncClient, pmcid: str) -> str | None:
        if pmcid in self._full_text_cache:
            return self._full_text_cache[pmcid]
        try:
            response = await self._get_with_retry(client, f"{pmcid}/fullTextXML")
        except httpx.HTTPError:
            logger.warning(
                "Europe PMC full-text enrichment failed for %s; using metadata.",
                pmcid,
            )
            self._full_text_cache[pmcid] = None
            return None
        if len(response.content) > self._MAX_FULL_TEXT_BYTES:
            self._full_text_cache[pmcid] = None
            return None
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError:
            self._full_text_cache[pmcid] = None
            return None
        text = " ".join(" ".join(root.itertext()).split()) or None
        self._full_text_cache[pmcid] = text
        return text

    async def _get_with_retry(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            response = await client.get(f"{self._base_url}/{path}", params=params)
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
        raise RuntimeError("Europe PMC retry loop ended unexpectedly")

    def _to_record(
        self, item: dict[str, Any], indexed_text: str | None
    ) -> BibliographicRecord:
        source = str(item.get("source", "")).strip()
        external_id = str(item.get("id", "")).strip()
        pmcid = str(item.get("pmcid", "")).strip()
        doi = str(item.get("doi", "")).strip() or None
        source_id = ":".join(part for part in (source, external_id) if part)
        if not source_id:
            source_id = pmcid or doi or str(item["title"])
        authors = self._authors(item)
        raw_hash = hashlib.sha256(
            json.dumps(item, sort_keys=True, default=str).encode()
        ).hexdigest()
        return BibliographicRecord(
            source=self.name,
            source_record_id=source_id,
            title=self._clean_markup(str(item["title"])) or str(item["title"]),
            authors=authors,
            publication_date=(
                str(item.get("firstPublicationDate", "")).strip()
                or str(
                    item.get("journalInfo", {}).get("printPublicationDate", "")
                ).strip()
                or str(item.get("pubYear", "")).strip()
                or None
            ),
            abstract=self._clean_markup(str(item.get("abstractText", ""))),
            url=self._url(item, source, external_id, pmcid),
            doi=doi,
            raw_metadata_hash=raw_hash,
            indexed_text=indexed_text,
            indexed_text_source="full_text" if indexed_text else None,
        )

    @staticmethod
    def _authors(item: dict[str, Any]) -> tuple[str, ...]:
        author_list = item.get("authorList") or {}
        if isinstance(author_list, dict):
            authors = author_list.get("author") or []
            if isinstance(authors, list):
                names = tuple(
                    str(author.get("fullName", "")).strip()
                    for author in authors
                    if isinstance(author, dict)
                )
                if any(names):
                    return tuple(name for name in names if name)
        author_string = str(item.get("authorString", "")).strip().rstrip(".")
        return tuple(name.strip() for name in author_string.split(",") if name.strip())

    @staticmethod
    def _url(
        item: dict[str, Any], source: str, external_id: str, pmcid: str
    ) -> str | None:
        urls = (item.get("fullTextUrlList") or {}).get("fullTextUrl") or []
        if isinstance(urls, list):
            for entry in urls:
                if not isinstance(entry, dict):
                    continue
                url = str(entry.get("url", "")).strip()
                if url:
                    return url
        if pmcid:
            return f"https://europepmc.org/articles/{pmcid}"
        if source and external_id:
            return f"https://europepmc.org/article/{source}/{external_id}"
        return None

    @staticmethod
    def _clean_markup(value: str) -> str | None:
        if not value.strip():
            return None
        without_tags = re.sub(r"<[^>]+>", " ", value)
        return " ".join(html.unescape(without_tags).split())
