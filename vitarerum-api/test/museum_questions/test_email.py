from email.message import EmailMessage

import pytest

from app.museum_questions.infrastructure.email import (
    SmtpMuseumQuestionEmailSender,
    _answer_html_body,
    _answer_text_body,
)


def test_answer_text_body_turns_allowed_html_into_readable_text() -> None:
    result = _answer_text_body(
        "Ana",
        "<p>Catalogue references found:</p>"
        "<ul><li><strong>Meteorito Allende</strong><br>"
        "Meteorites - rows.xlsx</li></ul>",
    )

    assert "<ul>" not in result
    assert "<li>" not in result
    assert "Olá Ana" in result
    assert "Catalogue references found:" in result
    assert "- Meteorito Allende" in result
    assert "Meteorites - rows.xlsx" in result
    assert result.endswith("Vitarerum")


def test_answer_html_body_keeps_allowed_markup_and_drops_unsafe_markup() -> None:
    result = _answer_html_body(
        "Ana <script>",
        '<p onclick="bad()">Safe</p>'
        "<script>alert(1)</script><img src=x>"
        "<ul><li><b>Hit</b></li></ul>",
    )

    assert "Olá Ana &lt;script&gt;" in result
    assert "<p>Safe</p>" in result
    assert "<script>" not in result
    assert "alert(1)" not in result
    assert "onclick" not in result
    assert "<img" not in result
    assert "<b>Hit</b>" in result


@pytest.mark.asyncio
async def test_smtp_answer_email_is_multipart_with_plain_and_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[EmailMessage] = []

    async def fake_send(message: EmailMessage, **kwargs: object) -> None:
        del kwargs
        sent.append(message)

    monkeypatch.setattr(
        "app.museum_questions.infrastructure.email.aiosmtplib.send",
        fake_send,
    )
    sender = SmtpMuseumQuestionEmailSender(
        host="smtp.example.org",
        port=587,
        username=None,
        password=None,
        from_address="museum@example.org",
    )

    await sender.send_answer(
        to_email="ana@example.org",
        requester_name="Ana",
        subject="Visit",
        answer_body="<p>Hello</p><ul><li><strong>Object</strong></li></ul>",
    )

    assert len(sent) == 1
    message = sent[0]
    assert message.is_multipart()
    plain = message.get_body(preferencelist=("plain",))
    html = message.get_body(preferencelist=("html",))
    assert plain is not None
    assert html is not None
    assert "<ul>" not in plain.get_content()
    assert "- Object" in plain.get_content()
    assert "<ul><li><strong>Object</strong></li></ul>" in html.get_content()
