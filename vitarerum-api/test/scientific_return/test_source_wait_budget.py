"""Bounded waiting: no source may park a worker beyond its stated budget."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from app.scientific_return.application.ports import (
    SourceDeadlineExceeded,
    SourceRetryDelayExceeded,
)
from app.scientific_return.infrastructure.crossref import CrossrefBibliographicSource
from app.scientific_return.infrastructure.europe_pmc import (
    EuropePmcBibliographicSource,
)
from app.scientific_return.infrastructure.openalex import OpenAlexBibliographicSource
from app.scientific_return.infrastructure.source_rate_limiter import (
    RateLimitedBibliographicSource,
)
from app.scientific_return.infrastructure.source_wait import SourceWaitBudget

_BUDGET = SourceWaitBudget(max_retry_after_seconds=60.0, total_timeout_seconds=120.0)


class _NoThrottle:
    async def acquire(self, source: str, interval_seconds: float) -> None:
        return None


def _throttled(retry_after: str) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": retry_after}, json={})

    return httpx.MockTransport(handler)


async def _never_sleep(seconds: float) -> None:
    raise AssertionError(f"An excessive delay must not be slept: {seconds}s")


@pytest.mark.asyncio
async def test_numeric_retry_after_above_the_ceiling_aborts_the_attempt() -> None:
    source = EuropePmcBibliographicSource(
        base_url="https://europe-pmc.test/rest",
        timeout_seconds=1,
        transport=_throttled("86400"),
        sleep=_never_sleep,
        wait_budget=_BUDGET,
    )

    with pytest.raises(SourceRetryDelayExceeded):
        await source.search("anything", 5)


@pytest.mark.asyncio
async def test_a_distant_http_date_is_read_and_refused() -> None:
    far = format_datetime(datetime.now(tz=UTC) + timedelta(hours=6))
    source = CrossrefBibliographicSource(
        base_url="https://crossref.test",
        timeout_seconds=1,
        min_interval_seconds=0.0,
        transport=_throttled(far),
        sleep=_never_sleep,
        wait_budget=_BUDGET,
    )

    with pytest.raises(SourceRetryDelayExceeded):
        await source.search("anything", 5)


@pytest.mark.asyncio
async def test_an_unparseable_retry_after_falls_back_to_backoff() -> None:
    slept: list[float] = []

    async def record(seconds: float) -> None:
        slept.append(seconds)

    source = OpenAlexBibliographicSource(
        base_url="https://openalex.test",
        api_key="key",
        timeout_seconds=1,
        max_retries=1,
        retry_base_seconds=0.5,
        transport=_throttled("soon-ish"),
        sleep=record,
        wait_budget=_BUDGET,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await source.search("anything", 5)
    assert slept == [0.5]


@pytest.mark.asyncio
async def test_the_total_budget_stops_a_source_that_keeps_asking_to_wait() -> None:
    async def instant(seconds: float) -> None:
        return None

    source = EuropePmcBibliographicSource(
        base_url="https://europe-pmc.test/rest",
        timeout_seconds=1,
        max_retries=50,
        retry_base_seconds=0.0,
        transport=_throttled("1"),
        sleep=instant,
        # Nothing fits: the budget is already spent when the first attempt asks
        # for room to run.
        wait_budget=SourceWaitBudget(
            max_retry_after_seconds=60.0, total_timeout_seconds=0.001
        ),
    )

    with pytest.raises(SourceDeadlineExceeded):
        await source.search("anything", 5)


@pytest.mark.asyncio
async def test_full_text_enrichment_degrades_instead_of_losing_the_search() -> None:
    """The search result survives an enrichment that runs out of budget."""

    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "resultList": {
                        "result": [
                            {
                                "source": "MED",
                                "id": "1",
                                "pmcid": "PMC1",
                                "title": "A record worth keeping",
                                "abstractText": "Metadata only.",
                            }
                        ]
                    }
                },
            )
        return httpx.Response(429, headers={"Retry-After": "86400"}, json={})

    source = EuropePmcBibliographicSource(
        base_url="https://europe-pmc.test/rest",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
        sleep=_never_sleep,
        wait_budget=_BUDGET,
    )

    records = await source.search("anything", 5)

    assert [record.title for record in records] == ["A record worth keeping"]
    assert records[0].indexed_text is None


@pytest.mark.asyncio
async def test_the_budget_is_a_ceiling_not_only_a_gate() -> None:
    """A slow request must be cut, not merely refused permission to start.

    The inner deadline only decides whether an operation may begin, so a
    request that runs long finishes regardless. The worker plans its slice from
    this budget, so something has to enforce it.
    """

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.3)
        return httpx.Response(200, json={"resultList": {"result": []}})

    source = EuropePmcBibliographicSource(
        base_url="https://europe-pmc.test/rest",
        timeout_seconds=5,
        transport=httpx.MockTransport(slow),
        wait_budget=_BUDGET,
    )
    limited = RateLimitedBibliographicSource(source, _NoThrottle(), 0.0, 0.05)

    with pytest.raises(SourceDeadlineExceeded):
        await limited.search("anything", 5)


@pytest.mark.asyncio
async def test_the_throttle_wait_counts_against_the_same_budget() -> None:
    """It used to run before the budget started, so it was outside it."""

    class SlowThrottle:
        async def acquire(self, source: str, interval_seconds: float) -> None:
            await asyncio.sleep(0.3)

    source = EuropePmcBibliographicSource(
        base_url="https://europe-pmc.test/rest",
        timeout_seconds=5,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"resultList": {"result": []}})
        ),
        wait_budget=_BUDGET,
    )
    limited = RateLimitedBibliographicSource(source, SlowThrottle(), 0.0, 0.05)

    with pytest.raises(SourceDeadlineExceeded):
        await limited.search("anything", 5)
