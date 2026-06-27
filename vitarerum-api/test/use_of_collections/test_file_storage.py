from pathlib import Path

import pytest

from app.use_of_collections.infrastructure.file_storage import LocalDiskFileStorage


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
