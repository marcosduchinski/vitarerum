from __future__ import annotations

import json

from app.scientific_return.application.full_agentic_ports import (
    AgenticPlan,
    LearningProposal,
)
from app.scientific_return.application.llm_json import (
    parse_json_object,
    required_bool,
    required_string,
    string_list,
)
from app.scientific_return.application.ports import (
    AgentPromptProvider,
    BibliographicRecord,
    ScientificReturnReasoner,
)
from app.scientific_return.domain.enums import AgentConfidence
from app.scientific_return.domain.full_agentic_models import ArticleAssessment

_PLAN_KEY = "scientific_return_full_agentic_plan"
_READER_KEY = "scientific_return_full_agentic_reader"
_LEARNING_KEY = "scientific_return_full_agentic_learning"


class PromptedFullAgenticReasoner:
    """Three isolated model contracts: planner, untrusted reader and learner."""

    def __init__(
        self,
        reasoner: ScientificReturnReasoner,
        prompts: AgentPromptProvider,
    ) -> None:
        self._reasoner = reasoner
        self._prompts = prompts

    @property
    def model_name(self) -> str:
        return self._reasoner.model_name

    async def plan(
        self,
        *,
        observation: dict[str, object],
        memory: tuple[str, ...],
        history: tuple[dict[str, object], ...],
        allowed_sources: tuple[str, ...],
        remaining_queries: int,
    ) -> AgenticPlan:
        prompt = await self._prompts.get_published(_PLAN_KEY)
        raw = await self._reasoner.generate(
            system_prompt=prompt.content,
            user_prompt=json.dumps(
                {
                    "observation": observation,
                    "curatorialMemory": memory,
                    "history": history,
                    "allowedSources": allowed_sources,
                    "remainingQueries": remaining_queries,
                },
                ensure_ascii=False,
            ),
            temperature=prompt.temperature,
        )
        payload = parse_json_object(
            raw,
            allowed_fields={"queries", "sources", "reasoning", "shouldStop"},
        )
        queries = string_list(payload, "queries")[:remaining_queries]
        requested_sources = string_list(payload, "sources")
        allowed = {source.upper() for source in allowed_sources}
        sources = tuple(
            source.upper() for source in requested_sources if source.upper() in allowed
        )
        should_stop = required_bool(payload, "shouldStop")
        if not should_stop and (not queries or not sources):
            raise ValueError("An active plan requires queries and allowed sources")
        return AgenticPlan(
            queries=queries,
            sources=sources,
            reasoning=required_string(payload, "reasoning"),
            should_stop=should_stop,
        )

    async def assess(
        self,
        *,
        record: BibliographicRecord,
        trusted_context: dict[str, object],
    ) -> ArticleAssessment:
        prompt = await self._prompts.get_published(_READER_KEY)
        # Raw publication text is present only in this tool-free reader call.
        raw = await self._reasoner.generate(
            system_prompt=prompt.content,
            user_prompt=json.dumps(
                {
                    "trustedMuseumContext": trusted_context,
                    "untrustedPublicationData": {
                        "title": record.title[:1000],
                        "authors": list(record.authors)[:30],
                        "abstract": (record.abstract or "")[:12000],
                        "indexedText": (record.indexed_text or "")[:16000],
                        "source": record.source,
                        "sourceRecordId": record.source_record_id,
                    },
                },
                ensure_ascii=False,
            ),
            temperature=prompt.temperature,
        )
        payload = parse_json_object(
            raw,
            allowed_fields={
                "relevant",
                "confidence",
                "explanation",
                "passages",
                "inventoryForms",
                "contradictions",
            },
        )
        passages = tuple(item[:1200] for item in string_list(payload, "passages")[:5])
        return ArticleAssessment(
            relevant=required_bool(payload, "relevant"),
            confidence=AgentConfidence(required_string(payload, "confidence").upper()),
            explanation=required_string(payload, "explanation"),
            passages=passages,
            inventory_forms=string_list(payload, "inventoryForms"),
            contradictions=string_list(payload, "contradictions"),
        )

    async def learn(
        self,
        *,
        decision: str,
        explanation: str,
        context: dict[str, object],
    ) -> LearningProposal:
        prompt = await self._prompts.get_published(_LEARNING_KEY)
        raw = await self._reasoner.generate(
            system_prompt=prompt.content,
            user_prompt=json.dumps(
                {
                    "decision": decision,
                    "curatorExplanation": explanation,
                    "context": context,
                },
                ensure_ascii=False,
            ),
            temperature=prompt.temperature,
        )
        payload = parse_json_object(
            raw,
            allowed_fields={"content", "registeredNumber", "observedForm"},
        )

        def optional_string(key: str) -> str | None:
            value = payload.get(key)
            return value.strip() if isinstance(value, str) and value.strip() else None

        return LearningProposal(
            content=required_string(payload, "content"),
            registered_number=optional_string("registeredNumber"),
            observed_form=optional_string("observedForm"),
        )
