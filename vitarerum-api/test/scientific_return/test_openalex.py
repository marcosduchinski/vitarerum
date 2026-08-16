from __future__ import annotations

import httpx
import pytest

from app.scientific_return.infrastructure.openalex import OpenAlexBibliographicSource


@pytest.mark.asyncio
async def test_openalex_maps_doi_authors_and_inverted_abstract() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "title": "A new species of Acontias",
                        "doi": "https://doi.org/10.1000/example",
                        "publication_date": "2023-09-19",
                        "authorships": [
                            {"author": {"display_name": "Mariana P. Marques"}}
                        ],
                        "abstract_inverted_index": {
                            "Examined": [0],
                            "MB03-001522": [1],
                        },
                        "best_oa_location": {
                            "landing_page_url": "https://example.test/work"
                        },
                    }
                ]
            },
        )

    source = OpenAlexBibliographicSource(
        base_url="https://api.openalex.test",
        api_key="key-1",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    records = await source.search('"MB03-001522"', 20)

    assert requests[0].url.params["api_key"] == "key-1"
    assert records[0].doi == "10.1000/example"
    assert records[0].authors == ("Mariana P. Marques",)
    assert records[0].abstract == "Examined MB03-001522"


def test_openalex_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        OpenAlexBibliographicSource(
            base_url="https://api.openalex.test",
            api_key="",
            timeout_seconds=1,
        )
