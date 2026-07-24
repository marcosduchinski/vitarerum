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

from app.shared.email_templates import (
    document_correction_invite_email,
    public_submission_confirmation_email,
)

logger = logging.getLogger(__name__)


def _confirm_link(public_origin: str, token: str) -> str:
    return f"{public_origin}/submit-proposal/confirm?token={token}"


def _amend_link(public_origin: str, token: str) -> str:
    return f"{public_origin}/submit-proposal/edit?token={token}"


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
        template = public_submission_confirmation_email(citizen_name, link)
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to_email
        message["Subject"] = template.subject
        message.set_content(template.body)
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
        template = document_correction_invite_email(citizen_name, link, reasons)
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to_email
        message["Subject"] = template.subject
        message.set_content(template.body)
        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            start_tls=self._use_tls,
        )
