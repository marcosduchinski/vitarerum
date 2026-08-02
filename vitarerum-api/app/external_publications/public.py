"""External-publications published language for downstream contexts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.external_publications.domain.models import (
    ExternalPublicationResourceType,
    ExternalPublicationStatus,
)
from app.shared.kernel import PermissionId

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def revoke_publications_for_resource(
    session: AsyncSession,
    *,
    resource_type: ExternalPublicationResourceType,
    resource_id: str,
    revoked_by: PermissionId,
) -> int:
    """Revoke all currently published external publications for one resource."""
    from app.external_publications.application.ports import PublicationFilters
    from app.external_publications.infrastructure.clock import SystemClock
    from app.external_publications.infrastructure.repositories import (
        SqlAlchemyExternalPublicationRepository,
    )

    repository = SqlAlchemyExternalPublicationRepository(session)
    clock = SystemClock()
    revoked_count = 0
    size = 100
    while True:
        publications, _total = await repository.list(
            PublicationFilters(
                resource_type=resource_type,
                resource_id=resource_id,
                status=ExternalPublicationStatus.PUBLISHED,
            ),
            0,
            size,
        )
        if not publications:
            break
        for publication in publications:
            publication.revoke(revoked_by=revoked_by, now=clock.now())
            await repository.save(publication)
            revoked_count += 1
    return revoked_count


__all__ = [
    "ExternalPublicationResourceType",
    "revoke_publications_for_resource",
]
