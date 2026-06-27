"""KG-RAG narrative application service.

Orchestrates the pipeline: resolve the rendering style → build/expand/validate the
CIDOC-CRM graph (via the ACL) → select the persona prompt → run the local LLM.
``execute`` takes an ``Input`` dataclass, per the repo-wide convention.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.museum_narrative.application.prompts import (
    build_system_prompt,
    build_user_prompt,
)
from app.ai.museum_narrative.domain.models import (
    DEFAULT_NARRATIVE_TYPE,
    GeneratedNarrative,
    NarrativeId,
    NarrativeType,
    ResolutionSource,
)
from app.ai.museum_narrative.domain.ports import (
    CidocGraphPort,
    ModelUnavailable,
    NarrativeModelPort,
    NarrativeNotFound,
    NarrativeRepository,
    UnsupportedNarrativeType,
)

_DEFAULT_TEMPERATURE = 0.3
_DEFAULT_LANGUAGE = "pt"


@dataclass(frozen=True, slots=True)
class GenerateNarrativeInput:
    record_id: str
    narrative_type: str | None = None
    target_language: str = _DEFAULT_LANGUAGE
    creativity_temperature: float = _DEFAULT_TEMPERATURE


@dataclass(frozen=True, slots=True)
class ListNarrativesInput:
    record_id: str
    page: int = 0
    size: int = 20


@dataclass(frozen=True, slots=True)
class GetNarrativeInput:
    record_id: str
    narrative_id: str


@dataclass(frozen=True, slots=True)
class UpdateNarrativeInput:
    record_id: str
    narrative_id: str
    narrative: str


def _resolve_type(raw: str | None) -> tuple[NarrativeType, ResolutionSource]:
    if raw is None:
        return DEFAULT_NARRATIVE_TYPE, ResolutionSource.DEFAULT
    try:
        return NarrativeType(raw), ResolutionSource.REQUEST_BODY
    except ValueError as exc:
        supported = ", ".join(t.value for t in NarrativeType)
        raise UnsupportedNarrativeType(
            f"The requested narrative_type '{raw}' is not supported. "
            f"Choose from: {supported}."
        ) from exc


class GenerateNarrative:
    def __init__(
        self,
        cidoc: CidocGraphPort,
        model: NarrativeModelPort,
        repository: NarrativeRepository,
        model_name: str,
    ) -> None:
        self._cidoc = cidoc
        self._model = model
        self._repository = repository
        self._model_name = model_name

    async def execute(self, data: GenerateNarrativeInput) -> GeneratedNarrative:
        narrative_type, source = _resolve_type(data.narrative_type)
        graph = await self._cidoc.prepare(data.record_id)
        narrative = await self._model.generate(
            system_prompt=build_system_prompt(narrative_type),
            user_prompt=build_user_prompt(graph, data.target_language),
            temperature=data.creativity_temperature,
        )
        text = narrative.strip()
        if not text:
            # An empty generation is a model failure, not a stored narrative.
            raise ModelUnavailable("The language model returned an empty narrative")
        record = GeneratedNarrative.create(
            record_id=data.record_id,
            narrative=text,
            resolved_narrative_type=narrative_type,
            resolution_source=source,
            target_language=data.target_language,
            creativity_temperature=data.creativity_temperature,
            llm_model=self._model_name,
        )
        await self._repository.add(record)
        return record


class ListNarratives:
    """Return a page of stored narratives for one in-situ visit record."""

    def __init__(self, repository: NarrativeRepository) -> None:
        self._repository = repository

    async def execute(
        self, data: ListNarrativesInput
    ) -> tuple[list[GeneratedNarrative], int]:
        return await self._repository.list_by_record(
            data.record_id, data.page, data.size
        )


class GetNarrative:
    """Return one stored narrative by id, or raise ``NarrativeNotFound``."""

    def __init__(self, repository: NarrativeRepository) -> None:
        self._repository = repository

    async def execute(self, data: GetNarrativeInput) -> GeneratedNarrative:
        record = await self._repository.get_by_id(NarrativeId(data.narrative_id))
        if record is None or record.record_id != data.record_id:
            raise NarrativeNotFound(
                f"No narrative found with id {data.narrative_id} "
                f"for record {data.record_id}"
            )
        return record


class UpdateNarrative:
    """Edit the text of a stored narrative, or raise ``NarrativeNotFound``."""

    def __init__(self, repository: NarrativeRepository) -> None:
        self._repository = repository

    async def execute(self, data: UpdateNarrativeInput) -> GeneratedNarrative:
        record = await self._repository.get_by_id(NarrativeId(data.narrative_id))
        if record is None or record.record_id != data.record_id:
            raise NarrativeNotFound(
                f"No narrative found with id {data.narrative_id} "
                f"for record {data.record_id}"
            )
        record.edit_narrative(data.narrative)
        await self._repository.save(record)
        return record
