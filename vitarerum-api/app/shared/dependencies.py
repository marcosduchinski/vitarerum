from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.identity.public import (
    Actor,
    PermissionId,
    TokenError,
    UserStatus,
    decode_access_token,
    get_permission_reader,
)

# auto_error=False so a missing/malformed header reaches our own 401 handler
# (with the contract's body) instead of FastAPI's default 403.
_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"message": message},
    )


def _forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"message": message},
    )


async def get_caller_permission(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
    x_permission_id: Annotated[str | None, Header(alias="X-Permission-Id")] = None,
) -> Actor:
    # 1. Authenticate the bearer token. A 401 here logs the user out (session expiry).
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing or malformed Authorization header")
    token = credentials.credentials.strip()
    try:
        decoded = decode_access_token(token)
    except TokenError:
        raise _unauthorized("Invalid or expired token") from None

    # 2. The acting role is named by X-Permission-Id. Problems here are 403, not 401:
    #    the token is valid, the user simply may not act as that permission.
    if not x_permission_id:
        raise _forbidden("Missing X-Permission-Id header")
    view = await get_permission_reader(session).get_detail(
        PermissionId(x_permission_id)
    )
    if view is None or view.user.id != decoded.user_id:
        raise _forbidden("Permission does not belong to the authenticated user")
    if view.user.status is UserStatus.DISABLED:
        raise _unauthorized("Invalid or expired token")
    # A password change/reset bumps password_changed_at; tokens minted before
    # that instant are stale sessions, not merely expired ones — same 401 as
    # an invalid token so a stolen bearer token stops working once the owner
    # reacts (docs/plans/plano-gestao-passwords.md).
    #
    # JWT `iat` only has whole-second resolution (PyJWT truncates it on
    # encode), while password_changed_at keeps microseconds. Comparing the two
    # as-is with `<=` made a token minted in the very same wall-clock second
    # as the change — e.g. the fresh login the client is told to perform right
    # after a reset — spuriously "stale" until the next second ticked over.
    # Flooring changed_at to whole seconds before comparing, with a strict
    # `<`, matches iat's own resolution: a token can't be proven to predate a
    # change that landed in the same second, so it's treated as valid. That
    # leaves a sub-second race in principle (an attacker's token minted in
    # that exact same second would also pass), which is an inherent limit of
    # second-granularity `iat` — not one this comparison can resolve either
    # way.
    changed_at = view.user.password_changed_at
    if changed_at is not None and decoded.issued_at < changed_at.replace(microsecond=0):
        raise _unauthorized("Invalid or expired token")
    return Actor(
        id=PermissionId(view.permission_id),
        group=view.group,
        email=view.user.email,
    )


CallerPermission = Annotated[Actor, Depends(get_caller_permission)]
