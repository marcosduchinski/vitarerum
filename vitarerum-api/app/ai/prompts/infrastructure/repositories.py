from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.ai.prompts.domain.models import (
    PromptPurpose,
    PromptStatus,
    PromptTemplate,
    PromptTemplateId,
    PromptTemplateVersion,
    PromptTemplateVersionId,
)
from app.ai.prompts.domain.ports import PromptPublicationConflict
from app.ai.prompts.infrastructure.models import (
    PromptTemplateOrm,
    PromptTemplateVersionOrm,
)


def template_to_orm(template: PromptTemplate) -> PromptTemplateOrm:
    return PromptTemplateOrm(
        id=template.id,
        purpose=template.purpose.value,
        key=template.key,
        name=template.name,
        description=template.description,
        variables_schema_json=template.variables_schema_json,
        active_version_id=template.active_version_id,
        created_at=template.created_at,
    )


def template_to_domain(orm: PromptTemplateOrm) -> PromptTemplate:
    return PromptTemplate(
        id=PromptTemplateId(orm.id),
        purpose=PromptPurpose(orm.purpose),
        key=orm.key,
        name=orm.name,
        description=orm.description,
        variables_schema_json=orm.variables_schema_json,
        active_version_id=(
            PromptTemplateVersionId(orm.active_version_id)
            if orm.active_version_id
            else None
        ),
        created_at=orm.created_at,
    )


def version_to_orm(version: PromptTemplateVersion) -> PromptTemplateVersionOrm:
    return PromptTemplateVersionOrm(
        id=version.id,
        template_id=version.template_id,
        version=version.version,
        version_label=version.version_label,
        status=version.status.value,
        content=version.content,
        default_temperature=version.default_temperature,
        created_by=version.created_by,
        created_at=version.created_at,
        published_by=version.published_by,
        published_at=version.published_at,
        archived_at=version.archived_at,
    )


def version_to_domain(orm: PromptTemplateVersionOrm) -> PromptTemplateVersion:
    return PromptTemplateVersion(
        id=PromptTemplateVersionId(orm.id),
        template_id=PromptTemplateId(orm.template_id),
        version=orm.version,
        version_label=orm.version_label,
        status=PromptStatus(orm.status),
        content=orm.content,
        default_temperature=orm.default_temperature,
        created_by=orm.created_by,
        created_at=orm.created_at,
        published_by=orm.published_by,
        published_at=orm.published_at,
        archived_at=orm.archived_at,
    )


class SqlAlchemyPromptTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_template(
        self, purpose: PromptPurpose, key: str
    ) -> PromptTemplate | None:
        stmt = select(PromptTemplateOrm).where(
            PromptTemplateOrm.purpose == purpose.value,
            PromptTemplateOrm.key == key,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return template_to_domain(orm) if orm else None

    async def get_template_by_id(
        self, template_id: PromptTemplateId
    ) -> PromptTemplate | None:
        stmt = select(PromptTemplateOrm).where(PromptTemplateOrm.id == template_id)
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return template_to_domain(orm) if orm else None

    async def get_template_by_id_for_update(
        self, template_id: PromptTemplateId
    ) -> PromptTemplate | None:
        stmt = (
            select(PromptTemplateOrm)
            .where(PromptTemplateOrm.id == template_id)
            .with_for_update()
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return template_to_domain(orm) if orm else None

    async def list_templates(
        self,
        *,
        purpose: PromptPurpose | None = None,
        status: PromptStatus | None = None,
    ) -> list[PromptTemplate]:
        stmt = select(PromptTemplateOrm)
        if purpose is not None:
            stmt = stmt.where(PromptTemplateOrm.purpose == purpose.value)
        if status is not None:
            active_version = aliased(PromptTemplateVersionOrm)
            active_status = (
                select(active_version.status)
                .where(active_version.id == PromptTemplateOrm.active_version_id)
                .correlate(PromptTemplateOrm)
                .scalar_subquery()
            )
            latest_status = (
                select(PromptTemplateVersionOrm.status)
                .where(PromptTemplateVersionOrm.template_id == PromptTemplateOrm.id)
                .order_by(
                    PromptTemplateVersionOrm.version.desc(),
                    PromptTemplateVersionOrm.created_at.desc(),
                )
                .limit(1)
                .correlate(PromptTemplateOrm)
                .scalar_subquery()
            )
            stmt = stmt.where(
                func.coalesce(active_status, latest_status) == status.value
            )
        stmt = stmt.order_by(
            PromptTemplateOrm.purpose.asc(),
            PromptTemplateOrm.key.asc(),
        )
        orms = (await self._session.execute(stmt)).scalars().all()
        return [template_to_domain(orm) for orm in orms]

    async def get_version(
        self, version_id: PromptTemplateVersionId
    ) -> PromptTemplateVersion | None:
        stmt = select(PromptTemplateVersionOrm).where(
            PromptTemplateVersionOrm.id == version_id
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return version_to_domain(orm) if orm else None

    async def get_published_version(
        self, purpose: PromptPurpose, key: str
    ) -> PromptTemplateVersion | None:
        stmt = (
            select(PromptTemplateVersionOrm)
            .join(
                PromptTemplateOrm,
                PromptTemplateOrm.id == PromptTemplateVersionOrm.template_id,
            )
            .where(
                PromptTemplateOrm.purpose == purpose.value,
                PromptTemplateOrm.key == key,
                PromptTemplateVersionOrm.status == PromptStatus.PUBLISHED.value,
            )
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return version_to_domain(orm) if orm else None

    async def list_versions(
        self, template_id: PromptTemplateId
    ) -> list[PromptTemplateVersion]:
        stmt = (
            select(PromptTemplateVersionOrm)
            .where(PromptTemplateVersionOrm.template_id == template_id)
            .order_by(PromptTemplateVersionOrm.version.asc())
        )
        orms = (await self._session.execute(stmt)).scalars().all()
        return [version_to_domain(orm) for orm in orms]

    async def add_template(self, template: PromptTemplate) -> None:
        self._session.add(template_to_orm(template))
        await self._session.flush()

    async def add_version(self, version: PromptTemplateVersion) -> None:
        self._session.add(version_to_orm(version))
        await self._session.flush()

    async def save_template(self, template: PromptTemplate) -> None:
        await self._session.merge(template_to_orm(template))
        await self._session.flush()

    async def save_version(self, version: PromptTemplateVersion) -> None:
        try:
            await self._session.merge(version_to_orm(version))
            await self._session.flush()
        except IntegrityError as exc:
            raise PromptPublicationConflict(
                "Prompt publication conflicted with another concurrent change."
            ) from exc

    async def next_version_number(self, template_id: PromptTemplateId) -> int:
        stmt = select(func.max(PromptTemplateVersionOrm.version)).where(
            PromptTemplateVersionOrm.template_id == template_id
        )
        current = (await self._session.execute(stmt)).scalar_one()
        return (current or 0) + 1
