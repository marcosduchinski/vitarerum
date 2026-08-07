import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from app.collection_object_index.presentation import dependencies as index_deps
from app.document_templates.presentation import dependencies as template_deps
from app.public_submission.presentation import dependencies as submission_deps
from app.shared.file_encryption import EncryptedFileStorage
from app.shared.file_storage import LocalDiskFileStorage, build_file_storage
from app.use_of_collections.presentation import dependencies as collections_deps


async def test_round_trip_into_subfolder(tmp_path: Path) -> None:
    storage = LocalDiskFileStorage(tmp_path)
    content = b"\x00\x01binary payload\xff"
    reference = "log-entries/entry-1/abc123_report.pdf"

    saved = await storage.save(content, reference)

    assert saved == reference
    # The file lands at the readable relative path under the data directory.
    assert (tmp_path / reference).read_bytes() == content
    assert await storage.read(reference) == content


async def test_read_missing_raises(tmp_path: Path) -> None:
    storage = LocalDiskFileStorage(tmp_path)
    with pytest.raises(FileNotFoundError):
        await storage.read("proposals/p-1/does-not-exist.pdf")


async def test_read_rejects_path_traversal(tmp_path: Path) -> None:
    # A secret outside the data directory must not be reachable via "..".
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"top secret")
    data_dir = tmp_path / "data"
    storage = LocalDiskFileStorage(data_dir)

    with pytest.raises(FileNotFoundError):
        await storage.read("../secret.txt")


async def test_save_is_atomic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    storage = LocalDiskFileStorage(tmp_path)
    reference = "proposals/p-1/abc_report.docx"

    await storage.save(b"payload", reference)

    folder = tmp_path / "proposals" / "p-1"
    # Only the final file remains — no leftover ".part" temp files.
    assert [p.name for p in folder.iterdir()] == ["abc_report.docx"]


async def test_delete_removes_file_and_is_idempotent(tmp_path: Path) -> None:
    storage = LocalDiskFileStorage(tmp_path)
    reference = "proposals/p-1/abc_report.docx"
    await storage.save(b"payload", reference)

    await storage.delete(reference)
    assert not (tmp_path / reference).exists()
    # Deleting again is a no-op (no error).
    await storage.delete(reference)


def test_build_file_storage_returns_plain_storage_without_key(tmp_path: Path) -> None:
    storage = build_file_storage(tmp_path, "")

    assert isinstance(storage, LocalDiskFileStorage)


def test_build_file_storage_wraps_storage_when_key_is_configured(
    tmp_path: Path,
) -> None:
    key = base64.b64encode(b"k" * 32).decode("ascii")
    storage = build_file_storage(tmp_path, key)

    assert isinstance(storage, EncryptedFileStorage)


@pytest.mark.parametrize(
    "settings_owner, storage_factory",
    [
        (collections_deps, collections_deps.get_file_storage),
        (index_deps, index_deps.get_file_storage),
        (template_deps, template_deps.get_file_storage),
        (
            submission_deps,
            lambda: submission_deps.get_submit_use_case(cast(Any, object()))._storage,
        ),
        (
            submission_deps,
            lambda: submission_deps.get_confirm_use_case(cast(Any, object()))._storage,
        ),
        (
            submission_deps,
            lambda: submission_deps.get_submit_amendment_document(
                cast(Any, object())
            )._storage,
        ),
        (
            submission_deps,
            lambda: submission_deps.get_remove_amendment_document(
                cast(Any, object())
            )._storage,
        ),
    ],
)
async def test_file_storage_dependencies_use_configured_encryption_key(
    settings_owner: Any,
    storage_factory: Callable[[], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = base64.b64encode(b"k" * 32).decode("ascii")
    monkeypatch.setattr(settings_owner.settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings_owner.settings, "file_encryption_key", key)
    monkeypatch.setattr(settings_owner.settings, "jwt_secret", "x" * 32)

    storage = storage_factory()
    await storage.save(b"payload", "context/file.txt")

    assert isinstance(storage, EncryptedFileStorage)
    assert (tmp_path / "context/file.txt").read_bytes() != b"payload"
    assert await storage.read("context/file.txt") == b"payload"
