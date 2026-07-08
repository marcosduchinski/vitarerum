"""E-mail adapters for :class:`RequesterAccessEmailSender`.

Notifies a newly provisioned external requester (a public proposal approved
for the first time) of their login e-mail and temporary password. There is no
password-reset flow yet, so this is the only way that requester can log in —
see ``ApproveProposal`` and ``ProvisionExternalRequester``.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

logger = logging.getLogger(__name__)


def _access_created_body(
    requester_name: str, login_url: str, temporary_password: str
) -> str:
    return (
        f"Olá {requester_name},\n\n"
        "A sua proposta foi aprovada e criámos um acesso à sua área pessoal "
        "no Vitarerum.\n\n"
        f"Link de acesso: {login_url}\n"
        f"Senha provisória: {temporary_password}\n\n"
        "Recomendamos que altere esta senha assim que possível."
    )


class LoggingRequesterAccessEmailSender:
    """Logs the credentials instead of sending. Local/dev only."""

    async def send_access_created(
        self,
        to_email: str,
        requester_name: str,
        login_url: str,
        temporary_password: str,
    ) -> None:
        logger.info(
            "[use-of-collections] access credentials for %s: %s (login: %s)",
            to_email,
            temporary_password,
            login_url,
        )


class SmtpRequesterAccessEmailSender:
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

    async def send_access_created(
        self,
        to_email: str,
        requester_name: str,
        login_url: str,
        temporary_password: str,
    ) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to_email
        message["Subject"] = "O seu acesso à área pessoal do Vitarerum"
        message.set_content(
            _access_created_body(requester_name, login_url, temporary_password)
        )
        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            start_tls=self._use_tls,
        )
