"""Shared persistence helpers (infrastructure-level, not for the pure
application layer)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def run_with_unique_retry[T](
    session: AsyncSession,
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 5,
) -> T:
    """Run ``operation`` inside a SAVEPOINT, retrying on a unique-constraint
    violation.

    Guards check-then-insert races (e.g. ``MAX(reference_number) + 1`` allocation):
    on conflict the savepoint is rolled back and the operation re-run, so a loser
    re-reads state and picks a fresh value instead of surfacing a 500. The outer
    transaction is left intact for the caller to ``commit``. The final
    ``IntegrityError`` propagates if every attempt conflicts.
    """
    for attempt in range(attempts):
        try:
            async with session.begin_nested():
                return await operation()
        except IntegrityError:
            if attempt == attempts - 1:
                raise
    raise AssertionError("unreachable")  # pragma: no cover
