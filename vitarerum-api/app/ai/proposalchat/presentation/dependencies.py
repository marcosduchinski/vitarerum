"""Composition root for the ProposalChat inbound adapter.

Wires the User Request ACL (over the published OHS) and the LangGraph/Ollama
model adapter to the application services. Route handlers depend only on these
FastAPI dependency factories.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.proposalchat.application.use_cases import (
    GetTriageContext,
    SuggestIntendedUseService,
)
from app.ai.proposalchat.domain.ports import (
    IntendedUseSuggestionPort,
    ProposalContextPort,
)
from app.ai.proposalchat.infrastructure.context_acl import UserRequestContextAdapter
from app.ai.proposalchat.infrastructure.model_ollama import (
    LangGraphIntendedUseAdapter,
)
from app.config import settings
from app.database import get_async_session
from app.use_of_collections.public import get_proposal_context_reader

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_context_port(session: DBSession) -> ProposalContextPort:
    return UserRequestContextAdapter(get_proposal_context_reader(session))


def get_model_port() -> IntendedUseSuggestionPort:
    return LangGraphIntendedUseAdapter(
        base_url=settings.ollama_base_url,
        model=settings.proposalchat_model,
        timeout_seconds=settings.proposalchat_timeout_seconds,
        api_key=settings.ollama_api_key,
    )


ContextPort = Annotated[ProposalContextPort, Depends(get_context_port)]
ModelPort = Annotated[IntendedUseSuggestionPort, Depends(get_model_port)]


def get_triage_context(context: ContextPort) -> GetTriageContext:
    return GetTriageContext(context)


def get_suggest_service(
    context: ContextPort, model: ModelPort
) -> SuggestIntendedUseService:
    return SuggestIntendedUseService(context, model)


TriageContextUseCase = Annotated[GetTriageContext, Depends(get_triage_context)]
SuggestUseCase = Annotated[SuggestIntendedUseService, Depends(get_suggest_service)]
