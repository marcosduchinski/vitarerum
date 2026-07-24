"""Password-reset e-mail adapters.

The reset link points at the frontend's reset route,
``{PUBLIC_ORIGIN}{PASSWORD_RESET_PUBLIC_PATH}?token=…`` (the page POSTs the
token back to ``/auth/password-reset/confirm``). ``SmtpPasswordEmailSender``
delivers via SMTP. Unlike the equivalent local/dev loggers in
``public_submission``/``museum_questions`` (which log their link, token
included), ``LoggingPasswordEmailSender`` deliberately never logs the raw
token — plano-gestao-passwords.md's objective 4 is unconditional ("nunca
armazenar nem logar passwords ou tokens de reset em claro") for this
specific feature. Testing the reset flow without SMTP configured therefore
requires reading the token from wherever the caller captured it (e.g. an
e-mail-sender test double), not from logs.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.shared.email_templates import (
    password_changed_email,
    password_reset_email,
)

logger = logging.getLogger(__name__)


def _reset_link(public_origin: str, public_path: str, token: str) -> str:
    return f"{public_origin}{public_path}?token={token}"


class LoggingPasswordEmailSender:
    """Logs the reset link / change notice instead of sending. Local/dev only."""

    def __init__(self, public_origin: str, public_path: str) -> None:
        self._origin = public_origin
        self._path = public_path

    async def send_password_reset(
        self, to_email: str, display_name: str, token: str
    ) -> None:
        del token  # never logged, even locally — see module docstring
        logger.info(
            "[identity] password reset requested for %s; SMTP_HOST is not "
            "configured so no link was delivered (the token is never logged)",
            to_email,
        )

    async def send_password_changed_notice(
        self, to_email: str, display_name: str
    ) -> None:
        logger.info("[identity] password changed notice for %s", to_email)


class SmtpPasswordEmailSender:
    def __init__(
        self,
        public_origin: str,
        public_path: str,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_address: str,
        use_tls: bool = True,
    ) -> None:
        self._origin = public_origin
        self._path = public_path
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_address
        self._use_tls = use_tls

    async def _send(self, to_email: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            start_tls=self._use_tls,
        )

    async def send_password_reset(
        self, to_email: str, display_name: str, token: str
    ) -> None:
        link = _reset_link(self._origin, self._path, token)
        template = password_reset_email(display_name, link)
        await self._send(
            to_email,
            template.subject,
            template.body,
        )

    async def send_password_changed_notice(
        self, to_email: str, display_name: str
    ) -> None:
        template = password_changed_email(display_name)
        await self._send(
            to_email,
            template.subject,
            template.body,
        )
