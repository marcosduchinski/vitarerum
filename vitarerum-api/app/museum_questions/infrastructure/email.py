"""E-mail sender adapters for the Museum Questions response workflow."""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

logger = logging.getLogger(__name__)

_OUT_OF_SCOPE_BODY = (
    "Obrigado por entrar em contato com o Vitarerum.\n\n"
    "Neste momento, o Pergunte ao Museu esta disponivel apenas para perguntas "
    "relacionadas ao uso de colecoes, especialmente visitas in situ para "
    "investigacao.\n\n"
    "Perguntas sobre exposicoes, emprestimos, eventos, atividades educativas "
    "ou outros servicos do museu ainda nao sao tratadas por este canal e "
    "serao disponibilizadas em uma versao futura.\n\n"
    "Agradecemos a compreensao."
)


def _answer_body(requester_name: str, answer_body: str) -> str:
    return f"Olá {requester_name},\n\n{answer_body}\n\nVitarerum"


class LoggingMuseumQuestionEmailSender:
    """Logs outgoing messages instead of sending. Local/dev only."""

    async def send_answer(
        self,
        *,
        to_email: str,
        requester_name: str,
        subject: str,
        answer_body: str,
    ) -> None:
        logger.info(
            "[museum-questions] answer e-mail for %s (%s): %s",
            to_email,
            subject,
            answer_body,
        )

    async def send_out_of_scope(
        self,
        *,
        to_email: str,
        requester_name: str,
        subject: str,
    ) -> None:
        logger.info(
            "[museum-questions] out-of-scope e-mail for %s (%s)",
            to_email,
            subject,
        )


class SmtpMuseumQuestionEmailSender:
    def __init__(
        self,
        *,
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

    async def send_answer(
        self,
        *,
        to_email: str,
        requester_name: str,
        subject: str,
        answer_body: str,
    ) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to_email
        message["Subject"] = f"Resposta do Vitarerum: {subject}"
        message.set_content(_answer_body(requester_name, answer_body))
        await self._send(message)

    async def send_out_of_scope(
        self,
        *,
        to_email: str,
        requester_name: str,
        subject: str,
    ) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to_email
        message["Subject"] = f"Pergunte ao Museu: {subject}"
        message.set_content(_OUT_OF_SCOPE_BODY)
        await self._send(message)

    async def _send(self, message: EmailMessage) -> None:
        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            start_tls=self._use_tls,
        )
