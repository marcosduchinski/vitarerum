"""Advisory lock held across a whole investigation.

The scheduled pipeline uses ``pg_try_advisory_xact_lock``, which is released at
commit. That is wrong here: the cycle commits between every step, so a
transaction-scoped lock would be dropped before the first external call and
protect nothing. This uses the session-scoped ``pg_try_advisory_lock`` and
releases it explicitly, so the lock spans the entire cycle including the time
spent waiting on a model or a source.

Non-blocking on purpose. Two staff members starting the same investigation
should get an immediate, explicable refusal rather than a request that hangs
until the other one finishes.
"""

from __future__ import annotations

import logging
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class InvestigationLocked(RuntimeError):
    """Another cycle already holds the lock for this target."""


class PostgresInvestigationLock:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._key: str | None = None

    async def acquire(self, key: str) -> None:
        acquired = bool(
            (
                await self._session.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                    {"key": key},
                )
            ).scalar_one()
        )
        if not acquired:
            raise InvestigationLocked(
                f"Another investigation is already running for {key}"
            )
        self._key = key

    async def release(self) -> None:
        if self._key is None:
            return
        try:
            await self._session.execute(
                text("SELECT pg_advisory_unlock(hashtext(:key))"),
                {"key": self._key},
            )
        except Exception:
            # A lost session releases the lock anyway; failing to unlock must
            # not mask the outcome of the investigation itself.
            logger.warning("Could not release the lock for %s", self._key)
        finally:
            self._key = None

    async def __aenter__(self) -> PostgresInvestigationLock:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.release()


class NullInvestigationLock:
    """No-op lock, for tests and for anything that is not Postgres."""

    async def acquire(self, key: str) -> None:
        return None

    async def release(self) -> None:
        return None
