from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.public_submission.application.use_cases import (
    CaptchaFailed,
    CaptchaUnavailable,
    ConfirmPublicProposal,
    RateLimitExceeded,
    SubmitPublicProposal,
    SubmitPublicProposalInput,
)
from app.public_submission.domain.models import (
    PendingPublicSubmission,
    PendingSubmissionStatus,
)

_NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


class FakeRepo:
    def __init__(self) -> None:
        self.by_token: dict[str, PendingPublicSubmission] = {}

    async def add(self, submission: PendingPublicSubmission) -> None:
        self.by_token[submission.token] = submission

    async def get_by_token(self, token: str) -> PendingPublicSubmission | None:
        return self.by_token.get(token)

    async def save(self, submission: PendingPublicSubmission) -> None:
        self.by_token[submission.token] = submission


class FakeCaptcha:
    def __init__(self, ok: bool = True, error: Exception | None = None) -> None:
        self._ok = ok
        self._error = error

    async def verify(self, token: str, remote_ip: str) -> bool:
        if self._error is not None:
            raise self._error
        return self._ok


class FakeEmail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to_email: str, citizen_name: str, token: str) -> None:
        self.sent.append((to_email, citizen_name, token))


class FakeRateLimiter:
    def __init__(self, block_prefix: str | None = None) -> None:
        self._block_prefix = block_prefix
        self.calls: list[str] = []

    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        self.calls.append(key)
        return self._block_prefix is not None and key.startswith(self._block_prefix)


class FakeClock:
    def __init__(self, now: datetime = _NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _submit_input(**overrides: object) -> SubmitPublicProposalInput:
    data = {
        "citizen_name": "Pedro Silva",
        "citizen_email": "pedro@example.test",
        "subject": "Acesso à coleção",
        "body": "Gostaria de estudar um espécime.",
        "consent": True,
        "captcha_token": "tok",
        "website": "",
        "remote_ip": "203.0.113.1",
    }
    data.update(overrides)
    return SubmitPublicProposalInput(**data)  # type: ignore[arg-type]


def _submit_use_case(
    repo: FakeRepo,
    *,
    captcha: FakeCaptcha | None = None,
    email: FakeEmail | None = None,
    limiter: FakeRateLimiter | None = None,
) -> tuple[SubmitPublicProposal, FakeEmail]:
    email = email or FakeEmail()
    use_case = SubmitPublicProposal(
        repository=repo,
        captcha=captcha or FakeCaptcha(),
        email_sender=email,
        rate_limiter=limiter or FakeRateLimiter(),
        clock=FakeClock(),
    )
    return use_case, email


# ── submit ─────────────────────────────────────────────────────────────────────


async def test_happy_path_stores_pending_and_sends_email() -> None:
    repo = FakeRepo()
    use_case, email = _submit_use_case(repo)

    out = await use_case.execute(_submit_input())

    assert out.email == "pedro@example.test"
    assert len(repo.by_token) == 1
    submission = next(iter(repo.by_token.values()))
    assert submission.status is PendingSubmissionStatus.PENDING_CONFIRMATION
    assert email.sent == [("pedro@example.test", "Pedro Silva", submission.token)]


async def test_honeypot_accepts_and_drops() -> None:
    repo = FakeRepo()
    use_case, email = _submit_use_case(repo)

    out = await use_case.execute(_submit_input(website="http://spam.example"))

    assert out.email == "pedro@example.test"
    assert repo.by_token == {}  # no work
    assert email.sent == []


async def test_rate_limited_raises() -> None:
    repo = FakeRepo()
    use_case, email = _submit_use_case(
        repo, limiter=FakeRateLimiter(block_prefix="ip:")
    )

    with pytest.raises(RateLimitExceeded) as exc:
        await use_case.execute(_submit_input())
    assert exc.value.retry_after == 60
    assert repo.by_token == {}
    assert email.sent == []


async def test_captcha_failure_raises() -> None:
    repo = FakeRepo()
    use_case, email = _submit_use_case(repo, captcha=FakeCaptcha(ok=False))

    with pytest.raises(CaptchaFailed):
        await use_case.execute(_submit_input())
    assert repo.by_token == {}
    assert email.sent == []


async def test_captcha_unavailable_raises() -> None:
    repo = FakeRepo()
    use_case, _ = _submit_use_case(
        repo, captcha=FakeCaptcha(error=RuntimeError("network down"))
    )

    with pytest.raises(CaptchaUnavailable):
        await use_case.execute(_submit_input())
    assert repo.by_token == {}


# ── confirm ────────────────────────────────────────────────────────────────────


class FakeProvision:
    async def execute(self, email: str, name: str) -> SimpleNamespace:
        return SimpleNamespace(
            actor=SimpleNamespace(id="perm-ext", email=email), user_created=True
        )


class FakeSubmitProposal:
    def __init__(self, reference: str = "VRP-20260626-0007") -> None:
        self._reference = reference
        self.calls: list[object] = []

    async def execute(self, data: object) -> SimpleNamespace:
        self.calls.append(data)
        return SimpleNamespace(
            proposal=SimpleNamespace(
                reference_number=SimpleNamespace(value=self._reference)
            ),
            conversation_id="conv-1",
        )


def _confirm_use_case(
    repo: FakeRepo, submit: FakeSubmitProposal | None = None
) -> ConfirmPublicProposal:
    return ConfirmPublicProposal(
        repository=repo,
        provision_requester=FakeProvision(),  # type: ignore[arg-type]
        submit_proposal=submit or FakeSubmitProposal(),  # type: ignore[arg-type]
        rate_limiter=FakeRateLimiter(),
        clock=FakeClock(),
        token_ttl=timedelta(hours=24),
    )


async def _seed_pending(repo: FakeRepo, *, created_at: datetime = _NOW) -> str:
    use_case, _ = _submit_use_case(repo)
    await use_case.execute(_submit_input())
    submission = next(iter(repo.by_token.values()))
    submission.created_at = created_at
    return submission.token


async def test_confirm_unknown_token_is_invalid() -> None:
    repo = FakeRepo()
    result = await _confirm_use_case(repo).execute("nope", "203.0.113.1")
    assert result.status == "INVALID"
    assert result.reference_number is None


async def test_confirm_materialises_proposal() -> None:
    repo = FakeRepo()
    token = await _seed_pending(repo)
    submit = FakeSubmitProposal(reference="VRP-20260626-0009")

    result = await _confirm_use_case(repo, submit).execute(token, "203.0.113.1")

    assert result.status == "CONFIRMED"
    assert result.reference_number == "VRP-20260626-0009"
    assert len(submit.calls) == 1
    assert repo.by_token[token].status is PendingSubmissionStatus.CONFIRMED


async def test_confirm_twice_is_already_confirmed() -> None:
    repo = FakeRepo()
    token = await _seed_pending(repo)
    use_case = _confirm_use_case(repo)

    first = await use_case.execute(token, "203.0.113.1")
    second = await use_case.execute(token, "203.0.113.1")

    assert first.status == "CONFIRMED"
    assert second.status == "ALREADY_CONFIRMED"
    assert second.reference_number == first.reference_number


async def test_confirm_expired_token() -> None:
    repo = FakeRepo()
    token = await _seed_pending(repo, created_at=_NOW - timedelta(hours=25))

    result = await _confirm_use_case(repo).execute(token, "203.0.113.1")

    assert result.status == "EXPIRED"
    assert repo.by_token[token].status is PendingSubmissionStatus.PENDING_CONFIRMATION


async def test_confirm_rate_limited_raises() -> None:
    repo = FakeRepo()
    token = await _seed_pending(repo)
    use_case = ConfirmPublicProposal(
        repository=repo,
        provision_requester=FakeProvision(),  # type: ignore[arg-type]
        submit_proposal=FakeSubmitProposal(),  # type: ignore[arg-type]
        rate_limiter=FakeRateLimiter(block_prefix="confirm-ip:"),
        clock=FakeClock(),
        token_ttl=timedelta(hours=24),
    )

    with pytest.raises(RateLimitExceeded):
        await use_case.execute(token, "203.0.113.1")
