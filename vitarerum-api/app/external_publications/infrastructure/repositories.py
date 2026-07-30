from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.external_publications.application.ports import PublicationFilters
from app.external_publications.domain.models import (
    ExternalPublication,
    ExternalPublicationAccess,
    ExternalPublicationAccessId,
    ExternalPublicationId,
)
from app.external_publications.infrastructure.models import (
    ExternalPublicationAccessOrm,
    ExternalPublicationOrm,
)
from app.shared.kernel import PermissionId


def publication_to_orm(publication: ExternalPublication) -> ExternalPublicationOrm:
    return ExternalPublicationOrm(
        id=publication.id,
        resource_type=publication.resource_type,
        resource_id=publication.resource_id,
        status=publication.status,
        access_mode=publication.access_mode,
        token_hash=publication.token_hash,
        integration_client_id=publication.integration_client_id,
        profile=publication.profile,
        expires_at=publication.expires_at,
        created_by=publication.created_by,
        created_at=publication.created_at,
        published_at=publication.published_at,
        revoked_by=publication.revoked_by,
        revoked_at=publication.revoked_at,
    )


def publication_to_domain(orm: ExternalPublicationOrm) -> ExternalPublication:
    return ExternalPublication(
        id=ExternalPublicationId(orm.id),
        resource_type=orm.resource_type,
        resource_id=orm.resource_id,
        status=orm.status,
        access_mode=orm.access_mode,
        profile=orm.profile,
        token_hash=orm.token_hash,
        integration_client_id=orm.integration_client_id,
        expires_at=orm.expires_at,
        created_by=PermissionId(orm.created_by),
        created_at=orm.created_at,
        published_at=orm.published_at,
        revoked_by=PermissionId(orm.revoked_by) if orm.revoked_by else None,
        revoked_at=orm.revoked_at,
    )


def access_to_orm(access: ExternalPublicationAccess) -> ExternalPublicationAccessOrm:
    return ExternalPublicationAccessOrm(
        id=access.id,
        publication_id=access.publication_id,
        accessed_at=access.accessed_at,
        access_mode=access.access_mode,
        integration_client_id=access.integration_client_id,
        remote_addr_hash=access.remote_addr_hash,
        user_agent=access.user_agent,
        outcome=access.outcome,
    )


def access_to_domain(orm: ExternalPublicationAccessOrm) -> ExternalPublicationAccess:
    return ExternalPublicationAccess(
        id=ExternalPublicationAccessId(orm.id),
        publication_id=(
            ExternalPublicationId(orm.publication_id)
            if orm.publication_id is not None
            else None
        ),
        accessed_at=orm.accessed_at,
        access_mode=orm.access_mode,
        integration_client_id=orm.integration_client_id,
        remote_addr_hash=orm.remote_addr_hash,
        user_agent=orm.user_agent,
        outcome=orm.outcome,
    )


class SqlAlchemyExternalPublicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, publication: ExternalPublication) -> None:
        self._session.add(publication_to_orm(publication))
        await self._session.flush()

    async def get_by_id(
        self, publication_id: ExternalPublicationId
    ) -> ExternalPublication | None:
        orm = await self._session.get(ExternalPublicationOrm, publication_id)
        return publication_to_domain(orm) if orm is not None else None

    async def get_by_token_hash(self, token_hash: str) -> ExternalPublication | None:
        stmt = select(ExternalPublicationOrm).where(
            ExternalPublicationOrm.token_hash == token_hash
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return publication_to_domain(orm) if orm is not None else None

    async def save(self, publication: ExternalPublication) -> None:
        orm = await self._session.get(ExternalPublicationOrm, publication.id)
        if orm is None:
            return
        orm.status = publication.status
        orm.revoked_by = publication.revoked_by
        orm.revoked_at = publication.revoked_at
        orm.expires_at = publication.expires_at
        await self._session.flush()

    async def list(
        self, filters: PublicationFilters, page: int, size: int
    ) -> tuple[list[ExternalPublication], int]:
        base_stmt = select(ExternalPublicationOrm)
        if filters.resource_type is not None:
            base_stmt = base_stmt.where(
                ExternalPublicationOrm.resource_type == filters.resource_type
            )
        if filters.resource_id:
            base_stmt = base_stmt.where(
                ExternalPublicationOrm.resource_id == filters.resource_id
            )
        if filters.status is not None:
            base_stmt = base_stmt.where(ExternalPublicationOrm.status == filters.status)
        if filters.profile is not None:
            base_stmt = base_stmt.where(
                ExternalPublicationOrm.profile == filters.profile
            )
        if filters.q:
            pattern = f"%{filters.q}%"
            base_stmt = base_stmt.where(
                or_(
                    ExternalPublicationOrm.id.ilike(pattern),
                    ExternalPublicationOrm.resource_id.ilike(pattern),
                )
            )

        total = (
            await self._session.execute(
                select(func.count()).select_from(base_stmt.subquery())
            )
        ).scalar_one()
        data_stmt = (
            base_stmt.order_by(ExternalPublicationOrm.created_at.desc())
            .offset(page * size)
            .limit(size)
        )
        orms = (await self._session.execute(data_stmt)).scalars().all()
        return [publication_to_domain(orm) for orm in orms], total


class SqlAlchemyExternalPublicationAccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, access: ExternalPublicationAccess) -> None:
        self._session.add(access_to_orm(access))
        await self._session.flush()

    async def list_by_publication(
        self, publication_id: ExternalPublicationId, page: int, size: int
    ) -> tuple[list[ExternalPublicationAccess], int]:
        base_stmt = select(ExternalPublicationAccessOrm).where(
            ExternalPublicationAccessOrm.publication_id == publication_id
        )
        total = (
            await self._session.execute(
                select(func.count()).select_from(base_stmt.subquery())
            )
        ).scalar_one()
        data_stmt = (
            base_stmt.order_by(ExternalPublicationAccessOrm.accessed_at.desc())
            .offset(page * size)
            .limit(size)
        )
        orms = (await self._session.execute(data_stmt)).scalars().all()
        return [access_to_domain(orm) for orm in orms], total
