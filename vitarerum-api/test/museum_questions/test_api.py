"""API tests for the public Museum Questions endpoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_async_session
from app.main import app
from app.museum_questions.application.use_cases import SubmitMuseumQuestion
from app.museum_questions.domain.models import MuseumQuestion
from app.museum_questions.presentation.dependencies import get_submit_use_case

_SUBMIT_URL = "/api/v1/public/museum-questions"
_NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class _Repo:
    def __init__(self) -> None:
        self.added: list[MuseumQuestion] = []

    async def add(self, question: MuseumQuestion) -> None:
        self.added.append(question)


class _Captcha:
    def __init__(self, ok: bool = True, raise_error: bool = False) -> None:
        self._ok = ok
        self._raise = raise_error

    async def verify(self, token: str, remote_ip: str) -> bool:
        if self._raise:
            raise RuntimeError("provider down")
        return self._ok


class _Limiter:
    def __init__(self, block: bool = False) -> None:
        self._block = block

    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        return self._block


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Session:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.committed = False
        self._fail_commit = fail_commit

    async def commit(self) -> None:
        if self._fail_commit:
            raise RuntimeError("commit failed")
        self.committed = True


@asynccontextmanager
async def _client(
    *,
    captcha_ok: bool = True,
    captcha_raises: bool = False,
    rate_limited: bool = False,
    fail_commit: bool = False,
) -> AsyncIterator[tuple[AsyncClient, _Repo]]:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(
        repository=repo,
        captcha=_Captcha(ok=captcha_ok, raise_error=captcha_raises),
        rate_limiter=_Limiter(block=rate_limited),
        clock=_Clock(),
    )
    app.dependency_overrides[get_submit_use_case] = lambda: use_case
    app.dependency_overrides[get_async_session] = lambda: _Session(
        fail_commit=fail_commit
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, repo
    finally:
        app.dependency_overrides.clear()


def _payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "requesterName": "Ana Souza",
        "requesterEmail": "ana@example.org",
        "subject": "Duvida sobre visita in situ",
        "message": "Gostaria de agendar uma visita para pesquisa.",
        "consent": True,
        "captchaToken": "token-123",
        "website": "",
    }
    data.update(overrides)
    return data


async def test_submit_returns_202_receipt() -> None:
    async with _client() as (client, repo):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 202
    assert resp.json() == {"status": "RECEIVED", "email": "ana@example.org"}
    assert len(repo.added) == 1
    assert repo.added[0].subject == "Duvida sobre visita in situ"
    assert repo.added[0].requester_name == "Ana Souza"


async def test_submit_missing_consent_is_rejected() -> None:
    async with _client() as (client, repo):
        resp = await client.post(_SUBMIT_URL, json=_payload(consent=False))
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_captcha_failure_403() -> None:
    async with _client(captcha_ok=False) as (client, repo):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 403
    assert resp.json()["message"] == "Captcha verification failed."
    assert repo.added == []


async def test_submit_captcha_unavailable_503() -> None:
    async with _client(captcha_raises=True) as (client, repo):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 503
    assert repo.added == []


async def test_submit_rate_limited_429_with_retry_after() -> None:
    async with _client(rate_limited=True) as (client, repo):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"
    assert repo.added == []


async def test_submit_honeypot_returns_202_no_work() -> None:
    async with _client() as (client, repo):
        resp = await client.post(_SUBMIT_URL, json=_payload(website="http://spam"))
    assert resp.status_code == 202
    assert repo.added == []


async def test_submit_sanitizes_control_characters_and_crlf() -> None:
    async with _client() as (client, repo):
        resp = await client.post(
            _SUBMIT_URL,
            json=_payload(requesterName="Ana\x00Souza", subject="Linha1\r\nLinha2"),
        )
    assert resp.status_code == 202
    question = repo.added[0]
    assert "\x00" not in question.requester_name
    assert "\r" not in question.subject
    assert "\n" not in question.subject


async def test_submit_whitespace_only_fields_are_rejected() -> None:
    # min_length=1 alone would accept "   " and let it collapse to "" after
    # the control-char/strip validator, silently persisting empty required
    # fields — this must 422 instead.
    async with _client() as (client, repo):
        resp = await client.post(
            _SUBMIT_URL,
            json=_payload(requesterName="   ", subject="   ", message="   "),
        )
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_missing_field_is_rejected() -> None:
    async with _client() as (client, repo):
        payload = _payload()
        del payload["subject"]
        resp = await client.post(_SUBMIT_URL, json=payload)
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_invalid_email_is_rejected() -> None:
    async with _client() as (client, repo):
        resp = await client.post(
            _SUBMIT_URL, json=_payload(requesterEmail="not-an-email")
        )
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_over_length_message_is_rejected() -> None:
    async with _client() as (client, repo):
        resp = await client.post(_SUBMIT_URL, json=_payload(message="x" * 4001))
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_commit_failure_propagates() -> None:
    async with _client(fail_commit=True) as (client, repo):
        with pytest.raises(RuntimeError):
            await client.post(_SUBMIT_URL, json=_payload())
    # The fake repo persisted in-memory before the (failed) commit — a real DB
    # session would roll this back; this only proves the route doesn't
    # swallow the commit error.
    assert len(repo.added) == 1
