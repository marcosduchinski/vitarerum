"""E-mail sender adapters for the Museum Questions response workflow."""

from __future__ import annotations

import logging
from email.message import EmailMessage
from html import escape, unescape
from html.parser import HTMLParser

import aiosmtplib

from app.shared.email_templates import (
    museum_question_answer_html_body,
    museum_question_answer_subject,
    museum_question_answer_text_body,
    museum_question_out_of_scope_email,
)

logger = logging.getLogger(__name__)

_ALLOWED_INLINE_TAGS = {"b", "em", "i", "strong"}
_ALLOWED_BLOCK_TAGS = {"br", "li", "ol", "p", "ul"}
_ALLOWED_TAGS = _ALLOWED_INLINE_TAGS | _ALLOWED_BLOCK_TAGS
_BLOCKED_CONTENT_TAGS = {"embed", "iframe", "link", "meta", "object", "script", "style"}


def _answer_body(requester_name: str, answer_body: str) -> str:
    return museum_question_answer_text_body(requester_name, answer_body)


class _AnswerHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_parts: list[str] = []
        self.text_parts: list[str] = []
        self._blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in _BLOCKED_CONTENT_TAGS:
            self._blocked_depth += 1
            return
        if self._blocked_depth:
            return
        if tag not in _ALLOWED_TAGS:
            return
        if tag in _ALLOWED_INLINE_TAGS:
            self.html_parts.append(f"<{tag}>")
        elif tag == "br":
            self.html_parts.append("<br>")
            self.text_parts.append("\n")
        elif tag == "li":
            self.html_parts.append("<li>")
            self._ensure_text_newline()
            self.text_parts.append("- ")
        else:
            self.html_parts.append(f"<{tag}>")
            self._ensure_text_newline()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _BLOCKED_CONTENT_TAGS and self._blocked_depth:
            self._blocked_depth -= 1
            return
        if self._blocked_depth:
            return
        if tag not in _ALLOWED_TAGS or tag == "br":
            return
        self.html_parts.append(f"</{tag}>")
        if tag in {"li", "ol", "p", "ul"}:
            self._ensure_text_newline()

    def handle_data(self, data: str) -> None:
        if self._blocked_depth:
            return
        self.html_parts.append(escape(data))
        self.text_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._blocked_depth:
            return
        text = f"&{name};"
        self.html_parts.append(text)
        self.text_parts.append(unescape(text))

    def handle_charref(self, name: str) -> None:
        if self._blocked_depth:
            return
        text = f"&#{name};"
        self.html_parts.append(text)
        self.text_parts.append(unescape(text))

    def _ensure_text_newline(self) -> None:
        if self.text_parts and not self.text_parts[-1].endswith("\n"):
            self.text_parts.append("\n")

    def html(self) -> str:
        return "".join(self.html_parts).strip()

    def text(self) -> str:
        lines = [line.rstrip() for line in "".join(self.text_parts).splitlines()]
        collapsed: list[str] = []
        previous_blank = False
        for line in lines:
            blank = not line.strip()
            if blank and previous_blank:
                continue
            collapsed.append(line)
            previous_blank = blank
        return "\n".join(collapsed).strip()


def _sanitize_answer_markup(answer_body: str) -> tuple[str, str]:
    parser = _AnswerHtmlParser()
    parser.feed(answer_body)
    parser.close()
    text = parser.text()
    html = parser.html()
    return text, html


def _answer_html_body(requester_name: str, answer_body: str) -> str:
    _text, sanitized_html = _sanitize_answer_markup(answer_body)
    return museum_question_answer_html_body(requester_name, sanitized_html)


def _answer_text_body(requester_name: str, answer_body: str) -> str:
    text, _html = _sanitize_answer_markup(answer_body)
    return _answer_body(requester_name, text)


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
        message["Subject"] = museum_question_answer_subject(subject)
        message.set_content(_answer_text_body(requester_name, answer_body))
        message.add_alternative(
            _answer_html_body(requester_name, answer_body),
            subtype="html",
        )
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
        template = museum_question_out_of_scope_email(subject)
        message["Subject"] = template.subject
        message.set_content(template.body)
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
