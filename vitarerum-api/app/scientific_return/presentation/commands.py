"""Operational commands for scientific-return monitoring."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.database import async_session_factory
from app.notifications.public import (
    NotificationKind,
    RelatedResourceType,
    get_notification_dispatcher,
)
from app.scientific_return.application.evaluation import evaluate_cases
from app.scientific_return.application.use_cases import RunScientificReturnSearch
from app.scientific_return.presentation.dependencies import (
    get_bibliographic_sources,
    get_max_queries,
    get_repository,
    get_result_limit,
)

logger = logging.getLogger(__name__)


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
    return parser


async def _amain() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.command == "run-due":
        _, failed = await run_due(limit=max(1, args.limit))
        return 1 if failed else 0
    if args.command == "evaluate-phase0":
        report = await evaluate_cases(
            get_bibliographic_sources(), result_limit=max(1, args.result_limit)
        )
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0
    raise ValueError(f"Unknown command: {args.command}")


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
