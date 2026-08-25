"""PostgreSQL integration tests for full-agentic candidate links."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import settings
from app.scientific_return.domain.enums import (
    AgentAnalysisStatus,
    AgentConfidence,
    AgenticCandidateRelationKind,
    AgenticToolExecutionStatus,
    AgentRecommendedAction,
    FullAgenticInvestigationStatus,
    InvestigationObjective,
)
from app.scientific_return.domain.full_agentic_models import (
    AgenticBudget,
    AgenticCandidateLink,
    AgenticToolExecution,
    AgenticToolExecutionId,
    AgenticUsage,
    FullAgenticInvestigation,
    FullAgenticInvestigationId,
)
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateAnalysisResult,
    CandidatePublicationId,
    ScientificReturnRunId,
    ScientificReturnWatchId,
)
from app.scientific_return.infrastructure.full_agentic_repository import (
    SqlAlchemyFullAgenticRepository,
)
from app.scientific_return.infrastructure.repositories import (
    SqlAlchemyScientificReturnRepository,
)
from app.shared.field_encryption import FieldEncryptor
from app.shared.kernel import PermissionId

pytestmark = pytest.mark.postgres


@pytest.fixture
async def postgres_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable at settings.database_url: {exc}")
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_candidate_link_table_has_expected_composite_primary_key(
    postgres_engine: AsyncEngine,
) -> None:
    async with postgres_engine.connect() as connection:
        definition = (
            await connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) "
                    "FROM pg_constraint "
                    "WHERE conrelid = "
                    "'sr_agentic_investigation_candidates'::regclass "
                    "AND contype = 'p'"
                )
            )
        ).scalar_one_or_none()

    assert definition == "PRIMARY KEY (investigation_id, candidate_id)"


async def test_link_candidate_is_idempotent_on_postgresql(
    postgres_engine: AsyncEngine,
) -> None:
    async with postgres_engine.connect() as connection:
        await connection.execute(
            text(
                "CREATE TEMP TABLE sr_agentic_investigation_candidates ("
                "investigation_id varchar(36) NOT NULL, "
                "candidate_id varchar(36) NOT NULL, "
                "relation_kind varchar(16) NOT NULL, "
                "rank integer NOT NULL, "
                "linked_at timestamptz NOT NULL, "
                "PRIMARY KEY (investigation_id, candidate_id)"
                ")"
            )
        )
        session = AsyncSession(bind=connection, expire_on_commit=False)
        repository = SqlAlchemyFullAgenticRepository(
            session,
            FieldEncryptor(bytes(32)),
        )
        link = AgenticCandidateLink(
            investigation_id=FullAgenticInvestigationId("investigation-1"),
            candidate_id=CandidatePublicationId("candidate-1"),
            relation_kind=AgenticCandidateRelationKind.CREATED,
            rank=1,
            linked_at=datetime.now(tz=UTC),
        )

        assert await repository.link_candidate(link) is True
        assert await repository.link_candidate(link) is False
        stored = (
            await session.execute(
                text("SELECT count(*) FROM sr_agentic_investigation_candidates")
            )
        ).scalar_one()
        assert stored == 1
        await session.close()


async def test_agent_analysis_accepts_the_real_published_prompt_id(
    postgres_engine: AsyncEngine,
) -> None:
    async with postgres_engine.connect() as connection:
        await connection.execute(
            text(
                "CREATE TEMP TABLE scientific_return_agent_analyses "
                "(LIKE public.scientific_return_agent_analyses INCLUDING ALL)"
            )
        )
        session = AsyncSession(bind=connection, expire_on_commit=False)
        repository = SqlAlchemyScientificReturnRepository(
            session, FieldEncryptor(bytes(32))
        )
        analysis = CandidateAgentAnalysis(
            id=CandidateAgentAnalysisId("analysis-v2"),
            candidate_id=CandidatePublicationId("candidate-v2"),
            run_id=ScientificReturnRunId("run-v2"),
            status=AgentAnalysisStatus.RUNNING,
            model="test-model",
            prompt_version_id="pver-sr-full-reader-v2",
            prompt_version="scientific-return-full-agentic-reader-v2",
            input_payload={"inventoryEvidenceStatus": "VERIFIED"},
            input_hash=hashlib.sha256(b"input").hexdigest(),
            started_at=datetime.now(tz=UTC),
            created_by=PermissionId("permission-v2"),
        )
        analysis.complete(
            CandidateAnalysisResult(
                summary="Grounded",
                supporting_evidence=("MB04-001066",),
                contradictions=(),
                missing_evidence=(),
                recommended_action=AgentRecommendedAction.PRESENT_FOR_REVIEW,
                proposed_queries=(),
                reasoning_summary="Grounded",
                confidence=AgentConfidence.HIGH,
            ),
            hashlib.sha256(b"response").hexdigest(),
            datetime.now(tz=UTC),
        )

        await repository.add_agent_analysis(analysis)
        stored = (
            await session.execute(
                text(
                    "SELECT prompt_version_id, prompt_version, input_payload "
                    "FROM scientific_return_agent_analyses WHERE id=:id"
                ),
                {"id": analysis.id},
            )
        ).one()

        assert stored.prompt_version_id == "pver-sr-full-reader-v2"
        assert len(stored.prompt_version_id) <= 36
        assert stored.prompt_version == "scientific-return-full-agentic-reader-v2"
        assert "VERIFIED" not in stored.input_payload
        await session.close()


async def test_tool_result_round_trips_encrypted_replay_text_and_unique_key(
    postgres_engine: AsyncEngine,
) -> None:
    async with postgres_engine.connect() as connection:
        await connection.execute(
            text(
                "CREATE TEMP TABLE sr_agentic_tool_executions "
                "(LIKE public.sr_agentic_tool_executions INCLUDING ALL)"
            )
        )
        session = AsyncSession(bind=connection, expire_on_commit=False)
        repository = SqlAlchemyFullAgenticRepository(session, FieldEncryptor(bytes(32)))
        execution = AgenticToolExecution(
            id=AgenticToolExecutionId("tool-v2"),
            investigation_id=FullAgenticInvestigationId("investigation-v2"),
            trajectory_sequence=1,
            idempotency_key="unique-attempt-v2",
            status=AgenticToolExecutionStatus.RUNNING,
            invocation={"source": "EUROPE_PMC", "query": "MB04-001066"},
            started_at=datetime.now(tz=UTC),
        )
        await repository.add_tool_execution(execution)
        execution.status = AgenticToolExecutionStatus.COMPLETED
        execution.result = {
            "records": [{"indexed_text": "Material examined MB04-001066"}]
        }
        execution.result_hash = hashlib.sha256(b"result").hexdigest()
        execution.completed_at = datetime.now(tz=UTC)
        await repository.save_tool_execution(execution)

        stored_ciphertext = await session.scalar(
            text(
                "SELECT result_encrypted FROM sr_agentic_tool_executions "
                "WHERE id=:id"
            ),
            {"id": execution.id},
        )
        replayed = await repository.get_tool_execution("unique-attempt-v2")

        assert replayed is not None
        assert replayed.result == execution.result
        assert "Material examined" not in str(stored_ciphertext)
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO sr_agentic_tool_executions "
                        "(id, investigation_id, trajectory_sequence, "
                        "idempotency_key, status, invocation_encrypted, attempts, "
                        "started_at) SELECT :duplicate_id, investigation_id, "
                        "trajectory_sequence, idempotency_key, status, "
                        "invocation_encrypted, attempts, started_at "
                        "FROM sr_agentic_tool_executions WHERE id=:id"
                    ),
                    {"duplicate_id": "tool-v2-duplicate", "id": execution.id},
                )
        await session.close()


async def test_claim_and_renew_lease_are_owner_safe_on_postgresql(
    postgres_engine: AsyncEngine,
) -> None:
    async with postgres_engine.connect() as connection:
        await connection.execute(
            text(
                "CREATE TEMP TABLE sr_full_agentic_investigations "
                "(LIKE public.sr_full_agentic_investigations INCLUDING ALL)"
            )
        )
        session = AsyncSession(bind=connection, expire_on_commit=False)
        repository = SqlAlchemyFullAgenticRepository(session, FieldEncryptor(bytes(32)))
        now = datetime.now(tz=UTC)
        investigation = FullAgenticInvestigation(
            id=FullAgenticInvestigationId("investigation-lease-v2"),
            watch_id=ScientificReturnWatchId("watch-lease-v2"),
            objective=InvestigationObjective.DISCOVER_CANDIDATE,
            status=FullAgenticInvestigationStatus.QUEUED,
            idempotency_key="lease-v2",
            budget=AgenticBudget(1, 1, 1, 1, 2),
            usage=AgenticUsage(),
            created_by=PermissionId("permission-v2"),
            created_at=now,
        )
        await repository.add_investigation(investigation)

        claimed = await repository.claim_investigation(
            investigation.id, "worker-a", now, now + timedelta(minutes=5)
        )
        competing = await repository.claim_investigation(
            investigation.id, "worker-b", now, now + timedelta(minutes=5)
        )
        wrong_owner = await repository.renew_investigation_lease(
            investigation.id, "worker-b", now, now + timedelta(minutes=10)
        )
        renewed = await repository.renew_investigation_lease(
            investigation.id, "worker-a", now, now + timedelta(minutes=10)
        )

        assert claimed is not None
        assert competing is None
        assert wrong_owner is None
        assert renewed is not None
        await session.close()


async def test_the_degraded_reason_round_trips_through_postgresql(
    postgres_engine: AsyncEngine,
) -> None:
    """A completed-but-degraded run must stay distinguishable after reload."""
    async with postgres_engine.connect() as connection:
        await connection.execute(
            text(
                "CREATE TEMP TABLE sr_full_agentic_investigations "
                "(LIKE public.sr_full_agentic_investigations INCLUDING ALL)"
            )
        )
        session = AsyncSession(bind=connection, expire_on_commit=False)
        repository = SqlAlchemyFullAgenticRepository(session, FieldEncryptor(bytes(32)))
        now = datetime.now(tz=UTC)
        investigation = FullAgenticInvestigation(
            id=FullAgenticInvestigationId("investigation-degraded"),
            watch_id=ScientificReturnWatchId("watch-degraded"),
            objective=InvestigationObjective.DISCOVER_CANDIDATE,
            status=FullAgenticInvestigationStatus.QUEUED,
            idempotency_key="degraded",
            budget=AgenticBudget(1, 1, 1, 1, 2),
            usage=AgenticUsage(),
            created_by=PermissionId("permission-degraded"),
            created_at=now,
        )
        await repository.add_investigation(investigation)
        investigation.start(now)
        investigation.degrade("The planner contract stayed invalid after a retry")
        investigation.complete(now)
        await repository.save_investigation(investigation)

        reloaded = await repository.get_investigation(investigation.id)

        assert reloaded is not None
        assert reloaded.status is FullAgenticInvestigationStatus.COMPLETED
        assert reloaded.degraded_reason == (
            "The planner contract stayed invalid after a retry"
        )
        await session.close()


def test_the_first_degradation_reason_is_the_one_kept() -> None:
    investigation = FullAgenticInvestigation(
        id=FullAgenticInvestigationId("investigation-first-reason"),
        watch_id=ScientificReturnWatchId("watch-first-reason"),
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        status=FullAgenticInvestigationStatus.QUEUED,
        idempotency_key="first-reason",
        budget=AgenticBudget(1, 1, 1, 1, 2),
        usage=AgenticUsage(),
        created_by=PermissionId("permission-first"),
        created_at=datetime.now(tz=UTC),
    )

    investigation.degrade("the planner failed")
    investigation.degrade("something else later")

    assert investigation.degraded_reason == "the planner failed"
