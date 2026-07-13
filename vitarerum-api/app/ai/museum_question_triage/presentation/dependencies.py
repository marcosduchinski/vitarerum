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

from app.ai.museum_question_triage.application.embedding_classifier import (
    EmbeddingThresholds,
    UseCategoryEmbeddingClassifier,
)
from app.ai.museum_question_triage.application.use_cases import (
    ClassifyPendingCascadeUseCategory,
    ClassifyPendingEmbeddingUseCategory,
    ClassifyPendingUseCategory,
    CreatePendingCascadeUseCategoryClassification,
    CreatePendingEmbeddingUseCategoryClassification,
    CreatePendingUseCategoryClassification,
    ExportUseCategoryCalibrationCsv,
    GetLatestTriage,
    OverrideTriageVerdict,
    SyncTriageSearchTerms,
    SyncUseCategories,
    TriageMuseumQuestion,
)
from app.ai.museum_question_triage.domain.ports import (
    EmbeddingClassifierPort,
    MessageClassificationRepository,
    MuseumQuestionPort,
    ObjectSearchPort,
    TriageModelPort,
    TriageRepository,
    UseCategoryTrainingExampleRepository,
)
from app.ai.museum_question_triage.infrastructure.embedding_ollama import (
    OllamaEmbeddingAdapter,
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
    SqlAlchemyUseCategoryTrainingExampleRepository,
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


def get_embedding_port() -> EmbeddingClassifierPort:
    return OllamaEmbeddingAdapter(
        base_url=settings.ollama_base_url,
        model=settings.use_category_embedding_model,
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


def get_training_example_repository(
    session: DBSession,
) -> UseCategoryTrainingExampleRepository:
    return SqlAlchemyUseCategoryTrainingExampleRepository(session)


MuseumQuestionAclPort = Annotated[MuseumQuestionPort, Depends(get_museum_question_port)]
ModelPort = Annotated[TriageModelPort, Depends(get_triage_model_port)]
EmbeddingPort = Annotated[EmbeddingClassifierPort, Depends(get_embedding_port)]
SearchPort = Annotated[ObjectSearchPort, Depends(get_object_search_port)]
Repository = Annotated[TriageRepository, Depends(get_triage_repository)]
ClassificationRepository = Annotated[
    MessageClassificationRepository, Depends(get_classification_repository)
]
TrainingExampleRepository = Annotated[
    UseCategoryTrainingExampleRepository, Depends(get_training_example_repository)
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


def get_create_pending_embedding_use_category_use_case(
    repository: ClassificationRepository,
) -> CreatePendingEmbeddingUseCategoryClassification:
    return CreatePendingEmbeddingUseCategoryClassification(
        repository,
        settings.use_category_embedding_model,
        settings.use_category_embedding_profile_version,
    )


def get_create_pending_cascade_use_category_use_case(
    repository: ClassificationRepository,
) -> CreatePendingCascadeUseCategoryClassification:
    return CreatePendingCascadeUseCategoryClassification(
        repository,
        settings.use_category_embedding_model,
        settings.use_category_cascade_classifier_version,
    )


def get_classify_pending_use_category_use_case(
    museum_question: MuseumQuestionAclPort,
    model: ModelPort,
    triage_repository: Repository,
    classification_repository: ClassificationRepository,
) -> ClassifyPendingUseCategory:
    return ClassifyPendingUseCategory(
        museum_question, model, triage_repository, classification_repository
    )


def get_embedding_classifier(
    embedding: EmbeddingPort,
) -> UseCategoryEmbeddingClassifier:
    return UseCategoryEmbeddingClassifier(
        embedding,
        EmbeddingThresholds(
            low=settings.use_category_embedding_low_threshold,
            high=settings.use_category_embedding_high_threshold,
            profile_version=settings.use_category_embedding_profile_version,
            long_message_words=settings.use_category_embedding_long_message_words,
        ),
    )


EmbeddingClassifier = Annotated[
    UseCategoryEmbeddingClassifier, Depends(get_embedding_classifier)
]


def get_classify_pending_embedding_use_category_use_case(
    museum_question: MuseumQuestionAclPort,
    classifier: EmbeddingClassifier,
    triage_repository: Repository,
    classification_repository: ClassificationRepository,
) -> ClassifyPendingEmbeddingUseCategory:
    return ClassifyPendingEmbeddingUseCategory(
        museum_question, classifier, triage_repository, classification_repository
    )


def get_classify_pending_cascade_use_category_use_case(
    museum_question: MuseumQuestionAclPort,
    classifier: EmbeddingClassifier,
    model: ModelPort,
    triage_repository: Repository,
    classification_repository: ClassificationRepository,
) -> ClassifyPendingCascadeUseCategory:
    return ClassifyPendingCascadeUseCategory(
        museum_question,
        classifier,
        model,
        triage_repository,
        classification_repository,
        high_threshold=settings.use_category_embedding_high_threshold,
        margin_delta=settings.use_category_cascade_margin_delta,
    )


def get_export_use_category_calibration_csv_use_case(
    museum_question: MuseumQuestionAclPort,
    triage_repository: Repository,
    classification_repository: ClassificationRepository,
) -> ExportUseCategoryCalibrationCsv:
    return ExportUseCategoryCalibrationCsv(
        museum_question, triage_repository, classification_repository
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


def get_sync_use_categories_use_case(
    museum_question: MuseumQuestionAclPort,
    triage_repository: Repository,
    classification_repository: ClassificationRepository,
    training_example_repository: TrainingExampleRepository,
) -> SyncUseCategories:
    return SyncUseCategories(
        museum_question,
        triage_repository,
        classification_repository,
        training_example_repository,
    )


TriageUseCase = Annotated[TriageMuseumQuestion, Depends(get_triage_use_case)]
GetLatestTriageUseCase = Annotated[GetLatestTriage, Depends(get_latest_triage_use_case)]
CreatePendingUseCategoryUseCase = Annotated[
    CreatePendingUseCategoryClassification,
    Depends(get_create_pending_use_category_use_case),
]
CreatePendingEmbeddingUseCategoryUseCase = Annotated[
    CreatePendingEmbeddingUseCategoryClassification,
    Depends(get_create_pending_embedding_use_category_use_case),
]
CreatePendingCascadeUseCategoryUseCase = Annotated[
    CreatePendingCascadeUseCategoryClassification,
    Depends(get_create_pending_cascade_use_category_use_case),
]
ClassifyPendingUseCategoryUseCase = Annotated[
    ClassifyPendingUseCategory,
    Depends(get_classify_pending_use_category_use_case),
]
ClassifyPendingEmbeddingUseCategoryUseCase = Annotated[
    ClassifyPendingEmbeddingUseCategory,
    Depends(get_classify_pending_embedding_use_category_use_case),
]
ClassifyPendingCascadeUseCategoryUseCase = Annotated[
    ClassifyPendingCascadeUseCategory,
    Depends(get_classify_pending_cascade_use_category_use_case),
]
ExportUseCategoryCalibrationCsvUseCase = Annotated[
    ExportUseCategoryCalibrationCsv,
    Depends(get_export_use_category_calibration_csv_use_case),
]
OverrideVerdictUseCase = Annotated[
    OverrideTriageVerdict, Depends(get_override_verdict_use_case)
]
SyncSearchTermsUseCase = Annotated[
    SyncTriageSearchTerms, Depends(get_sync_search_terms_use_case)
]
SyncUseCategoriesUseCase = Annotated[
    SyncUseCategories, Depends(get_sync_use_categories_use_case)
]
