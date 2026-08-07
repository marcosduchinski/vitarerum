import pytest

from app.shared.field_encryption import CorruptedEncryptedField, FieldEncryptor


def _encryptor() -> FieldEncryptor:
    return FieldEncryptor(b"k" * 32)


def test_text_round_trip_returns_original_value() -> None:
    encryptor = _encryptor()

    encrypted = encryptor.encrypt_text("secret value", "table.column")

    assert encryptor.decrypt_text(encrypted, "table.column") == "secret value"


def test_ciphertext_does_not_contain_plaintext() -> None:
    encrypted = _encryptor().encrypt_text("secret value", "table.column")

    assert encrypted is not None
    assert "secret value" not in encrypted


def test_same_value_encrypts_with_distinct_nonce() -> None:
    encryptor = _encryptor()

    first = encryptor.encrypt_text("same", "table.column")
    second = encryptor.encrypt_text("same", "table.column")

    assert first != second


def test_aad_mismatch_raises_corrupted_field() -> None:
    encryptor = _encryptor()
    encrypted = encryptor.encrypt_text("secret", "table.column")

    with pytest.raises(CorruptedEncryptedField):
        encryptor.decrypt_text(encrypted, "table.other_column")


def test_invalid_key_length_is_rejected() -> None:
    with pytest.raises(ValueError, match="key must be exactly 32 bytes"):
        FieldEncryptor(b"k" * 31)


def test_none_remains_none() -> None:
    encryptor = _encryptor()

    assert encryptor.encrypt_text(None, "table.column") is None
    assert encryptor.decrypt_text(None, "table.column") is None
    assert encryptor.lookup_hash(None, "table.column") is None


def test_email_hash_is_normalized_and_stable() -> None:
    encryptor = _encryptor()

    assert encryptor.lookup_hash(" Ana@Example.Org ", "table.email") == (
        encryptor.lookup_hash("ana@example.org", "table.email")
    )


def test_hash_changes_with_aad() -> None:
    encryptor = _encryptor()

    assert encryptor.lookup_hash("ana@example.org", "table.email") != (
        encryptor.lookup_hash("ana@example.org", "table.other_email")
    )


def test_missing_prefix_raises_corrupted_field() -> None:
    with pytest.raises(CorruptedEncryptedField):
        _encryptor().decrypt_text("plaintext", "table.column")


def test_unknown_version_raises_corrupted_field() -> None:
    with pytest.raises(CorruptedEncryptedField):
        _encryptor().decrypt_text("v2:abcd", "table.column")


def test_invalid_base64_raises_corrupted_field() -> None:
    with pytest.raises(CorruptedEncryptedField):
        _encryptor().decrypt_text("v1:not base64!", "table.column")


def test_tampered_ciphertext_raises_corrupted_field() -> None:
    encryptor = _encryptor()
    encrypted = encryptor.encrypt_text("secret", "table.column")
    assert encrypted is not None
    tampered = encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B")

    with pytest.raises(CorruptedEncryptedField):
        encryptor.decrypt_text(tampered, "table.column")


def test_json_round_trip_returns_original_value() -> None:
    encryptor = _encryptor()
    value = [{"field": "message", "reason": "missing"}]

    encrypted = encryptor.encrypt_json(value, "table.json_column")

    assert encryptor.decrypt_json(encrypted, "table.json_column") == value


def test_json_decode_failure_raises_corrupted_field() -> None:
    encryptor = _encryptor()
    encrypted = encryptor.encrypt_text("not json", "table.json_column")

    with pytest.raises(CorruptedEncryptedField):
        encryptor.decrypt_json(encrypted, "table.json_column")
