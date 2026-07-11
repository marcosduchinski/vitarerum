"""Composition root for the museum-question triage inbound adapter.

Wires the Museum Questions ACL, the Ollama model adapter, and the Object
Search ACL to the ``TriageMuseumQuestion``/``GetLatestTriage`` use cases.
Route handlers depend only on the ``TriageUseCase``/``GetLatestTriageUseCase``
aliases. This is the only module where ``Depends`` appears for the object
search wiring — it reuses the Collection Object Index's own
``get_object_index`` provider rather than recreating the adapter.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_question_triage.application.use_cases import (
    ClassifyPendingUseCategory,
    CreatePendingUseCategoryClassification,
    GetLatestTriage,
    OverrideTriageVerdict,
    SyncTriageSearchTerms,
    TriageMuseumQuestion,
)
from app.ai.museum_question_triage.domain.ports import (
    MessageClassificationRepository,
    MuseumQuestionPort,
    ObjectSearchPort,
    TriageModelPort,
    TriageRepository,
)
from app.ai.museum_question_triage.infrastructure.model_ollama import (
    OllamaTriageAdapter,
)
from app.ai.museum_question_triage.infrastructure.museum_questions_acl import (
    MuseumQuestionAdapter,
)
from app.ai.museum_question_triage.infrastructure.object_search_acl import (
    ObjectSearchAdapter,
)
from app.ai.museum_question_triage.infrastructure.repositories import (
    SqlAlchemyMessageClassificationRepository,
    SqlAlchemyTriageRepository,
)
from app.collection_object_index.application.ports import CollectionObjectIndexPort
from app.collection_object_index.presentation.dependencies import get_object_index
from app.config import settings
from app.database import get_async_session

DBSession = Annotated[AsyncSession, Depends(get_async_session)]
ObjectIndex = Annotated[CollectionObjectIndexPort, Depends(get_object_index)]


def get_museum_question_port(session: DBSession) -> MuseumQuestionPort:
    return MuseumQuestionAdapter(session)


def get_triage_model_port() -> TriageModelPort:
    return OllamaTriageAdapter(
        base_url=settings.ollama_base_url,
        model=settings.triage_model,
        timeout_seconds=settings.triage_timeout_seconds,
        api_key=settings.ollama_api_key,
    )


def get_object_search_port(index: ObjectIndex) -> ObjectSearchPort:
    return ObjectSearchAdapter(index)


def get_triage_repository(session: DBSession) -> TriageRepository:
    return SqlAlchemyTriageRepository(session)


def get_classification_repository(
    session: DBSession,
) -> MessageClassificationRepository:
    return SqlAlchemyMessageClassificationRepository(session)


MuseumQuestionAclPort = Annotated[MuseumQuestionPort, Depends(get_museum_question_port)]
ModelPort = Annotated[TriageModelPort, Depends(get_triage_model_port)]
SearchPort = Annotated[ObjectSearchPort, Depends(get_object_search_port)]
Repository = Annotated[TriageRepository, Depends(get_triage_repository)]
ClassificationRepository = Annotated[
    MessageClassificationRepository, Depends(get_classification_repository)
]


def get_triage_use_case(
    museum_question: MuseumQuestionAclPort,
    model: ModelPort,
    object_search: SearchPort,
    repository: Repository,
) -> TriageMuseumQuestion:
    return TriageMuseumQuestion(
        museum_question, model, object_search, repository, settings.triage_model
    )


def get_latest_triage_use_case(repository: Repository) -> GetLatestTriage:
    return GetLatestTriage(repository)


def get_create_pending_use_category_use_case(
    repository: ClassificationRepository,
) -> CreatePendingUseCategoryClassification:
    return CreatePendingUseCategoryClassification(repository, settings.triage_model)


def get_classify_pending_use_category_use_case(
    museum_question: MuseumQuestionAclPort,
    model: ModelPort,
    triage_repository: Repository,
    classification_repository: ClassificationRepository,
) -> ClassifyPendingUseCategory:
    return ClassifyPendingUseCategory(
        museum_question, model, triage_repository, classification_repository
    )


def get_override_verdict_use_case(
    museum_question: MuseumQuestionAclPort,
    model: ModelPort,
    repository: Repository,
) -> OverrideTriageVerdict:
    return OverrideTriageVerdict(museum_question, model, repository)


def get_sync_search_terms_use_case(
    object_search: SearchPort,
    repository: Repository,
) -> SyncTriageSearchTerms:
    return SyncTriageSearchTerms(object_search, repository)


TriageUseCase = Annotated[TriageMuseumQuestion, Depends(get_triage_use_case)]
GetLatestTriageUseCase = Annotated[GetLatestTriage, Depends(get_latest_triage_use_case)]
CreatePendingUseCategoryUseCase = Annotated[
    CreatePendingUseCategoryClassification,
    Depends(get_create_pending_use_category_use_case),
]
ClassifyPendingUseCategoryUseCase = Annotated[
    ClassifyPendingUseCategory,
    Depends(get_classify_pending_use_category_use_case),
]
OverrideVerdictUseCase = Annotated[
    OverrideTriageVerdict, Depends(get_override_verdict_use_case)
]
SyncSearchTermsUseCase = Annotated[
    SyncTriageSearchTerms, Depends(get_sync_search_terms_use_case)
]
