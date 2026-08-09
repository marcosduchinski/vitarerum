"""Operational commands for the Museum Questions context."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.database import async_session_factory
from app.identity.public import get_permission_reader
from app.museum_questions.presentation.dependencies import get_notify_overdue_use_case
from app.notifications.public import get_notification_dispatcher

logger = logging.getLogger(__name__)


async def notify_overdue(*, limit: int) -> int:
    async with async_session_factory() as session:
        use_case = get_notify_overdue_use_case(
            session,
            get_permission_reader(session),
            get_notification_dispatcher(session),
        )
        output = await use_case.execute(limit=limit)
        await session.commit()
    logger.info(
        "Processed %s overdue museum questions and attempted %s notifications.",
        output.questions_processed,
        output.notifications_attempted,
    )
    return output.questions_processed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="museum-questions")
    subcommands = parser.add_subparsers(dest="command", required=True)
    overdue = subcommands.add_parser(
        "notify-overdue",
        help="Notify collections managers about unanswered overdue questions.",
    )
    overdue.add_argument("--limit", type=int, default=100)
    return parser


async def _amain() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.command == "notify-overdue":
        await notify_overdue(limit=max(1, args.limit))
        return 0
    raise ValueError(f"Unknown command: {args.command}")


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
