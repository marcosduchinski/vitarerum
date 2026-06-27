"""Permission hydration for responses, via Identity's published PermissionReader.

Replaces the old infrastructure/hydration.py: presentation consumes Identity
read models and maps them to the local PermissionDetail schema (the JSON
contract is unchanged).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.public import PermissionView, get_permission_reader
from app.shared.kernel import PermissionId
from app.use_of_collections.presentation.schemas import PermissionDetail, UserSummary


def permission_detail_from_view(view: PermissionView) -> PermissionDetail:
    return PermissionDetail(
        permissionId=view.permission_id,
        user=UserSummary(
            id=view.user.id,
            name=view.user.name,
            email=view.user.email,
        ),
        group=view.group,
    )


async def hydrate_permission(
    permission_id: PermissionId,
    session: AsyncSession,
) -> PermissionDetail | None:
    view = await get_permission_reader(session).get_detail(permission_id)
    if view is None:
        return None
    return permission_detail_from_view(view)


async def hydrate_permission_or_stub(
    permission_id: PermissionId | None,
    session: AsyncSession,
) -> PermissionDetail | None:
    if permission_id is None:
        return None
    return await hydrate_permission(permission_id, session)
