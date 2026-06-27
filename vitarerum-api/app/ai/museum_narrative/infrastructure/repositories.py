"""SQLAlchemy repository for the generated-narrative aggregate.

Append-only: each generation is one row, read back by id or listed per in-situ
visit record (newest first).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_narrative.domain.models import (
    GeneratedNarrative,
    NarrativeId,
    NarrativeType,
    ResolutionSource,
)
from app.ai.museum_narrative.infrastructure.models import GeneratedNarrativeOrm


def narrative_to_orm(narrative: GeneratedNarrative) -> GeneratedNarrativeOrm:
    return GeneratedNarrativeOrm(
        id=narrative.id,
        record_id=narrative.record_id,
        narrative=narrative.narrative,
        narrative_type=narrative.resolved_narrative_type.value,
        resolution_source=narrative.resolution_source.value,
        target_language=narrative.target_language,
        creativity_temperature=narrative.creativity_temperature,
        llm_model=narrative.llm_model,
        generated_at=narrative.generated_at,
    )


def narrative_to_domain(orm: GeneratedNarrativeOrm) -> GeneratedNarrative:
    return GeneratedNarrative(
        id=NarrativeId(orm.id),
        record_id=orm.record_id,
        narrative=orm.narrative,
        resolved_narrative_type=NarrativeType(orm.narrative_type),
        resolution_source=ResolutionSource(orm.resolution_source),
        target_language=orm.target_language,
        creativity_temperature=orm.creativity_temperature,
        llm_model=orm.llm_model,
        generated_at=orm.generated_at,
    )


class SqlAlchemyNarrativeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, narrative: GeneratedNarrative) -> None:
        self._session.add(narrative_to_orm(narrative))
        await self._session.flush()

    async def save(self, narrative: GeneratedNarrative) -> None:
        await self._session.merge(narrative_to_orm(narrative))
        await self._session.flush()

    async def get_by_id(self, narrative_id: NarrativeId) -> GeneratedNarrative | None:
        stmt = select(GeneratedNarrativeOrm).where(
            GeneratedNarrativeOrm.id == narrative_id
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return narrative_to_domain(orm) if orm else None

    async def list_by_record(
        self, record_id: str, page: int, size: int
    ) -> tuple[list[GeneratedNarrative], int]:
        count_stmt = (
            select(func.count())
            .select_from(GeneratedNarrativeOrm)
            .where(GeneratedNarrativeOrm.record_id == record_id)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            select(GeneratedNarrativeOrm)
            .where(GeneratedNarrativeOrm.record_id == record_id)
            .order_by(GeneratedNarrativeOrm.generated_at.desc())
            .offset(page * size)
            .limit(size)
        )
        orms = (await self._session.execute(data_stmt)).scalars().all()
        return [narrative_to_domain(orm) for orm in orms], total
