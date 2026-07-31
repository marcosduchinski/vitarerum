from __future__ import annotations

from typing import Annotated

import aiosmtplib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.identity.application.password_policy import WeakPassword
from app.identity.application.use_cases import (
    AuthenticateUser,
    ChangeOwnPassword,
    IncorrectCurrentPassword,
    InvalidCredentials,
    InvalidOrExpiredResetToken,
    RateLimitExceeded,
)
from app.identity.domain.models import InstitutionId
from app.identity.infrastructure.clock import SystemClock
from app.identity.infrastructure.repositories import (
    SqlAlchemyInstitutionRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyUserRepository,
)
from app.identity.infrastructure.security import (
    BcryptPasswordHasher,
    create_access_token,
)
from app.identity.presentation.dependencies import (
    ConfirmPasswordResetUseCase,
    PasswordEmailSenderDep,
    RequestPasswordResetUseCase,
)
from app.identity.presentation.schemas import (
    AuthPermission,
    AuthUser,
    ChangePasswordRequest,
    InstitutionSummary,
    LoginRequest,
    LoginResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequestBody,
)
from app.shared.dependencies import CallerPermission

auth_router = APIRouter(prefix="/auth", tags=["auth"])

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited(exc: RateLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"message": str(exc)},
        headers={"Retry-After": str(exc.retry_after)},
    )


def _email_delivery_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "error": "EMAIL_DELIVERY_FAILED",
            "message": "Password reset email could not be delivered",
        },
    )


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


@auth_router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    caller: CallerPermission,
    session: DBSession,
    email_sender: PasswordEmailSenderDep,
) -> None:
    user_repo = SqlAlchemyUserRepository(session)
    try:
        user = await ChangeOwnPassword(
            user_repo, BcryptPasswordHasher(), SystemClock()
        ).execute(
            email=caller.email,
            current_password=body.currentPassword,
            new_password=body.newPassword,
        )
    except IncorrectCurrentPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INCORRECT_CURRENT_PASSWORD",
                "message": "Current password is incorrect",
            },
        ) from exc
    except WeakPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "WEAK_PASSWORD", "message": str(exc)},
        ) from exc
    await session.commit()
    # Notice sent only after commit, so a rolled-back write can't still notify.
    await email_sender.send_password_changed_notice(user.email, user.name)


@auth_router.post(
    "/password-reset/request", status_code=status.HTTP_204_NO_CONTENT
)
async def request_password_reset(
    body: PasswordResetRequestBody,
    request: Request,
    session: DBSession,
    use_case: RequestPasswordResetUseCase,
    email_sender: PasswordEmailSenderDep,
) -> None:
    try:
        outcome = await use_case.execute(
            email=body.email, remote_ip=_client_ip(request)
        )
    except RateLimitExceeded as exc:
        raise _rate_limited(exc) from exc
    await session.commit()
    # Always 204 regardless of whether the account exists, and no e-mail sent
    # for an unknown address — otherwise a prober could learn which accounts
    # exist from response content alone.
    if outcome is not None:
        try:
            await email_sender.send_password_reset(
                outcome.email, outcome.display_name, outcome.raw_token
            )
        except aiosmtplib.SMTPException as exc:
            raise _email_delivery_failed() from exc


@auth_router.post(
    "/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT
)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    request: Request,
    session: DBSession,
    use_case: ConfirmPasswordResetUseCase,
    email_sender: PasswordEmailSenderDep,
) -> None:
    try:
        user = await use_case.execute(
            raw_token=body.token,
            new_password=body.newPassword,
            remote_ip=_client_ip(request),
        )
    except RateLimitExceeded as exc:
        raise _rate_limited(exc) from exc
    except InvalidOrExpiredResetToken as exc:
        # Opaque 404: don't tell a probing client whether the token exists,
        # expired, or was already used (mirrors public_submission's amendment
        # token confirm).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Invalid or expired token"},
        ) from exc
    except WeakPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "WEAK_PASSWORD", "message": str(exc)},
        ) from exc
    await session.commit()
    await email_sender.send_password_changed_notice(user.email, user.name)
