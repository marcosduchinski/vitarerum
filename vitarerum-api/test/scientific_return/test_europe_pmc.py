from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from app.scientific_return.application.analysis import build_evidences
from app.scientific_return.domain.enums import EvidenceType
from app.scientific_return.domain.models import CandidatePublicationId
from app.scientific_return.infrastructure.europe_pmc import (
    EuropePmcBibliographicSource,
)
from test.scientific_return.test_scientific_return import _snapshot


@pytest.mark.asyncio
async def test_europe_pmc_enriches_record_with_open_access_full_text() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "resultList": {
                        "result": [
                            {
                                "source": "MED",
                                "id": "123",
                                "pmcid": "PMC123",
                                "doi": "10.1000/example",
                                "title": "A new species of Acontias",
                                "firstPublicationDate": "2023-09-19",
                                "authorList": {
                                    "author": [
                                        {"fullName": "Mariana P. Marques"}
                                    ]
                                },
                                "abstractText": "A taxonomic account.",
                            }
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            content=(
                b"<article><body><p>Examined specimen "
                b"MB03-001524: Acontias mukwando.</p></body></article>"
            ),
            headers={"Content-Type": "application/xml"},
        )

    source = EuropePmcBibliographicSource(
        base_url="https://europe-pmc.test/rest",
        timeout_seconds=1,
        full_text_result_limit=10,
        transport=httpx.MockTransport(handler),
    )

    records = await source.search('"MUHNAC/MB03-001524"', 10)
    evidences = build_evidences(
        CandidatePublicationId("candidate-1"),
        _snapshot(),
        records[0],
        created_at=datetime.now(tz=UTC),
    )

    assert len(requests) == 2
    assert parse_qs(requests[0].url.query.decode())["resultType"] == ["core"]
    assert records[0].authors == ("Mariana P. Marques",)
    assert records[0].indexed_text_source == "full_text"
    assert any(
        evidence.type is EvidenceType.INVENTORY_NUMBER
        and evidence.source_field == "full_text"
        for evidence in evidences
    )


@pytest.mark.asyncio
async def test_europe_pmc_caches_full_text_between_queries() -> None:
    full_text_requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal full_text_requests
        if request.url.path.endswith("/fullTextXML"):
            full_text_requests += 1
            return httpx.Response(200, content=b"<article><body>text</body></article>")
        return httpx.Response(
            200,
            json={
                "resultList": {
                    "result": [
                        {
                            "source": "PMC",
                            "id": "PMC123",
                            "pmcid": "PMC123",
                            "title": "Title",
                        }
                    ]
                }
            },
        )

    source = EuropePmcBibliographicSource(
        base_url="https://europe-pmc.test/rest",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    await source.search("first", 10)
    await source.search("second", 10)

    assert full_text_requests == 1
