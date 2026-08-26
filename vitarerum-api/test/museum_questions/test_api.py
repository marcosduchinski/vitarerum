"""API tests for the public Museum Questions endpoint."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.config import settings
from app.database import get_async_session
from app.identity.public import (
    Actor,
    GroupName,
    PermissionId,
    PermissionView,
    UserView,
)
from app.main import app
from app.museum_questions.application.read_models import MuseumQuestionListItem
from app.museum_questions.application.use_cases import (
    AnswerMuseumQuestion,
    CloseMuseumQuestion,
    ForwardMuseumQuestion,
    GetMuseumQuestion,
    ListMuseumQuestions,
    MarkMuseumQuestionOutOfScope,
    SubmitMuseumQuestion,
)
from app.museum_questions.domain.models import (
    MuseumQuestion,
    MuseumQuestionAttachment,
    MuseumQuestionStatus,
)
from app.museum_questions.presentation.dependencies import (
    get_answer_use_case,
    get_close_use_case,
    get_email_sender,
    get_file_storage,
    get_forward_use_case,
    get_get_use_case,
    get_list_use_case,
    get_mark_out_of_scope_use_case,
    get_museum_question_notification_email_recipients,
    get_museum_question_notification_recipients,
    get_notifications_dispatcher,
    get_reader,
    get_submit_use_case,
)
from app.museum_questions.presentation.routes import _uploaded_images
from app.shared.dependencies import get_caller_permission

_SUBMIT_URL = "/api/v1/public/museum-questions"
_INTERNAL_URL = "/api/v1/museum-questions"
_NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
_STAFF = Actor(
    id=PermissionId("perm-staff"),
    group=GroupName.COLLECTIONS_MANAGEMENT,
    email="s@example.org",
)
_DIRECTION = Actor(
    id=PermissionId("perm-direction"),
    group=GroupName.DIRECTION,
    email="direction@example.org",
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
        assigned_to: str | None,
        unassigned_only: bool,
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
        if assigned_to:
            rows = [q for q in rows if q.assigned_to == assigned_to]
        if unassigned_only:
            rows = [q for q in rows if q.assigned_to is None]
        return [
            MuseumQuestionListItem(q, len(q.attachments or []))
            for q in rows[page * size : page * size + size]
        ], len(rows)

    async def save(self, question: MuseumQuestion) -> None:
        self.questions[question.id] = question

    async def list_unanswered_due_for_overdue_notification(
        self, *, now: datetime, limit: int
    ) -> Sequence[MuseumQuestion]:
        rows = [
            q
            for q in self.questions.values()
            if q.status == MuseumQuestionStatus.SUBMITTED
            and q.answered_at is None
            and q.response_due_at <= now
            and q.response_overdue_notified_at is None
        ]
        rows.sort(key=lambda q: (q.response_due_at, q.created_at, q.id))
        return rows[:limit]


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
        self.question_submitted: list[tuple[str, str, str]] = []

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

    async def send_question_submitted(
        self,
        *,
        to_email: str,
        recipient_name: str,
        requester_name: str,
        subject: str,
        link: str,
    ) -> None:
        self.question_submitted.append((to_email, recipient_name, link))


class _NotificationDispatcher:
    def __init__(self) -> None:
        self.single: list[dict[str, object]] = []
        self.many: list[dict[str, object]] = []

    async def notify(self, **kwargs: object) -> None:
        self.single.append(kwargs)

    async def notify_many(self, **kwargs: object) -> None:
        self.many.append(kwargs)


class _Reader:
    def __init__(self, permissions: list[PermissionView] | None = None) -> None:
        self.permissions = {
            permission.permission_id: permission for permission in permissions or []
        }

    async def get_detail(self, permission_id: PermissionId) -> PermissionView | None:
        return self.permissions.get(permission_id)

    async def list_by_group(self, group: GroupName) -> list[PermissionView]:
        return [
            permission
            for permission in self.permissions.values()
            if permission.group == group
        ]


class _Storage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, content: bytes, reference: str) -> str:
        self.files[reference] = content
        return reference

    async def read(self, reference: str) -> bytes:
        try:
            return self.files[reference]
        except KeyError as exc:
            raise FileNotFoundError(reference) from exc

    async def delete(self, reference: str) -> None:
        self.deleted.append(reference)
        self.files.pop(reference, None)


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
    notification_dispatcher: _NotificationDispatcher | None = None,
    notification_recipients: list[PermissionView] | None = None,
    notification_email_recipients: list[PermissionView] | None = None,
    permissions: list[PermissionView] | None = None,
) -> AsyncIterator[tuple[AsyncClient, _Repo, _EmailSender, _Session, _Storage]]:
    repo = _Repo(questions)
    email_sender = _EmailSender()
    session = _Session(fail_commit=fail_commit)
    storage = _Storage()
    dispatcher = notification_dispatcher or _NotificationDispatcher()
    reader = _Reader(permissions)
    use_case = SubmitMuseumQuestion(
        repository=repo,
        captcha=_Captcha(ok=captcha_ok, raise_error=captcha_raises),
        rate_limiter=_Limiter(block=rate_limited),
        clock=_Clock(),
        file_storage=storage,
    )
    app.dependency_overrides[get_submit_use_case] = lambda: use_case
    app.dependency_overrides[get_list_use_case] = lambda: ListMuseumQuestions(
        repo, reader
    )
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
    app.dependency_overrides[get_forward_use_case] = lambda: ForwardMuseumQuestion(repo)
    app.dependency_overrides[get_email_sender] = lambda: email_sender
    app.dependency_overrides[get_file_storage] = lambda: storage
    app.dependency_overrides[get_notifications_dispatcher] = lambda: dispatcher
    app.dependency_overrides[get_reader] = lambda: reader
    app.dependency_overrides[get_museum_question_notification_recipients] = lambda: (
        notification_recipients or []
    )
    app.dependency_overrides[get_museum_question_notification_email_recipients] = (
        lambda: notification_email_recipients or []
    )
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[get_caller_permission] = lambda: caller
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, repo, email_sender, session, storage
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
    assigned_to: str | None = None,
) -> MuseumQuestion:
    return MuseumQuestion(
        id=question_id,
        requester_name="Ana Souza",
        requester_email=requester_email,
        subject="Duvida sobre visita in situ",
        message="Gostaria de agendar uma visita para pesquisa.",
        created_at=created_at,
        response_due_at=created_at + timedelta(days=15),
        status=status,
        assigned_to=assigned_to,
    )


def _attachment(
    *,
    attachment_id: str = "att-1",
    question_id: str = "q1",
    file_name: str = "artifact.png",
    file_reference: str = "museum-questions/q1/att-1.png",
) -> MuseumQuestionAttachment:
    return MuseumQuestionAttachment(
        id=attachment_id,
        question_id=question_id,
        file_name=file_name,
        file_reference=file_reference,
        content_type="image/png",
        size_bytes=13,
        created_at=_NOW,
        sort_order=0,
    )


def _permission(
    permission_id: str,
    *,
    name: str,
    email: str,
    group: GroupName,
    user_id: str | None = None,
) -> PermissionView:
    return PermissionView(
        permission_id=permission_id,
        user=UserView(id=user_id or permission_id, name=name, email=email),
        group=group,
    )


async def test_submit_returns_202_receipt() -> None:
    async with _client() as (client, repo, _, _, _storage):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 202
    assert resp.json() == {"status": "RECEIVED", "email": "ana@example.org"}
    assert len(repo.added) == 1
    assert repo.added[0].subject == "Duvida sobre visita in situ"
    assert repo.added[0].requester_name == "Ana Souza"


async def test_submit_notifies_access_groups_and_emails_curators_and_managers() -> None:
    dispatcher = _NotificationDispatcher()
    notification_recipients = [
        _permission(
            "perm-collections",
            name="Collections Manager",
            email="collections@example.org",
            group=GroupName.COLLECTIONS_MANAGEMENT,
        ),
        _permission(
            "perm-curatorial",
            name="Curator",
            email="curator@example.org",
            group=GroupName.CURATORIAL,
        ),
    ]
    email_recipients = [
        _permission(
            "perm-curatorial",
            name="Curator",
            email="curator@example.org",
            group=GroupName.CURATORIAL,
        ),
        _permission(
            "perm-collections",
            name="Collections Manager",
            email="collections@example.org",
            group=GroupName.COLLECTIONS_MANAGEMENT,
        ),
    ]
    async with _client(
        notification_dispatcher=dispatcher,
        notification_recipients=notification_recipients,
        notification_email_recipients=email_recipients,
    ) as (client, repo, sender, _, _storage):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 202
    question_id = repo.added[0].id
    assert dispatcher.many == [
        {
            "recipient_permission_ids": [
                PermissionId("perm-collections"),
                PermissionId("perm-curatorial"),
            ],
            "kind": "MUSEUM_QUESTION_SUBMITTED",
            "triggered_by": None,
            "related_resource_type": "MUSEUM_QUESTION",
            "related_resource_id": question_id,
            "related_resource_label": "Duvida sobre visita in situ",
            "note": "Submitted by Ana Souza <ana@example.org>",
        }
    ]
    assert sender.question_submitted == [
        (
            "curator@example.org",
            "Curator",
            f"{settings.public_origin}/p/museum-questions/{question_id}",
        ),
        (
            "collections@example.org",
            "Collections Manager",
            f"{settings.public_origin}/p/museum-questions/{question_id}",
        ),
    ]


async def test_submit_accepts_multipart_images() -> None:
    async with _client() as (client, repo, _, _, storage):
        resp = await client.post(
            _SUBMIT_URL,
            data={
                key: str(value).lower() if value is True else str(value)
                for key, value in _payload().items()
            },
            files=[
                (
                    "attachments",
                    ("artifact.png", b"\x89PNG\r\n\x1a\nimage", "image/png"),
                ),
                ("attachments", ("detail.jpg", b"\xff\xd8\xffimage", "image/jpeg")),
            ],
        )
    assert resp.status_code == 202
    question = repo.added[0]
    assert question.attachments is not None
    assert [item.file_name for item in question.attachments] == [
        "artifact.png",
        "detail.jpg",
    ]
    assert [item.sort_order for item in question.attachments] == [0, 1]
    assert set(storage.files) == {item.file_reference for item in question.attachments}


async def test_submit_rejects_more_than_ten_images() -> None:
    async with _client() as (client, repo, _, _, _storage):
        resp = await client.post(
            _SUBMIT_URL,
            data={
                key: str(value).lower() if value is True else str(value)
                for key, value in _payload().items()
            },
            files=[
                ("attachments", (f"{idx}.png", b"\x89PNG\r\n\x1a\nimage", "image/png"))
                for idx in range(11)
            ],
        )
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_rejects_non_image_attachment() -> None:
    async with _client() as (client, repo, _, _, _storage):
        resp = await client.post(
            _SUBMIT_URL,
            data={
                key: str(value).lower() if value is True else str(value)
                for key, value in _payload().items()
            },
            files=[("attachments", ("notes.txt", b"not an image", "text/plain"))],
        )
    assert resp.status_code == 415
    assert resp.json()["error"] == "UNSUPPORTED_FILE_TYPE"
    assert repo.added == []


async def test_uploaded_images_rejects_configurable_total_limit() -> None:
    files = [
        StarletteUploadFile(io.BytesIO(b"\x89PNG\r\n\x1a\n1234"), filename="one.png"),
        StarletteUploadFile(io.BytesIO(b"\x89PNG\r\n\x1a\n5678"), filename="two.png"),
    ]
    with pytest.raises(HTTPException) as exc_info:
        await _uploaded_images(files, total_limit=15)
    assert exc_info.value.status_code == 413


async def test_submit_missing_consent_is_rejected() -> None:
    async with _client() as (client, repo, _, _, _storage):
        resp = await client.post(_SUBMIT_URL, json=_payload(consent=False))
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_captcha_failure_403() -> None:
    async with _client(captcha_ok=False) as (client, repo, _, _, _storage):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 403
    assert resp.json()["message"] == "Captcha verification failed."
    assert repo.added == []


async def test_submit_captcha_unavailable_503() -> None:
    async with _client(captcha_raises=True) as (client, repo, _, _, _storage):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 503
    assert repo.added == []


async def test_submit_rate_limited_429_with_retry_after() -> None:
    async with _client(rate_limited=True) as (client, repo, _, _, _storage):
        resp = await client.post(_SUBMIT_URL, json=_payload())
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"
    assert repo.added == []


async def test_submit_honeypot_returns_202_no_work() -> None:
    dispatcher = _NotificationDispatcher()
    async with _client(notification_dispatcher=dispatcher) as (
        client,
        repo,
        sender,
        _,
        _storage,
    ):
        resp = await client.post(_SUBMIT_URL, json=_payload(website="http://spam"))
    assert resp.status_code == 202
    assert repo.added == []
    assert dispatcher.many == []
    assert sender.question_submitted == []


async def test_submit_sanitizes_control_characters_and_crlf() -> None:
    async with _client() as (client, repo, _, _, _storage):
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
    async with _client() as (client, repo, _, _, _storage):
        resp = await client.post(
            _SUBMIT_URL,
            json=_payload(requesterName="   ", subject="   ", message="   "),
        )
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_missing_field_is_rejected() -> None:
    async with _client() as (client, repo, _, _, _storage):
        payload = _payload()
        del payload["subject"]
        resp = await client.post(_SUBMIT_URL, json=payload)
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_invalid_email_is_rejected() -> None:
    async with _client() as (client, repo, _, _, _storage):
        resp = await client.post(
            _SUBMIT_URL, json=_payload(requesterEmail="not-an-email")
        )
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_over_length_message_is_rejected() -> None:
    async with _client() as (client, repo, _, _, _storage):
        resp = await client.post(_SUBMIT_URL, json=_payload(message="x" * 4001))
    assert resp.status_code == 422
    assert repo.added == []


async def test_submit_commit_failure_propagates() -> None:
    async with _client(
        fail_commit=True,
        notification_email_recipients=[
            _permission(
                "perm-curatorial",
                name="Curator",
                email="curator@example.org",
                group=GroupName.CURATORIAL,
            )
        ],
    ) as (client, repo, sender, _, storage):
        with pytest.raises(RuntimeError):
            await client.post(
                _SUBMIT_URL,
                data={
                    key: str(value).lower() if value is True else str(value)
                    for key, value in _payload().items()
                },
                files=[
                    (
                        "attachments",
                        ("artifact.png", b"\x89PNG\r\n\x1a\nimage", "image/png"),
                    )
                ],
            )
    # The fake repo persisted in-memory before the (failed) commit — a real DB
    # session would roll this back; this only proves the route doesn't
    # swallow the commit error.
    assert len(repo.added) == 1
    assert storage.files == {}
    assert storage.deleted
    assert sender.question_submitted == []


async def test_list_internal_questions_filters_and_paginates() -> None:
    questions = [
        _question("q2", created_at=_NOW + timedelta(minutes=1)),
        _question("q1", created_at=_NOW),
        _question("q3", status=MuseumQuestionStatus.ANSWERED),
    ]
    async with _client(questions=questions) as (client, _, _, _, _storage):
        resp = await client.get(
            _INTERNAL_URL, params={"status": "SUBMITTED", "page": 0, "size": 1}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalElements"] == 2
    assert body["totalPages"] == 2
    assert [item["id"] for item in body["content"]] == ["q1"]
    assert body["content"][0]["attachmentCount"] == 0


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
    async with _client(questions=questions) as (client, _, _, _, _storage):
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


async def test_list_questions_filters_by_assignee_and_hydrates_assignment() -> None:
    assignee = _permission(
        "perm-curator",
        name="Curator",
        email="curator@example.org",
        group=GroupName.CURATORIAL,
    )
    questions = [
        _question("q1", assigned_to="perm-curator"),
        _question("q2", assigned_to="perm-other"),
    ]
    async with _client(questions=questions, permissions=[assignee]) as (
        client,
        _,
        _,
        _,
        _storage,
    ):
        resp = await client.get(
            _INTERNAL_URL,
            params={"assignedTo": "perm-curator", "page": 0, "size": 20},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert [item["id"] for item in body["content"]] == ["q1"]
    assert body["content"][0]["assignedTo"] == {
        "permissionId": "perm-curator",
        "user": {
            "id": "perm-curator",
            "name": "Curator",
            "email": "curator@example.org",
        },
        "group": "CURATORIAL",
    }


async def test_list_questions_filters_unassigned_submitted() -> None:
    questions = [
        _question("q1"),
        _question("q2", assigned_to="perm-curator"),
        _question("q3", status=MuseumQuestionStatus.ANSWERED),
    ]
    async with _client(questions=questions) as (client, _, _, _, _storage):
        resp = await client.get(
            _INTERNAL_URL,
            params={
                "status": "SUBMITTED",
                "unassignedOnly": "true",
                "page": 0,
                "size": 20,
            },
        )
    assert resp.status_code == 200
    assert [item["id"] for item in resp.json()["content"]] == ["q1"]


async def test_internal_questions_reject_non_staff() -> None:
    async with _client(caller=_EXTERNAL, questions=[_question()]) as (
        client,
        _,
        _,
        _,
        _storage,
    ):
        resp = await client.get(_INTERNAL_URL)
    assert resp.status_code == 403
    assert resp.json()["error"] == "INSUFFICIENT_GROUP"


async def test_internal_questions_reject_direction_initial_access() -> None:
    async with _client(caller=_DIRECTION, questions=[_question()]) as (
        client,
        _,
        _,
        _,
        _storage,
    ):
        resp = await client.get(_INTERNAL_URL)
    assert resp.status_code == 403
    assert resp.json()["error"] == "INSUFFICIENT_GROUP"


async def test_get_internal_question_detail() -> None:
    assignee = _permission(
        "perm-curator",
        name="Curator",
        email="curator@example.org",
        group=GroupName.CURATORIAL,
    )
    async with _client(
        questions=[_question(assigned_to="perm-curator")],
        permissions=[assignee],
    ) as (client, _, _, _, _storage):
        resp = await client.get(f"{_INTERNAL_URL}/q1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "q1"
    assert body["message"] == "Gostaria de agendar uma visita para pesquisa."
    assert body["attachments"] == []
    assert body["assignedTo"]["permissionId"] == "perm-curator"


async def test_get_internal_question_detail_includes_attachments() -> None:
    question = _question()
    question.attachments = [_attachment()]
    async with _client(questions=[question]) as (client, _, _, _, _storage):
        resp = await client.get(f"{_INTERNAL_URL}/q1")
    assert resp.status_code == 200
    assert resp.json()["attachments"] == [
        {
            "id": "att-1",
            "fileName": "artifact.png",
            "contentType": "image/png",
            "sizeBytes": 13,
            "createdAt": _NOW.isoformat().replace("+00:00", "Z"),
        }
    ]


async def test_download_internal_question_attachment_returns_inline_image() -> None:
    question = _question()
    question.attachments = [_attachment()]
    async with _client(questions=[question]) as (client, _, _, _, storage):
        storage.files["museum-questions/q1/att-1.png"] = b"\x89PNG\r\n\x1a\nimage"
        resp = await client.get(f"{_INTERNAL_URL}/q1/attachments/att-1")
    assert resp.status_code == 200
    assert resp.content == b"\x89PNG\r\n\x1a\nimage"
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["content-disposition"].startswith("inline;")


async def test_get_internal_question_unknown_is_404() -> None:
    async with _client() as (client, _, _, _, _storage):
        resp = await client.get(f"{_INTERNAL_URL}/missing")
    assert resp.status_code == 404
    assert resp.json()["error"] == "MUSEUM_QUESTION_NOT_FOUND"


async def test_answer_internal_question_sends_email_and_commits() -> None:
    async with _client(questions=[_question()]) as (
        client,
        repo,
        sender,
        session,
        _storage,
    ):
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
        _storage,
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
        _storage,
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
        _storage,
    ):
        resp = await client.post(
            f"{_INTERNAL_URL}/q1/answer", json={"answerBody": "Again"}
        )
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_MUSEUM_QUESTION_TRANSITION"
    assert sender.answers == []


async def test_mark_out_of_scope_sends_standard_email() -> None:
    async with _client(questions=[_question()]) as (client, repo, sender, _, _storage):
        resp = await client.post(
            f"{_INTERNAL_URL}/q1/mark-out-of-scope",
            json={"reason": "  Exhibition request  "},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "OUT_OF_SCOPE"
    assert repo.questions["q1"].out_of_scope_reason == "Exhibition request"
    assert sender.out_of_scope == ["ana@example.org"]


async def test_forward_internal_question_assigns_and_notifies_target() -> None:
    dispatcher = _NotificationDispatcher()
    assignee = _permission(
        "perm-curator",
        name="Curator",
        email="curator@example.org",
        group=GroupName.CURATORIAL,
    )
    async with _client(
        questions=[_question()],
        permissions=[assignee],
        notification_dispatcher=dispatcher,
    ) as (client, repo, _, session, _storage):
        resp = await client.post(
            f"{_INTERNAL_URL}/q1/forward",
            json={"targetPermissionId": "perm-curator"},
        )
    assert resp.status_code == 200
    assert repo.questions["q1"].assigned_to == "perm-curator"
    assert resp.json()["assignedTo"]["permissionId"] == "perm-curator"
    assert dispatcher.single == [
        {
            "recipient_permission_id": PermissionId("perm-curator"),
            "kind": "MUSEUM_QUESTION_FORWARDED",
            "triggered_by": _STAFF.id,
            "related_resource_type": "MUSEUM_QUESTION",
            "related_resource_id": "q1",
            "related_resource_label": "Duvida sobre visita in situ",
        }
    ]
    assert session.committed is True


async def test_forward_internal_question_rejects_invalid_target_group() -> None:
    direction = _permission(
        "perm-direction",
        name="Director",
        email="direction@example.org",
        group=GroupName.DIRECTION,
    )
    async with _client(questions=[_question()], permissions=[direction]) as (
        client,
        repo,
        _,
        _session,
        _storage,
    ):
        resp = await client.post(
            f"{_INTERNAL_URL}/q1/forward",
            json={"targetPermissionId": "perm-direction"},
        )
    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_PERMISSION_TARGET"
    assert repo.questions["q1"].assigned_to is None


async def test_forward_internal_question_rejects_answered_question() -> None:
    assignee = _permission(
        "perm-curator",
        name="Curator",
        email="curator@example.org",
        group=GroupName.CURATORIAL,
    )
    async with _client(
        questions=[_question(status=MuseumQuestionStatus.ANSWERED)],
        permissions=[assignee],
    ) as (client, repo, _, _session, _storage):
        resp = await client.post(
            f"{_INTERNAL_URL}/q1/forward",
            json={"targetPermissionId": "perm-curator"},
        )
    assert resp.status_code == 409
    assert repo.questions["q1"].assigned_to is None


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
        _storage,
    ):
        resp = await client.patch(f"{_INTERNAL_URL}/q1/close")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CLOSED"
    assert repo.questions["q1"].closed_by == _STAFF.id
    assert sender.answers == []
    assert sender.out_of_scope == []


async def test_close_submitted_internal_question_is_rejected() -> None:
    async with _client(questions=[_question()]) as (client, _, _, _, _storage):
        resp = await client.patch(f"{_INTERNAL_URL}/q1/close")
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_MUSEUM_QUESTION_TRANSITION"
