"""Encryption wrapper for file storage adapters.

Encrypts file content with AES-256-GCM before delegating writes, and decrypts it
on reads. It implements the same structural shape as the file-storage protocols
declared by the bounded contexts, so composition roots can wrap storage without
changing use-case signatures.

The ``file_reference`` is not encrypted. It remains the storage address and is
used as GCM associated data, binding the ciphertext to that reference.
"""

from __future__ import annotations

import os
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION_AES_256_GCM = 1
_NONCE_BYTES = 12
_TAG_BYTES = 16
_HEADER = 1 + _NONCE_BYTES
_MIN_BLOB_BYTES = _HEADER + _TAG_BYTES


class _InnerStorage(Protocol):
    async def save(self, content: bytes, file_reference: str) -> str: ...
    async def read(self, file_reference: str) -> bytes: ...
    async def delete(self, file_reference: str) -> None: ...


class CorruptedEncryptedFile(Exception):
    """Stored file content failed GCM authenticity verification."""


class EncryptedFileStorage:
    def __init__(self, inner: _InnerStorage, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("key must be exactly 32 bytes")
        self._inner = inner
        self._aes = AESGCM(key)

    async def save(self, content: bytes, file_reference: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        aad = file_reference.encode("utf-8")
        sealed = self._aes.encrypt(nonce, content, aad)
        blob = bytes([_VERSION_AES_256_GCM]) + nonce + sealed
        return await self._inner.save(blob, file_reference)

    async def read(self, file_reference: str) -> bytes:
        raw = await self._inner.read(file_reference)
        if len(raw) < _MIN_BLOB_BYTES or raw[0] != _VERSION_AES_256_GCM:
            raise CorruptedEncryptedFile(file_reference)
        aad = file_reference.encode("utf-8")
        try:
            return self._aes.decrypt(raw[1:_HEADER], raw[_HEADER:], aad)
        except InvalidTag as exc:
            raise CorruptedEncryptedFile(file_reference) from exc

    async def delete(self, file_reference: str) -> None:
        await self._inner.delete(file_reference)
