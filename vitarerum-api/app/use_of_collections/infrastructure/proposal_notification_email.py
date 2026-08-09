from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.shared.email_templates import (
    project_cancelled_email,
    project_completed_email,
    project_started_email,
    proposal_approved_email,
    proposal_assigned_email,
    proposal_corrections_submitted_email,
    proposal_documents_submitted_email,
    proposal_forwarded_email,
    proposal_rejected_email,
    proposal_submitted_email,
    proposal_taken_over_email,
)

logger = logging.getLogger(__name__)


class LoggingProposalNotificationEmailSender:
    async def send_proposal_submitted(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        submitted_by_name: str,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] proposal %s submitted; notifying %s by %s (link: %s)",
            proposal_reference,
            to_email,
            submitted_by_name,
            link,
        )

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

    async def send_proposal_taken_over(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        taken_over_by_name: str,
        note: str | None,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] proposal %s taken over from %s by %s "
            "(link: %s, note: %s)",
            proposal_reference,
            to_email,
            taken_over_by_name,
            link,
            note,
        )

    async def send_proposal_documents_submitted(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        submitted_by_name: str,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] proposal %s documents submitted; "
            "notifying %s by %s (link: %s)",
            proposal_reference,
            to_email,
            submitted_by_name,
            link,
        )

    async def send_proposal_corrections_submitted(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        submitted_by_name: str,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] proposal %s corrections submitted; "
            "notifying %s by %s (link: %s)",
            proposal_reference,
            to_email,
            submitted_by_name,
            link,
        )

    async def send_proposal_rejected(
        self,
        *,
        to_email: str,
        requester_name: str,
        proposal_reference: str,
        rejected_by_name: str,
        reason: str,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] proposal %s rejected; notifying %s by %s "
            "(link: %s, reason: %s)",
            proposal_reference,
            to_email,
            rejected_by_name,
            link,
            reason,
        )

    async def send_proposal_approved(
        self,
        *,
        to_email: str,
        requester_name: str,
        proposal_reference: str,
        project_reference: str,
        approved_by_name: str,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] proposal %s approved as project %s; "
            "notifying %s by %s (link: %s)",
            proposal_reference,
            project_reference,
            to_email,
            approved_by_name,
            link,
        )

    async def send_project_started(
        self,
        *,
        to_email: str,
        requester_name: str,
        project_reference: str,
        started_by_name: str,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] project %s started; notifying %s by %s (link: %s)",
            project_reference,
            to_email,
            started_by_name,
            link,
        )

    async def send_project_cancelled(
        self,
        *,
        to_email: str,
        requester_name: str,
        project_reference: str,
        cancelled_by_name: str,
        reason: str,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] project %s cancelled; notifying %s by %s "
            "(link: %s, reason: %s)",
            project_reference,
            to_email,
            cancelled_by_name,
            link,
            reason,
        )

    async def send_project_completed(
        self,
        *,
        to_email: str,
        requester_name: str,
        project_reference: str,
        completed_by_name: str,
        link: str,
    ) -> None:
        logger.info(
            "[use-of-collections] project %s completed; notifying %s by %s (link: %s)",
            project_reference,
            to_email,
            completed_by_name,
            link,
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

    async def send_proposal_submitted(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        submitted_by_name: str,
        link: str,
    ) -> None:
        template = proposal_submitted_email(
            recipient_name=recipient_name,
            proposal_reference=proposal_reference,
            submitted_by_name=submitted_by_name,
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

    async def send_proposal_taken_over(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        taken_over_by_name: str,
        note: str | None,
        link: str,
    ) -> None:
        template = proposal_taken_over_email(
            recipient_name=recipient_name,
            proposal_reference=proposal_reference,
            taken_over_by_name=taken_over_by_name,
            note=note,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

    async def send_proposal_documents_submitted(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        submitted_by_name: str,
        link: str,
    ) -> None:
        template = proposal_documents_submitted_email(
            recipient_name=recipient_name,
            proposal_reference=proposal_reference,
            submitted_by_name=submitted_by_name,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

    async def send_proposal_corrections_submitted(
        self,
        *,
        to_email: str,
        recipient_name: str,
        proposal_reference: str,
        submitted_by_name: str,
        link: str,
    ) -> None:
        template = proposal_corrections_submitted_email(
            recipient_name=recipient_name,
            proposal_reference=proposal_reference,
            submitted_by_name=submitted_by_name,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

    async def send_proposal_rejected(
        self,
        *,
        to_email: str,
        requester_name: str,
        proposal_reference: str,
        rejected_by_name: str,
        reason: str,
        link: str,
    ) -> None:
        template = proposal_rejected_email(
            requester_name=requester_name,
            proposal_reference=proposal_reference,
            rejected_by_name=rejected_by_name,
            reason=reason,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

    async def send_proposal_approved(
        self,
        *,
        to_email: str,
        requester_name: str,
        proposal_reference: str,
        project_reference: str,
        approved_by_name: str,
        link: str,
    ) -> None:
        template = proposal_approved_email(
            requester_name=requester_name,
            proposal_reference=proposal_reference,
            project_reference=project_reference,
            approved_by_name=approved_by_name,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

    async def send_project_started(
        self,
        *,
        to_email: str,
        requester_name: str,
        project_reference: str,
        started_by_name: str,
        link: str,
    ) -> None:
        template = project_started_email(
            requester_name=requester_name,
            project_reference=project_reference,
            started_by_name=started_by_name,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

    async def send_project_cancelled(
        self,
        *,
        to_email: str,
        requester_name: str,
        project_reference: str,
        cancelled_by_name: str,
        reason: str,
        link: str,
    ) -> None:
        template = project_cancelled_email(
            requester_name=requester_name,
            project_reference=project_reference,
            cancelled_by_name=cancelled_by_name,
            reason=reason,
            link=link,
        )
        await self._send(to_email, template.subject, template.body)

    async def send_project_completed(
        self,
        *,
        to_email: str,
        requester_name: str,
        project_reference: str,
        completed_by_name: str,
        link: str,
    ) -> None:
        template = project_completed_email(
            requester_name=requester_name,
            project_reference=project_reference,
            completed_by_name=completed_by_name,
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
