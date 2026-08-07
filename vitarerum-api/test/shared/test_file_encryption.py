import os

import pytest

from app.shared.file_encryption import CorruptedEncryptedFile, EncryptedFileStorage


class CapturingStorage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, content: bytes, file_reference: str) -> str:
        self.saved[file_reference] = content
        return file_reference

    async def read(self, file_reference: str) -> bytes:
        return self.saved[file_reference]

    async def delete(self, file_reference: str) -> None:
        self.deleted.append(file_reference)


class PathIgnoringStorage(CapturingStorage):
    async def read(self, file_reference: str) -> bytes:
        return next(iter(self.saved.values()))


def _key() -> bytes:
    return b"k" * 32


async def test_round_trip_returns_original_content() -> None:
    inner = CapturingStorage()
    storage = EncryptedFileStorage(inner, _key())

    await storage.save(b"secret payload", "a/file.pdf")

    assert await storage.read("a/file.pdf") == b"secret payload"


async def test_saved_blob_does_not_contain_plaintext() -> None:
    inner = CapturingStorage()
    storage = EncryptedFileStorage(inner, _key())

    await storage.save(b"secret payload", "a/file.pdf")

    assert b"secret payload" not in inner.saved["a/file.pdf"]


async def test_same_content_saves_with_distinct_nonce() -> None:
    inner = CapturingStorage()
    storage = EncryptedFileStorage(inner, _key())

    await storage.save(b"same payload", "a/one.pdf")
    await storage.save(b"same payload", "a/two.pdf")

    assert inner.saved["a/one.pdf"] != inner.saved["a/two.pdf"]


async def test_ciphertext_tampering_raises_corrupted_file() -> None:
    inner = CapturingStorage()
    storage = EncryptedFileStorage(inner, _key())
    await storage.save(b"secret payload", "a/file.pdf")
    blob = bytearray(inner.saved["a/file.pdf"])
    blob[-1] ^= 1
    inner.saved["a/file.pdf"] = bytes(blob)

    with pytest.raises(CorruptedEncryptedFile):
        await storage.read("a/file.pdf")


async def test_wrong_key_raises_corrupted_file() -> None:
    inner = CapturingStorage()
    writer = EncryptedFileStorage(inner, _key())
    reader = EncryptedFileStorage(inner, b"w" * 32)
    await writer.save(b"secret payload", "a/file.pdf")

    with pytest.raises(CorruptedEncryptedFile):
        await reader.read("a/file.pdf")


async def test_aad_binds_blob_to_file_reference() -> None:
    inner = PathIgnoringStorage()
    storage = EncryptedFileStorage(inner, _key())
    await storage.save(b"secret payload", "a/x.pdf")

    with pytest.raises(CorruptedEncryptedFile):
        await storage.read("b/x.pdf")


async def test_blob_without_version_header_raises_corrupted_file() -> None:
    inner = CapturingStorage()
    inner.saved["legacy/file.pdf"] = b"%PDF plaintext"
    storage = EncryptedFileStorage(inner, _key())

    with pytest.raises(CorruptedEncryptedFile):
        await storage.read("legacy/file.pdf")


async def test_truncated_versioned_blob_raises_corrupted_file() -> None:
    inner = CapturingStorage()
    inner.saved["truncated/file.pdf"] = b"\x01short"
    storage = EncryptedFileStorage(inner, _key())

    with pytest.raises(CorruptedEncryptedFile):
        await storage.read("truncated/file.pdf")


def test_invalid_key_length_is_rejected() -> None:
    with pytest.raises(ValueError, match="key must be exactly 32 bytes"):
        EncryptedFileStorage(CapturingStorage(), os.urandom(31))


async def test_empty_file_round_trips() -> None:
    inner = CapturingStorage()
    storage = EncryptedFileStorage(inner, _key())

    await storage.save(b"", "a/empty.pdf")

    assert await storage.read("a/empty.pdf") == b""


async def test_delete_delegates_to_inner_storage() -> None:
    inner = CapturingStorage()
    storage = EncryptedFileStorage(inner, _key())

    await storage.delete("a/file.pdf")

    assert inner.deleted == ["a/file.pdf"]
