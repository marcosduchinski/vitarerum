"""Operational commands for scientific-return monitoring."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.config import settings
from app.database import async_session_factory
from app.notifications.public import (
    NotificationKind,
    RelatedResourceType,
    get_notification_dispatcher,
)
from app.scientific_return.application.evaluation import (
    evaluate_cases,
    finalize_human_review_report,
)
from app.scientific_return.application.full_agentic import ExecuteFullAgenticInput
from app.scientific_return.application.ports import (
    BibliographicSource,
    InvestigationReasoner,
)
from app.scientific_return.application.use_cases import RunScientificReturnSearch
from app.scientific_return.domain.enums import InvestigationMode
from app.scientific_return.domain.full_agentic_models import (
    FullAgenticInvestigationId,
)
from app.scientific_return.presentation.dependencies import (
    get_bench_repository,
    get_bibliographic_sources,
    get_crossref_source,
    get_europe_pmc_source,
    get_full_agentic_executor,
    get_max_queries,
    get_openalex_source,
    get_repository,
    get_result_limit,
)

logger = logging.getLogger(__name__)


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
            except Exception:
                failed += 1
                await session.rollback()
                logger.exception("Scientific-return watch %s failed.", due_watch.id)

    logger.info(
        "Processed %s due scientific-return watches; %s failed.", completed, failed
    )
    return completed, failed


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


async def run_test_bench_queue(*, limit: int, worker_id: str) -> tuple[int, int]:
    """Recover pending or lease-expired test items from the durable DB queue."""
    completed = 0
    failed = 0
    for _ in range(limit):
        async with async_session_factory() as session:
            item_id = (
                await session.execute(
                    text(
                        "SELECT id FROM sr_test_items "
                        "WHERE status = 'PENDING' OR "
                        "(status = 'RUNNING' AND lease_expires_at < now()) "
                        "ORDER BY batch_id, ordinal "
                        "FOR UPDATE SKIP LOCKED LIMIT 1"
                    )
                )
            ).scalar_one_or_none()
            if item_id is None:
                await session.rollback()
                break
            try:
                await get_bench_repository(session).claim_and_execute(
                    item_id, worker_id
                )
                await session.commit()
                item_status = (
                    await session.execute(
                        text("SELECT status FROM sr_test_items WHERE id = :item_id"),
                        {"item_id": item_id},
                    )
                ).scalar_one()
                failed += item_status == "ERROR"
                completed += item_status == "COMPLETED"
            except Exception:
                failed += 1
                await session.rollback()
                logger.exception("Could not execute test-bench item %s.", item_id)
    logger.info("Processed %s test-bench items; %s failed.", completed, failed)
    return completed, failed


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
    test_queued = subcommands.add_parser(
        "run-test-queue",
        help="Claim and execute pending or abandoned Scientific Return Test items.",
    )
    test_queued.add_argument("--limit", type=int, default=25)
    test_queued.add_argument("--worker-id", default="scientific-return-test-cli")
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
    if args.command == "run-agentic-queue":
        _, failed = await run_full_agentic_queue(
            limit=max(1, args.limit), worker_id=args.worker_id
        )
        return 1 if failed else 0
    if args.command == "run-test-queue":
        _, failed = await run_test_bench_queue(
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
