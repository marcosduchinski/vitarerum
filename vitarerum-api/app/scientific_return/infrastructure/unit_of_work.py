"""Transaction boundary and clock adapters for the agentic cycle.

The cycle commits between external calls, so the commit belongs to the use case
rather than to the router. These adapters give it that ability without letting
it reach for a session.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyInvestigationUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(tz=UTC)
