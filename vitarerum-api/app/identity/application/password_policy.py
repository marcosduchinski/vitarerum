"""Single password policy shared by every flow that sets a user's password:
``CreateUser``, ``ChangeOwnPassword``, reset confirmation and the eventual
administrative reset. Centralised so none of those flows can drift apart
(e.g. a SYS_ADMIN creating an account with a weaker password than self-service
allows)."""

from __future__ import annotations

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class WeakPassword(ValueError):
    """Raised when a password fails the minimum policy."""


def validate_password_policy(password: str) -> None:
    if not password.strip():
        raise WeakPassword("Password cannot be empty or made only of whitespace")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long"
        )
