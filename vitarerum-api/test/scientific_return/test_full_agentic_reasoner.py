import json

import pytest

from app.scientific_return.application.ports import (
    BibliographicRecord,
    PublishedAgentPrompt,
)
from app.scientific_return.infrastructure.full_agentic_reasoner import (
    PromptedFullAgenticReasoner,
)


class PromptProvider:
    async def get_published(self, key: str) -> PublishedAgentPrompt:
        return PublishedAgentPrompt("version-id", "v2", "prompt", 0.1)


class Reasoner:
    model_name = "test"

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.user_prompt = ""

    async def generate(
        self, *, system_prompt: str, user_prompt: str, temperature: float
    ) -> str:
        self.user_prompt = user_prompt
        return json.dumps(self.payload)


_CAPABILITIES = (
    {
        "name": "EUROPE_PMC",
        "searchesMetadata": True,
        "searchesIndexedFullText": True,
        "returnsInspectableFullText": True,
    },
)


@pytest.mark.asyncio
async def test_planner_parses_specs_and_filters_unknown_sources() -> None:
    reasoner = Reasoner(
        {
            "searches": [
                {
                    "source": "EUROPE_PMC",
                    "query": '"MB04-001066"',
                    "author": None,
                    "intent": "INVENTORY_EVIDENCE",
                    "strategy": "INVENTORY_QUERY",
                    "objectId": "object-1",
                },
                {
                    "source": "INVENTED",
                    "query": "anything",
                    "author": None,
                    "intent": "DISCOVERY",
                    "strategy": "OBJECT_QUERY",
                    "objectId": None,
                },
            ],
            "reasoning": "Search inspectable text",
            "shouldStop": False,
        }
    )

    plan = await PromptedFullAgenticReasoner(reasoner, PromptProvider()).plan(
        observation={},
        memory=(),
        history=(),
        source_capabilities=_CAPABILITIES,
        remaining_queries=2,
    )

    assert len(plan.searches) == 1
    assert plan.searches[0].source == "EUROPE_PMC"
    assert "sourceCapabilities" in json.loads(reasoner.user_prompt)


@pytest.mark.asyncio
async def test_planner_requires_a_real_boolean_stop_value() -> None:
    reasoner = Reasoner(
        {
            "searches": [],
            "reasoning": "Stop",
            "shouldStop": "false",
        }
    )

    with pytest.raises(ValueError, match="shouldStop"):
        await PromptedFullAgenticReasoner(reasoner, PromptProvider()).plan(
            observation={},
            memory=(),
            history=(),
            source_capabilities=_CAPABILITIES,
            remaining_queries=2,
        )


@pytest.mark.asyncio
async def test_reader_returns_the_published_prompt_identity() -> None:
    reasoner = Reasoner(
        {
            "relevant": True,
            "confidence": "HIGH",
            "explanation": "Observed in the abstract",
            "passages": ["MB04-001066"],
            "inventoryForms": ["MB04-001066"],
            "contradictions": [],
        }
    )
    record = BibliographicRecord(
        source="EUROPE_PMC",
        source_record_id="PMC1",
        title="Study",
        authors=(),
        publication_date=None,
        abstract="MB04-001066",
        url=None,
        doi=None,
        raw_metadata_hash="hash",
    )

    result = await PromptedFullAgenticReasoner(reasoner, PromptProvider()).assess(
        record=record,
        trusted_context={},
    )

    assert result.prompt_version_id == "version-id"
    assert result.prompt_version == "v2"
    assert result.assessment.relevant is True


@pytest.mark.asyncio
async def test_a_plan_survives_the_flags_the_model_omits() -> None:
    """Measured against gemma4:12b: valid searches, both flags absent."""
    reasoner = Reasoner(
        {
            "searches": [
                {
                    "source": "EUROPE_PMC",
                    "query": "Eluma cristata",
                    "author": None,
                    "intent": "DISCOVERY",
                    "strategy": "OBJECT_QUERY",
                    "objectId": "o1",
                }
            ]
        }
    )

    plan = await PromptedFullAgenticReasoner(reasoner, PromptProvider()).plan(
        observation={},
        memory=(),
        history=(),
        source_capabilities=_CAPABILITIES,
        remaining_queries=6,
    )

    assert [search.query for search in plan.searches] == ["Eluma cristata"]
    assert plan.should_stop is False
    assert plan.reasoning == "The planner stated no reason"


@pytest.mark.asyncio
async def test_an_empty_answer_without_flags_stops_instead_of_looping() -> None:
    reasoner = Reasoner({"searches": []})

    plan = await PromptedFullAgenticReasoner(reasoner, PromptProvider()).plan(
        observation={},
        memory=(),
        history=(),
        source_capabilities=_CAPABILITIES,
        remaining_queries=6,
    )

    assert plan.searches == ()
    assert plan.should_stop is True


@pytest.mark.asyncio
async def test_a_stated_reasoning_of_the_wrong_type_is_still_refused() -> None:
    reasoner = Reasoner(
        {
            "searches": [],
            "reasoning": 42,
            "shouldStop": True,
        }
    )

    with pytest.raises(ValueError, match="reasoning"):
        await PromptedFullAgenticReasoner(reasoner, PromptProvider()).plan(
            observation={},
            memory=(),
            history=(),
            source_capabilities=_CAPABILITIES,
            remaining_queries=2,
        )
