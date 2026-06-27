from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.identity.application.ports import UserFilters
from app.identity.application.use_cases import (
    AssignUserToGroup,
    CreateUser,
    GetUser,
    ListUsers,
    RemoveUserFromGroup,
)
from app.identity.domain.enums import GroupName
from app.identity.domain.models import GroupId, UserId
from app.identity.infrastructure.repositories import (
    SqlAlchemyGroupRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyUserRepository,
)
from app.identity.infrastructure.security import BcryptPasswordHasher
from app.identity.presentation.schemas import (
    CreateUserRequest,
    GroupMemberResponse,
    GroupResponse,
    GroupsListResponse,
    PaginatedGroupMembersResponse,
    PaginatedUsersResponse,
    PermissionDetail,
    UserDetailResponse,
    UserListItemResponse,
    UserPermissionsResponse,
    UserSummary,
)
from app.shared.authorization import require_group
from app.shared.dependencies import CallerPermission

users_router = APIRouter(prefix="/users", tags=["identity"])
groups_router = APIRouter(prefix="/groups", tags=["identity"])

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def _permission_detail(p: object) -> PermissionDetail:
    from app.identity.domain.models import Permission
    perm: Permission = p  # type: ignore[assignment]
    return PermissionDetail(
        permissionId=perm.id,
        user=UserSummary(
            id=perm.user.id if perm.user else "",
            name=perm.user.name if perm.user else "",
            email=perm.user.email if perm.user else "",
        ),
        group=perm.group.name if perm.group else "EXTERNAL",
    )


@users_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=UserDetailResponse,
)
async def create_user(
    body: CreateUserRequest,
    caller: CallerPermission,
    session: DBSession,
) -> UserDetailResponse:
    require_group(caller, GroupName.SYS_ADMIN)
    user_repo = SqlAlchemyUserRepository(session)
    try:
        user = await CreateUser(user_repo, BcryptPasswordHasher()).execute(
            name=body.name, email=body.email, password=body.password
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "EMAIL_ALREADY_EXISTS",
                "message": "A user with this email already exists",
            },
        ) from exc
    return UserDetailResponse(
        id=user.id, name=user.name, email=user.email, permissions=[]
    )


@users_router.get("", response_model=PaginatedUsersResponse)
async def list_users(
    caller: CallerPermission,
    session: DBSession,
    group_id: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedUsersResponse:
    # require_group(caller, GroupName.SYS_ADMIN)
    # Temporary measure: non-sysadmins may list users. This might change later.
    user_repo = SqlAlchemyUserRepository(session)
    perm_repo = SqlAlchemyPermissionRepository(session)

    users, total = await ListUsers(user_repo).execute(
        UserFilters(group_id=group_id, search=search), page, size
    )
    items = []
    for u in users:
        perms = await perm_repo.get_by_user_id(UserId(u.id))
        items.append(
            UserListItemResponse(
                id=u.id,
                name=u.name,
                email=u.email,
                permissions=[_permission_detail(p) for p in perms],
            )
        )
    return PaginatedUsersResponse(
        content=items,
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@users_router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: str,
    caller: CallerPermission,
    session: DBSession,
) -> UserDetailResponse:
    # require_group(caller, GroupName.SYS_ADMIN)
    # TODO: for now sysadmin is not required to view user details; may change later.
    user_repo = SqlAlchemyUserRepository(session)
    perm_repo = SqlAlchemyPermissionRepository(session)

    user = await GetUser(user_repo).execute(UserId(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "USER_NOT_FOUND",
                "message": f"No user found with id {user_id}",
            },
        )
    perms = await perm_repo.get_by_user_id(UserId(user_id))
    return UserDetailResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        permissions=[_permission_detail(p) for p in perms],
    )


@users_router.post(
    "/{user_id}/groups/{group_id}",
    status_code=status.HTTP_201_CREATED,
)
async def assign_user_to_group(
    user_id: str,
    group_id: str,
    caller: CallerPermission,
    session: DBSession,
) -> dict[str, object]:
    require_group(caller, GroupName.SYS_ADMIN)
    user_repo = SqlAlchemyUserRepository(session)
    group_repo = SqlAlchemyGroupRepository(session)
    perm_repo = SqlAlchemyPermissionRepository(session)

    try:
        permission, created = await AssignUserToGroup(
            user_repo, group_repo, perm_repo
        ).execute(UserId(user_id), GroupId(group_id))
    except LookupError as exc:
        error_code = (
            "USER_NOT_FOUND"
            if "user" in str(exc).lower()
            else "GROUP_NOT_FOUND"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": error_code, "message": str(exc)},
        ) from exc

    if created:
        try:
            await session.commit()
        except IntegrityError as exc:
            # Lost a concurrent race: the (user, group) permission already exists.
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "PERMISSION_ALREADY_EXISTS",
                    "message": "User is already assigned to this group",
                },
            ) from exc

    return {
        "permissionId": permission.id,
        "user": {
            "id": permission.user.id if permission.user else user_id,
            "name": permission.user.name if permission.user else "",
            "email": permission.user.email if permission.user else "",
        },
        "group": {
            "id": permission.group_id,
            "name": permission.group.name if permission.group else "",
        },
    }


@users_router.delete(
    "/{user_id}/groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_user_from_group(
    user_id: str,
    group_id: str,
    caller: CallerPermission,
    session: DBSession,
) -> None:
    require_group(caller, GroupName.SYS_ADMIN)
    perm_repo = SqlAlchemyPermissionRepository(session)
    try:
        await RemoveUserFromGroup(perm_repo).execute(UserId(user_id), GroupId(group_id))
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PERMISSION_NOT_FOUND", "message": str(exc)},
        ) from exc
    await session.commit()


@users_router.get("/{user_id}/permissions", response_model=UserPermissionsResponse)
async def get_user_permissions(
    user_id: str,
    caller: CallerPermission,
    session: DBSession,
) -> UserPermissionsResponse:
    require_group(caller, GroupName.SYS_ADMIN)
    perm_repo = SqlAlchemyPermissionRepository(session)
    perms = await perm_repo.get_by_user_id(UserId(user_id))
    return UserPermissionsResponse(
        userId=user_id,
        permissions=[_permission_detail(p) for p in perms],
    )


@groups_router.get("", response_model=GroupsListResponse)
async def list_groups(
    caller: CallerPermission,
    session: DBSession,
) -> GroupsListResponse:
    group_repo = SqlAlchemyGroupRepository(session)
    groups = await group_repo.list()
    return GroupsListResponse(
        groups=[GroupResponse(id=g.id, name=g.name) for g in groups]
    )


@groups_router.get("/{group_id}/users", response_model=PaginatedGroupMembersResponse)
async def list_group_users(
    group_id: str,
    caller: CallerPermission,
    session: DBSession,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedGroupMembersResponse:
    require_group(caller, GroupName.SYS_ADMIN)
    group_repo = SqlAlchemyGroupRepository(session)
    perm_repo = SqlAlchemyPermissionRepository(session)

    group = await group_repo.get_by_id(GroupId(group_id))
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "GROUP_NOT_FOUND",
                "message": f"No group found with id {group_id}",
            },
        )

    perms, total = await perm_repo.get_by_group_id(GroupId(group_id), page, size)
    return PaginatedGroupMembersResponse(
        group=GroupResponse(id=group.id, name=group.name),
        content=[
            GroupMemberResponse(
                permissionId=p.id,
                user=UserSummary(
                    id=p.user.id if p.user else "",
                    name=p.user.name if p.user else "",
                    email=p.user.email if p.user else "",
                ),
            )
            for p in perms
        ],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )
