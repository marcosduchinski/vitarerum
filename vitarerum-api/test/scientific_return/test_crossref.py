from __future__ import annotations

import httpx
import pytest

from app.scientific_return.infrastructure.crossref import CrossrefBibliographicSource


@pytest.mark.asyncio
async def test_crossref_retries_429_using_retry_after() -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "title": ["A new species of <i>Acontias</i> &amp; allies"],
                            "author": [{"given": "Mariana P.", "family": "Marques"}],
                            "DOI": "10.1000/example",
                        }
                    ]
                }
            },
        )

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    source = CrossrefBibliographicSource(
        base_url="https://api.crossref.test",
        timeout_seconds=1,
        mailto="collections@example.test",
        max_retries=2,
        min_interval_seconds=0,
        transport=httpx.MockTransport(handler),
        sleep=record_sleep,
    )

    records = await source.search('"Mariana P. Marques" "Acontias mukwando"', 20)

    assert len(requests) == 2
    assert sleeps == [2.0]
    assert requests[0].url.params["mailto"] == "collections@example.test"
    assert records[0].doi == "10.1000/example"
    assert records[0].title == "A new species of Acontias & allies"


@pytest.mark.asyncio
async def test_crossref_does_not_retry_permanent_client_error() -> None:
    request_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(400, request=request)

    source = CrossrefBibliographicSource(
        base_url="https://api.crossref.test",
        timeout_seconds=1,
        max_retries=3,
        min_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await source.search("invalid", 20)

    assert request_count == 1
