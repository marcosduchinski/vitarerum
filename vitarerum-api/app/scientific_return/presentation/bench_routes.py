"""HTTP adapter for the institution-scoped Scientific Return Test bench."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)

from app.config import settings
from app.database import async_session_factory
from app.scientific_return.application.bench_export import export_candidates
from app.scientific_return.application.ports import AgentPromptProvider
from app.scientific_return.domain.bench_models import (
    TestSourceStatus,
    TestSubject,
)
from app.scientific_return.infrastructure.bench_repository import (
    BenchConflict,
    BenchInvalid,
    BenchNotFound,
    SqlAlchemyBenchRepository,
)
from app.scientific_return.presentation.dependencies import (
    get_agent_prompt_provider,
    get_bench_repository,
)
from app.scientific_return.presentation.schemas import (
    TestBatchCreateRequest,
    TestBatchResponse,
    TestBatchUpdateRequest,
    TestCandidateResponse,
    TestItemResponse,
    TestItemsCreateRequest,
    TestReadinessResponse,
    TestSourceResponse,
    TestSourceWriteRequest,
)
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission
from app.shared.uploads import content_disposition_attachment

logger = logging.getLogger(__name__)
test_bench_router = APIRouter(prefix="/scientific-return", tags=["scientific-return"])

BenchRepository = Annotated[SqlAlchemyBenchRepository, Depends(get_bench_repository)]
AgentPrompt = Annotated[AgentPromptProvider, Depends(get_agent_prompt_provider)]


def _scope(caller: CallerPermission) -> str:
    require_staff(caller)
    if caller.institution_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "error": "TEST_INSTITUTION_REQUIRED",
                "message": "The acting permission has no institution",
            },
        )
    return caller.institution_id


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BenchNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "TEST_RESOURCE_NOT_FOUND", "message": str(exc)},
        )
    if isinstance(exc, BenchConflict):
        code = str(exc) if str(exc).startswith("TEST_") else "TEST_CONFLICT"
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": code, "message": str(exc)},
        )
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error": str(exc), "message": str(exc)},
    )


async def _execute_one_bench_item(item_id: str) -> None:
    async with async_session_factory() as session:
        repository = get_bench_repository(session)
        try:
            await repository.claim_and_execute(item_id, "in-process-test-bench")
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scientific-return test item %s failed", item_id)


async def _execute_bench_background(item_ids: list[str]) -> None:
    semaphore = asyncio.Semaphore(2)

    async def execute_one(item_id: str) -> None:
        async with semaphore:
            try:
                await _execute_one_bench_item(item_id)
            except Exception:
                logger.exception("Scientific-return test item %s escaped", item_id)

    async with asyncio.TaskGroup() as tasks:
        for item_id in item_ids:
            tasks.create_task(execute_one(item_id))


@test_bench_router.get("/test-readiness", response_model=TestReadinessResponse)
async def readiness(
    caller: CallerPermission,
    prompt_provider: AgentPrompt,
) -> TestReadinessResponse:
    _scope(caller)
    message: str | None = None
    try:
        for prompt_key in (
            "scientific_return_full_agentic_plan",
            "scientific_return_full_agentic_reader",
        ):
            await prompt_provider.get_published(prompt_key)
    except Exception:
        message = "The published autonomous-search prompts are unavailable"
    configured = bool(settings.db_field_encryption_key) and message is None
    if not settings.db_field_encryption_key:
        message = "Database field encryption is not configured"
    return TestReadinessResponse(
        enabled=settings.scientific_return_test_enabled,
        configurationValid=configured,
        message=message,
    )


@test_bench_router.get("/test-sources", response_model=list[TestSourceResponse])
async def list_sources(
    caller: CallerPermission,
    repository: BenchRepository,
    source_status: Annotated[TestSourceStatus | None, Query(alias="status")] = None,
) -> list[dict[str, object]]:
    return await repository.list_sources(_scope(caller), source_status)


@test_bench_router.post(
    "/test-sources",
    status_code=status.HTTP_201_CREATED,
    response_model=TestSourceResponse,
)
async def create_source(
    body: TestSourceWriteRequest,
    caller: CallerPermission,
    repository: BenchRepository,
) -> dict[str, object]:
    if len(body.content) > settings.scientific_return_test_max_source_characters:
        raise _http_error(BenchInvalid("TEST_SOURCE_TOO_LARGE"))
    try:
        source = await repository.create_source(
            institution_id=_scope(caller),
            actor_id=str(caller.id),
            name=body.name,
            kind=body.kind,
            content=body.content,
            locator=body.locator,
            authors=body.authors,
        )
        await repository.session.commit()
        return await repository.source_detail(source.id, source.institution_id)
    except (BenchConflict, BenchInvalid, BenchNotFound) as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


@test_bench_router.get("/test-sources/{source_id}", response_model=TestSourceResponse)
async def source_detail(
    source_id: str, caller: CallerPermission, repository: BenchRepository
) -> dict[str, object]:
    try:
        return await repository.source_detail(source_id, _scope(caller))
    except BenchNotFound as exc:
        raise _http_error(exc) from exc


@test_bench_router.put("/test-sources/{source_id}", response_model=TestSourceResponse)
async def replace_source(
    source_id: str,
    body: TestSourceWriteRequest,
    caller: CallerPermission,
    repository: BenchRepository,
) -> dict[str, object]:
    if len(body.content) > settings.scientific_return_test_max_source_characters:
        raise _http_error(BenchInvalid("TEST_SOURCE_TOO_LARGE"))
    institution_id = _scope(caller)
    try:
        await repository.replace_source(
            source_id=source_id,
            institution_id=institution_id,
            actor_id=str(caller.id),
            name=body.name,
            kind=body.kind,
            content=body.content,
            locator=body.locator,
            authors=body.authors,
        )
        await repository.session.commit()
        return await repository.source_detail(source_id, institution_id)
    except (BenchConflict, BenchInvalid, BenchNotFound) as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


async def _change_source_status(
    source_id: str,
    caller: CallerPermission,
    repository: SqlAlchemyBenchRepository,
    source_status: TestSourceStatus,
) -> dict[str, object]:
    institution_id = _scope(caller)
    try:
        await repository.set_source_status(source_id, institution_id, source_status)
        await repository.session.commit()
        return await repository.source_detail(source_id, institution_id)
    except BenchNotFound as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


@test_bench_router.delete(
    "/test-sources/{source_id}", response_model=TestSourceResponse
)
async def retire_source(
    source_id: str, caller: CallerPermission, repository: BenchRepository
) -> dict[str, object]:
    return await _change_source_status(
        source_id, caller, repository, TestSourceStatus.RETIRED
    )


@test_bench_router.post(
    "/test-sources/{source_id}/activate", response_model=TestSourceResponse
)
async def activate_source(
    source_id: str, caller: CallerPermission, repository: BenchRepository
) -> dict[str, object]:
    return await _change_source_status(
        source_id, caller, repository, TestSourceStatus.ACTIVE
    )


@test_bench_router.get("/test-batches", response_model=list[TestBatchResponse])
async def list_batches(
    caller: CallerPermission, repository: BenchRepository
) -> list[dict[str, object]]:
    return await repository.list_batches(_scope(caller))


@test_bench_router.post(
    "/test-batches",
    status_code=status.HTTP_201_CREATED,
    response_model=TestBatchResponse,
)
async def create_batch(
    body: TestBatchCreateRequest,
    caller: CallerPermission,
    repository: BenchRepository,
) -> dict[str, object]:
    batch = await repository.create_batch(
        _scope(caller), str(caller.id), body.name, body.description
    )
    await repository.session.commit()
    return await repository.batch_view(batch)


@test_bench_router.get("/test-batches/{batch_id}", response_model=TestBatchResponse)
async def batch_detail(
    batch_id: str, caller: CallerPermission, repository: BenchRepository
) -> dict[str, object]:
    try:
        return await repository.batch_detail(batch_id, _scope(caller))
    except BenchNotFound as exc:
        raise _http_error(exc) from exc


@test_bench_router.put("/test-batches/{batch_id}", response_model=TestBatchResponse)
async def select_batch_sources(
    batch_id: str,
    body: TestBatchUpdateRequest,
    caller: CallerPermission,
    repository: BenchRepository,
) -> dict[str, object]:
    if len(body.sourceIds) > settings.scientific_return_test_max_sources:
        raise _http_error(BenchInvalid("TEST_TOO_MANY_SOURCES"))
    institution_id = _scope(caller)
    try:
        await repository.select_sources(batch_id, institution_id, body.sourceIds)
        await repository.session.commit()
        return await repository.batch_detail(batch_id, institution_id)
    except (BenchConflict, BenchInvalid, BenchNotFound) as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


@test_bench_router.post(
    "/test-batches/{batch_id}/items", response_model=TestBatchResponse
)
async def add_batch_items(
    batch_id: str,
    body: TestItemsCreateRequest,
    caller: CallerPermission,
    repository: BenchRepository,
) -> dict[str, object]:
    institution_id = _scope(caller)
    if len(body.items) > settings.scientific_return_test_max_items:
        raise _http_error(BenchInvalid("TEST_TOO_MANY_ITEMS"))
    try:
        await repository.add_items(
            batch_id,
            institution_id,
            [
                TestSubject(item.author, item.objectName, item.inventoryNumber)
                for item in body.items
            ],
        )
        await repository.session.commit()
        return await repository.batch_detail(batch_id, institution_id)
    except (BenchConflict, BenchInvalid, BenchNotFound, ValueError) as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


@test_bench_router.delete(
    "/test-batches/{batch_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_batch_item(
    batch_id: str,
    item_id: str,
    caller: CallerPermission,
    repository: BenchRepository,
) -> Response:
    try:
        await repository.remove_item(batch_id, item_id, _scope(caller))
        await repository.session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (BenchConflict, BenchNotFound) as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


@test_bench_router.post(
    "/test-batches/{batch_id}/start",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TestBatchResponse,
)
async def start_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    caller: CallerPermission,
    repository: BenchRepository,
    prompt_provider: AgentPrompt,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
    ],
) -> dict[str, object]:
    if not settings.scientific_return_test_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "TEST_BENCH_DISABLED",
                "message": "Scientific Return Test is disabled",
            },
        )
    try:
        for prompt_key in (
            "scientific_return_full_agentic_plan",
            "scientific_return_full_agentic_reader",
        ):
            await prompt_provider.get_published(prompt_key)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "TEST_BENCH_NOT_READY",
                "message": "The autonomous-search prompts are not ready",
            },
        ) from exc
    institution_id = _scope(caller)
    try:
        characters = await repository.snapshot_character_count(batch_id, institution_id)
        if characters > settings.scientific_return_test_max_snapshot_characters:
            raise BenchInvalid("TEST_SNAPSHOT_TOO_LARGE")
        view, item_ids = await repository.start_batch(
            batch_id, institution_id, idempotency_key
        )
        await repository.session.commit()
        if item_ids:
            background_tasks.add_task(_execute_bench_background, item_ids)
        return view
    except (BenchConflict, BenchInvalid, BenchNotFound) as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


@test_bench_router.post(
    "/test-batches/{batch_id}/cancel", response_model=TestBatchResponse
)
async def cancel_batch(
    batch_id: str, caller: CallerPermission, repository: BenchRepository
) -> dict[str, object]:
    try:
        view = await repository.cancel_batch(batch_id, _scope(caller))
        await repository.session.commit()
        return view
    except BenchNotFound as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


@test_bench_router.post(
    "/test-batches/{batch_id}/items/{item_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TestItemResponse,
)
async def retry_item(
    batch_id: str,
    item_id: str,
    background_tasks: BackgroundTasks,
    caller: CallerPermission,
    repository: BenchRepository,
) -> dict[str, object]:
    try:
        view = await repository.retry_item(batch_id, item_id, _scope(caller))
        await repository.session.commit()
        background_tasks.add_task(_execute_bench_background, [item_id])
        return view
    except (BenchConflict, BenchNotFound) as exc:
        await repository.session.rollback()
        raise _http_error(exc) from exc


@test_bench_router.get(
    "/test-batches/{batch_id}/candidates",
    response_model=list[TestCandidateResponse],
)
async def candidates(
    batch_id: str,
    caller: CallerPermission,
    repository: BenchRepository,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, object]]:
    try:
        rows = await repository.candidates(batch_id, _scope(caller))
        return rows[page * size : (page + 1) * size]
    except BenchNotFound as exc:
        raise _http_error(exc) from exc


@test_bench_router.get("/test-batches/{batch_id}/export.csv")
async def export_csv(
    batch_id: str, caller: CallerPermission, repository: BenchRepository
) -> Response:
    try:
        rows = await repository.candidates(batch_id, _scope(caller))
    except BenchNotFound as exc:
        raise _http_error(exc) from exc
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"scientific-return-test-{batch_id}-{timestamp}.csv"
    return Response(
        content=export_candidates(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": content_disposition_attachment(filename),
            "Cache-Control": "private, no-store",
        },
    )


@test_bench_router.post(
    "/internal/test-items/{item_id}/execute",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def execute_internal(
    item_id: str,
    repository: BenchRepository,
    x_worker_token: Annotated[str | None, Header(alias="X-Worker-Token")] = None,
) -> Response:
    configured = settings.scientific_return_test_worker_token
    if (
        not configured
        or not x_worker_token
        or not secrets.compare_digest(x_worker_token, configured)
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "error": "TEST_WORKER_FORBIDDEN",
                "message": "Invalid worker token",
            },
        )
    await repository.claim_and_execute(item_id, "internal-test-bench-worker")
    await repository.session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
