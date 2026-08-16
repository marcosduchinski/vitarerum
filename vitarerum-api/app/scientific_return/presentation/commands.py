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
from app.scientific_return.application.ports import BibliographicSource
from app.scientific_return.application.use_cases import RunScientificReturnSearch
from app.scientific_return.presentation.dependencies import (
    get_bibliographic_sources,
    get_crossref_source,
    get_europe_pmc_source,
    get_max_queries,
    get_openalex_source,
    get_repository,
    get_result_limit,
)

logger = logging.getLogger(__name__)


def phase_zero_sources(selection: str) -> tuple[BibliographicSource, ...]:
    requested = tuple(
        dict.fromkeys(
            item.strip().casefold()
            for item in selection.split(",")
            if item.strip()
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scientific-return")
    subcommands = parser.add_subparsers(dest="command", required=True)
    due = subcommands.add_parser(
        "run-due", help="Run active scientific-return watches whose date is due."
    )
    due.add_argument("--limit", type=int, default=25)
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
