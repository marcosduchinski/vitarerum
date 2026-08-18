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


@pytest.mark.asyncio
async def test_openalex_routes_the_author_out_of_the_free_text_search() -> None:
    """Measured against the live API: a name inside ``search`` matches nothing.

    ``search`` covers title, abstract and full text, never authorship, so the
    author has to travel in ``raw_author_name.search`` or the whole conjunction
    returns zero results.
    """
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    source = OpenAlexBibliographicSource(
        base_url="https://api.openalex.test",
        api_key="key-1",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    await source.search(
        '"Diogo Parrinha" "Rhoptropus nivimontanus"',
        20,
        author="Diogo Parrinha",
    )

    params = requests[0].url.params
    assert params["search"] == '"Rhoptropus nivimontanus"'
    assert params["filter"] == "raw_author_name.search:Diogo Parrinha"


@pytest.mark.asyncio
async def test_openalex_keeps_an_author_free_query_untouched() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    source = OpenAlexBibliographicSource(
        base_url="https://api.openalex.test",
        api_key="key-1",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    await source.search('"MB03-001522" "Acontias"', 20)

    params = requests[0].url.params
    assert params["search"] == '"MB03-001522" "Acontias"'
    assert "filter" not in params


@pytest.mark.asyncio
async def test_openalex_searches_by_author_alone_when_no_terms_remain() -> None:
    """An author-only strategy must not send an empty ``search``."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    source = OpenAlexBibliographicSource(
        base_url="https://api.openalex.test",
        api_key="key-1",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    await source.search('"Diogo Parrinha"', 20, author="Diogo Parrinha")

    params = requests[0].url.params
    assert "search" not in params
    assert params["filter"] == "raw_author_name.search:Diogo Parrinha"


def test_openalex_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        OpenAlexBibliographicSource(
            base_url="https://api.openalex.test",
            api_key="",
            timeout_seconds=1,
        )
