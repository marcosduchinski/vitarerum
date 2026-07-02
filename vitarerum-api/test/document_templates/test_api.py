"""API tests for the Document Templates context.

Uses in-memory fakes wired through FastAPI dependency overrides — no database.
"""

import io
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.document_templates.domain.models import (
    DocumentTemplate,
    DocumentTemplateId,
)
from app.document_templates.presentation.dependencies import (
    get_clock,
    get_file_storage,
    get_repository,
)
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission
from app.shared.kernel import UseType

_STAFF = Actor(
    id=PermissionId("permission-staff"),
    group=GroupName.CURATORIAL,
    email="staff@example.org",
)
_EXTERNAL = Actor(
    id=PermissionId("permission-ext"),
    group=GroupName.EXTERNAL,
    email="cit@example.org",
)
_NOW = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


def _docx_bytes(marker: str = "hello") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", marker)
    return buffer.getvalue()


class _FakeRepo:
    def __init__(self) -> None:
        self.items: dict[str, DocumentTemplate] = {}

    async def add(self, template: DocumentTemplate) -> None:
        self.items[template.id] = template

    async def get_by_id(
        self, template_id: DocumentTemplateId
    ) -> DocumentTemplate | None:
        return self.items.get(template_id)

    async def list_by_use_type(
        self, use_type: UseType, active_only: bool
    ) -> list[DocumentTemplate]:
        out = [
            t
            for t in self.items.values()
            if t.use_type == use_type and (t.active or not active_only)
        ]
        return sorted(out, key=lambda t: (t.display_order, t.title))

    async def list_all(
        self, use_type: UseType | None
    ) -> list[DocumentTemplate]:
        out = [
            t
            for t in self.items.values()
            if use_type is None or t.use_type == use_type
        ]
        return sorted(out, key=lambda t: (t.use_type.value, t.display_order))

    async def save(self, template: DocumentTemplate) -> None:
        self.items[template.id] = template

    async def delete(self, template_id: DocumentTemplateId) -> None:
        self.items.pop(template_id, None)


class _FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def save(self, content: bytes, file_reference: str) -> str:
        self.files[file_reference] = content
        return file_reference

    async def read(self, file_reference: str) -> bytes:
        if file_reference not in self.files:
            raise FileNotFoundError(file_reference)
        return self.files[file_reference]

    async def delete(self, file_reference: str) -> None:
        self.files.pop(file_reference, None)


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


class _FakeSession:
    def __init__(self, commit_fails: bool = False) -> None:
        self._commit_fails = commit_fails

    async def commit(self) -> None:
        if self._commit_fails:
            raise RuntimeError("commit failed")


@asynccontextmanager
async def _client(
    caller: Actor = _STAFF,
    commit_fails: bool = False,
) -> AsyncIterator[tuple[AsyncClient, _FakeRepo, _FakeStorage]]:
    repo = _FakeRepo()
    storage = _FakeStorage()
    from app.document_templates.presentation import dependencies as deps

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_file_storage] = lambda: storage
    app.dependency_overrides[get_clock] = lambda: _FakeClock()
    app.dependency_overrides[deps.get_async_session] = lambda: _FakeSession(
        commit_fails
    )
    app.dependency_overrides[get_caller_permission] = lambda: caller
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client, repo, storage
    finally:
        app.dependency_overrides.clear()


def _seed(
    repo: _FakeRepo,
    storage: _FakeStorage,
    *,
    template_id: str,
    use_type: UseType = UseType.IN_SITU_VISIT,
    active: bool = True,
    mandatory: bool = True,
) -> None:
    reference = f"document_templates/{template_id}/form.docx"
    storage.files[reference] = _docx_bytes(template_id)
    repo.items[template_id] = DocumentTemplate(
        id=DocumentTemplateId(template_id),
        use_type=use_type,
        title=f"Template {template_id}",
        description="desc",
        mandatory=mandatory,
        active=active,
        display_order=0,
        file_name="form.docx",
        file_reference=reference,
        uploaded_by=PermissionId("permission-staff"),
        uploaded_at=_NOW,
    )


# ── Public endpoints ──────────────────────────────────────────────────────────


async def test_public_list_returns_only_active_for_use_type() -> None:
    async with _client() as (client, repo, storage):
        _seed(repo, storage, template_id="t1", use_type=UseType.IN_SITU_VISIT)
        _seed(
            repo,
            storage,
            template_id="t2",
            use_type=UseType.IN_SITU_VISIT,
            active=False,
        )
        _seed(repo, storage, template_id="t3", use_type=UseType.EXHIBITION)

        response = await client.get(
            "/api/v1/public/document-templates?useType=IN_SITU_VISIT"
        )

    assert response.status_code == 200
    body = response.json()
    assert [t["id"] for t in body] == ["t1"]
    assert body[0].keys() == {"id", "title", "description", "mandatory"}


async def test_public_download_streams_docx() -> None:
    async with _client() as (client, repo, storage):
        _seed(repo, storage, template_id="t1")

        response = await client.get(
            "/api/v1/public/document-templates/t1/file"
        )

    assert response.status_code == 200
    assert response.content == _docx_bytes("t1")
    assert 'filename="form.docx"' in response.headers["content-disposition"]


async def test_public_download_missing_returns_404() -> None:
    async with _client() as (client, _, _):
        response = await client.get(
            "/api/v1/public/document-templates/nope/file"
        )
    assert response.status_code == 404
    assert response.json()["error"] == "DOCUMENT_TEMPLATE_NOT_FOUND"


# ── Staff endpoints ───────────────────────────────────────────────────────────


async def test_staff_create_persists_template_and_file() -> None:
    async with _client() as (client, repo, storage):
        response = await client.post(
            "/api/v1/document-templates",
            data={
                "useType": "IN_SITU_VISIT",
                "title": "Safety form",
                "description": "Fill and sign",
                "mandatory": "true",
                "active": "true",
                "displayOrder": "1",
            },
            files={"file": ("safety.docx", _docx_bytes(), "application/octet-stream")},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Safety form"
    assert body["useType"] == "IN_SITU_VISIT"
    assert body["fileName"] == "safety.docx"
    assert len(repo.items) == 1
    assert len(storage.files) == 1


async def test_staff_create_sanitizes_traversal_filename() -> None:
    async with _client() as (client, repo, storage):
        response = await client.post(
            "/api/v1/document-templates",
            data={"useType": "IN_SITU_VISIT", "title": "Safety"},
            files={
                "file": (
                    "../../etc/evil.docx",
                    _docx_bytes(),
                    "application/octet-stream",
                ),
            },
        )

    assert response.status_code == 201
    assert response.json()["fileName"] == "evil.docx"
    reference = next(iter(storage.files))
    assert ".." not in reference
    assert reference.endswith("/evil.docx")


async def test_public_download_uses_safe_content_disposition() -> None:
    async with _client() as (client, repo, storage):
        created = await client.post(
            "/api/v1/document-templates",
            data={"useType": "IN_SITU_VISIT", "title": "Safety"},
            files={
                "file": (
                    "sub/dir/report.docx",
                    _docx_bytes(),
                    "application/octet-stream",
                ),
            },
        )
        template_id = created.json()["id"]
        response = await client.get(
            f"/api/v1/public/document-templates/{template_id}/file"
        )

    assert created.json()["fileName"] == "report.docx"
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    # The header carries only the sanitised basename — no path separators.
    assert 'filename="report.docx"' in disposition
    assert "/" not in disposition
    assert "\n" not in disposition and "\r" not in disposition


async def test_staff_create_cleans_up_file_when_commit_fails() -> None:
    async with _client(commit_fails=True) as (client, repo, storage):
        try:
            await client.post(
                "/api/v1/document-templates",
                data={"useType": "IN_SITU_VISIT", "title": "Safety"},
                files={
                    "file": (
                        "safety.docx",
                        _docx_bytes(),
                        "application/octet-stream",
                    ),
                },
            )
        except RuntimeError:
            pass  # the app re-raises after cleanup; the effect is what matters

    # The just-written file must not be left orphaned on the failed commit.
    assert storage.files == {}


async def test_staff_create_rejects_non_docx() -> None:
    async with _client() as (client, repo, _):
        response = await client.post(
            "/api/v1/document-templates",
            data={"useType": "IN_SITU_VISIT", "title": "Bad"},
            files={"file": ("note.txt", b"not a docx", "text/plain")},
        )
    assert response.status_code == 415
    assert response.json()["error"] == "INVALID_FILE_FORMAT"
    assert repo.items == {}


async def test_staff_list_includes_inactive() -> None:
    async with _client() as (client, repo, storage):
        _seed(repo, storage, template_id="t1", active=True)
        _seed(repo, storage, template_id="t2", active=False)

        response = await client.get("/api/v1/document-templates")

    assert response.status_code == 200
    assert {t["id"] for t in response.json()} == {"t1", "t2"}


async def test_staff_patch_updates_metadata() -> None:
    async with _client() as (client, repo, storage):
        _seed(repo, storage, template_id="t1", mandatory=True, active=True)

        response = await client.patch(
            "/api/v1/document-templates/t1",
            json={
                "title": "Renamed",
                "description": "new",
                "mandatory": False,
                "active": False,
                "displayOrder": 5,
            },
        )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    assert repo.items["t1"].mandatory is False
    assert repo.items["t1"].active is False
    assert repo.items["t1"].display_order == 5


async def test_staff_patch_missing_returns_404() -> None:
    async with _client() as (client, _, _):
        response = await client.patch(
            "/api/v1/document-templates/nope",
            json={"title": "x"},
        )
    assert response.status_code == 404


async def test_staff_replace_file_swaps_stored_bytes() -> None:
    async with _client() as (client, repo, storage):
        _seed(repo, storage, template_id="t1")
        old_reference = repo.items["t1"].file_reference

        response = await client.put(
            "/api/v1/document-templates/t1/file",
            files={"file": ("v2.docx", _docx_bytes("v2"), "application/octet-stream")},
        )

    assert response.status_code == 200
    assert repo.items["t1"].file_name == "v2.docx"
    assert old_reference not in storage.files
    assert storage.files[repo.items["t1"].file_reference] == _docx_bytes("v2")


async def test_staff_delete_removes_template_and_file() -> None:
    async with _client() as (client, repo, storage):
        _seed(repo, storage, template_id="t1")

        response = await client.delete("/api/v1/document-templates/t1")

    assert response.status_code == 204
    assert repo.items == {}
    assert storage.files == {}


async def test_staff_endpoints_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as (client, repo, storage):
        _seed(repo, storage, template_id="t1")
        response = await client.get("/api/v1/document-templates")
    assert response.status_code == 403
