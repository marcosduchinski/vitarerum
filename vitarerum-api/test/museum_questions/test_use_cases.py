"""Unit tests for the SubmitMuseumQuestion use case."""

from datetime import UTC, datetime

import pytest

from app.museum_questions.application.use_cases import (
    CaptchaFailed,
    CaptchaUnavailable,
    RateLimitExceeded,
    SubmitMuseumQuestion,
    SubmitMuseumQuestionInput,
)
from app.museum_questions.domain.models import MuseumQuestion, MuseumQuestionStatus

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


def _input(**overrides: str) -> SubmitMuseumQuestionInput:
    data = {
        "requester_name": "Ana Souza",
        "requester_email": "ana@example.org",
        "subject": "Duvida sobre visita in situ",
        "message": "Gostaria de agendar uma visita para pesquisa.",
        "captcha_token": "token-123",
        "website": "",
        "remote_ip": "203.0.113.5",
    }
    data.update(overrides)
    return SubmitMuseumQuestionInput(**data)  # type: ignore[arg-type]


async def test_execute_persists_submitted_question() -> None:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(repo, _Captcha(), _Limiter(), _Clock())
    output = await use_case.execute(_input())
    assert output.email == "ana@example.org"
    assert output.question_id is not None
    assert len(repo.added) == 1
    question = repo.added[0]
    assert question.status == MuseumQuestionStatus.SUBMITTED
    assert question.created_at == _NOW
    assert question.subject == "Duvida sobre visita in situ"


async def test_honeypot_accepts_and_drops() -> None:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(repo, _Captcha(), _Limiter(), _Clock())
    output = await use_case.execute(_input(website="http://spam"))
    assert output.question_id is None
    assert repo.added == []


async def test_rate_limit_raises() -> None:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(repo, _Captcha(), _Limiter(block=True), _Clock())
    with pytest.raises(RateLimitExceeded):
        await use_case.execute(_input())
    assert repo.added == []


async def test_captcha_failure_raises() -> None:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(repo, _Captcha(ok=False), _Limiter(), _Clock())
    with pytest.raises(CaptchaFailed):
        await use_case.execute(_input())
    assert repo.added == []


async def test_captcha_unavailable_raises() -> None:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(
        repo, _Captcha(raise_error=True), _Limiter(), _Clock()
    )
    with pytest.raises(CaptchaUnavailable):
        await use_case.execute(_input())
    assert repo.added == []
