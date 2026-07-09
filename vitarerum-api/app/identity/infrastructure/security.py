"""Password hashing (bcrypt) and access-token issuing/validation (JWT)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings


class TokenError(Exception):
    """Raised when an access token is missing, malformed, or expired."""


class BcryptPasswordHasher:
    """Implements the ``PasswordHasher`` port using bcrypt."""

    def hash(self, plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    def verify(self, plain: str, hashed: str) -> bool:
        if not hashed:
            return False
        try:
            return bcrypt.checkpw(plain.encode(), hashed.encode())
        except ValueError:
            # Stored value is not a valid bcrypt hash.
            return False


def create_access_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@dataclass(slots=True, frozen=True)
class DecodedAccessToken:
    """The claims callers need: who the token is for, and when it was issued
    (so session invalidation can reject tokens minted before a password
    change/reset — see ``password_changed_at`` on ``User``)."""

    user_id: str
    issued_at: datetime


def decode_access_token(token: str) -> DecodedAccessToken:
    """Return the subject and issued-at instant for a valid token, else raise
    ``TokenError``."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenError("Token is missing a subject claim")
    issued_at = payload.get("iat")
    if not isinstance(issued_at, int):
        raise TokenError("Token is missing an iat claim")
    return DecodedAccessToken(
        user_id=subject, issued_at=datetime.fromtimestamp(issued_at, tz=UTC)
    )
