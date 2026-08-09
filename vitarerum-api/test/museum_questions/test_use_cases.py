"""Unit tests for Museum Questions use cases."""

from datetime import UTC, datetime, timedelta

import pytest

from app.identity.public import Actor, GroupName, PermissionId
from app.museum_questions.application.read_models import MuseumQuestionListItem
from app.museum_questions.application.use_cases import (
    AnswerMuseumQuestion,
    AnswerMuseumQuestionInput,
    CaptchaFailed,
    CaptchaUnavailable,
    CloseMuseumQuestion,
    CloseMuseumQuestionInput,
    ListMuseumQuestions,
    MarkMuseumQuestionOutOfScope,
    MarkMuseumQuestionOutOfScopeInput,
    RateLimitExceeded,
    SubmitMuseumQuestion,
    SubmitMuseumQuestionInput,
    UploadedMuseumQuestionImage,
)
from app.museum_questions.domain.models import (
    InvalidMuseumQuestionTransition,
    MuseumQuestion,
    MuseumQuestionAttachment,
    MuseumQuestionStatus,
)
from app.shared.exceptions import InsufficientGroup

_NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
_STAFF = Actor(
    id=PermissionId("perm-staff"),
    group=GroupName.CURATORIAL,
    email="staff@example.org",
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"),
    group=GroupName.EXTERNAL,
    email="external@example.org",
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
    ) -> tuple[list[MuseumQuestionListItem], int]:
        rows = sorted(self.questions.values(), key=lambda q: q.created_at)
        if status is not None:
            rows = [q for q in rows if q.status == status]
        if requester_email:
            rows = [
                q
                for q in rows
                if q.requester_email.lower() == requester_email.strip().lower()
            ]
        return [
            MuseumQuestionListItem(q, len(q.attachments or []))
            for q in rows[page * size : page * size + size]
        ], len(rows)

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


class _Storage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, content: bytes, reference: str) -> str:
        self.files[reference] = content
        return reference

    async def read(self, reference: str) -> bytes:
        return self.files[reference]

    async def delete(self, reference: str) -> None:
        self.deleted.append(reference)
        self.files.pop(reference, None)


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
    use_case = SubmitMuseumQuestion(repo, _Captcha(), _Limiter(), _Clock(), _Storage())
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
    use_case = SubmitMuseumQuestion(repo, _Captcha(), _Limiter(), _Clock(), _Storage())
    output = await use_case.execute(_input(website="http://spam"))
    assert output.question_id is None
    assert repo.added == []


async def test_rate_limit_raises() -> None:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(
        repo, _Captcha(), _Limiter(block=True), _Clock(), _Storage()
    )
    with pytest.raises(RateLimitExceeded):
        await use_case.execute(_input())
    assert repo.added == []


async def test_captcha_failure_raises() -> None:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(
        repo, _Captcha(ok=False), _Limiter(), _Clock(), _Storage()
    )
    with pytest.raises(CaptchaFailed):
        await use_case.execute(_input())
    assert repo.added == []


async def test_captcha_unavailable_raises() -> None:
    repo = _Repo()
    use_case = SubmitMuseumQuestion(
        repo, _Captcha(raise_error=True), _Limiter(), _Clock(), _Storage()
    )
    with pytest.raises(CaptchaUnavailable):
        await use_case.execute(_input())
    assert repo.added == []


async def test_list_questions_filters_and_orders() -> None:
    older = _question("q-old", created_at=_NOW - timedelta(days=1))
    answered = _question("q-answered", status=MuseumQuestionStatus.ANSWERED)
    repo = _Repo([answered, older])
    result = await ListMuseumQuestions(repo).execute(
        _STAFF, status=MuseumQuestionStatus.SUBMITTED, page=0, size=20
    )
    assert result.total == 1
    assert [item.question.id for item in result.content] == ["q-old"]


async def test_list_questions_filters_by_requester_email() -> None:
    repo = _Repo(
        [
            _question("q-ana", status=MuseumQuestionStatus.ANSWERED),
            _question(
                "q-bruno",
                status=MuseumQuestionStatus.ANSWERED,
                requester_email="bruno@example.org",
            ),
        ]
    )
    result = await ListMuseumQuestions(repo).execute(
        _STAFF,
        status=MuseumQuestionStatus.ANSWERED,
        requester_email="ANA@example.org",
        page=0,
        size=20,
    )
    assert result.total == 1
    assert [item.question.id for item in result.content] == ["q-ana"]


async def test_persist_uploads_images_and_tracks_attachment_metadata() -> None:
    repo = _Repo()
    storage = _Storage()
    use_case = SubmitMuseumQuestion(repo, _Captcha(), _Limiter(), _Clock(), storage)
    output = await use_case.execute(
        _input(
            attachments=[
                UploadedMuseumQuestionImage(
                    file_name="artifact.png",
                    content=b"\x89PNG\r\n\x1a\nimage",
                    content_type="image/png",
                    extension=".png",
                )
            ]
        )
    )
    question = repo.added[0]
    attachment = question.attachments[0]
    assert output.file_references == [attachment.file_reference]
    assert question.attachments == [
        MuseumQuestionAttachment(
            id=attachment.id,
            question_id=question.id,
            file_name="artifact.png",
            file_reference=attachment.file_reference,
            content_type="image/png",
            size_bytes=13,
            created_at=_NOW,
            sort_order=0,
        )
    ]
    assert storage.files[attachment.file_reference] == b"\x89PNG\r\n\x1a\nimage"


async def test_persist_discards_uploaded_files_when_repository_fails() -> None:
    class FailingRepo(_Repo):
        async def add(self, question: MuseumQuestion) -> None:
            raise RuntimeError("db failed")

    storage = _Storage()
    use_case = SubmitMuseumQuestion(
        FailingRepo(), _Captcha(), _Limiter(), _Clock(), storage
    )
    with pytest.raises(RuntimeError):
        await use_case.execute(
            _input(
                attachments=[
                    UploadedMuseumQuestionImage(
                        file_name="artifact.jpg",
                        content=b"\xff\xd8\xffimage",
                        content_type="image/jpeg",
                        extension=".jpg",
                    )
                ]
            )
        )
    assert storage.files == {}
    assert storage.deleted


async def test_list_questions_requires_staff() -> None:
    with pytest.raises(InsufficientGroup):
        await ListMuseumQuestions(_Repo()).execute(
            _EXTERNAL, status=None, page=0, size=20
        )


async def test_answer_question_marks_answered() -> None:
    # E-mail dispatch is the route's job (only after commit) — see
    # test_api.py's test_answer_internal_question_sends_email_and_commits and
    # test_answer_internal_question_does_not_email_when_commit_fails.
    question = _question()
    repo = _Repo([question])
    result = await AnswerMuseumQuestion(repo, _Clock()).execute(
        AnswerMuseumQuestionInput(_STAFF, "q1", "  Yes, we can help.  ")
    )
    assert result.status == MuseumQuestionStatus.ANSWERED
    assert result.answer_body == "Yes, we can help."
    assert result.answered_by == _STAFF.id
    assert result.answer_sent_at == _NOW


async def test_answer_question_rejects_finalized_question() -> None:
    repo = _Repo([_question(status=MuseumQuestionStatus.ANSWERED)])
    with pytest.raises(InvalidMuseumQuestionTransition):
        await AnswerMuseumQuestion(repo, _Clock()).execute(
            AnswerMuseumQuestionInput(_STAFF, "q1", "Answer")
        )


async def test_mark_out_of_scope_updates_status() -> None:
    repo = _Repo([_question()])
    result = await MarkMuseumQuestionOutOfScope(repo, _Clock()).execute(
        MarkMuseumQuestionOutOfScopeInput(_STAFF, "q1", "  Exhibition question  ")
    )
    assert result.status == MuseumQuestionStatus.OUT_OF_SCOPE
    assert result.out_of_scope_reason == "Exhibition question"
    assert result.out_of_scope_by == _STAFF.id
    assert result.out_of_scope_email_sent_at == _NOW


@pytest.mark.parametrize(
    "status",
    [MuseumQuestionStatus.ANSWERED, MuseumQuestionStatus.OUT_OF_SCOPE],
)
async def test_close_question_after_final_response(
    status: MuseumQuestionStatus,
) -> None:
    repo = _Repo([_question(status=status)])
    result = await CloseMuseumQuestion(repo, _Clock()).execute(
        CloseMuseumQuestionInput(_STAFF, "q1")
    )
    assert result.status == MuseumQuestionStatus.CLOSED
    assert result.closed_by == _STAFF.id
    assert result.closed_at == _NOW


async def test_close_submitted_question_is_rejected() -> None:
    repo = _Repo([_question()])
    with pytest.raises(InvalidMuseumQuestionTransition):
        await CloseMuseumQuestion(repo, _Clock()).execute(
            CloseMuseumQuestionInput(_STAFF, "q1")
        )
