from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.database import get_async_session
from app.main import app
from app.public_submission.application.use_cases import (
    ConfirmPublicProposal,
    SubmitPublicProposal,
)
from app.public_submission.domain.models import (
    PendingPublicSubmission,
    ProposalAmendmentToken,
)
from app.public_submission.infrastructure.amendment import hash_token
from app.public_submission.presentation.dependencies import (
    get_amendment_clock,
    get_amendment_rate_limiter,
    get_amendment_token_repo,
    get_confirm_use_case,
    get_email_sender,
    get_notifications_dispatcher,
    get_proposal_notification_email_sender,
    get_reader,
    get_staff_notification_recipients,
    get_submit_amendment_corrections,
    get_submit_use_case,
    get_uoc_proposal_repo,
)
from app.shared.kernel import PermissionId, UseType
from app.use_of_collections.application.use_cases import SubmitAmendmentCorrections
from app.use_of_collections.domain.enums import (
    DocumentCorrectionStatus,
    ProposalStatus,
    SubmissionChannel,
)
from app.use_of_collections.domain.models import (
    CollectionUseProjectId,
    Document,
    DocumentCorrectionItem,
    DocumentCorrectionItemId,
    DocumentId,
    DocumentType,
    EmailAddress,
    Proposal,
    ProposalId,
    ReferenceNumber,
    RequesterContact,
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


class _Storage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, content: bytes, file_reference: str) -> str:
        self.saved[file_reference] = content
        return file_reference

    async def delete(self, file_reference: str) -> None:
        self.deleted.append(file_reference)
        self.saved.pop(file_reference, None)


class _Submit:
    async def execute(self, data: object) -> SimpleNamespace:
        return SimpleNamespace(
            proposal=SimpleNamespace(
                id="proposal-public-1",
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


class _AmendmentTokenRepo:
    def __init__(self, token: ProposalAmendmentToken) -> None:
        self.token = token

    async def get_by_hash(self, token_hash: str) -> ProposalAmendmentToken | None:
        return self.token if self.token.token_hash == token_hash else None

    async def save(self, token: ProposalAmendmentToken) -> None:
        self.token = token


class _ProposalRepo:
    def __init__(self, proposal: Proposal) -> None:
        self.proposal = proposal

    async def get_by_id(self, proposal_id: ProposalId) -> Proposal | None:
        return self.proposal if self.proposal.id == proposal_id else None

    async def save(self, proposal: Proposal) -> None:
        self.proposal = proposal


class _NotificationDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def notify(self, **kwargs) -> None:
        self.calls.append(kwargs)

    async def notify_many(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _ProposalNotificationEmail:
    def __init__(self) -> None:
        self.submitted: list[dict[str, object]] = []
        self.corrections_submitted: list[dict[str, object]] = []

    async def send_proposal_submitted(self, **kwargs) -> None:
        self.submitted.append(kwargs)

    async def send_proposal_forwarded(self, **kwargs) -> None:
        raise AssertionError("send_proposal_forwarded should not be called")

    async def send_proposal_assigned(self, **kwargs) -> None:
        raise AssertionError("send_proposal_assigned should not be called")

    async def send_proposal_taken_over(self, **kwargs) -> None:
        raise AssertionError("send_proposal_taken_over should not be called")

    async def send_proposal_documents_submitted(self, **kwargs) -> None:
        raise AssertionError("send_proposal_documents_submitted should not be called")

    async def send_proposal_corrections_submitted(self, **kwargs) -> None:
        self.corrections_submitted.append(kwargs)

    async def send_proposal_rejected(self, **kwargs) -> None:
        raise AssertionError("send_proposal_rejected should not be called")


class _PermissionReader:
    async def get_detail(self, permission_id: PermissionId):
        if permission_id == "perm-assignee":
            return SimpleNamespace(
                permission_id="perm-assignee",
                user=SimpleNamespace(
                    id="user-assignee",
                    name="Assignee User",
                    email="assignee@example.test",
                ),
                group="CURATORIAL",
            )
        if permission_id == "perm-requester":
            return SimpleNamespace(
                permission_id="perm-requester",
                user=SimpleNamespace(
                    id="user-requester",
                    name="Requester User",
                    email="requester@example.test",
                ),
                group="EXTERNAL",
            )
        return None

    async def list_by_group(self, group):
        return []


async def _passthrough_retry(op):  # type: ignore[no-untyped-def]
    return await op()


@asynccontextmanager
async def _client(
    *,
    captcha_ok: bool = True,
    rate_limited: bool = False,
    fail_commit: bool = False,
    staff_recipients: list[SimpleNamespace] | None = None,
    notification_dispatcher: _NotificationDispatcher | None = None,
    proposal_email: _ProposalNotificationEmail | None = None,
) -> AsyncIterator[
    tuple[
        AsyncClient,
        _Repo,
        _Email,
        _Storage,
    ]
]:
    repo = _Repo()
    email = _Email()
    storage = _Storage()
    notification_dispatcher = notification_dispatcher or _NotificationDispatcher()
    proposal_email = proposal_email or _ProposalNotificationEmail()
    limiter = _Limiter(block=rate_limited)
    submit_uc = SubmitPublicProposal(
        repository=repo,
        captcha=_Captcha(ok=captcha_ok),
        rate_limiter=limiter,
        clock=_Clock(),
        file_storage=storage,
    )
    confirm_uc = ConfirmPublicProposal(
        repository=repo,
        submit_proposal=_Submit(),  # type: ignore[arg-type]
        rate_limiter=limiter,
        clock=_Clock(),
        token_ttl=timedelta(hours=24),
        retry_runner=_passthrough_retry,
        file_storage=storage,
    )
    app.dependency_overrides[get_submit_use_case] = lambda: submit_uc
    app.dependency_overrides[get_confirm_use_case] = lambda: confirm_uc
    app.dependency_overrides[get_email_sender] = lambda: email
    app.dependency_overrides[get_staff_notification_recipients] = lambda: (
        staff_recipients or []
    )
    app.dependency_overrides[get_notifications_dispatcher] = lambda: (
        notification_dispatcher
    )
    app.dependency_overrides[get_proposal_notification_email_sender] = lambda: (
        proposal_email
    )
    app.dependency_overrides[get_async_session] = lambda: _Session(
        fail_commit=fail_commit
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, repo, email, storage
    finally:
        app.dependency_overrides.clear()


def _payload(**overrides: str) -> dict[str, str]:
    data = {
        "citizenName": "Pedro Silva",
        "citizenEmail": "pedro@example.org",
        "subject": "Acesso à Coleção de Zoologia",
        "body": "Gostaria de estudar um espécime para a minha tese.",
        "useType": "IN_SITU_VISIT",
        "proposedBeginDate": "2026-07-01",
        "proposedEndDate": "2026-07-15",
        "consent": "true",
        "captchaToken": "0.AbC-token",
        "website": "",
    }
    data.update(overrides)
    return data


def _files(
    *items: tuple[str, bytes, str],
) -> list[tuple[str, tuple[str, bytes, str]]]:
    source = items or (("support.pdf", b"%PDF-1.4\n", "application/pdf"),)
    return [("documents", item) for item in source]


async def _post_submit(
    client: AsyncClient,
    *,
    data: dict[str, str] | None = None,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
) -> Response:
    return await client.post(
        _SUBMIT_URL,
        data=_payload() if data is None else data,
        files=_files() if files is None else files,
    )


async def test_submit_returns_202_receipt() -> None:
    async with _client() as (client, repo, email, _):
        resp = await _post_submit(client)
    assert resp.status_code == 202
    assert resp.json() == {
        "status": "PENDING_CONFIRMATION",
        "email": "pedro@example.org",
    }
    assert len(repo.by_token) == 1
    submission = next(iter(repo.by_token.values()))
    assert len(submission.documents) == 1
    assert submission.documents[0].file_name == "support.pdf"
    assert len(email.sent) == 1


async def test_submit_persists_proposed_dates() -> None:
    async with _client() as (client, repo, _, _):
        resp = await _post_submit(
            client,
            data=_payload(proposedBeginDate="2026-08-01", proposedEndDate="2026-08-15"),
        )
    assert resp.status_code == 202
    submission = next(iter(repo.by_token.values()))
    assert submission.proposed_begin_date == date(2026, 8, 1)
    assert submission.proposed_end_date == date(2026, 8, 15)


async def test_submit_missing_proposed_dates_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        payload = _payload()
        del payload["proposedBeginDate"]
        del payload["proposedEndDate"]
        resp = await _post_submit(client, data=payload)
    assert resp.status_code == 422
    assert repo.by_token == {}


async def test_submit_honeypot_returns_202_no_work() -> None:
    async with _client() as (client, repo, email, _):
        resp = await _post_submit(client, data=_payload(website="http://spam"))
    assert resp.status_code == 202
    assert repo.by_token == {}
    assert email.sent == []


async def test_submit_honeypot_skips_document_validation() -> None:
    async with _client() as (client, repo, email, _):
        resp = await _post_submit(
            client,
            data=_payload(website="http://spam"),
            files=[],
        )
    assert resp.status_code == 202
    assert repo.by_token == {}
    assert email.sent == []


async def test_submit_captcha_failure_403() -> None:
    async with _client(captcha_ok=False) as (client, repo, _, _):
        resp = await _post_submit(client)
    assert resp.status_code == 403
    assert resp.json()["message"] == "Captcha verification failed."
    assert repo.by_token == {}


async def test_submit_rate_limited_429_with_retry_after() -> None:
    async with _client(rate_limited=True) as (client, _, _, _):
        resp = await _post_submit(client)
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"


async def test_submit_rate_limited_before_reading_uploads() -> None:
    # The rate-limit / captcha gates must run BEFORE the route buffers and
    # validates uploads, so abusive traffic is shed without the server first
    # reading files into memory. A rate-limited request with no documents must
    # therefore surface 429 (admission), not 422 (document validation).
    async with _client(rate_limited=True) as (client, repo, _, storage):
        resp = await _post_submit(client, files=[])
    assert resp.status_code == 429
    assert repo.by_token == {}
    assert storage.saved == {}


async def test_submit_captcha_checked_before_reading_uploads() -> None:
    async with _client(captcha_ok=False) as (client, repo, _, storage):
        resp = await _post_submit(client, files=[])
    assert resp.status_code == 403
    assert storage.saved == {}


async def test_submit_missing_consent_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        resp = await _post_submit(client, data=_payload(consent="false"))
    assert resp.status_code == 422
    assert repo.by_token == {}


async def test_submit_invalid_use_type_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        resp = await _post_submit(client, data=_payload(useType="WHATEVER"))
    assert resp.status_code == 422
    assert repo.by_token == {}


async def test_submit_missing_documents_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        resp = await _post_submit(client, files=[])
    assert resp.status_code == 422
    assert repo.by_token == {}


async def test_submit_too_many_documents_is_rejected() -> None:
    files = _files(
        ("one.pdf", b"%PDF-1.4\n", "application/pdf"),
        ("two.pdf", b"%PDF-1.4\n", "application/pdf"),
        ("three.pdf", b"%PDF-1.4\n", "application/pdf"),
        ("four.pdf", b"%PDF-1.4\n", "application/pdf"),
        ("five.pdf", b"%PDF-1.4\n", "application/pdf"),
        ("six.pdf", b"%PDF-1.4\n", "application/pdf"),
    )
    async with _client() as (client, repo, _, _):
        resp = await _post_submit(client, files=files)
    assert resp.status_code == 422
    assert repo.by_token == {}


async def test_submit_oversized_document_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        resp = await _post_submit(
            client,
            files=_files(
                (
                    "large.pdf",
                    b"%PDF-1.4\n" + b"x" * (10 * 1024 * 1024),
                    "application/pdf",
                )
            ),
        )
    assert resp.status_code == 413
    assert repo.by_token == {}


async def test_submit_unsupported_document_is_rejected() -> None:
    async with _client() as (client, repo, _, _):
        resp = await _post_submit(
            client,
            files=_files(("notes.txt", b"plain text", "text/plain")),
        )
    assert resp.status_code == 415
    assert repo.by_token == {}


async def test_submit_then_confirm_flow() -> None:
    async with _client() as (client, repo, email, _):
        submitted = await _post_submit(client)
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


async def test_confirm_public_proposal_notifies_staff_once() -> None:
    staff_recipients = [
        SimpleNamespace(
            permission_id="perm-curatorial",
            user=SimpleNamespace(
                id="user-bob",
                name="Bob Santos",
                email="bob@example.test",
            ),
            group="CURATORIAL",
        ),
        SimpleNamespace(
            permission_id="perm-collections",
            user=SimpleNamespace(
                id="user-bob",
                name="Bob Santos",
                email="bob@example.test",
            ),
            group="COLLECTIONS_MANAGEMENT",
        ),
        SimpleNamespace(
            permission_id="perm-direction",
            user=SimpleNamespace(
                id="user-bob",
                name="Bob Santos",
                email="bob@example.test",
            ),
            group="DIRECTION",
        ),
    ]
    notification_dispatcher = _NotificationDispatcher()
    proposal_email = _ProposalNotificationEmail()
    async with _client(
        staff_recipients=staff_recipients,
        notification_dispatcher=notification_dispatcher,
        proposal_email=proposal_email,
    ) as (client, _, email, _):
        submitted = await _post_submit(client)
        assert submitted.status_code == 202
        token = email.sent[0][2]

        confirmed = await client.post(_CONFIRM_URL, json={"token": token})
        again = await client.post(_CONFIRM_URL, json={"token": token})

    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"
    assert again.status_code == 200
    assert again.json()["status"] == "ALREADY_CONFIRMED"
    assert notification_dispatcher.calls == [
        {
            "recipient_permission_ids": [
                PermissionId("perm-curatorial"),
                PermissionId("perm-collections"),
                PermissionId("perm-direction"),
            ],
            "kind": "PROPOSAL_SUBMITTED",
            "triggered_by": None,
            "related_resource_type": "PROPOSAL",
            "related_resource_id": "proposal-public-1",
            "related_resource_label": "VRP-20260626-0007",
        }
    ]
    assert proposal_email.submitted == [
        {
            "to_email": "bob@example.test",
            "recipient_name": "Bob Santos",
            "proposal_reference": "VRP-20260626-0007",
            "submitted_by_name": "Pedro Silva",
            "link": "http://localhost:4200/p/collections/proposals/proposal-public-1",
        },
    ]


async def test_submit_amendment_notifies_assigned_staff() -> None:
    raw_token = "raw-amendment-token"
    token = ProposalAmendmentToken(
        id="token-1",
        proposal_id="prop-1",
        token_hash=hash_token(raw_token),
        requester_email="requester@example.test",
        correction_item_ids=["correction-1"],
        created_at=_NOW,
        expires_at=_NOW + timedelta(hours=1),
    )
    proposal = Proposal(
        id=ProposalId("prop-1"),
        reference_number=ReferenceNumber("VRP-20260626-0007"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("proj-1"),
        intended_use=UseType.IN_SITU_VISIT,
        begin_date=date(2026, 7, 1),
        end_date=date(2026, 7, 15),
        status=ProposalStatus.PENDING,
        requested_by=PermissionId("perm-requester"),
        requester_contact=RequesterContact(
            name="Pedro Silva",
            email=EmailAddress("requester@example.test"),
        ),
        assigned_to=PermissionId("perm-assignee"),
        submitted_at=_NOW,
        submission_channel=SubmissionChannel.PUBLIC,
        documents=[
            Document(
                id=DocumentId("doc-1"),
                type=DocumentType("REQUEST_FORM"),
                file_name="request.docx",
                file_reference="request.docx",
                submitted_at=_NOW,
                submitted_by=None,
            )
        ],
        correction_items=[
            DocumentCorrectionItem(
                id=DocumentCorrectionItemId("correction-1"),
                document_type=DocumentType("REQUEST_FORM"),
                reason="Missing form",
                requested_at=_NOW,
                requested_by=PermissionId("perm-staff"),
                status=DocumentCorrectionStatus.REQUESTED,
            )
        ],
    )
    proposal_repo = _ProposalRepo(proposal)
    token_repo = _AmendmentTokenRepo(token)
    notification_dispatcher = _NotificationDispatcher()
    proposal_email = _ProposalNotificationEmail()
    app.dependency_overrides[get_amendment_token_repo] = lambda: token_repo
    app.dependency_overrides[get_uoc_proposal_repo] = lambda: proposal_repo
    app.dependency_overrides[get_amendment_clock] = lambda: _Clock()
    app.dependency_overrides[get_amendment_rate_limiter] = lambda: _Limiter()
    app.dependency_overrides[get_submit_amendment_corrections] = lambda: (
        SubmitAmendmentCorrections(proposal_repo)  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_notifications_dispatcher] = lambda: (
        notification_dispatcher
    )
    app.dependency_overrides[get_proposal_notification_email_sender] = lambda: (
        proposal_email
    )
    app.dependency_overrides[get_reader] = lambda: _PermissionReader()
    app.dependency_overrides[get_async_session] = lambda: _Session()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/public/proposals/amendments/{raw_token}/submit"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert notification_dispatcher.calls == [
        {
            "recipient_permission_id": "perm-assignee",
            "kind": "PROPOSAL_CORRECTIONS_SUBMITTED",
            "triggered_by": None,
            "related_resource_type": "PROPOSAL",
            "related_resource_id": "prop-1",
            "related_resource_label": "VRP-20260626-0007",
        }
    ]
    assert proposal_email.corrections_submitted == [
        {
            "to_email": "assignee@example.test",
            "recipient_name": "Assignee User",
            "proposal_reference": "VRP-20260626-0007",
            "submitted_by_name": "Requester User",
            "link": (
                "http://localhost:4200/p/collections/proposals/"
                "my-assignments/prop-1?tab=documents"
            ),
        }
    ]
    assert token.used_at == _NOW
    assert proposal.correction_items[0].status == DocumentCorrectionStatus.RESOLVED


async def test_confirm_unknown_token_returns_200_invalid() -> None:
    async with _client() as (client, _, _, _):
        resp = await client.post(_CONFIRM_URL, json={"token": "nope"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "INVALID", "referenceNumber": None}


async def test_submit_does_not_email_when_commit_fails() -> None:
    # Bug #2: the confirmation e-mail must be sent only after the pending row is
    # durably committed. If the commit fails, the citizen must not receive a link
    # whose token was rolled back.
    async with _client(fail_commit=True) as (client, repo, email, storage):
        with pytest.raises(RuntimeError):
            await _post_submit(client)
        assert email.sent == []
        assert storage.saved == {}
        assert len(storage.deleted) == 1
