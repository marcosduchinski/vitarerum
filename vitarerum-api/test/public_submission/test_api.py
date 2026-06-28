from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_async_session
from app.main import app
from app.public_submission.application.use_cases import (
    ConfirmPublicProposal,
    SubmitPublicProposal,
)
from app.public_submission.domain.models import PendingPublicSubmission
from app.public_submission.presentation.dependencies import (
    get_confirm_use_case,
    get_email_sender,
    get_submit_use_case,
)

_SUBMIT_URL = "/api/v1/public/proposals"
_CONFIRM_URL = "/api/v1/public/proposals/confirm"
_NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


class _Repo:
    def __init__(self) -> None:
        self.by_token: dict[str, PendingPublicSubmission] = {}

    async def add(self, s: PendingPublicSubmission) -> None:
        self.by_token[s.token] = s

    async def get_by_token(self, token: str) -> PendingPublicSubmission | None:
        return self.by_token.get(token)

    async def get_by_token_for_update(
        self, token: str
    ) -> PendingPublicSubmission | None:
        return self.by_token.get(token)

    async def save(self, s: PendingPublicSubmission) -> None:
        self.by_token[s.token] = s


class _Captcha:
    def __init__(self, ok: bool = True) -> None:
        self._ok = ok

    async def verify(self, token: str, remote_ip: str) -> bool:
        return self._ok


class _Email:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to_email: str, citizen_name: str, token: str) -> None:
        self.sent.append((to_email, citizen_name, token))


class _Limiter:
    def __init__(self, block: bool = False) -> None:
        self._block = block

    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        return self._block


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Provision:
    async def execute(self, email: str, name: str) -> SimpleNamespace:
        return SimpleNamespace(actor=SimpleNamespace(id="perm-ext", email=email))


class _Submit:
    async def execute(self, data: object) -> SimpleNamespace:
        return SimpleNamespace(
            proposal=SimpleNamespace(
                reference_number=SimpleNamespace(value="VRP-20260626-0007")
            ),
            conversation_id="conv-1",
        )


class _Session:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.committed = False
        self._fail_commit = fail_commit

    async def commit(self) -> None:
        if self._fail_commit:
            raise RuntimeError("commit failed")
        self.committed = True


async def _passthrough_retry(op):  # type: ignore[no-untyped-def]
    return await op()


@asynccontextmanager
async def _client(
    *, captcha_ok: bool = True, rate_limited: bool = False, fail_commit: bool = False
) -> AsyncIterator[tuple[AsyncClient, _Repo, _Email]]:
    repo = _Repo()
    email = _Email()
    limiter = _Limiter(block=rate_limited)
    submit_uc = SubmitPublicProposal(
        repository=repo,
        captcha=_Captcha(ok=captcha_ok),
        rate_limiter=limiter,
        clock=_Clock(),
    )
    confirm_uc = ConfirmPublicProposal(
        repository=repo,
        provision_requester=_Provision(),  # type: ignore[arg-type]
        submit_proposal=_Submit(),  # type: ignore[arg-type]
        rate_limiter=limiter,
        clock=_Clock(),
        token_ttl=timedelta(hours=24),
        retry_runner=_passthrough_retry,
    )
    app.dependency_overrides[get_submit_use_case] = lambda: submit_uc
    app.dependency_overrides[get_confirm_use_case] = lambda: confirm_uc
    app.dependency_overrides[get_email_sender] = lambda: email
    app.dependency_overrides[get_async_session] = lambda: _Session(
        fail_commit=fail_commit
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, repo, email
    finally:
        app.dependency_overrides.clear()


def _payload(**overrides: object) -> dict:
    data = {
        "citizenName": "Pedro Silva",
        "citizenEmail": "pedro@example.org",
        "subject": "Acesso à Coleção de Zoologia",
        "body": "Gostaria de estudar um espécime para a minha tese.",
        "consent": True,
        "captchaToken": "0.AbC-token",
        "website": "",
    }
    data.update(overrides)
    return data


async def test_submit_returns_202_receipt() -> None:
    async with _client() as (client, repo, email):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 202
    assert resp.json() == {
        "status": "PENDING_CONFIRMATION",
        "email": "pedro@example.org",
    }
    assert len(repo.by_token) == 1
    assert len(email.sent) == 1


async def test_submit_honeypot_returns_202_no_work() -> None:
    async with _client() as (client, repo, email):
        resp = await client.post(_SUBMIT_URL, json=_payload(website="http://spam"))
    assert resp.status_code == 202
    assert repo.by_token == {}
    assert email.sent == []


async def test_submit_captcha_failure_403() -> None:
    async with _client(captcha_ok=False) as (client, repo, _):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 403
    assert resp.json()["message"] == "Captcha verification failed."
    assert repo.by_token == {}


async def test_submit_rate_limited_429_with_retry_after() -> None:
    async with _client(rate_limited=True) as (client, _, _):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"


async def test_submit_missing_consent_is_rejected() -> None:
    async with _client() as (client, repo, _):
        resp = await client.post(_SUBMIT_URL, json=_payload(consent=False))
    assert resp.status_code == 422
    assert repo.by_token == {}


async def test_submit_then_confirm_flow() -> None:
    async with _client() as (client, repo, email):
        submitted = await client.post(_SUBMIT_URL, json=_payload())
        assert submitted.status_code == 202
        token = email.sent[0][2]

        confirmed = await client.post(_CONFIRM_URL, json={"token": token})
        assert confirmed.status_code == 200
        assert confirmed.json() == {
            "status": "CONFIRMED",
            "referenceNumber": "VRP-20260626-0007",
        }

        again = await client.post(_CONFIRM_URL, json={"token": token})
        assert again.status_code == 200
        assert again.json()["status"] == "ALREADY_CONFIRMED"


async def test_confirm_unknown_token_returns_200_invalid() -> None:
    async with _client() as (client, _, _):
        resp = await client.post(_CONFIRM_URL, json={"token": "nope"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "INVALID", "referenceNumber": None}


async def test_submit_does_not_email_when_commit_fails() -> None:
    # Bug #2: the confirmation e-mail must be sent only after the pending row is
    # durably committed. If the commit fails, the citizen must not receive a link
    # whose token was rolled back.
    async with _client(fail_commit=True) as (client, repo, email):
        with pytest.raises(RuntimeError):
            await client.post(_SUBMIT_URL, json=_payload())
        assert email.sent == []
