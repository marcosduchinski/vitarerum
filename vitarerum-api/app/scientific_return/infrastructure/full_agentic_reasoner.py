from __future__ import annotations

import json

from app.scientific_return.application.full_agentic_ports import (
    AgenticPlan,
    AssessmentResult,
    LearningProposal,
)
from app.scientific_return.application.llm_json import (
    optional_bool,
    optional_string,
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
from app.scientific_return.domain.enums import (
    AgentConfidence,
    SearchIntent,
    SearchStrategy,
)
from app.scientific_return.domain.full_agentic_models import (
    AgenticSearchSpec,
    ArticleAssessment,
)

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
        source_capabilities: tuple[dict[str, object], ...],
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
                    "sourceCapabilities": source_capabilities,
                    "allowedSources": [
                        item.get("name") for item in source_capabilities
                    ],
                    "remainingQueries": remaining_queries,
                },
                ensure_ascii=False,
            ),
            temperature=prompt.temperature,
        )
        payload = parse_json_object(
            raw,
            allowed_fields={"searches", "reasoning", "shouldStop"},
        )
        raw_searches = payload.get("searches")
        if not isinstance(raw_searches, list):
            raise ValueError("searches must be an array")
        allowed = {
            str(item.get("name", "")).upper()
            for item in source_capabilities
            if isinstance(item, dict)
        }
        searches: list[AgenticSearchSpec] = []
        for raw_search in raw_searches[:remaining_queries]:
            if not isinstance(raw_search, dict):
                raise ValueError("Every search must be an object")
            unknown = set(raw_search) - {
                "source",
                "query",
                "intent",
                "strategy",
                "author",
                "objectId",
            }
            if unknown:
                raise ValueError(f"Unknown search fields: {sorted(unknown)}")
            source = required_string(raw_search, "source").upper()
            if source not in allowed:
                continue
            author_value = raw_search.get("author")
            object_value = raw_search.get("objectId")
            searches.append(
                AgenticSearchSpec(
                    source=source,
                    query=required_string(raw_search, "query"),
                    intent=SearchIntent(required_string(raw_search, "intent").upper()),
                    strategy=SearchStrategy(
                        required_string(raw_search, "strategy").upper()
                    ),
                    author=(
                        author_value.strip()
                        if isinstance(author_value, str) and author_value.strip()
                        else None
                    ),
                    object_id=(
                        object_value.strip()
                        if isinstance(object_value, str) and object_value.strip()
                        else None
                    ),
                )
            )
        # Measured against gemma4:12b: the model returns well-formed JSON with
        # correct searches and simply omits both flags. Deriving the stop signal
        # from the searches keeps the loop safe — no searches means stop, so an
        # empty answer cannot spin the planner — while a stated value that is
        # not a boolean is still a contract violation.
        should_stop = optional_bool(payload, "shouldStop", default=not searches)
        if not should_stop and not searches:
            raise ValueError("An active plan requires allowed searches")
        return AgenticPlan(
            searches=tuple(searches),
            reasoning=optional_string(
                payload, "reasoning", default="The planner stated no reason"
            ),
            should_stop=should_stop,
        )

    async def assess(
        self,
        *,
        record: BibliographicRecord,
        trusted_context: dict[str, object],
    ) -> AssessmentResult:
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
        return AssessmentResult(
            assessment=ArticleAssessment(
                relevant=required_bool(payload, "relevant"),
                confidence=AgentConfidence(
                    required_string(payload, "confidence").upper()
                ),
                explanation=required_string(payload, "explanation"),
                passages=passages,
                inventory_forms=string_list(payload, "inventoryForms"),
                contradictions=string_list(payload, "contradictions"),
            ),
            prompt_version_id=prompt.version_id,
            prompt_version=prompt.version_label,
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
