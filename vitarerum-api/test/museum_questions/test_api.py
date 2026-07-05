"""API tests for the public Museum Questions endpoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_async_session
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.museum_questions.application.use_cases import (
    AnswerMuseumQuestion,
    CloseMuseumQuestion,
    GetMuseumQuestion,
    ListMuseumQuestions,
    MarkMuseumQuestionOutOfScope,
    SubmitMuseumQuestion,
)
from app.museum_questions.domain.models import MuseumQuestion, MuseumQuestionStatus
from app.museum_questions.presentation.dependencies import (
    get_answer_use_case,
    get_close_use_case,
    get_email_sender,
    get_get_use_case,
    get_list_use_case,
    get_mark_out_of_scope_use_case,
    get_submit_use_case,
)
from app.shared.dependencies import get_caller_permission

_SUBMIT_URL = "/api/v1/public/museum-questions"
_INTERNAL_URL = "/api/v1/museum-questions"
_NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@example.org"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="e@example.org"
)


class _Repo:
    def __init__(self, questions: list[MuseumQuestion] | None = None) -> None:
        self.questions = {q.id: q for q in questions or []}

    @property
    def added(self) -> list[MuseumQuestion]:
        return list(self.questions.values())

    async def add(self, question: MuseumQuestion) -> None:
        self.questions[question.id] = question

    async def get_by_id(self, question_id: str) -> MuseumQuestion | None:
        return self.questions.get(question_id)

    async def list(
        self,
        *,
        status: MuseumQuestionStatus | None,
        requester_email: str | None,
        page: int,
        size: int,
    ) -> tuple[list[MuseumQuestion], int]:
        rows = sorted(self.questions.values(), key=lambda q: q.created_at)
        if status is not None:
            rows = [q for q in rows if q.status == status]
        if requester_email:
            rows = [
                q
                for q in rows
                if q.requester_email.lower() == requester_email.strip().lower()
            ]
        return rows[page * size : page * size + size], len(rows)

    async def save(self, question: MuseumQuestion) -> None:
        self.questions[question.id] = question


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


class _EmailSender:
    def __init__(self) -> None:
        self.answers: list[tuple[str, str]] = []
        self.out_of_scope: list[str] = []

    async def send_answer(
        self,
        *,
        to_email: str,
        requester_name: str,
        subject: str,
        answer_body: str,
    ) -> None:
        self.answers.append((to_email, answer_body))

    async def send_out_of_scope(
        self,
        *,
        to_email: str,
        requester_name: str,
        subject: str,
    ) -> None:
        self.out_of_scope.append(to_email)


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
    caller: Actor = _STAFF,
    questions: list[MuseumQuestion] | None = None,
) -> AsyncIterator[tuple[AsyncClient, _Repo, _EmailSender, _Session]]:
    repo = _Repo(questions)
    email_sender = _EmailSender()
    session = _Session(fail_commit=fail_commit)
    use_case = SubmitMuseumQuestion(
        repository=repo,
        captcha=_Captcha(ok=captcha_ok, raise_error=captcha_raises),
        rate_limiter=_Limiter(block=rate_limited),
        clock=_Clock(),
    )
    app.dependency_overrides[get_submit_use_case] = lambda: use_case
    app.dependency_overrides[get_list_use_case] = lambda: ListMuseumQuestions(repo)
    app.dependency_overrides[get_get_use_case] = lambda: GetMuseumQuestion(repo)
    app.dependency_overrides[get_answer_use_case] = lambda: AnswerMuseumQuestion(
        repo, _Clock()
    )
    app.dependency_overrides[get_mark_out_of_scope_use_case] = lambda: (
        MarkMuseumQuestionOutOfScope(repo, _Clock())
    )
    app.dependency_overrides[get_close_use_case] = lambda: CloseMuseumQuestion(
        repo, _Clock()
    )
    app.dependency_overrides[get_email_sender] = lambda: email_sender
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[get_caller_permission] = lambda: caller
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, repo, email_sender, session
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


def _question(
    question_id: str = "q1",
    status: MuseumQuestionStatus = MuseumQuestionStatus.SUBMITTED,
    created_at: datetime = _NOW,
    requester_email: str = "ana@example.org",
) -> MuseumQuestion:
    return MuseumQuestion(
        id=question_id,
        requester_name="Ana Souza",
        requester_email=requester_email,
        subject="Duvida sobre visita in situ",
        message="Gostaria de agendar uma visita para pesquisa.",
        created_at=created_at,
        status=status,
    )


async def test_submit_returns_202_receipt() -> None:
    async with _client() as (client, repo, _, _):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 202
    assert resp.json() == {"status": "RECEIVED", "email": "ana@example.org"}
    assert len(repo.added) == 1
    assert repo.added[0].subject == "Duvida sobre visita in situ"
    assert repo.added[0].requester_name == "Ana Souza"


async def test_submit_missing_consent_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        resp = await client.post(_SUBMIT_URL, json=_payload(consent=False))
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_captcha_failure_403() -> None:
    async with _client(captcha_ok=False) as (client, repo, _, _):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 403
    assert resp.json()["message"] == "Captcha verification failed."
    assert repo.added == []


async def test_submit_captcha_unavailable_503() -> None:
    async with _client(captcha_raises=True) as (client, repo, _, _):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 503
    assert repo.added == []


async def test_submit_rate_limited_429_with_retry_after() -> None:
    async with _client(rate_limited=True) as (client, repo, _, _):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"
    assert repo.added == []


async def test_submit_honeypot_returns_202_no_work() -> None:
    async with _client() as (client, repo, _, _):
        resp = await client.post(_SUBMIT_URL, json=_payload(website="http://spam"))
    assert resp.status_code == 202
    assert repo.added == []


async def test_submit_sanitizes_control_characters_and_crlf() -> None:
    async with _client() as (client, repo, _, _):
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
    async with _client() as (client, repo, _, _):
        resp = await client.post(
            _SUBMIT_URL,
            json=_payload(requesterName="   ", subject="   ", message="   "),
        )
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_missing_field_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        payload = _payload()
        del payload["subject"]
        resp = await client.post(_SUBMIT_URL, json=payload)
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_invalid_email_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        resp = await client.post(
            _SUBMIT_URL, json=_payload(requesterEmail="not-an-email")
        )
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_over_length_message_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        resp = await client.post(_SUBMIT_URL, json=_payload(message="x" * 4001))
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_commit_failure_propagates() -> None:
    async with _client(fail_commit=True) as (client, repo, _, _):
        with pytest.raises(RuntimeError):
            await client.post(_SUBMIT_URL, json=_payload())
    # The fake repo persisted in-memory before the (failed) commit — a real DB
    # session would roll this back; this only proves the route doesn't
    # swallow the commit error.
    assert len(repo.added) == 1


async def test_list_internal_questions_filters_and_paginates() -> None:
    questions = [
        _question("q2", created_at=_NOW + timedelta(minutes=1)),
        _question("q1", created_at=_NOW),
        _question("q3", status=MuseumQuestionStatus.ANSWERED),
    ]
    async with _client(questions=questions) as (client, _, _, _):
        resp = await client.get(
            _INTERNAL_URL, params={"status": "SUBMITTED", "page": 0, "size": 1}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalElements"] == 2
    assert body["totalPages"] == 2
    assert [item["id"] for item in body["content"]] == ["q1"]


async def test_list_internal_questions_filters_by_requester_email() -> None:
    questions = [
        _question("q1", status=MuseumQuestionStatus.ANSWERED),
        _question(
            "q2",
            status=MuseumQuestionStatus.ANSWERED,
            requester_email="bruno@example.org",
        ),
        _question("q3", status=MuseumQuestionStatus.SUBMITTED),
    ]
    async with _client(questions=questions) as (client, _, _, _):
        resp = await client.get(
            _INTERNAL_URL,
            params={
                "status": "ANSWERED",
                "requesterEmail": "ANA@example.org",
                "page": 0,
                "size": 20,
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalElements"] == 1
    assert [item["id"] for item in body["content"]] == ["q1"]


async def test_internal_questions_reject_non_staff() -> None:
    async with _client(caller=_EXTERNAL, questions=[_question()]) as (client, _, _, _):
        resp = await client.get(_INTERNAL_URL)
    assert resp.status_code == 403
    assert resp.json()["error"] == "INSUFFICIENT_GROUP"


async def test_get_internal_question_detail() -> None:
    async with _client(questions=[_question()]) as (client, _, _, _):
        resp = await client.get(f"{_INTERNAL_URL}/q1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "q1"
    assert body["message"] == "Gostaria de agendar uma visita para pesquisa."


async def test_get_internal_question_unknown_is_404() -> None:
    async with _client() as (client, _, _, _):
        resp = await client.get(f"{_INTERNAL_URL}/missing")
    assert resp.status_code == 404
    assert resp.json()["error"] == "MUSEUM_QUESTION_NOT_FOUND"


async def test_answer_internal_question_sends_email_and_commits() -> None:
    async with _client(questions=[_question()]) as (client, repo, sender, session):
        resp = await client.post(
            f"{_INTERNAL_URL}/q1/answer",
            json={"answerBody": "  Please contact collections.  "},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ANSWERED"
    assert repo.questions["q1"].answer_body == "Please contact collections."
    assert sender.answers == [("ana@example.org", "Please contact collections.")]
    assert session.committed is True


async def test_answer_internal_question_does_not_email_when_commit_fails() -> None:
    # The e-mail must only go out after the status change is durably
    # committed — otherwise a citizen could receive an answer for an update
    # that rolled back, and a staff retry would send a duplicate.
    async with _client(fail_commit=True, questions=[_question()]) as (
        client,
        _,
        sender,
        _,
    ):
        with pytest.raises(RuntimeError):
            await client.post(
                f"{_INTERNAL_URL}/q1/answer", json={"answerBody": "Answer"}
            )
    assert sender.answers == []


async def test_mark_out_of_scope_does_not_email_when_commit_fails() -> None:
    async with _client(fail_commit=True, questions=[_question()]) as (
        client,
        _,
        sender,
        _,
    ):
        with pytest.raises(RuntimeError):
            await client.post(
                f"{_INTERNAL_URL}/q1/mark-out-of-scope", json={"reason": "Exhibition"}
            )
    assert sender.out_of_scope == []


async def test_answer_internal_question_rejects_already_answered() -> None:
    async with _client(questions=[_question(status=MuseumQuestionStatus.ANSWERED)]) as (
        client,
        _,
        sender,
        _,
    ):
        resp = await client.post(
            f"{_INTERNAL_URL}/q1/answer", json={"answerBody": "Again"}
        )
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_MUSEUM_QUESTION_TRANSITION"
    assert sender.answers == []


async def test_mark_out_of_scope_sends_standard_email() -> None:
    async with _client(questions=[_question()]) as (client, repo, sender, _):
        resp = await client.post(
            f"{_INTERNAL_URL}/q1/mark-out-of-scope",
            json={"reason": "  Exhibition request  "},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "OUT_OF_SCOPE"
    assert repo.questions["q1"].out_of_scope_reason == "Exhibition request"
    assert sender.out_of_scope == ["ana@example.org"]


@pytest.mark.parametrize(
    "initial_status",
    [MuseumQuestionStatus.ANSWERED, MuseumQuestionStatus.OUT_OF_SCOPE],
)
async def test_close_internal_question_after_response(
    initial_status: MuseumQuestionStatus,
) -> None:
    async with _client(questions=[_question(status=initial_status)]) as (
        client,
        repo,
        sender,
        _,
    ):
        resp = await client.patch(f"{_INTERNAL_URL}/q1/close")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CLOSED"
    assert repo.questions["q1"].closed_by == _STAFF.id
    assert sender.answers == []
    assert sender.out_of_scope == []


async def test_close_submitted_internal_question_is_rejected() -> None:
    async with _client(questions=[_question()]) as (client, _, _, _):
        resp = await client.patch(f"{_INTERNAL_URL}/q1/close")
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_MUSEUM_QUESTION_TRANSITION"
