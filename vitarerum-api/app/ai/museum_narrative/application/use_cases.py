"""KG-RAG narrative application service.

Orchestrates the pipeline: resolve the rendering style → validate the CIDOC-CRM
projection and prepare canonical facts (via the ACL) → select the persona prompt
→ run the local LLM. ``execute`` takes an ``Input`` dataclass, per the repo-wide
convention.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from app.ai.museum_narrative.application.prompts import (
    build_user_prompt,
)
from app.ai.museum_narrative.domain.facts import CanonicalVisitFacts
from app.ai.museum_narrative.domain.models import (
    DEFAULT_NARRATIVE_TYPE,
    GeneratedNarrative,
    GeneratedNarrativeRevision,
    NarrativeFactSnapshot,
    NarrativeId,
    NarrativeType,
    ResolutionSource,
)
from app.ai.museum_narrative.domain.ports import (
    InvalidPreviewInput,
    ModelUnavailable,
    NarrativeFactsPort,
    NarrativeModelPort,
    NarrativeNotFound,
    NarrativePromptPort,
    NarrativeRepository,
    UnsupportedNarrativeType,
)
from app.ai.museum_narrative.domain.validation import (
    NarrativeFinding,
    validate_generated_narrative,
)
from app.shared.kernel import PermissionId

_DEFAULT_TEMPERATURE = 0.3
_DEFAULT_LANGUAGE = "pt"
_FACTS_BUILDER_VERSION = "canonical-visit-facts-v1"


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
class ListNarrativeRevisionsInput:
    record_id: str
    narrative_id: str
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
    edited_by: str


@dataclass(frozen=True, slots=True)
class PreviewNarrativeInput:
    record_id: str
    prompt_version_id: str | None = None
    content: str | None = None
    narrative_type: str | None = None
    target_language: str = _DEFAULT_LANGUAGE
    creativity_temperature: float | None = None


@dataclass(frozen=True, slots=True)
class PreviewNarrativeResult:
    record_id: str
    narrative: str
    generated_at: datetime
    resolved_narrative_type: NarrativeType
    resolution_source: ResolutionSource
    target_language: str
    creativity_temperature: float
    llm_model: str
    prompt_version_id: str | None
    prompt_version: str | None
    prompt_status: str | None
    prompt_source: Literal["version", "adhoc"]
    model_response_hash: str
    validation_conforms: bool
    validation_findings: list[NarrativeFinding]


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


def _facts_payload(facts: CanonicalVisitFacts) -> str:
    return json.dumps(asdict(facts), ensure_ascii=False, default=str, sort_keys=True)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GenerateNarrative:
    def __init__(
        self,
        facts: NarrativeFactsPort,
        prompts: NarrativePromptPort,
        model: NarrativeModelPort,
        repository: NarrativeRepository,
        model_name: str,
    ) -> None:
        self._facts = facts
        self._prompts = prompts
        self._model = model
        self._repository = repository
        self._model_name = model_name

    async def execute(self, data: GenerateNarrativeInput) -> GeneratedNarrative:
        narrative_type, source = _resolve_type(data.narrative_type)
        prompt = await self._prompts.get_published(narrative_type)
        prepared = await self._facts.prepare(data.record_id)
        facts = prepared.facts
        payload_json = _facts_payload(facts)
        fact_snapshot = NarrativeFactSnapshot.create(
            record_id=data.record_id,
            payload_json=payload_json,
            payload_hash=_sha256(payload_json),
            builder_version=_FACTS_BUILDER_VERSION,
            prompt_version=prompt.version_label,
            cidoc_document_json=prepared.cidoc_document_json,
            cidoc_validation_report=prepared.cidoc_validation_report,
            cidoc_conforms=prepared.cidoc_conforms,
        )
        await self._repository.add_facts_snapshot(fact_snapshot)
        narrative = await self._model.generate(
            system_prompt=prompt.content,
            user_prompt=build_user_prompt(facts, data.target_language),
            temperature=data.creativity_temperature,
        )
        text = narrative.strip()
        if not text:
            # An empty generation is a model failure, not a stored narrative.
            raise ModelUnavailable("The language model returned an empty narrative")
        validation = validate_generated_narrative(text, facts)
        record = GeneratedNarrative.create(
            record_id=data.record_id,
            narrative=text,
            resolved_narrative_type=narrative_type,
            resolution_source=source,
            target_language=data.target_language,
            creativity_temperature=data.creativity_temperature,
            llm_model=self._model_name,
            facts_snapshot_id=fact_snapshot.id,
            prompt_version_id=prompt.version_id,
            prompt_version=prompt.version_label,
            model_response_hash=_sha256(text),
            facts_snapshot=fact_snapshot,
            validation_conforms=validation.conforms,
            validation_findings=validation.findings,
        )
        await self._repository.add(record)
        return record


class PreviewNarrative:
    def __init__(
        self,
        facts: NarrativeFactsPort,
        prompts: NarrativePromptPort,
        model: NarrativeModelPort,
        model_name: str,
    ) -> None:
        self._facts = facts
        self._prompts = prompts
        self._model = model
        self._model_name = model_name

    async def execute(self, data: PreviewNarrativeInput) -> PreviewNarrativeResult:
        prompt_version_id = (
            data.prompt_version_id.strip()
            if data.prompt_version_id is not None
            else None
        )
        content = data.content.strip() if data.content is not None else None
        has_version = prompt_version_id is not None and bool(prompt_version_id)
        has_content = content is not None and bool(content)
        if has_version == has_content:
            raise InvalidPreviewInput(
                "Provide exactly one of prompt_version_id or content"
            )
        if data.prompt_version_id is not None and not prompt_version_id:
            raise InvalidPreviewInput("prompt_version_id must not be blank")
        if data.content is not None and not content:
            raise InvalidPreviewInput("content must not be blank")
        if has_content and data.narrative_type is None:
            raise InvalidPreviewInput(
                "narrative_type is required when content is provided"
            )

        narrative_type, source = _resolve_type(data.narrative_type)
        prompt = None
        system_prompt = content
        prompt_source: Literal["version", "adhoc"] = "adhoc"
        if prompt_version_id is not None:
            prompt = await self._prompts.get_version(prompt_version_id, narrative_type)
            system_prompt = prompt.content
            prompt_source = "version"

        prepared = await self._facts.prepare(data.record_id)
        temperature = data.creativity_temperature
        if temperature is None:
            temperature = _DEFAULT_TEMPERATURE
        narrative = await self._model.generate(
            system_prompt=system_prompt or "",
            user_prompt=build_user_prompt(prepared.facts, data.target_language),
            temperature=temperature,
        )
        text = narrative.strip()
        if not text:
            raise ModelUnavailable("The language model returned an empty narrative")
        validation = validate_generated_narrative(text, prepared.facts)
        return PreviewNarrativeResult(
            record_id=data.record_id,
            narrative=text,
            generated_at=datetime.now(UTC),
            resolved_narrative_type=narrative_type,
            resolution_source=source,
            target_language=data.target_language,
            creativity_temperature=temperature,
            llm_model=self._model_name,
            prompt_version_id=prompt.version_id if prompt is not None else None,
            prompt_version=prompt.version_label if prompt is not None else None,
            prompt_status=prompt.status if prompt is not None else None,
            prompt_source=prompt_source,
            model_response_hash=_sha256(text),
            validation_conforms=validation.conforms,
            validation_findings=list(validation.findings),
        )


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


class ListNarrativeRevisions:
    """Return editorial revisions for one narrative in chronological order."""

    def __init__(self, repository: NarrativeRepository) -> None:
        self._repository = repository

    async def execute(
        self, data: ListNarrativeRevisionsInput
    ) -> tuple[list[GeneratedNarrativeRevision], int]:
        result = await self._repository.list_revisions(
            data.record_id, NarrativeId(data.narrative_id), data.page, data.size
        )
        if result is None:
            raise NarrativeNotFound(
                f"No narrative found with id {data.narrative_id} "
                f"for record {data.record_id}"
            )
        return result


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
        revision = record.edit_narrative(
            data.narrative, edited_by=PermissionId(data.edited_by)
        )
        await self._repository.add_revision(revision)
        await self._repository.save(record)
        return record
