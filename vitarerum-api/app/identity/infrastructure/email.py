"""Password-reset e-mail adapters.

The reset link points at the frontend's reset route,
``{PUBLIC_ORIGIN}{PASSWORD_RESET_PUBLIC_PATH}?token=…`` (the page POSTs the
token back to ``/auth/password-reset/confirm``). ``SmtpPasswordEmailSender``
delivers via SMTP; ``LoggingPasswordEmailSender`` logs the link for
local/dev, matching the equivalent adapters in ``public_submission`` and
``museum_questions``.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

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
        link = _reset_link(self._origin, self._path, token)
        logger.info("[identity] password reset link for %s: %s", to_email, link)

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
        await self._send(
            to_email,
            "Redefinição de password",
            f"Olá {display_name},\n\n"
            "Recebemos um pedido para redefinir a sua password. Para "
            "continuar, aceda ao link abaixo (válido por tempo limitado):\n\n"
            f"{link}\n\n"
            "Se não foi você quem pediu, ignore esta mensagem — a sua "
            "password atual continua válida.",
        )

    async def send_password_changed_notice(
        self, to_email: str, display_name: str
    ) -> None:
        await self._send(
            to_email,
            "A sua password foi alterada",
            f"Olá {display_name},\n\n"
            "A password da sua conta Vitarerum acabou de ser alterada.\n\n"
            "Se foi você, pode ignorar esta mensagem. Se não foi, contacte o "
            "suporte o mais rápido possível.",
        )
