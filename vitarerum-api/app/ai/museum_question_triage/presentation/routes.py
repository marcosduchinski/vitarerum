"""Museum-question triage endpoints (the driving adapter).

Staff-only. Co-located as a sub-resource of the existing internal
museum-questions prefix, even though the router is physically defined under
``app/ai/`` — mirrors how ``museum_narrative``'s router lives under ``app/ai/``
but is addressed by its own resource path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_question_triage.application.embedding_classifier import (
    EmbeddingThresholds,
    UseCategoryEmbeddingClassifier,
    build_use_category_embedding_classifier,
)
from app.ai.museum_question_triage.application.use_cases import (
    ClassifyPendingCascadeUseCategory,
    ClassifyPendingCascadeUseCategoryInput,
    ClassifyPendingEmbeddingUseCategory,
    ClassifyPendingEmbeddingUseCategoryInput,
    ClassifyPendingUseCategory,
    ClassifyPendingUseCategoryInput,
    CreatePendingCascadeUseCategoryClassificationInput,
    CreatePendingEmbeddingUseCategoryClassificationInput,
    CreatePendingUseCategoryClassificationInput,
    ExportUseCategoryCalibrationInput,
    GenerateEmbeddingPrototypeVersionInput,
    GetLatestTriageInput,
    NotEnoughTrainingExamples,
    OverrideTriageVerdictInput,
    SyncTriageSearchTermsInput,
    SyncUseCategoriesInput,
    TriageMuseumQuestionInput,
)
from app.ai.museum_question_triage.domain.models import (
    ClassificationId,
    ClassificationStatus,
    ClassifierKind,
    EmbeddingPrototypeAggregation,
    HumanCategoryOutcome,
    InvalidEmbeddingPrototypeVersion,
    InvalidUseCategoryTrainingExample,
    MessageClassification,
    TriageId,
    TriageVerdict,
    UseCategory,
)
from app.ai.museum_question_triage.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
    QuestionNotFound,
    TriageNotFound,
    TriageNotInScope,
    TriageTermValidationError,
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
from app.ai.museum_question_triage.infrastructure.repositories import (
    SqlAlchemyEmbeddingPrototypeVersionRepository,
    SqlAlchemyMessageClassificationRepository,
    SqlAlchemyTriageRepository,
)
from app.ai.museum_question_triage.presentation.dependencies import (
    ClassificationRepository,
    CreatePendingCascadeUseCategoryUseCase,
    CreatePendingEmbeddingUseCategoryUseCase,
    CreatePendingUseCategoryUseCase,
    EmbeddingPrototypeRepository,
    ExportUseCategoryCalibrationCsvUseCase,
    GenerateEmbeddingPrototypeVersionUseCase,
    GetLatestTriageUseCase,
    OverrideVerdictUseCase,
    SyncSearchTermsUseCase,
    SyncUseCategoriesUseCase,
    TriageUseCase,
)
from app.ai.museum_question_triage.presentation.mappers import (
    embedding_prototype_version_response,
    triage_response,
    use_category_classification_audit_list_response,
)
from app.ai.museum_question_triage.presentation.schemas import (
    EmbeddingPrototypeVersionResponse,
    GenerateEmbeddingPrototypeVersionRequest,
    OverrideTriageVerdictRequest,
    TriageResponse,
    TriageSearchTermsRequest,
    UseCategoryClassificationAuditListResponse,
    UseCategoryCorrectionRequest,
)
from app.config import settings
from app.database import async_session_factory, get_async_session
from app.identity.public import GroupName
from app.shared.authorization import require_group, require_staff
from app.shared.dependencies import CallerPermission

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

museum_question_triage_router = APIRouter(
    prefix="/museum-questions", tags=["museum-question-triage"]
)


@museum_question_triage_router.get("/triage/classifications/calibration.csv")
async def export_use_category_calibration_csv(
    caller: CallerPermission,
    use_case: ExportUseCategoryCalibrationCsvUseCase,
    limit: int = Query(default=100, ge=1, le=500),
) -> Response:
    require_staff(caller)
    content = await use_case.execute(ExportUseCategoryCalibrationInput(limit=limit))
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="museum-question-use-category-calibration.csv"'
            )
        },
    )


@museum_question_triage_router.get(
    "/triage/embedding-prototypes",
    response_model=list[EmbeddingPrototypeVersionResponse],
)
async def list_embedding_prototype_versions(
    caller: CallerPermission,
    repository: EmbeddingPrototypeRepository,
) -> list[EmbeddingPrototypeVersionResponse]:
    require_group(caller, GroupName.CURATORIAL)
    return [
        embedding_prototype_version_response(version)
        for version in await repository.list()
    ]


@museum_question_triage_router.post(
    "/triage/embedding-prototypes",
    response_model=EmbeddingPrototypeVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_embedding_prototype_version(
    body: GenerateEmbeddingPrototypeVersionRequest,
    caller: CallerPermission,
    use_case: GenerateEmbeddingPrototypeVersionUseCase,
    session: DBSession,
) -> EmbeddingPrototypeVersionResponse:
    require_group(caller, GroupName.CURATORIAL)
    try:
        result = await use_case.execute(
            GenerateEmbeddingPrototypeVersionInput(
                version=body.version,
                embedding_model=settings.use_category_embedding_model,
                aggregation_method=EmbeddingPrototypeAggregation(
                    body.aggregationMethod
                ),
                threshold_profile={
                    "profile_version": settings.use_category_embedding_profile_version,
                    "low": settings.use_category_embedding_low_threshold,
                    "high": settings.use_category_embedding_high_threshold,
                    "long_message_words": (
                        settings.use_category_embedding_long_message_words
                    ),
                },
                promote=body.promote,
            )
        )
    except NotEnoughTrainingExamples as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "NOT_ENOUGH_TRAINING_EXAMPLES", "message": str(exc)},
        ) from exc
    except (InvalidEmbeddingPrototypeVersion, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "INVALID_PROTOTYPE_VERSION", "message": str(exc)},
        ) from exc
    await session.commit()
    return embedding_prototype_version_response(result)


@museum_question_triage_router.patch(
    "/triage/embedding-prototypes/{version}/promotion",
    response_model=EmbeddingPrototypeVersionResponse,
)
async def promote_embedding_prototype_version(
    version: str,
    caller: CallerPermission,
    repository: EmbeddingPrototypeRepository,
    session: DBSession,
) -> EmbeddingPrototypeVersionResponse:
    require_group(caller, GroupName.CURATORIAL)
    existing = await repository.get_by_version(version)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "EMBEDDING_PROTOTYPE_VERSION_NOT_FOUND",
                "message": f"Embedding prototype version {version!r} was not found.",
            },
        )

    await repository.promote(version, datetime.now(UTC))
    promoted = await repository.get_by_version(version)
    await session.commit()
    assert promoted is not None
    return embedding_prototype_version_response(promoted)


def _not_found(question_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "MUSEUM_QUESTION_NOT_FOUND",
            "message": f"Museum question {question_id!r} was not found.",
        },
    )


def _triage_not_found(question_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "TRIAGE_NOT_FOUND",
            "message": f"No triage has been run for question {question_id!r} yet.",
        },
    )


async def _current_llm_use_category_classification(
    classification_repository: ClassificationRepository, triage_id: str
) -> MessageClassification | None:
    return await classification_repository.get_current_by_triage(
        TriageId(triage_id), ClassifierKind.LLM
    )


async def _mark_background_classification_failed(
    classification_id: str, error: Exception
) -> None:
    async with async_session_factory() as session:
        repository = SqlAlchemyMessageClassificationRepository(session)
        classification = await repository.get_by_id(ClassificationId(classification_id))
        if (
            classification is None
            or classification.status is not ClassificationStatus.PENDING
        ):
            return

        failed = MessageClassification(
            id=classification.id,
            triage_id=classification.triage_id,
            classifier_kind=classification.classifier_kind,
            classifier_model=classification.classifier_model,
            classifier_version=classification.classifier_version,
            run_number=classification.run_number,
            superseded_at=classification.superseded_at,
            status=ClassificationStatus.FAILED,
            outcome=None,
            quality=None,
            category_scores=[],
            assigned_categories=[],
            error=str(error),
            metadata=dict(classification.metadata),
            classified_at=datetime.now(UTC),
            created_at=classification.created_at,
        )
        await repository.update(failed)
        await session.commit()


async def _classify_use_categories_background(classification_id: str) -> None:
    async with async_session_factory() as session:
        use_case = ClassifyPendingUseCategory(
            MuseumQuestionAdapter(session),
            OllamaTriageAdapter(
                base_url=settings.ollama_base_url,
                model=settings.triage_model,
                timeout_seconds=settings.triage_timeout_seconds,
                api_key=settings.ollama_api_key,
            ),
            SqlAlchemyTriageRepository(session),
            SqlAlchemyMessageClassificationRepository(session),
        )
        try:
            await use_case.execute(
                ClassifyPendingUseCategoryInput(classification_id=classification_id)
            )
        except Exception as error:
            await session.rollback()
            await _mark_background_classification_failed(classification_id, error)
            raise
        await session.commit()


async def _embedding_classifier(
    session: AsyncSession,
) -> UseCategoryEmbeddingClassifier:
    return await build_use_category_embedding_classifier(
        OllamaEmbeddingAdapter(
            base_url=settings.ollama_base_url,
            model=settings.use_category_embedding_model,
            timeout_seconds=settings.triage_timeout_seconds,
            api_key=settings.ollama_api_key,
        ),
        EmbeddingThresholds(
            low=settings.use_category_embedding_low_threshold,
            high=settings.use_category_embedding_high_threshold,
            profile_version=settings.use_category_embedding_profile_version,
            long_message_words=settings.use_category_embedding_long_message_words,
        ),
        SqlAlchemyEmbeddingPrototypeVersionRepository(session),
        prototype_source=settings.use_category_embedding_prototype_source,
    )


async def _classify_embedding_use_categories_background(classification_id: str) -> None:
    async with async_session_factory() as session:
        use_case = ClassifyPendingEmbeddingUseCategory(
            MuseumQuestionAdapter(session),
            await _embedding_classifier(session),
            SqlAlchemyTriageRepository(session),
            SqlAlchemyMessageClassificationRepository(session),
        )
        try:
            await use_case.execute(
                ClassifyPendingEmbeddingUseCategoryInput(
                    classification_id=classification_id
                )
            )
        except Exception as error:
            await session.rollback()
            await _mark_background_classification_failed(classification_id, error)
            raise
        await session.commit()


async def _classify_cascade_use_categories_background(classification_id: str) -> None:
    async with async_session_factory() as session:
        use_case = ClassifyPendingCascadeUseCategory(
            MuseumQuestionAdapter(session),
            await _embedding_classifier(session),
            OllamaTriageAdapter(
                base_url=settings.ollama_base_url,
                model=settings.triage_model,
                timeout_seconds=settings.triage_timeout_seconds,
                api_key=settings.ollama_api_key,
            ),
            SqlAlchemyTriageRepository(session),
            SqlAlchemyMessageClassificationRepository(session),
            high_threshold=settings.use_category_embedding_high_threshold,
            margin_delta=settings.use_category_cascade_margin_delta,
        )
        try:
            await use_case.execute(
                ClassifyPendingCascadeUseCategoryInput(
                    classification_id=classification_id
                )
            )
        except Exception as error:
            await session.rollback()
            await _mark_background_classification_failed(classification_id, error)
            raise
        await session.commit()


@museum_question_triage_router.post(
    "/{question_id}/triage", response_model=TriageResponse
)
async def triage_museum_question(
    question_id: str,
    background_tasks: BackgroundTasks,
    caller: CallerPermission,
    use_case: TriageUseCase,
    create_pending_use_category: CreatePendingUseCategoryUseCase,
    create_pending_embedding_use_category: CreatePendingEmbeddingUseCategoryUseCase,
    create_pending_cascade_use_category: CreatePendingCascadeUseCategoryUseCase,
    classification_repository: ClassificationRepository,
    session: DBSession,
) -> TriageResponse:
    require_staff(caller)
    try:
        result = await use_case.execute(
            TriageMuseumQuestionInput(question_id=question_id, caller=caller)
        )
    except QuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except ModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "MODEL_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except ModelTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": "MODEL_TIMEOUT", "message": str(exc)},
        ) from exc
    pending_classification_id: str | None = None
    pending_embedding_classification_id: str | None = None
    pending_cascade_classification_id: str | None = None
    if settings.use_category_classification_enabled:
        pending = await create_pending_use_category.execute(
            CreatePendingUseCategoryClassificationInput(triage_id=result.id)
        )
        pending_classification_id = pending.id
        if settings.use_category_embedding_shadow_enabled:
            pending_embedding = await create_pending_embedding_use_category.execute(
                CreatePendingEmbeddingUseCategoryClassificationInput(
                    triage_id=result.id
                )
            )
            pending_embedding_classification_id = pending_embedding.id
        if settings.use_category_cascade_enabled:
            pending_cascade = await create_pending_cascade_use_category.execute(
                CreatePendingCascadeUseCategoryClassificationInput(triage_id=result.id)
            )
            pending_cascade_classification_id = pending_cascade.id
    await session.commit()
    if pending_classification_id is not None:
        background_tasks.add_task(
            _classify_use_categories_background, pending_classification_id
        )
    if pending_embedding_classification_id is not None:
        background_tasks.add_task(
            _classify_embedding_use_categories_background,
            pending_embedding_classification_id,
        )
    if pending_cascade_classification_id is not None:
        background_tasks.add_task(
            _classify_cascade_use_categories_background,
            pending_cascade_classification_id,
        )
    use_category_classification = await _current_llm_use_category_classification(
        classification_repository, result.id
    )
    return triage_response(result, use_category_classification)


@museum_question_triage_router.get(
    "/{question_id}/triage", response_model=TriageResponse
)
async def get_latest_museum_question_triage(
    question_id: str,
    caller: CallerPermission,
    use_case: GetLatestTriageUseCase,
    classification_repository: ClassificationRepository,
) -> TriageResponse:
    require_staff(caller)
    result = await use_case.execute(GetLatestTriageInput(question_id=question_id))
    if result is None:
        raise _triage_not_found(question_id)
    use_category_classification = await _current_llm_use_category_classification(
        classification_repository, result.id
    )
    return triage_response(result, use_category_classification)


@museum_question_triage_router.get(
    "/{question_id}/triage/classifications",
    response_model=UseCategoryClassificationAuditListResponse,
)
async def list_museum_question_triage_classifications(
    question_id: str,
    caller: CallerPermission,
    use_case: GetLatestTriageUseCase,
    classification_repository: ClassificationRepository,
) -> UseCategoryClassificationAuditListResponse:
    require_staff(caller)
    result = await use_case.execute(GetLatestTriageInput(question_id=question_id))
    if result is None:
        raise _triage_not_found(question_id)
    classifications = await classification_repository.list_current_by_triage(result.id)
    return use_category_classification_audit_list_response(result.id, classifications)


@museum_question_triage_router.put(
    "/{question_id}/triage/use-categories",
    response_model=UseCategoryClassificationAuditListResponse,
)
async def sync_triage_use_categories(
    question_id: str,
    body: UseCategoryCorrectionRequest,
    caller: CallerPermission,
    use_case: SyncUseCategoriesUseCase,
    latest_triage: GetLatestTriageUseCase,
    classification_repository: ClassificationRepository,
    session: DBSession,
) -> UseCategoryClassificationAuditListResponse:
    require_group(caller, GroupName.CURATORIAL)
    try:
        await use_case.execute(
            SyncUseCategoriesInput(
                question_id=question_id,
                categories=[UseCategory(category) for category in body.categories],
                human_outcome=HumanCategoryOutcome(body.humanOutcome),
                caller=caller,
            )
        )
    except TriageNotFound as exc:
        raise _triage_not_found(question_id) from exc
    except QuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except InvalidUseCategoryTrainingExample as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "INVALID_USE_CATEGORY_TRAINING_EXAMPLE",
                "message": str(exc),
            },
        ) from exc
    await session.commit()
    triage = await latest_triage.execute(GetLatestTriageInput(question_id=question_id))
    if triage is None:
        raise _triage_not_found(question_id)
    classifications = await classification_repository.list_current_by_triage(triage.id)
    return use_category_classification_audit_list_response(triage.id, classifications)


@museum_question_triage_router.patch(
    "/{question_id}/triage/verdict", response_model=TriageResponse
)
async def override_triage_verdict(
    question_id: str,
    body: OverrideTriageVerdictRequest,
    caller: CallerPermission,
    use_case: OverrideVerdictUseCase,
    classification_repository: ClassificationRepository,
    session: DBSession,
) -> TriageResponse:
    """Staff contesting the AI's scope verdict — see
    docs/plans/museum-questions-ai-triage-refinements-plan.md, checkpoint 1."""
    require_staff(caller)
    try:
        result = await use_case.execute(
            OverrideTriageVerdictInput(
                question_id=question_id,
                verdict=TriageVerdict(body.verdict),
                caller=caller,
            )
        )
    except TriageNotFound as exc:
        raise _triage_not_found(question_id) from exc
    except QuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except ModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "MODEL_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except ModelTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": "MODEL_TIMEOUT", "message": str(exc)},
        ) from exc
    await session.commit()
    use_category_classification = await _current_llm_use_category_classification(
        classification_repository, result.id
    )
    return triage_response(result, use_category_classification)


@museum_question_triage_router.put(
    "/{question_id}/triage/search-terms", response_model=TriageResponse
)
async def sync_triage_search_terms(
    question_id: str,
    body: TriageSearchTermsRequest,
    caller: CallerPermission,
    use_case: SyncSearchTermsUseCase,
    classification_repository: ClassificationRepository,
    session: DBSession,
) -> TriageResponse:
    """Staff editing/adding/removing extracted search terms — see
    docs/plans/museum-questions-ai-triage-refinements-plan.md, checkpoint 2.
    Rejects with 409 while the triage is OUT_OF_SCOPE (valid payload, wrong
    state) and 422 on validation failures (field too long, too many terms)."""
    require_staff(caller)
    try:
        result = await use_case.execute(
            SyncTriageSearchTermsInput(
                question_id=question_id,
                terms=[(term.english, term.portuguese) for term in body.terms],
                caller=caller,
            )
        )
    except TriageNotFound as exc:
        raise _triage_not_found(question_id) from exc
    except TriageNotInScope as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "TRIAGE_NOT_IN_SCOPE", "message": str(exc)},
        ) from exc
    except TriageTermValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "INVALID_SEARCH_TERMS", "message": str(exc)},
        ) from exc
    await session.commit()
    use_category_classification = await _current_llm_use_category_classification(
        classification_repository, result.id
    )
    return triage_response(result, use_category_classification)
