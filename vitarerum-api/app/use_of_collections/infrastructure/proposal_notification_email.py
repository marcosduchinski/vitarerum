from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.shared.email_templates import (
    proposal_assigned_email,
    proposal_forwarded_email,
)

logger = logging.getLogger(__name__)


class LoggingProposalNotificationEmailSender:
    async def send_proposal_forwarded(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        forwarded_by_name: str,
        note: str | None,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] proposal %s forwarded to %s by %s "
            "(link: %s, note: %s)",
            proposal_reference,
            to_email,
            forwarded_by_name,
            link,
            note,
        )

    async def send_proposal_assigned(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        assigned_by_name: str,
        note: str | None,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] proposal %s assigned to %s by %s "
            "(link: %s, note: %s)",
            proposal_reference,
            to_email,
            assigned_by_name,
            link,
            note,
        )


class SmtpProposalNotificationEmailSender:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_address: str,
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_address
        self._use_tls = use_tls

    async def send_proposal_forwarded(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        forwarded_by_name: str,
        note: str | None,
        link: str,
    ) -> None:
        template = proposal_forwarded_email(
            recipient_name=recipient_name,
            proposal_reference=proposal_reference,
            forwarded_by_name=forwarded_by_name,
            note=note,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

    async def send_proposal_assigned(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        assigned_by_name: str,
        note: str | None,
        link: str,
    ) -> None:
        template = proposal_assigned_email(
            recipient_name=recipient_name,
            proposal_reference=proposal_reference,
            assigned_by_name=assigned_by_name,
            note=note,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

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
