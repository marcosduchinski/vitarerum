"""Driven ports (hexagonal) and error vocabulary for the museum-narrative context.

``CidocGraphPort`` is implemented by an anti-corruption adapter over
``app.cidoc_crm.public``; ``NarrativeModelPort`` by the local Ollama adapter. The
application depends only on these Protocols.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.ai.museum_narrative.domain.models import (
        GeneratedNarrative,
        NarrativeId,
    )


class RecordNotFound(Exception):
    """No in-situ visit record matches the requested id."""


class NarrativeNotFound(Exception):
    """No stored narrative matches the requested id."""


class SemanticValidationFailed(Exception):
    """The reasoner/SHACL rejected the generated CIDOC-CRM graph."""


class UnsupportedNarrativeType(Exception):
    """The requested narrative_type is not one of the supported styles."""


class ModelUnavailable(Exception):
    """The narrative model could not be reached."""


class ModelTimeout(Exception):
    """The narrative model did not respond in time."""


class CidocGraphPort(Protocol):
    """Build, expand and validate the CIDOC-CRM graph for a record. Raises
    :class:`RecordNotFound` / :class:`SemanticValidationFailed`."""

    async def prepare(self, record_id: str) -> dict[str, Any]: ...


class NarrativeModelPort(Protocol):
    """Run the local LLM. Raises :class:`ModelUnavailable` / :class:`ModelTimeout`."""

    async def generate(
        self, *, system_prompt: str, user_prompt: str, temperature: float
    ) -> str: ...


class NarrativeRepository(Protocol):
    """Persists and reads back generated narratives (append-only history)."""

    async def add(self, narrative: GeneratedNarrative) -> None: ...

    async def save(self, narrative: GeneratedNarrative) -> None: ...

    async def get_by_id(
        self, narrative_id: NarrativeId
    ) -> GeneratedNarrative | None: ...

    async def list_by_record(
        self, record_id: str, page: int, size: int
    ) -> tuple[list[GeneratedNarrative], int]: ...
