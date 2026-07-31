from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.public_submission.application.use_cases import (
    CaptchaFailed,
    CaptchaUnavailable,
    ConfirmPublicProposal,
    RateLimitExceeded,
    SubmitPublicProposal,
    SubmitPublicProposalInput,
    UploadedDocument,
)
from app.public_submission.domain.models import (
    PendingPublicSubmission,
    PendingSubmissionStatus,
)
from app.shared.kernel import UseType
from app.use_of_collections.domain.enums import SubmissionChannel

_NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


class FakeRepo:
    def __init__(self) -> None:
        self.by_token: dict[str, PendingPublicSubmission] = {}

    async def add(self, submission: PendingPublicSubmission) -> None:
        self.by_token[submission.token] = submission

    async def get_by_token(self, token: str) -> PendingPublicSubmission | None:
        return self.by_token.get(token)

    async def get_by_token_for_update(
        self, token: str
    ) -> PendingPublicSubmission | None:
        return self.by_token.get(token)

    async def save(self, submission: PendingPublicSubmission) -> None:
        self.by_token[submission.token] = submission

    async def delete(self, submission: PendingPublicSubmission) -> None:
        self.by_token.pop(submission.token, None)


async def _passthrough_retry(op):  # type: ignore[no-untyped-def]
    return await op()


class FakeCaptcha:
    def __init__(self, ok: bool = True, error: Exception | None = None) -> None:
        self._ok = ok
        self._error = error

    async def verify(self, token: str, remote_ip: str) -> bool:
        if self._error is not None:
            raise self._error
        return self._ok


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


class FakeStorage:
    def __init__(self, fail_on_save: bool = False) -> None:
        self.fail_on_save = fail_on_save
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, content: bytes, file_reference: str) -> str:
        if self.fail_on_save:
            raise RuntimeError("storage failed")
        self.saved[file_reference] = content
        return file_reference

    async def delete(self, file_reference: str) -> None:
        self.deleted.append(file_reference)
        self.saved.pop(file_reference, None)


def _submit_input(**overrides: object) -> SubmitPublicProposalInput:
    data = {
        "citizen_name": "Pedro Silva",
        "citizen_email": "pedro@example.test",
        "subject": "Acesso à coleção",
        "body": "Gostaria de estudar um espécime.",
        "use_type": UseType.IN_SITU_VISIT,
        "consent": True,
        "captcha_token": "tok",
        "website": "",
        "remote_ip": "203.0.113.1",
        "proposed_begin_date": date(2026, 7, 1),
        "proposed_end_date": date(2026, 7, 15),
        "documents": [UploadedDocument(file_name="support.pdf", content=b"%PDF-1.4\n")],
    }
    data.update(overrides)
    return SubmitPublicProposalInput(**data)  # type: ignore[arg-type]


def _submit_use_case(
    repo: FakeRepo,
    *,
    captcha: FakeCaptcha | None = None,
    limiter: FakeRateLimiter | None = None,
    storage: FakeStorage | None = None,
) -> SubmitPublicProposal:
    return SubmitPublicProposal(
        repository=repo,
        captcha=captcha or FakeCaptcha(),
        rate_limiter=limiter or FakeRateLimiter(),
        clock=FakeClock(),
        file_storage=storage or FakeStorage(),
    )


# ── submit ─────────────────────────────────────────────────────────────────────


async def test_happy_path_stores_pending_and_returns_token() -> None:
    repo = FakeRepo()
    use_case = _submit_use_case(repo)

    out = await use_case.execute(_submit_input())

    assert out.email == "pedro@example.test"
    assert len(repo.by_token) == 1
    submission = next(iter(repo.by_token.values()))
    assert submission.status is PendingSubmissionStatus.PENDING_CONFIRMATION
    assert len(submission.documents) == 1
    assert submission.documents[0].file_name == "support.pdf"
    assert submission.documents[0].file_reference.startswith("public-submissions/")
    # The use case no longer sends e-mail itself; it returns the token + name so
    # the route can dispatch the confirmation only after it commits (bug #2).
    assert out.token == submission.token
    assert out.name == "Pedro Silva"


async def test_honeypot_accepts_and_drops() -> None:
    repo = FakeRepo()
    storage = FakeStorage()
    use_case = _submit_use_case(repo, storage=storage)

    out = await use_case.execute(_submit_input(website="http://spam.example"))

    assert out.email == "pedro@example.test"
    assert out.token is None  # nothing to send
    assert repo.by_token == {}  # no work
    assert storage.saved == {}


async def test_rate_limited_raises() -> None:
    repo = FakeRepo()
    use_case = _submit_use_case(repo, limiter=FakeRateLimiter(block_prefix="ip:"))

    with pytest.raises(RateLimitExceeded) as exc:
        await use_case.execute(_submit_input())
    assert exc.value.retry_after == 60
    assert repo.by_token == {}


async def test_captcha_failure_raises() -> None:
    repo = FakeRepo()
    use_case = _submit_use_case(repo, captcha=FakeCaptcha(ok=False))

    with pytest.raises(CaptchaFailed):
        await use_case.execute(_submit_input())
    assert repo.by_token == {}


async def test_captcha_unavailable_raises() -> None:
    repo = FakeRepo()
    use_case = _submit_use_case(
        repo, captcha=FakeCaptcha(error=RuntimeError("network down"))
    )

    with pytest.raises(CaptchaUnavailable):
        await use_case.execute(_submit_input())
    assert repo.by_token == {}


async def test_submit_deletes_saved_files_when_persistence_fails() -> None:
    class FailingRepo(FakeRepo):
        async def add(self, submission: PendingPublicSubmission) -> None:
            raise RuntimeError("database failed")

    storage = FakeStorage()
    use_case = _submit_use_case(FailingRepo(), storage=storage)

    with pytest.raises(RuntimeError, match="database failed"):
        await use_case.execute(_submit_input())

    assert storage.saved == {}
    assert len(storage.deleted) == 1


# ── confirm ────────────────────────────────────────────────────────────────────


class FakeSubmitProposal:
    def __init__(self, reference: str = "VRP-20260626-0007") -> None:
        self._reference = reference
        self.calls: list[Any] = []

    async def execute(self, data: object) -> SimpleNamespace:
        self.calls.append(data)
        return SimpleNamespace(
            proposal=SimpleNamespace(
                id="proposal-1",
                reference_number=SimpleNamespace(value=self._reference)
            ),
            conversation_id="conv-1",
        )


def _confirm_use_case(
    repo: FakeRepo,
    submit: FakeSubmitProposal | None = None,
    *,
    storage: FakeStorage | None = None,
    ) -> ConfirmPublicProposal:
    return ConfirmPublicProposal(
        repository=repo,
        submit_proposal=submit or FakeSubmitProposal(),  # type: ignore[arg-type]
        rate_limiter=FakeRateLimiter(),
        clock=FakeClock(),
        token_ttl=timedelta(hours=24),
        retry_runner=_passthrough_retry,
        file_storage=storage or FakeStorage(),
    )


async def _seed_pending(
    repo: FakeRepo, *, created_at: datetime = _NOW, **overrides: object
) -> str:
    use_case = _submit_use_case(repo)
    await use_case.execute(_submit_input(**overrides))
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
    token = await _seed_pending(
        repo,
        proposed_begin_date=date(2026, 7, 1),
        proposed_end_date=date(2026, 7, 15),
    )
    submit = FakeSubmitProposal(reference="VRP-20260626-0009")

    result = await _confirm_use_case(repo, submit).execute(token, "203.0.113.1")

    assert result.status == "CONFIRMED"
    assert result.reference_number == "VRP-20260626-0009"
    assert len(submit.calls) == 1
    # The citizen's intended use is carried into the materialised proposal.
    assert submit.calls[0].intended_use == UseType.IN_SITU_VISIT
    assert submit.calls[0].submission_channel == SubmissionChannel.PUBLIC
    # As are the dates the citizen proposed.
    assert submit.calls[0].begin_date == date(2026, 7, 1)
    assert submit.calls[0].end_date == date(2026, 7, 15)
    assert submit.calls[0].requested_by is None
    assert submit.calls[0].requester_contact.name == "Pedro Silva"
    assert submit.calls[0].requester_contact.email.value == "pedro@example.test"
    assert submit.calls[0].initial_message_sender == "pedro@example.test"
    assert len(submit.calls[0].documents) == 1
    assert submit.calls[0].documents[0].type.value == "PUBLIC_SUBMISSION"
    assert submit.calls[0].documents[0].file_name == "support.pdf"
    assert submit.calls[0].documents[0].submitted_by is None
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


async def test_confirm_expired_token_reclaims_files_and_row() -> None:
    repo = FakeRepo()
    token = await _seed_pending(repo, created_at=_NOW - timedelta(hours=25))
    file_reference = repo.by_token[token].documents[0].file_reference
    storage = FakeStorage()

    result = await _confirm_use_case(repo, storage=storage).execute(
        token, "203.0.113.1"
    )

    assert result.status == "EXPIRED"
    # The dead link's files and pending row are reclaimed on discovery, rather
    # than lingering until a (still-needed) bulk purge job runs.
    assert token not in repo.by_token
    assert storage.deleted == [file_reference]


async def test_confirm_rate_limited_raises() -> None:
    repo = FakeRepo()
    token = await _seed_pending(repo)
    use_case = ConfirmPublicProposal(
        repository=repo,
        submit_proposal=FakeSubmitProposal(),  # type: ignore[arg-type]
        rate_limiter=FakeRateLimiter(block_prefix="confirm-ip:"),
        clock=FakeClock(),
        token_ttl=timedelta(hours=24),
        retry_runner=_passthrough_retry,
        file_storage=FakeStorage(),
    )

    with pytest.raises(RateLimitExceeded):
        await use_case.execute(token, "203.0.113.1")


# ── #1: confirm resolves the pending row through the locking read ───────────────


async def test_confirm_uses_locking_read() -> None:
    # Bug #1: the confirm path must read the pending row with a row lock so two
    # concurrent confirmations cannot both materialise. Prove it goes through
    # get_by_token_for_update (not the plain get_by_token) by making the plain
    # read blind.
    repo = FakeRepo()
    token = await _seed_pending(repo)

    async def _blind(_token: str) -> None:
        raise AssertionError("confirm must use get_by_token_for_update")

    repo.get_by_token = _blind  # type: ignore[assignment,method-assign]

    result = await _confirm_use_case(repo).execute(token, "203.0.113.1")
    assert result.status == "CONFIRMED"


# ── #4: confirm retries a reference-number unique conflict ──────────────────────


class FlakySubmitProposal:
    """Raises IntegrityError on the first materialisation, then succeeds — the
    sequential MAX+1 reference-number race the retry runner must absorb."""

    def __init__(self, reference: str = "VRP-20260626-0011") -> None:
        self._reference = reference
        self.calls = 0

    async def execute(self, data: object) -> SimpleNamespace:
        self.calls += 1
        if self.calls == 1:
            raise IntegrityError("INSERT proposals", {}, Exception("duplicate ref"))
        return SimpleNamespace(
            proposal=SimpleNamespace(
                id="proposal-1",
                reference_number=SimpleNamespace(value=self._reference)
            ),
            conversation_id="conv-1",
        )


async def _retry_on_integrity(op, attempts: int = 3):  # type: ignore[no-untyped-def]
    for attempt in range(attempts):
        try:
            return await op()
        except IntegrityError:
            if attempt == attempts - 1:
                raise


async def test_confirm_retries_reference_number_conflict() -> None:
    repo = FakeRepo()
    token = await _seed_pending(repo)
    submit = FlakySubmitProposal()
    use_case = ConfirmPublicProposal(
        repository=repo,
        submit_proposal=submit,  # type: ignore[arg-type]
        rate_limiter=FakeRateLimiter(),
        clock=FakeClock(),
        token_ttl=timedelta(hours=24),
        retry_runner=_retry_on_integrity,  # type: ignore[arg-type]
        file_storage=FakeStorage(),
    )

    result = await use_case.execute(token, "203.0.113.1")

    assert result.status == "CONFIRMED"
    assert result.reference_number == "VRP-20260626-0011"
    assert submit.calls == 2  # first conflicted, retry succeeded
    assert repo.by_token[token].status is PendingSubmissionStatus.CONFIRMED
