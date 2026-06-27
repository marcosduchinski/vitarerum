from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.identity.public import (
    Actor,
    PermissionId,
    TokenError,
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
        user_id = decode_access_token(token)
    except TokenError:
        raise _unauthorized("Invalid or expired token") from None

    # 2. The acting role is named by X-Permission-Id. Problems here are 403, not 401:
    #    the token is valid, the user simply may not act as that permission.
    if not x_permission_id:
        raise _forbidden("Missing X-Permission-Id header")
    view = await get_permission_reader(session).get_detail(
        PermissionId(x_permission_id)
    )
    if view is None or view.user.id != user_id:
        raise _forbidden("Permission does not belong to the authenticated user")
    return Actor(
        id=PermissionId(view.permission_id),
        group=view.group,
        email=view.user.email,
    )


CallerPermission = Annotated[Actor, Depends(get_caller_permission)]
