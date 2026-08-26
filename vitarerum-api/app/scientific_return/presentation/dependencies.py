from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory, get_async_session
from app.identity.public import get_permission_reader
from app.notifications.public import (
    NotificationDispatcher,
    get_notification_dispatcher,
)
from app.scientific_return.application.agent_tools import build_default_registry
from app.scientific_return.application.full_agentic import (
    ExecuteFullAgenticScientificReturn,
    FullAgenticConfiguration,
    StartFullAgenticScientificReturn,
)
from app.scientific_return.application.full_agentic_ports import (
    AgenticInvestigationDispatcher,
    FullAgenticReasoner,
    FullAgenticRepository,
)
from app.scientific_return.application.investigation_reasoner import (
    PromptedInvestigationReasoner,
)
from app.scientific_return.application.ports import (
    AgentPromptProvider,
    AgentToolRegistry,
    BibliographicSource,
    ConfirmedPublicationWriter,
    InvestigationReasoner,
    ProjectSnapshotProvider,
    ScientificReturnInvestigationRepository,
    ScientificReturnReasoner,
    ScientificReturnRepository,
)
from app.scientific_return.application.run_investigation import (
    AgentConfiguration,
    RunScientificReturnInvestigation,
)
from app.scientific_return.domain.enums import (
    AgentRecommendedAction,
    InvestigationMode,
)
from app.scientific_return.domain.full_agentic_models import AgenticBudget
from app.scientific_return.domain.investigation_contracts import ExecutionBudget
from app.scientific_return.infrastructure.acls import (
    UseOfCollectionsProjectSnapshotProvider,
    UseOfCollectionsPublicationWriter,
)
from app.scientific_return.infrastructure.crossref import CrossrefBibliographicSource
from app.scientific_return.infrastructure.europe_pmc import EuropePmcBibliographicSource
from app.scientific_return.infrastructure.full_agentic_dispatcher import (
    CloudTasksDispatcher,
    DatabaseQueueDispatcher,
)
from app.scientific_return.infrastructure.full_agentic_reasoner import (
    PromptedFullAgenticReasoner,
)
from app.scientific_return.infrastructure.full_agentic_repository import (
    SqlAlchemyFullAgenticRepository,
)
from app.scientific_return.infrastructure.investigation_lock import (
    PostgresInvestigationLock,
)
from app.scientific_return.infrastructure.openalex import OpenAlexBibliographicSource
from app.scientific_return.infrastructure.prompt_acl import AiPromptRegistryAdapter
from app.scientific_return.infrastructure.reasoner_ollama import (
    OllamaScientificReturnReasoner,
)
from app.scientific_return.infrastructure.repositories import (
    SqlAlchemyInvestigationRepository,
    SqlAlchemyScientificReturnRepository,
)
from app.scientific_return.infrastructure.source_rate_limiter import (
    PostgresBibliographicSourceRateLimiter,
    RateLimitedBibliographicSource,
)
from app.scientific_return.infrastructure.unit_of_work import (
    SqlAlchemyInvestigationUnitOfWork,
    SystemClock,
)
from app.shared.field_encryption import FieldEncryptor
from app.use_of_collections.public import (
    get_published_publication_entry_writer,
    get_published_use_of_collections_reader,
)

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def _field_encryptor() -> FieldEncryptor:
    return FieldEncryptor.from_base64(settings.db_field_encryption_key)


def get_repository(session: DBSession) -> ScientificReturnRepository:
    return SqlAlchemyScientificReturnRepository(session, _field_encryptor())


def get_full_agentic_repository(session: DBSession) -> FullAgenticRepository:
    return SqlAlchemyFullAgenticRepository(session, _field_encryptor())


def get_full_agentic_configuration() -> FullAgenticConfiguration:
    operational_sources = ["CROSSREF"]
    evidence_sources: list[str] = []
    if settings.openalex_api_key:
        operational_sources.append("OPENALEX")
    if settings.europe_pmc_enabled:
        operational_sources.append("EUROPE_PMC")
        evidence_sources.append("EUROPE_PMC")
    return FullAgenticConfiguration(
        enabled=settings.scientific_return_full_agentic_enabled,
        allowed_sources=tuple(
            value.strip().upper()
            for value in settings.scientific_return_full_agentic_sources.split(",")
            if value.strip()
        ),
        budget=AgenticBudget(
            max_iterations=settings.scientific_return_full_agentic_max_iterations,
            max_queries=settings.scientific_return_full_agentic_max_queries,
            max_results=settings.scientific_return_full_agentic_max_results,
            max_candidates=settings.scientific_return_full_agentic_max_candidates,
            max_llm_calls=settings.scientific_return_full_agentic_max_llm_calls,
        ),
        circuit_min_decisions=(
            settings.scientific_return_full_agentic_circuit_min_decisions
        ),
        circuit_min_precision=(
            settings.scientific_return_full_agentic_circuit_min_precision
        ),
        operational_sources=tuple(operational_sources),
        evidence_sources=tuple(evidence_sources),
    )


def get_full_agentic_reasoner(session: DBSession) -> FullAgenticReasoner:
    return PromptedFullAgenticReasoner(
        get_agent_reasoner(), get_agent_prompt_provider(session)
    )


def get_full_agentic_dispatcher() -> AgenticInvestigationDispatcher:
    if settings.scientific_return_full_agentic_dispatcher.upper() == "CLOUD_TASKS":
        return CloudTasksDispatcher(
            queue_url=settings.scientific_return_cloud_tasks_queue_url,
            worker_url=settings.scientific_return_cloud_tasks_worker_url,
            service_account=settings.scientific_return_cloud_tasks_service_account,
            worker_token=settings.scientific_return_full_agentic_worker_token,
        )
    return DatabaseQueueDispatcher()


def get_full_agentic_starter(
    session: DBSession,
) -> StartFullAgenticScientificReturn:
    return StartFullAgenticScientificReturn(
        get_repository(session),
        get_full_agentic_repository(session),
        get_full_agentic_dispatcher(),
        SqlAlchemyInvestigationUnitOfWork(session),
        SystemClock(),
        get_full_agentic_configuration(),
    )


def get_full_agentic_executor(
    session: DBSession,
) -> ExecuteFullAgenticScientificReturn:
    enabled_sources = {
        value.upper() for value in get_full_agentic_configuration().allowed_sources
    }
    sources = tuple(
        source
        for source in get_bibliographic_sources()
        if source.name.upper() in enabled_sources
    )
    return ExecuteFullAgenticScientificReturn(
        get_repository(session),
        get_full_agentic_repository(session),
        get_full_agentic_reasoner(session),
        sources,
        SqlAlchemyInvestigationUnitOfWork(session),
        SystemClock(),
        get_full_agentic_configuration(),
    )


def get_project_provider(session: DBSession) -> ProjectSnapshotProvider:
    return UseOfCollectionsProjectSnapshotProvider(
        get_published_use_of_collections_reader(session),
        get_permission_reader(session),
    )


def get_publication_writer(session: DBSession) -> ConfirmedPublicationWriter:
    return UseOfCollectionsPublicationWriter(
        get_published_publication_entry_writer(session)
    )


def get_notifications(session: DBSession) -> NotificationDispatcher:
    return get_notification_dispatcher(session)


def get_crossref_source() -> BibliographicSource:
    return CrossrefBibliographicSource(
        base_url=settings.crossref_base_url,
        timeout_seconds=settings.crossref_timeout_seconds,
        mailto=settings.crossref_mailto or None,
        max_retries=settings.crossref_max_retries,
        retry_base_seconds=settings.crossref_retry_base_seconds,
        min_interval_seconds=settings.crossref_min_interval_seconds,
    )


def get_openalex_source() -> BibliographicSource:
    return OpenAlexBibliographicSource(
        base_url=settings.openalex_base_url,
        api_key=settings.openalex_api_key,
        timeout_seconds=settings.openalex_timeout_seconds,
        max_retries=settings.openalex_max_retries,
        retry_base_seconds=settings.openalex_retry_base_seconds,
    )


def get_europe_pmc_source() -> BibliographicSource:
    return EuropePmcBibliographicSource(
        base_url=settings.europe_pmc_base_url,
        timeout_seconds=settings.europe_pmc_timeout_seconds,
        max_retries=settings.europe_pmc_max_retries,
        retry_base_seconds=settings.europe_pmc_retry_base_seconds,
        full_text_result_limit=settings.europe_pmc_full_text_result_limit,
        email=settings.europe_pmc_email or None,
    )


def get_bibliographic_sources() -> tuple[BibliographicSource, ...]:
    limiter = PostgresBibliographicSourceRateLimiter(async_session_factory)
    sources: list[BibliographicSource] = [
        RateLimitedBibliographicSource(
            get_crossref_source(), limiter, settings.crossref_min_interval_seconds
        )
    ]
    if settings.openalex_api_key:
        sources.append(
            RateLimitedBibliographicSource(get_openalex_source(), limiter, 0.1)
        )
    if settings.europe_pmc_enabled:
        sources.append(
            RateLimitedBibliographicSource(get_europe_pmc_source(), limiter, 0.1)
        )
    return tuple(sources)


def get_result_limit() -> int:
    return settings.scientific_return_result_limit


def get_max_queries() -> int:
    return settings.scientific_return_max_queries_per_run


def get_agent_prompt_provider(session: DBSession) -> AgentPromptProvider:
    return AiPromptRegistryAdapter(session)


def get_agent_reasoner() -> ScientificReturnReasoner:
    return OllamaScientificReturnReasoner(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
        model=settings.scientific_return_llm_model,
        timeout_seconds=settings.scientific_return_llm_timeout_seconds,
    )


def get_agent_enabled() -> bool:
    return settings.scientific_return_llm_enabled


def get_investigation_repository(
    session: DBSession,
) -> ScientificReturnInvestigationRepository:
    return SqlAlchemyInvestigationRepository(session, _field_encryptor())


def get_agent_tool_registry() -> AgentToolRegistry:
    return build_default_registry(get_bibliographic_sources())


def get_investigation_reasoner(session: DBSession) -> InvestigationReasoner:
    return PromptedInvestigationReasoner(
        get_agent_reasoner(), get_agent_prompt_provider(session)
    )


Repository = Annotated[ScientificReturnRepository, Depends(get_repository)]
ProjectProvider = Annotated[ProjectSnapshotProvider, Depends(get_project_provider)]
PublicationWriter = Annotated[
    ConfirmedPublicationWriter, Depends(get_publication_writer)
]
BibliographicSources = Annotated[
    tuple[BibliographicSource, ...], Depends(get_bibliographic_sources)
]
ResultLimit = Annotated[int, Depends(get_result_limit)]
MaxQueries = Annotated[int, Depends(get_max_queries)]
Notifications = Annotated[NotificationDispatcher, Depends(get_notifications)]
AgentPrompt = Annotated[AgentPromptProvider, Depends(get_agent_prompt_provider)]
AgentReasoner = Annotated[ScientificReturnReasoner, Depends(get_agent_reasoner)]
AgentEnabled = Annotated[bool, Depends(get_agent_enabled)]
InvestigationReasonerDep = Annotated[
    InvestigationReasoner, Depends(get_investigation_reasoner)
]
AgentTools = Annotated[AgentToolRegistry, Depends(get_agent_tool_registry)]
InvestigationRepository = Annotated[
    ScientificReturnInvestigationRepository, Depends(get_investigation_repository)
]
FullAgenticRepositoryDep = Annotated[
    FullAgenticRepository, Depends(get_full_agentic_repository)
]
FullAgenticConfigDep = Annotated[
    FullAgenticConfiguration, Depends(get_full_agentic_configuration)
]
FullAgenticStarter = Annotated[
    StartFullAgenticScientificReturn, Depends(get_full_agentic_starter)
]
FullAgenticExecutor = Annotated[
    ExecuteFullAgenticScientificReturn, Depends(get_full_agentic_executor)
]
FullAgenticReasonerDep = Annotated[
    FullAgenticReasoner, Depends(get_full_agentic_reasoner)
]


def get_agent_configuration() -> AgentConfiguration:
    """Read the server-side limits. No client or model value ever widens these."""
    actions = frozenset(
        AgentRecommendedAction(item.strip().upper())
        for item in settings.scientific_return_agent_allowed_actions.split(",")
        if item.strip()
    )
    sources = tuple(
        item.strip().upper()
        for item in settings.scientific_return_agent_allowed_sources.split(",")
        if item.strip()
    )
    return AgentConfiguration(
        mode=InvestigationMode(settings.scientific_return_agent_mode.upper()),
        allowed_actions=actions,
        allowed_sources=sources,
        budget=ExecutionBudget(
            max_iterations=settings.scientific_return_agent_max_iterations,
            max_actions=settings.scientific_return_agent_max_actions,
            max_queries=settings.scientific_return_agent_max_queries,
            max_results_per_query=settings.scientific_return_agent_max_results,
            max_new_candidates=settings.scientific_return_agent_max_new_candidates,
        ),
    )


def get_investigation_runner(session: DBSession) -> RunScientificReturnInvestigation:
    return RunScientificReturnInvestigation(
        get_repository(session),
        get_investigation_repository(session),
        get_investigation_reasoner(session),
        get_agent_tool_registry(),
        SqlAlchemyInvestigationUnitOfWork(session),
        SystemClock(),
        get_agent_configuration(),
        PostgresInvestigationLock(session),
    )


InvestigationRunner = Annotated[
    RunScientificReturnInvestigation, Depends(get_investigation_runner)
]
