"""Composition root for the museum-narrative inbound adapter.

Wires the CIDOC facts ACL (over cidoc_crm.public) and the Ollama model adapter to
the ``GenerateNarrative`` use case. Route handlers depend only on
``NarrativeUseCase``.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_narrative.application.use_cases import (
    GenerateNarrative,
    GetNarrative,
    ListNarrativeRevisions,
    ListNarratives,
    UpdateNarrative,
)
from app.ai.museum_narrative.domain.ports import (
    NarrativeFactsPort,
    NarrativeModelPort,
    NarrativeRepository,
)
from app.ai.museum_narrative.infrastructure.cidoc_acl import NarrativeFactsAdapter
from app.ai.museum_narrative.infrastructure.model_ollama import OllamaNarrativeAdapter
from app.ai.museum_narrative.infrastructure.repositories import (
    SqlAlchemyNarrativeRepository,
)
from app.config import settings
from app.database import get_async_session

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_facts_port(session: DBSession) -> NarrativeFactsPort:
    return NarrativeFactsAdapter(session)


def get_model_port() -> NarrativeModelPort:
    return OllamaNarrativeAdapter(
        base_url=settings.ollama_base_url,
        model=settings.narrative_model,
        timeout_seconds=settings.narrative_timeout_seconds,
        api_key=settings.ollama_api_key,
    )


def get_narrative_repository(session: DBSession) -> NarrativeRepository:
    return SqlAlchemyNarrativeRepository(session)


FactsPort = Annotated[NarrativeFactsPort, Depends(get_facts_port)]
ModelPort = Annotated[NarrativeModelPort, Depends(get_model_port)]
Repository = Annotated[NarrativeRepository, Depends(get_narrative_repository)]


def get_narrative_use_case(
    facts: FactsPort, model: ModelPort, repository: Repository
) -> GenerateNarrative:
    return GenerateNarrative(facts, model, repository, settings.narrative_model)


def get_list_use_case(repository: Repository) -> ListNarratives:
    return ListNarratives(repository)


def get_revision_list_use_case(repository: Repository) -> ListNarrativeRevisions:
    return ListNarrativeRevisions(repository)


def get_narrative_by_id_use_case(repository: Repository) -> GetNarrative:
    return GetNarrative(repository)


def get_update_use_case(repository: Repository) -> UpdateNarrative:
    return UpdateNarrative(repository)


NarrativeUseCase = Annotated[GenerateNarrative, Depends(get_narrative_use_case)]
ListUseCase = Annotated[ListNarratives, Depends(get_list_use_case)]
RevisionListUseCase = Annotated[
    ListNarrativeRevisions, Depends(get_revision_list_use_case)
]
GetUseCase = Annotated[GetNarrative, Depends(get_narrative_by_id_use_case)]
UpdateUseCase = Annotated[UpdateNarrative, Depends(get_update_use_case)]
