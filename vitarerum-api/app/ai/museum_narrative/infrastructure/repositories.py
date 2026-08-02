"""SQLAlchemy repository for the generated-narrative aggregate.

Append-only: each generation is one row, read back by id or listed per in-situ
visit record (newest first).
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_narrative.domain.models import (
    GeneratedNarrative,
    GeneratedNarrativeRevision,
    NarrativeFactSnapshot,
    NarrativeFactSnapshotId,
    NarrativeId,
    NarrativeRevisionId,
    NarrativeType,
    ResolutionSource,
)
from app.ai.museum_narrative.domain.validation import (
    NarrativeFinding,
    NarrativeFindingCode,
)
from app.ai.museum_narrative.infrastructure.models import (
    GeneratedNarrativeOrm,
    GeneratedNarrativeRevisionOrm,
    NarrativeFactSnapshotOrm,
)
from app.shared.kernel import PermissionId


def facts_snapshot_to_orm(snapshot: NarrativeFactSnapshot) -> NarrativeFactSnapshotOrm:
    return NarrativeFactSnapshotOrm(
        id=snapshot.id,
        record_id=snapshot.record_id,
        payload_json=snapshot.payload_json,
        payload_hash=snapshot.payload_hash,
        builder_version=snapshot.builder_version,
        prompt_version=snapshot.prompt_version,
        created_at=snapshot.created_at,
        cidoc_document_json=snapshot.cidoc_document_json,
        cidoc_validation_report=snapshot.cidoc_validation_report,
        cidoc_conforms=snapshot.cidoc_conforms,
    )


def facts_snapshot_to_domain(orm: NarrativeFactSnapshotOrm) -> NarrativeFactSnapshot:
    return NarrativeFactSnapshot(
        id=NarrativeFactSnapshotId(orm.id),
        record_id=orm.record_id,
        payload_json=orm.payload_json,
        payload_hash=orm.payload_hash,
        builder_version=orm.builder_version,
        prompt_version=orm.prompt_version,
        created_at=orm.created_at,
        cidoc_document_json=orm.cidoc_document_json,
        cidoc_validation_report=orm.cidoc_validation_report,
        cidoc_conforms=orm.cidoc_conforms,
    )


def revision_to_orm(
    revision: GeneratedNarrativeRevision,
) -> GeneratedNarrativeRevisionOrm:
    return GeneratedNarrativeRevisionOrm(
        id=revision.id,
        narrative_id=revision.narrative_id,
        previous_narrative=revision.previous_narrative,
        revised_narrative=revision.revised_narrative,
        created_at=revision.created_at,
        edited_by=str(revision.edited_by) if revision.edited_by else None,
    )


def revision_to_domain(
    orm: GeneratedNarrativeRevisionOrm,
) -> GeneratedNarrativeRevision:
    return GeneratedNarrativeRevision(
        id=NarrativeRevisionId(orm.id),
        narrative_id=NarrativeId(orm.narrative_id),
        previous_narrative=orm.previous_narrative,
        revised_narrative=orm.revised_narrative,
        created_at=orm.created_at,
        edited_by=PermissionId(orm.edited_by) if orm.edited_by else None,
    )


def findings_to_json(findings: list[NarrativeFinding]) -> list[dict[str, str]]:
    return [
        {
            "code": finding.code.value,
            "message": finding.message,
            "evidence": finding.evidence,
        }
        for finding in findings
    ]


def findings_to_domain(items: list[dict[str, str]] | None) -> list[NarrativeFinding]:
    return [
        NarrativeFinding(
            code=NarrativeFindingCode(item["code"]),
            message=item["message"],
            evidence=item["evidence"],
        )
        for item in (items or [])
    ]


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
        facts_snapshot_id=narrative.facts_snapshot_id,
        prompt_version_id=narrative.prompt_version_id,
        prompt_version=narrative.prompt_version,
        model_response_hash=narrative.model_response_hash,
        validation_conforms=narrative.validation_conforms,
        validation_findings=findings_to_json(narrative.validation_findings),
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
        facts_snapshot_id=(
            NarrativeFactSnapshotId(orm.facts_snapshot_id)
            if orm.facts_snapshot_id
            else None
        ),
        prompt_version_id=orm.prompt_version_id,
        prompt_version=orm.prompt_version,
        model_response_hash=orm.model_response_hash,
        validation_conforms=orm.validation_conforms,
        validation_findings=findings_to_domain(orm.validation_findings),
    )


class SqlAlchemyNarrativeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_facts_snapshot(self, snapshot: NarrativeFactSnapshot) -> None:
        self._session.add(facts_snapshot_to_orm(snapshot))
        await self._session.flush()

    async def get_facts_snapshot(
        self, snapshot_id: NarrativeFactSnapshotId
    ) -> NarrativeFactSnapshot | None:
        stmt = select(NarrativeFactSnapshotOrm).where(
            NarrativeFactSnapshotOrm.id == snapshot_id
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return facts_snapshot_to_domain(orm) if orm else None

    async def add(self, narrative: GeneratedNarrative) -> None:
        self._session.add(narrative_to_orm(narrative))
        await self._session.flush()

    async def save(self, narrative: GeneratedNarrative) -> None:
        await self._session.merge(narrative_to_orm(narrative))
        await self._session.flush()

    async def add_revision(self, revision: GeneratedNarrativeRevision) -> None:
        self._session.add(revision_to_orm(revision))
        await self._session.flush()

    async def delete(self, narrative_id: NarrativeId) -> bool:
        narrative = await self.get_by_id(narrative_id)
        if narrative is None:
            return False

        await self._session.execute(
            delete(GeneratedNarrativeRevisionOrm).where(
                GeneratedNarrativeRevisionOrm.narrative_id == narrative_id
            )
        )
        await self._session.execute(
            delete(GeneratedNarrativeOrm).where(
                GeneratedNarrativeOrm.id == narrative_id
            )
        )
        if narrative.facts_snapshot_id is not None:
            await self._session.execute(
                delete(NarrativeFactSnapshotOrm).where(
                    NarrativeFactSnapshotOrm.id == narrative.facts_snapshot_id
                )
            )
        await self._session.flush()
        return True

    async def _with_snapshot(self, narrative: GeneratedNarrative) -> GeneratedNarrative:
        if narrative.facts_snapshot_id is None:
            return narrative
        narrative.facts_snapshot = await self.get_facts_snapshot(
            narrative.facts_snapshot_id
        )
        return narrative

    async def get_by_id(self, narrative_id: NarrativeId) -> GeneratedNarrative | None:
        stmt = select(GeneratedNarrativeOrm).where(
            GeneratedNarrativeOrm.id == narrative_id
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        if orm is None:
            return None
        return await self._with_snapshot(narrative_to_domain(orm))

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
        narratives = [
            await self._with_snapshot(narrative_to_domain(orm)) for orm in orms
        ]
        return narratives, total

    async def list_revisions(
        self, record_id: str, narrative_id: NarrativeId, page: int, size: int
    ) -> tuple[list[GeneratedNarrativeRevision], int] | None:
        narrative = await self.get_by_id(narrative_id)
        if narrative is None or narrative.record_id != record_id:
            return None
        count_stmt = (
            select(func.count())
            .select_from(GeneratedNarrativeRevisionOrm)
            .where(GeneratedNarrativeRevisionOrm.narrative_id == narrative_id)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            select(GeneratedNarrativeRevisionOrm)
            .where(GeneratedNarrativeRevisionOrm.narrative_id == narrative_id)
            .order_by(GeneratedNarrativeRevisionOrm.created_at.asc())
            .offset(page * size)
            .limit(size)
        )
        orms = (await self._session.execute(data_stmt)).scalars().all()
        return [revision_to_domain(orm) for orm in orms], total
