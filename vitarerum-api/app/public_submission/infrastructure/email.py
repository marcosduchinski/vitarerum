"""Confirmation e-mail sender adapters.

The confirmation link points at the public SPA route
``/submit-proposal/confirm?token=…`` (the page POSTs the token back to
``/public/proposals/confirm``). ``SmtpConfirmationEmailSender`` delivers via
SMTP; ``LoggingConfirmationEmailSender`` logs the link for local/dev (matching
the reference impl's ``print``).
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

logger = logging.getLogger(__name__)


def _confirm_link(public_origin: str, token: str) -> str:
    return f"{public_origin}/submit-proposal/confirm?token={token}"


def _amend_link(public_origin: str, token: str) -> str:
    return f"{public_origin}/submit-proposal/edit?token={token}"


def _amend_body(citizen_name: str, link: str, reasons: list[str]) -> str:
    bullet_list = "\n".join(f"  - {reason}" for reason in reasons)
    reasons_block = f"\n\nDocumentos a corrigir:\n{bullet_list}" if reasons else ""
    return (
        f"Olá {citizen_name},\n\n"
        "A análise do seu pedido identificou documentos que precisam de "
        f"correção.{reasons_block}\n\n"
        "Para corrigir, aceda ao link abaixo (válido por tempo limitado):\n\n"
        f"{link}\n\n"
        "Se não foi você, ignore esta mensagem."
    )


class LoggingConfirmationEmailSender:
    """Logs the confirmation link instead of sending. Local/dev only."""

    def __init__(self, public_origin: str) -> None:
        self._origin = public_origin

    async def send(self, to_email: str, citizen_name: str, token: str) -> None:
        link = _confirm_link(self._origin, token)
        logger.info("[public-submission] confirmation link for %s: %s", to_email, link)

    async def send_amendment_invite(
        self,
        to_email: str,
        citizen_name: str,
        token: str,
        reasons: list[str],
    ) -> None:
        link = _amend_link(self._origin, token)
        logger.info("[public-submission] amendment link for %s: %s", to_email, link)


class SmtpConfirmationEmailSender:
    def __init__(
        self,
        public_origin: str,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_address: str,
        use_tls: bool = True,
    ) -> None:
        self._origin = public_origin
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_address
        self._use_tls = use_tls

    async def send(self, to_email: str, citizen_name: str, token: str) -> None:
        link = _confirm_link(self._origin, token)
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to_email
        message["Subject"] = "Confirme o seu pedido de acesso à coleção / "
        message.set_content(
            f"Olá {citizen_name},\n\n"
            "Para concluir o seu pedido, confirme através do link abaixo:\n\n"
            f"{link}\n\n"
            "Se não foi você, ignore esta mensagem."
        )
        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            start_tls=self._use_tls,
        )

    async def send_amendment_invite(
        self,
        to_email: str,
        citizen_name: str,
        token: str,
        reasons: list[str],
    ) -> None:
        link = _amend_link(self._origin, token)
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to_email
        message["Subject"] = "Correção de documentos do seu pedido"
        message.set_content(_amend_body(citizen_name, link, reasons))
        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            start_tls=self._use_tls,
        )
