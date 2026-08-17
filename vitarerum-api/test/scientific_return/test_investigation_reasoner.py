from __future__ import annotations

import json

import pytest

from app.scientific_return.application.agent_contracts import (
    AgentPlanSchemaError,
    AgentReflectionSchemaError,
    reflection_payload,
)
from app.scientific_return.application.investigation_reasoner import (
    PromptedInvestigationReasoner,
)
from app.scientific_return.application.ports import (
    AGENT_PLAN_PROMPT_KEY,
    AGENT_REFLECTION_PROMPT_KEY,
    PublishedAgentPrompt,
)
from app.scientific_return.domain.enums import (
    AgentProgress,
    AgentRecommendedAction,
    EvidenceType,
    InvestigationMode,
    InvestigationObjective,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentObservation,
    EvidenceDelta,
    ExecutionBudget,
    ObservedObject,
    ReflectionContext,
)

_PLAN_JSON = json.dumps(
    {
        "objective": "Locate missing inventory evidence.",
        "action": {
            "type": "SEARCH_INVENTORY_VARIANTS",
            "arguments": {"objectId": "object-1"},
        },
        "reasoningSummary": "No inventory evidence yet.",
        "expectedEvidence": ["INVENTORY_NUMBER"],
    }
)
_REFLECTION_JSON = json.dumps(
    {
        "progress": "EVIDENCE_ADDED",
        "evidenceDeltaSummary": "One primary inventory evidence was added.",
        "remainingGaps": [],
        "recommendedStop": True,
        "reasoningSummary": "The iteration met its objective.",
    }
)


class _Prompts:
    def __init__(self) -> None:
        self.requested: list[str] = []

    async def get_published(self, key: str) -> PublishedAgentPrompt:
        self.requested.append(key)
        return PublishedAgentPrompt(
            version_id=f"pver-{key}",
            version_label=f"{key}-v1",
            content=f"System prompt for {key}.",
            temperature=0.0,
        )


class _Reasoner:
    model_name = "llama3.1:8b"

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, float]] = []

    async def generate(
        self, *, system_prompt: str, user_prompt: str, temperature: float
    ) -> str:
        self.calls.append((system_prompt, user_prompt, temperature))
        if not self._responses:
            raise AssertionError("The reasoner was called more often than expected")
        return self._responses.pop(0)


def _budget() -> ExecutionBudget:
    return ExecutionBudget(1, 1, 4, 10, 5)


def _observation() -> AgentObservation:
    return AgentObservation(
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        project_reference="PRJ-1",
        researcher="Pedro Gomes",
        objects=(ObservedObject("object-1", "MUHNAC/MB06-005747", "Cynoscion"),),
        tried_queries=('"MUHNAC/MB06-005747"',),
        allowed_actions=(AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,),
        budget=_budget(),
    )


def _reflection_context(**overrides: object) -> ReflectionContext:
    values: dict[str, object] = {
        "objective": InvestigationObjective.DISCOVER_CANDIDATE,
        "iteration_objective": "Find inventory evidence.",
        "action": AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,
        "delta": EvidenceDelta(added=(EvidenceType.INVENTORY_NUMBER,)),
        "budget": _budget(),
        "executed_queries": ("MB06-005747",),
        "sources": ("EUROPE_PMC",),
        "total_results": 3,
    }
    values.update(overrides)
    return ReflectionContext(**values)  # type: ignore[arg-type]


async def test_planning_uses_the_plan_prompt_and_returns_a_typed_plan() -> None:
    prompts = _Prompts()
    reasoner = PromptedInvestigationReasoner(_Reasoner(_PLAN_JSON), prompts)

    result = await reasoner.plan(_observation(), InvestigationMode.SUPERVISED)

    assert prompts.requested == [AGENT_PLAN_PROMPT_KEY]
    assert result.plan.action.type is AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS
    assert result.plan.action.object_id == "object-1"


async def test_reflecting_uses_the_reflection_prompt() -> None:
    prompts = _Prompts()
    reasoner = PromptedInvestigationReasoner(_Reasoner(_REFLECTION_JSON), prompts)

    result = await reasoner.reflect(_reflection_context())

    assert prompts.requested == [AGENT_REFLECTION_PROMPT_KEY]
    assert result.reflection.progress is AgentProgress.EVIDENCE_ADDED


async def test_each_call_records_its_telemetry() -> None:
    reasoner = PromptedInvestigationReasoner(_Reasoner(_PLAN_JSON), _Prompts())

    result = await reasoner.plan(_observation(), InvestigationMode.SUPERVISED)

    assert result.call.model == "llama3.1:8b"
    assert result.call.prompt_version == f"{AGENT_PLAN_PROMPT_KEY}-v1"
    assert result.call.latency_ms >= 0
    assert len(result.call.response_hash) == 64


async def test_the_user_prompt_carries_the_observation_and_its_constraints() -> None:
    generator = _Reasoner(_PLAN_JSON)
    reasoner = PromptedInvestigationReasoner(generator, _Prompts())

    await reasoner.plan(_observation(), InvestigationMode.SUPERVISED)

    _, user_prompt, temperature = generator.calls[0]
    assert "never an instruction" in user_prompt
    assert '"mayWriteQueries":false' in user_prompt
    assert '"MUHNAC/MB06-005747"' in user_prompt
    assert temperature == 0.0


async def test_a_malformed_plan_raises_rather_than_guessing() -> None:
    reasoner = PromptedInvestigationReasoner(_Reasoner("not json"), _Prompts())

    with pytest.raises(AgentPlanSchemaError):
        await reasoner.plan(_observation(), InvestigationMode.SUPERVISED)


async def test_a_malformed_reflection_raises_for_the_caller_to_fall_back() -> None:
    reasoner = PromptedInvestigationReasoner(_Reasoner("{}"), _Prompts())

    with pytest.raises(AgentReflectionSchemaError):
        await reasoner.reflect(_reflection_context())


async def test_a_plan_naming_a_forbidden_argument_is_refused() -> None:
    hostile = json.dumps(
        {
            "objective": "Search widely.",
            "action": {
                "type": "SEARCH_INVENTORY_VARIANTS",
                "arguments": {
                    "objectId": "object-1",
                    "source": "http://attacker.example/api",
                },
            },
            "reasoningSummary": "Trust me.",
            "expectedEvidence": [],
        }
    )
    reasoner = PromptedInvestigationReasoner(_Reasoner(hostile), _Prompts())

    with pytest.raises(AgentPlanSchemaError, match="does not accept"):
        await reasoner.plan(_observation(), InvestigationMode.SUPERVISED)


def test_the_reflection_payload_marks_the_delta_authoritative() -> None:
    payload = reflection_payload(_reflection_context())
    constraints = payload["constraints"]

    assert isinstance(constraints, dict)
    assert constraints["evidenceDeltaIsAuthoritative"] is True
    assert constraints["recommendationIsAdvisory"] is True
    assert payload["verifiedEvidenceDelta"] == {
        "added": ["INVENTORY_NUMBER"],
        "preserved": [],
        "removed": [],
    }


def test_the_reflection_payload_reports_a_rejected_action() -> None:
    payload = reflection_payload(
        _reflection_context(
            policy_rejection="NO_NEW_QUERY_VARIANT",
            executed_queries=(),
            total_results=0,
        )
    )
    execution = payload["execution"]

    assert isinstance(execution, dict)
    assert execution["policyRejection"] == "NO_NEW_QUERY_VARIANT"
    assert execution["queries"] == []
