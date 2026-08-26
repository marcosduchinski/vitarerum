"""Operational commands for scientific-return monitoring."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.identity.public import Actor, GroupName, PermissionId
from app.notifications.public import (
    NotificationKind,
    RelatedResourceType,
    get_notification_dispatcher,
)
from app.scientific_return.application.evaluation import (
    evaluate_cases,
    finalize_human_review_report,
)
from app.scientific_return.application.full_agentic import (
    ExecuteFullAgenticInput,
    FullAgenticAlreadyRunning,
    FullAgenticCircuitOpen,
    FullAgenticDisabled,
    FullAgenticSourceConfigurationInvalid,
    StartFullAgenticInput,
)
from app.scientific_return.application.ports import (
    BibliographicSource,
    InvestigationReasoner,
)
from app.scientific_return.application.run_investigation import (
    CloseAbandonedInvestigations,
    InvestigationAlreadyRunning,
    InvestigationDisabled,
    InvestigationNotPossible,
    RunInvestigationInput,
)
from app.scientific_return.application.use_cases import RunScientificReturnSearch
from app.scientific_return.domain.enums import (
    FullAgenticInvestigationStatus,
    InvestigationMode,
    InvestigationObjective,
)
from app.scientific_return.domain.full_agentic_models import (
    FullAgenticInvestigationId,
)
from app.scientific_return.domain.models import (
    CandidatePublicationId,
    ScientificReturnWatchId,
)
from app.scientific_return.infrastructure.unit_of_work import (
    SqlAlchemyInvestigationUnitOfWork,
    SystemClock,
)
from app.scientific_return.presentation.dependencies import (
    get_bibliographic_sources,
    get_crossref_source,
    get_europe_pmc_source,
    get_full_agentic_executor,
    get_full_agentic_starter,
    get_investigation_repository,
    get_investigation_runner,
    get_max_queries,
    get_openalex_source,
    get_repository,
    get_result_limit,
)

logger = logging.getLogger(__name__)

# How many unproven candidates one watch may spend an enrichment cycle on per
# sweep. Each cycle is a handful of exact-phrase queries, but a watch with a
# large pending queue would otherwise turn one sweep into a long tail of them.
_PROOF_LIMIT_PER_WATCH = 5

# A supervised cycle is one iteration and one action, and its longest
# legitimate silence is a single reasoner call. Thirty minutes is far beyond
# any live cycle, so anything quieter than this is gone rather than slow.
_ABANDONED_AFTER = timedelta(minutes=30)

# Unattended work is attributed to the scheduler, never to the curator who
# happens to own the watch: "who started this?" must answer truthfully, and a
# person who was not there did not start it. The scheduled entry points skip
# authorisation, so this identity is a provenance label and grants nothing.
_SCHEDULER = Actor(
    id=PermissionId("system-scientific-return-scheduler"),
    group=GroupName.CURATORIAL,
    email="",
)


def phase_zero_sources(selection: str) -> tuple[BibliographicSource, ...]:
    requested = tuple(
        dict.fromkeys(
            item.strip().casefold() for item in selection.split(",") if item.strip()
        )
    )
    if not requested or requested == ("all",):
        requested = ("crossref", "openalex", "europe_pmc")

    supported = {"crossref", "openalex", "europe_pmc"}
    unknown = set(requested) - supported
    if unknown:
        raise ValueError(f"Unknown Phase 0 source(s): {', '.join(sorted(unknown))}")

    sources: list[BibliographicSource] = []
    for name in requested:
        if name == "crossref":
            sources.append(get_crossref_source())
        elif name == "europe_pmc":
            sources.append(get_europe_pmc_source())
        elif settings.openalex_api_key:
            sources.append(get_openalex_source())
        elif selection.strip().casefold() != "all":
            raise ValueError("OpenAlex evaluation requires OPENALEX_API_KEY")
        else:
            logger.warning(
                "Skipping OpenAlex because OPENALEX_API_KEY is not configured."
            )
    return tuple(sources)


def _evaluation_reasoner() -> InvestigationReasoner:
    """A reasoner backed by the published prompts, read through a live session.

    The evaluator needs no repository, but it does need the prompts, which live
    in the database like every other published prompt.
    """
    from app.scientific_return.application.investigation_reasoner import (
        PromptedInvestigationReasoner,
    )
    from app.scientific_return.infrastructure.prompt_acl import AiPromptRegistryAdapter
    from app.scientific_return.presentation.dependencies import get_agent_reasoner

    session = async_session_factory()
    return PromptedInvestigationReasoner(
        get_agent_reasoner(), AiPromptRegistryAdapter(session)
    )


async def _queue_autonomous_search(
    session: AsyncSession, watch_id: ScientificReturnWatchId, run_id: str
) -> None:
    """Chain the autonomous agent onto a completed scheduled sweep.

    The deterministic run is the cheap first pass; the agent is what finds the
    publications no rule can match. Queuing is best-effort: a disabled feature,
    an open circuit breaker or an investigation already live for this watch are
    all normal outcomes of an unattended sweep, not failures of the sweep.

    The key is derived from the run, so replaying a sweep never buys a second
    investigation for work that was already paid for.
    """
    try:
        investigation = await get_full_agentic_starter(session).execute_scheduled(
            StartFullAgenticInput(
                watch_id=watch_id,
                objective=InvestigationObjective.DISCOVER_CANDIDATE,
                candidate_id=None,
                idempotency_key=f"scheduled-sweep:{run_id}",
                caller=_SCHEDULER,
            )
        )
        logger.info(
            "Queued autonomous investigation %s for watch %s.",
            investigation.id,
            watch_id,
        )
    except (
        FullAgenticDisabled,
        FullAgenticCircuitOpen,
        FullAgenticAlreadyRunning,
        FullAgenticSourceConfigurationInvalid,
    ) as exc:
        logger.info("No autonomous investigation for watch %s: %s", watch_id, exc)
    except Exception:
        await session.rollback()
        logger.exception(
            "Could not queue an autonomous investigation for watch %s.", watch_id
        )


async def run_due(*, limit: int) -> tuple[int, int]:
    now = datetime.now(tz=UTC)
    async with async_session_factory() as session:
        due = await get_repository(session).list_due_watches(now, limit)

    completed = 0
    failed = 0
    for due_watch in due:
        async with async_session_factory() as session:
            try:
                locked = bool(
                    (
                        await session.execute(
                            text(
                                "SELECT pg_try_advisory_xact_lock(hashtext(:lock_key))"
                            ),
                            {"lock_key": f"scientific-return:{due_watch.id}"},
                        )
                    ).scalar_one()
                )
                if not locked:
                    logger.info("Watch %s is already being processed.", due_watch.id)
                    await session.rollback()
                    continue

                repository = get_repository(session)
                watch = await repository.get_watch(due_watch.id)
                if watch is None or watch.next_run_at > datetime.now(tz=UTC):
                    await session.rollback()
                    continue
                run = await RunScientificReturnSearch(
                    repository,
                    get_bibliographic_sources(),
                    get_result_limit(),
                    get_max_queries(),
                ).execute_scheduled(watch.id)
                await session.commit()
                completed += 1

                if run.new_candidate_count:
                    try:
                        await get_notification_dispatcher(session).notify(
                            recipient_permission_id=watch.created_by,
                            kind=NotificationKind.SCIENTIFIC_RETURN_CANDIDATES_FOUND,
                            triggered_by=None,
                            related_resource_type=RelatedResourceType.PROJECT,
                            related_resource_id=watch.project_id,
                            note=(
                                f"Scientific return found {run.new_candidate_count} "
                                "new candidate(s) for review."
                            ),
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        logger.exception(
                            "Could not notify scientific-return run %s.", run.id
                        )

                await _queue_autonomous_search(session, watch.id, run.id)
            except Exception:
                failed += 1
                await session.rollback()
                logger.exception("Scientific-return watch %s failed.", due_watch.id)

    logger.info(
        "Processed %s due scientific-return watches; %s failed.", completed, failed
    )
    return completed, failed


async def _prove_pending_candidates(
    session: AsyncSession, watch_id: ScientificReturnWatchId, limit: int
) -> int:
    """Try to tie unproven pending candidates to a consulted specimen.

    The autonomous agent finds publications by taxon and author, so it can leave
    a candidate that is plausible but carries no inventory evidence. This runs
    the enrichment cycle over exactly those, spending inventory variants the
    agent has not already used. It never decides anything: a candidate that
    stays unproven simply stays pending for a curator.
    """
    proved = 0
    candidates = await get_repository(session).list_candidates_needing_inventory_proof(
        watch_id, limit
    )
    for candidate in candidates:
        try:
            investigation = await get_investigation_runner(session).execute_scheduled(
                RunInvestigationInput(
                    watch_id=watch_id,
                    objective=InvestigationObjective.ENRICH_CANDIDATE,
                    caller=_SCHEDULER,
                    candidate_id=CandidatePublicationId(str(candidate.id)),
                    idempotency_key=f"scheduled-proof:{candidate.id}",
                )
            )
            await session.commit()
            proved += 1
            logger.info(
                "Enrichment %s for candidate %s ended with %s.",
                investigation.id,
                candidate.id,
                investigation.stop_reason.value if investigation.stop_reason else "-",
            )
        except (
            InvestigationDisabled,
            InvestigationAlreadyRunning,
            InvestigationNotPossible,
        ) as exc:
            # Normal outcomes of an unattended sweep, exactly as for the rung
            # above: the mode forbids execution, another cycle already covers
            # this candidate, or the objective's preconditions are not met.
            # None of them is a fault of the sweep, so none is logged as one.
            logger.info("No enrichment for candidate %s: %s", candidate.id, exc)
        except Exception:
            await session.rollback()
            logger.exception(
                "Could not run enrichment for candidate %s.", candidate.id
            )
    return proved


async def run_full_agentic_queue(*, limit: int, worker_id: str) -> tuple[int, int]:
    """Claim and execute durable DB-queued investigations without overlap."""
    completed = 0
    failed = 0
    for _ in range(limit):
        async with async_session_factory() as session:
            investigation_id = (
                await session.execute(
                    text(
                        "SELECT id FROM sr_full_agentic_investigations "
                        "WHERE status = 'QUEUED' "
                        "OR (status IN ('RUNNING','CANCEL_REQUESTED') AND "
                        "(lease_expires_at IS NULL OR lease_expires_at < now())) "
                        "ORDER BY created_at "
                        "FOR UPDATE SKIP LOCKED LIMIT 1"
                    )
                )
            ).scalar_one_or_none()
            if investigation_id is None:
                await session.rollback()
                break
            try:
                item = await get_full_agentic_executor(session).execute(
                    ExecuteFullAgenticInput(
                        investigation_id=FullAgenticInvestigationId(investigation_id),
                        worker_id=worker_id,
                    )
                )
                if item.status.value == "FAILED":
                    failed += 1
                else:
                    completed += 1
                if item.search_run_id is not None:
                    repository = get_repository(session)
                    run = await repository.get_run(item.search_run_id)
                    watch = await repository.get_watch(item.watch_id)
                    if run and watch and run.new_candidate_count:
                        try:
                            await get_notification_dispatcher(session).notify(
                                recipient_permission_id=watch.created_by,
                                kind=(
                                    NotificationKind.SCIENTIFIC_RETURN_CANDIDATES_FOUND
                                ),
                                triggered_by=None,
                                related_resource_type=RelatedResourceType.PROJECT,
                                related_resource_id=watch.project_id,
                                note=(
                                    "Autonomous scientific-return search found "
                                    f"{run.new_candidate_count} new candidate(s) "
                                    "for review."
                                ),
                            )
                            await session.commit()
                        except Exception:
                            await session.rollback()
                            logger.exception(
                                "Could not notify full-agentic investigation %s.",
                                item.id,
                            )
                if item.status is FullAgenticInvestigationStatus.COMPLETED:
                    # Third rung of the scheduled chain: the agent has just added
                    # whatever it could find, so this is the moment the unproven
                    # candidates of this watch are known and worth one cycle each.
                    await _prove_pending_candidates(
                        session, item.watch_id, _PROOF_LIMIT_PER_WATCH
                    )
            except Exception:
                failed += 1
                await session.rollback()
                logger.exception(
                    "Could not execute full-agentic investigation %s.",
                    investigation_id,
                )
    logger.info(
        "Processed %s full-agentic investigations; %s failed.", completed, failed
    )
    return completed, failed


async def run_sweep(*, limit: int, agent_limit: int, worker_id: str) -> tuple[int, int]:
    """One scheduled pass over the whole chain, in order.

    The deterministic sweep queues the autonomous investigations, so draining
    the queue in the same run is what turns "queued" into "done" on a single
    schedule. Running the drain even when no watch was due is deliberate: an
    investigation left behind by an earlier pass, or abandoned by a worker that
    died holding a lease, is picked up here rather than waiting for a watch to
    come due again.
    """
    # First, so a cycle stranded by an earlier pass stops blocking its target
    # before this pass tries to investigate it again. Housekeeping never decides
    # whether the real work runs: one unreadable row must not cost a whole sweep.
    try:
        async with async_session_factory() as session:
            closed = await CloseAbandonedInvestigations(
                get_investigation_repository(session),
                SqlAlchemyInvestigationUnitOfWork(session),
                SystemClock(),
                _ABANDONED_AFTER,
            ).execute(limit=limit)
        if closed:
            logger.info("Closed %s abandoned investigation(s).", closed)
    except Exception:
        logger.exception("Could not close abandoned investigations; sweeping anyway.")
    completed, failed = await run_due(limit=limit)
    agent_completed, agent_failed = await run_full_agentic_queue(
        limit=agent_limit, worker_id=worker_id
    )
    return completed + agent_completed, failed + agent_failed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scientific-return")
    subcommands = parser.add_subparsers(dest="command", required=True)
    due = subcommands.add_parser(
        "run-due", help="Run active scientific-return watches whose date is due."
    )
    due.add_argument("--limit", type=int, default=25)
    queued = subcommands.add_parser(
        "run-agentic-queue",
        help="Claim and execute queued or abandoned full-agentic investigations.",
    )
    queued.add_argument("--limit", type=int, default=10)
    queued.add_argument("--worker-id", default="scientific-return-cli-worker")
    sweep = subcommands.add_parser(
        "run-sweep",
        help="Run due watches and then drain the agentic queue, in one pass.",
    )
    sweep.add_argument("--limit", type=int, default=25)
    sweep.add_argument("--agent-limit", type=int, default=10)
    sweep.add_argument("--worker-id", default="scientific-return-cli-worker")
    evaluation = subcommands.add_parser(
        "evaluate-phase0", help="Run the five-case empirical baseline."
    )
    evaluation.add_argument("--result-limit", type=int, default=20)
    evaluation.add_argument(
        "--sources",
        default="all",
        help="Comma-separated sources: crossref, openalex, europe_pmc (default: all).",
    )
    evaluation.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this path instead of stdout.",
    )
    agentic = subcommands.add_parser(
        "evaluate-agentic",
        help="Measure the agentic cycle over the fixture, without persisting.",
    )
    agentic.add_argument(
        "--mode",
        default="SUPERVISED",
        help="SHADOW, POLICY_ONLY or SUPERVISED (default: SUPERVISED).",
    )
    agentic.add_argument("--sources", default="europe_pmc")
    agentic.add_argument("--output", type=Path)
    evaluation.add_argument(
        "--reviews",
        type=Path,
        help=(
            "Finalize human metrics from a previous report whose reviewQueue "
            "was completed by staff, without repeating external searches."
        ),
    )
    return parser


async def _amain() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.command == "run-due":
        _, failed = await run_due(limit=max(1, args.limit))
        return 1 if failed else 0
    if args.command == "run-sweep":
        _, failed = await run_sweep(
            limit=max(1, args.limit),
            agent_limit=max(1, args.agent_limit),
            worker_id=args.worker_id,
        )
        return 1 if failed else 0
    if args.command == "run-agentic-queue":
        _, failed = await run_full_agentic_queue(
            limit=max(1, args.limit), worker_id=args.worker_id
        )
        return 1 if failed else 0
    if args.command == "evaluate-agentic":
        from app.scientific_return.application.agentic_evaluation import (
            evaluate_agentic_cases,
        )
        from app.scientific_return.presentation.dependencies import (
            get_agent_configuration,
        )

        configuration = get_agent_configuration()
        mode = InvestigationMode(args.mode.upper())
        report = await evaluate_agentic_cases(
            phase_zero_sources(args.sources),
            _evaluation_reasoner(),
            mode=mode,
            budget=configuration.budget,
            allowed_sources=configuration.allowed_sources,
        )
        payload = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0
    if args.command == "evaluate-phase0":
        if args.reviews:
            report = finalize_human_review_report(
                json.loads(args.reviews.read_text(encoding="utf-8"))
            )
        else:
            report = await evaluate_cases(
                phase_zero_sources(args.sources),
                result_limit=max(1, args.result_limit),
            )
        payload = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0
    raise ValueError(f"Unknown command: {args.command}")


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
