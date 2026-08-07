"""Application-level encryption for sensitive database fields."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
from hashlib import sha256
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_INFO_AES = b"vitarerum/field-encryption/aes-gcm/v1"
_INFO_HMAC = b"vitarerum/field-lookup/hmac/v1"
_VERSION = "v1"
_PREFIX = f"{_VERSION}:"
_NONCE_BYTES = 12


class CorruptedEncryptedField(Exception):
    """A stored encrypted database field could not be decoded or authenticated."""


class FieldEncryptor:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("key must be exactly 32 bytes")
        self._aes = AESGCM(_derive_key(key, _INFO_AES))
        self._hmac_key = _derive_key(key, _INFO_HMAC)

    @classmethod
    def from_base64(cls, key: str) -> FieldEncryptor:
        if not key:
            raise ValueError("db_field_encryption_key must be configured")
        try:
            raw = base64.b64decode(key, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("db_field_encryption_key must be valid base64") from None
        return cls(raw)

    def encrypt_text(self, value: str | None, aad: str) -> str | None:
        if value is None:
            return None
        nonce = os.urandom(_NONCE_BYTES)
        sealed = self._aes.encrypt(nonce, value.encode("utf-8"), _aad(aad))
        return _PREFIX + base64.b64encode(nonce + sealed).decode("ascii")

    def encrypt_required_text(self, value: str, aad: str) -> str:
        return self.encrypt_text(value, aad) or ""

    def decrypt_text(self, value: str | None, aad: str) -> str | None:
        if value is None:
            return None
        raw = self._decode_value(value)
        try:
            return self._aes.decrypt(
                raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], _aad(aad)
            ).decode("utf-8")
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise CorruptedEncryptedField(aad) from exc

    def encrypt_json(self, value: object | None, aad: str) -> str | None:
        if value is None:
            return None
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
        return self.encrypt_text(encoded, aad)

    def decrypt_json(self, value: str | None, aad: str) -> Any | None:
        decoded = self.decrypt_text(value, aad)
        if decoded is None:
            return None
        try:
            return json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise CorruptedEncryptedField(aad) from exc

    def lookup_hash(self, value: str | None, aad: str) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower().encode("utf-8")
        message = _aad(aad) + b"\0" + normalized
        return hmac.new(self._hmac_key, message, sha256).hexdigest()

    def lookup_required_hash(self, value: str, aad: str) -> str:
        return self.lookup_hash(value, aad) or ""

    def _decode_value(self, value: str) -> bytes:
        if not value.startswith(_PREFIX):
            raise CorruptedEncryptedField("unsupported field encryption version")
        payload = value[len(_PREFIX) :]
        try:
            raw = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise CorruptedEncryptedField("invalid encrypted field payload") from exc
        if len(raw) <= _NONCE_BYTES:
            raise CorruptedEncryptedField("truncated encrypted field payload")
        return raw


def _derive_key(key: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    ).derive(key)


def _aad(aad: str) -> bytes:
    return aad.encode("utf-8")
