"""Integration tests for the investigation repository, against a real session.

The mapping round-trip tests never touch a session, so they cannot see the
failure mode that actually bit: reading a relationship that was not eagerly
loaded raises ``MissingGreenlet`` under asyncio instead of quietly querying.
These exist so that class of bug fails here rather than in front of a curator.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Importing every model registers the tables the scientific-return foreign
# keys point at, so ``create_all`` can resolve them.
import app.use_of_collections.infrastructure.models  # noqa: F401
from app.config import settings
from app.database import Base
from app.identity.public import PermissionId
from app.scientific_return.application.ports import (
    InvestigationConcurrencyConflict,
    ToolExecutionRecord,
)
from app.scientific_return.domain.enums import (
    AgentProgress,
    AgentRecommendedAction,
    EvidenceStrength,
    EvidenceType,
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
    PolicyRejectionReason,
    RunStatus,
    StopReason,
    WatchStatus,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentObservation,
    AgentPlan,
    AgentReflection,
    EvidenceDelta,
    ExecutionBudget,
    ObservedObject,
    PolicyDecision,
    ProposedAction,
    ReasonerTelemetry,
    ToolResultSummary,
)
from app.scientific_return.domain.investigation_models import (
    InvestigationId,
    ScientificReturnInvestigation,
    ToolExecutionId,
)
from app.scientific_return.domain.models import (
    CandidateEvidence,
    CandidateEvidenceId,
    CandidatePublication,
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnQuery,
    ScientificReturnQueryId,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnSnapshotId,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)
from app.scientific_return.infrastructure.repositories import (
    SqlAlchemyInvestigationRepository,
    SqlAlchemyScientificReturnRepository,
)
from app.shared.field_encryption import FieldEncryptor

_NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_WATCH = ScientificReturnWatchId("watch-1")
_RUN = ScientificReturnRunId("run-1")


def _encryptor() -> FieldEncryptor:
    return FieldEncryptor.from_base64(settings.db_field_encryption_key)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as opened:
        yield opened
    await engine.dispose()


async def _seed(session: AsyncSession) -> None:
    repository = SqlAlchemyScientificReturnRepository(session, _encryptor())
    snapshot = ScientificReturnProjectSnapshot(
        id=ScientificReturnSnapshotId("snap-1"),
        project_id="project-1",
        payload=ProjectSnapshotPayload(
            project_id="project-1",
            project_reference="PRJ-1",
            researcher="Rita P. Eusébio",
            consulted_objects=(
                ConsultedObjectSnapshot(
                    id="object-1",
                    inventory_number="MUHNAC/MB11-001283",
                    object_name="Trichoniscoides machadoi",
                ),
            ),
        ),
        payload_hash="h",
        builder_version="v1",
        created_at=_NOW,
    )
    await repository.add_snapshot(snapshot)
    await repository.add_watch(
        ScientificReturnWatch(
            id=_WATCH,
            project_id="project-1",
            status=WatchStatus.ACTIVE,
            review_interval_days=30,
            created_by=PermissionId("perm-1"),
            created_at=_NOW,
            next_run_at=_NOW,
            schedule_anchor_at=_NOW,
            project_snapshot_id=snapshot.id,
        )
    )
    await repository.add_run(
        ScientificReturnSearchRun(
            id=_RUN,
            watch_id=_WATCH,
            status=RunStatus.COMPLETED,
            started_at=_NOW,
            completed_at=_NOW,
        )
    )
    await session.commit()


def _investigation(**overrides: object) -> ScientificReturnInvestigation:
    values: dict[str, object] = {
        "id": InvestigationId("inv-1"),
        "watch_id": _WATCH,
        "objective": InvestigationObjective.DISCOVER_CANDIDATE,
        "mode": InvestigationMode.SUPERVISED,
        "initial_run_id": _RUN,
        "budget": ExecutionBudget(1, 1, 4, 10, 5),
        "created_by": PermissionId("perm-1"),
        "started_at": _NOW,
    }
    values.update(overrides)
    return ScientificReturnInvestigation(**values)  # type: ignore[arg-type]


def _observation() -> AgentObservation:
    return AgentObservation(
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        project_reference="PRJ-1",
        researcher="Rita P. Eusébio",
        objects=(ObservedObject("object-1", "MUHNAC/MB11-001283", "Trichoniscoides"),),
        tried_queries=('"MUHNAC/MB11-001283"',),
        allowed_actions=(AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,),
        budget=ExecutionBudget(1, 1, 4, 10, 5),
    )


async def _run_cycle(
    repository: SqlAlchemyInvestigationRepository,
    investigation: ScientificReturnInvestigation,
) -> None:
    """Walk the cycle the way the use case does: add, then save at each step."""
    await repository.add(investigation)
    investigation.begin_observation(_NOW + timedelta(seconds=1))
    investigation.record_observation(_observation(), _NOW + timedelta(seconds=2))
    await repository.save(investigation)
    investigation.record_plan(
        AgentPlan(
            objective="Find inventory evidence.",
            action=ProposedAction(
                AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS, "object-1"
            ),
            reasoning_summary="No inventory evidence yet.",
            expected_evidence=(EvidenceType.INVENTORY_NUMBER,),
        ),
        _NOW + timedelta(seconds=3),
    )
    investigation.record_telemetry(
        ReasonerTelemetry(
            model="llama3.1:8b",
            prompt_version="scientific-return-agent-plan-v1",
            plan_latency_ms=40413,
        )
    )
    await repository.save(investigation)
    investigation.record_policy_decision(
        PolicyDecision.authorize("Three untried variants."),
        _NOW + timedelta(seconds=4),
        reserved_queries=3,
    )
    await repository.save(investigation)
    await repository.add_tool_execution(
        ToolExecutionRecord(
            id=ToolExecutionId("tool-1"),
            investigation_id=investigation.id,
            iteration_id="inv-1:1",
            idempotency_key="cycle-key-1",
            action=AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,
            started_at=_NOW + timedelta(seconds=4),
            queries=('"MB11-001283"',),
            sources=("EUROPE_PMC",),
            succeeded=True,
            total_results=2,
        )
    )
    investigation.record_tool_result(
        ToolResultSummary(
            executed_queries=('"MB11-001283"',),
            sources=("EUROPE_PMC",),
            total_results=2,
        ),
        "before",
        "after",
        EvidenceDelta(added=(EvidenceType.INVENTORY_NUMBER,)),
        _NOW + timedelta(seconds=5),
        tool_execution_id=ToolExecutionId("tool-1"),
    )
    await repository.save(investigation)
    investigation.record_reflection(
        AgentReflection(
            progress=AgentProgress.EVIDENCE_ADDED,
            evidence_delta_summary="One evidence added.",
            recommended_stop=True,
            reasoning_summary="Objective met.",
        )
    )
    investigation.present_for_review(
        StopReason.EVIDENCE_SUFFICIENT, _NOW + timedelta(seconds=6)
    )
    await repository.save(investigation)


# --- the regression ----------------------------------------------------------


async def test_saving_step_by_step_does_not_lazy_load(session: AsyncSession) -> None:
    """The bug this file exists for: a lazy load here raises under asyncio."""
    await _seed(session)
    repository = SqlAlchemyInvestigationRepository(session, _encryptor())

    await _run_cycle(repository, _investigation())
    await session.commit()

    reloaded = await repository.get(InvestigationId("inv-1"))
    assert reloaded is not None
    assert reloaded.status is InvestigationStatus.AWAITING_HUMAN_REVIEW


async def test_the_whole_trajectory_survives_the_database(
    session: AsyncSession,
) -> None:
    await _seed(session)
    repository = SqlAlchemyInvestigationRepository(session, _encryptor())
    await _run_cycle(repository, _investigation())
    await session.commit()

    reloaded = await repository.get(InvestigationId("inv-1"))

    assert reloaded is not None
    iteration = reloaded.iterations[0]
    assert iteration.observation is not None
    assert iteration.observation.researcher == "Rita P. Eusébio"
    assert iteration.plan is not None
    assert iteration.plan.action.object_id == "object-1"
    assert iteration.policy_decision is not None
    assert iteration.policy_decision.authorized
    assert iteration.reflection is not None
    assert iteration.telemetry is not None
    assert iteration.telemetry.model == "llama3.1:8b"
    assert iteration.evidence_delta is not None
    assert iteration.evidence_delta.has_primary_inventory_evidence
    # The outcome lives on the execution row, not on the iteration. Without it
    # a reloaded trajectory says a search was planned and never what it sent.
    assert iteration.tool_result is not None
    assert iteration.tool_result.executed_queries == ('"MB11-001283"',)
    assert iteration.tool_result.sources == ("EUROPE_PMC",)
    assert iteration.tool_result.total_results == 2
    assert reloaded.budget.used_queries == 3


async def test_only_one_iteration_row_is_written_per_iteration(
    session: AsyncSession,
) -> None:
    """Saving five times must update, not accumulate."""
    await _seed(session)
    repository = SqlAlchemyInvestigationRepository(session, _encryptor())
    await _run_cycle(repository, _investigation())
    await session.commit()

    reloaded = await repository.get(InvestigationId("inv-1"))

    assert reloaded is not None
    assert len(reloaded.iterations) == 1


# --- lookups -----------------------------------------------------------------


async def test_a_live_investigation_is_found_and_a_terminal_one_is_not(
    session: AsyncSession,
) -> None:
    await _seed(session)
    repository = SqlAlchemyInvestigationRepository(session, _encryptor())
    investigation = _investigation()
    await repository.add(investigation)
    investigation.begin_observation(_NOW + timedelta(seconds=1))
    await repository.save(investigation)
    await session.commit()

    live = await repository.find_live(
        _WATCH, InvestigationObjective.DISCOVER_CANDIDATE, None
    )
    assert live is not None

    investigation.fail(StopReason.TOOL_FAILED, "boom", _NOW + timedelta(seconds=9))
    await repository.save(investigation)
    await session.commit()

    assert (
        await repository.find_live(
            _WATCH, InvestigationObjective.DISCOVER_CANDIDATE, None
        )
        is None
    )


async def test_the_client_key_finds_the_investigation_it_produced(
    session: AsyncSession,
) -> None:
    await _seed(session)
    repository = SqlAlchemyInvestigationRepository(session, _encryptor())
    await repository.add(_investigation(idempotency_key="client-key-1"))
    await session.commit()

    found = await repository.find_by_idempotency_key("client-key-1")

    assert found is not None
    assert found.idempotency_key == "client-key-1"
    assert await repository.find_by_idempotency_key("other") is None


async def test_a_tool_execution_is_found_by_its_key(session: AsyncSession) -> None:
    await _seed(session)
    repository = SqlAlchemyInvestigationRepository(session, _encryptor())
    await repository.add(_investigation())
    await repository.add_tool_execution(
        ToolExecutionRecord(
            id=ToolExecutionId("tool-1"),
            investigation_id=InvestigationId("inv-1"),
            iteration_id="inv-1:1",
            idempotency_key="key-1",
            action=AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,
            started_at=_NOW,
            queries=('"MB11-001283"',),
            sources=("EUROPE_PMC",),
            succeeded=True,
            total_results=2,
        )
    )
    await session.commit()

    found = await repository.find_tool_execution("key-1")

    assert found is not None
    assert found.succeeded
    assert found.queries == ('"MB11-001283"',)
    assert await repository.find_tool_execution("absent") is None


# --- the deterministic repository's new operations ---------------------------


async def test_queries_are_listed_across_every_run_of_a_watch(
    session: AsyncSession,
) -> None:
    """Repetition is a property of the watch, not of one run."""
    await _seed(session)
    repository = SqlAlchemyScientificReturnRepository(session, _encryptor())
    await repository.add_run(
        ScientificReturnSearchRun(
            id=ScientificReturnRunId("run-2"),
            watch_id=_WATCH,
            status=RunStatus.COMPLETED,
            started_at=_NOW,
        )
    )
    for index, run in enumerate((_RUN, ScientificReturnRunId("run-2"))):
        await repository.add_query(
            ScientificReturnQuery(
                id=ScientificReturnQueryId(f"query-{index}"),
                run_id=run,
                source="CROSSREF",
                query_text=f'"MUHNAC/MB11-00128{index}"',
                query_type=__import__(
                    "app.scientific_return.domain.enums", fromlist=["QueryType"]
                ).QueryType.INVENTORY,
                sent_at=_NOW,
                result_count=0,
                status=__import__(
                    "app.scientific_return.domain.enums", fromlist=["QueryStatus"]
                ).QueryStatus.COMPLETED,
            )
        )
    await session.commit()

    found = await repository.list_queries_for_watch(_WATCH)

    assert len(found) == 2
    assert {item.query_text for item in found} == {
        '"MUHNAC/MB11-001280"',
        '"MUHNAC/MB11-001281"',
    }


async def test_appending_the_same_evidence_twice_writes_it_once(
    session: AsyncSession,
) -> None:
    await _seed(session)
    repository = SqlAlchemyScientificReturnRepository(session, _encryptor())
    candidate_id = CandidatePublicationId("cand-1")
    await repository.add_candidate(
        CandidatePublication(
            id=candidate_id,
            watch_id=_WATCH,
            first_seen_run_id=_RUN,
            source="EUROPE_PMC",
            source_record_id="PMC1",
            deduplication_key="doi:10.0/x",
            title="A study",
            authors=("Rita P. Eusébio",),
            publication_date="2025",
            abstract=None,
            url=None,
            raw_metadata_hash="h",
            created_at=_NOW,
            doi="10.0/x",
        )
    )
    await session.commit()

    def _evidence(row_id: str) -> CandidateEvidence:
        return CandidateEvidence(
            id=CandidateEvidenceId(row_id),
            candidate_id=candidate_id,
            type=EvidenceType.INVENTORY_NUMBER,
            strength=EvidenceStrength.PRIMARY,
            value="MUHNAC/MB11-001283",
            source_field="full_text",
            explanation="Found in the full text.",
            created_at=_NOW,
            object_id="object-1",
            investigation_id="inv-1",
            iteration_id="inv-1:1",
            source_record_id="PMC1",
            content_hash="abc",
        )

    first = await repository.append_candidate_evidences(
        candidate_id, (_evidence("ev-1"),)
    )
    second = await repository.append_candidate_evidences(
        candidate_id, (_evidence("ev-2"),)
    )
    await session.commit()

    assert len(first) == 1
    assert second == (), "the same finding must not be written twice"
    reloaded = await repository.get_candidate(candidate_id)
    assert reloaded is not None
    assert len(reloaded.evidences) == 1
    assert reloaded.evidences[0].is_agentic
    assert reloaded.evidences[0].investigation_id == "inv-1"


async def test_a_rejected_decision_keeps_its_reason_through_the_database(
    session: AsyncSession,
) -> None:
    await _seed(session)
    repository = SqlAlchemyInvestigationRepository(session, _encryptor())
    investigation = _investigation()
    await repository.add(investigation)
    investigation.begin_observation(_NOW + timedelta(seconds=1))
    investigation.record_observation(_observation(), _NOW + timedelta(seconds=2))
    investigation.record_plan(
        AgentPlan(
            objective="Search.",
            action=ProposedAction(
                AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS, "object-1"
            ),
            reasoning_summary="Try variants.",
        ),
        _NOW + timedelta(seconds=3),
    )
    investigation.record_policy_decision(
        PolicyDecision.reject(
            PolicyRejectionReason.NO_NEW_QUERY_VARIANT, "All tried."
        ),
        _NOW + timedelta(seconds=4),
    )
    await repository.save(investigation)
    await session.commit()

    reloaded = await repository.get(InvestigationId("inv-1"))

    assert reloaded is not None
    decision = reloaded.iterations[0].policy_decision
    assert decision is not None
    assert decision.rejection_reason is PolicyRejectionReason.NO_NEW_QUERY_VARIANT


async def test_a_save_is_refused_after_another_writer_moved_the_row(
    session: AsyncSession,
) -> None:
    """The race the version check exists for.

    The sweep's reaper judges a cycle abandoned and closes it; the cycle turns
    out to be alive and saves moments later. Without the check the live cycle
    would overwrite the terminal row and quietly resurrect an investigation the
    sweep had already ended.
    """
    await _seed(session)
    cycle = SqlAlchemyInvestigationRepository(session, _encryptor())
    investigation = _investigation()
    await cycle.add(investigation)
    await session.commit()

    # A second repository, as the reaper would have: its own baseline, taken
    # when it read the row.
    reaper = SqlAlchemyInvestigationRepository(session, _encryptor())
    stranded = await reaper.get(InvestigationId("inv-1"))
    assert stranded is not None
    stranded.abandon(datetime.now(tz=UTC))
    await reaper.save(stranded)
    await session.commit()

    # The original cycle now writes against a baseline that no longer holds.
    investigation.begin_observation(datetime.now(tz=UTC))
    with pytest.raises(InvestigationConcurrencyConflict):
        await cycle.save(investigation)

    survivor = await reaper.get(InvestigationId("inv-1"))
    assert survivor is not None
    assert survivor.stop_reason is StopReason.ABANDONED
