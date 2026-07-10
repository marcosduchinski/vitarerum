"""LoggingPasswordEmailSender must never leak the raw reset token, even to
local/dev logs (plano-gestao-passwords.md objective 4)."""

import logging

import pytest

from app.identity.infrastructure.email import LoggingPasswordEmailSender


async def test_logging_sender_never_logs_the_raw_reset_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sender = LoggingPasswordEmailSender("http://localhost:4200", "/reset-password")
    raw_token = "super-secret-raw-token-value"

    with caplog.at_level(logging.DEBUG):
        await sender.send_password_reset("alice@x.org", "Alice", raw_token)

    assert raw_token not in caplog.text
    assert "alice@x.org" in caplog.text
