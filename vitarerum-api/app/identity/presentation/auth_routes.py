from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.identity.application.use_cases import AuthenticateUser, InvalidCredentials
from app.identity.domain.models import InstitutionId
from app.identity.infrastructure.repositories import (
    SqlAlchemyInstitutionRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyUserRepository,
)
from app.identity.infrastructure.security import (
    BcryptPasswordHasher,
    create_access_token,
)
from app.identity.presentation.schemas import (
    AuthPermission,
    AuthUser,
    InstitutionSummary,
    LoginRequest,
    LoginResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


@auth_router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, session: DBSession) -> LoginResponse:
    user_repo = SqlAlchemyUserRepository(session)
    perm_repo = SqlAlchemyPermissionRepository(session)

    try:
        user, permissions = await AuthenticateUser(
            user_repo, perm_repo, BcryptPasswordHasher()
        ).execute(email=body.email, password=body.password)
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid email or password"},
        ) from None

    # Resolve the acting institution via the principal's group. Single-institution
    # today, so any group resolves to the same one; first hydrated group wins.
    institution: InstitutionSummary | None = None
    acting_group = next((p.group for p in permissions if p.group), None)
    if acting_group is not None:
        record = await SqlAlchemyInstitutionRepository(session).get_by_id(
            InstitutionId(acting_group.institution_id)
        )
        if record is not None:
            institution = InstitutionSummary(id=record.id, name=record.name)

    return LoginResponse(
        accessToken=create_access_token(user.id),
        user=AuthUser(id=user.id, email=user.email, displayName=user.name),
        permissions=[
            AuthPermission(
                permissionId=p.id,
                group=p.group.name if p.group else "EXTERNAL",
            )
            for p in permissions
        ],
        institution=institution,
    )
