import base64

import pytest
from pydantic import ValidationError

from app.config import Settings

VALID_FILE_ENCRYPTION_KEY = base64.b64encode(b"a" * 32).decode("ascii")
VALID_DB_FIELD_ENCRYPTION_KEY = base64.b64encode(b"b" * 32).decode("ascii")


@pytest.fixture(autouse=True)
def _settings_read_no_ambient_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build every Settings in this module from in-code defaults alone.

    ``_env_file=None`` keeps the repo's .env out, but a real environment
    variable outranks a dotenv file in pydantic-settings, so an exported
    ``INSTITUTION_NAME`` would still decide what these assertions see. Every
    field name is cleared, so a field added later is covered without an edit.
    """
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


def test_local_settings_allow_development_defaults() -> None:
    # _env_file=None isolates the assertion from the repo's dev .env, which
    # overrides jwt_secret/cors_origins; this test checks the in-code defaults.
    settings = Settings(app_env="local", _env_file=None)

    assert settings.jwt_secret == "change-me-too-local-dev-secret-32b"
    assert settings.cors_origins == ["*"]


def test_non_local_settings_reject_placeholder_secrets_and_wildcard_cors() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(app_env="production", _env_file=None)

    message = str(exc.value)
    assert "jwt_secret must be configured" in message
    assert "file_encryption_key must be configured" in message
    assert "db_field_encryption_key must be configured" in message
    assert "turnstile_secret_key must be configured" in message
    assert "smtp_host must be configured" in message
    assert "cors_origins cannot contain '*'" in message
    assert "institution_name must be configured" in message


def test_non_local_settings_require_strong_jwt_secret() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="production",
            jwt_secret="too-short",
            cors_origins=["https://app.example.org"],
        )

    assert "jwt_secret must be at least 32 bytes" in str(exc.value)


def test_non_local_settings_accept_explicit_security_values() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret="a-production-jwt-secret-with-32-bytes",
        file_encryption_key=VALID_FILE_ENCRYPTION_KEY,
        db_field_encryption_key=VALID_DB_FIELD_ENCRYPTION_KEY,
        turnstile_secret_key="a-real-turnstile-secret",
        smtp_host="smtp.example.org",
        cors_origins=["https://app.example.org"],
        institution_name="Museu Nacional de História Natural e da Ciência",
    )

    assert settings.app_env == "production"


def test_non_local_settings_require_file_encryption_key() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="production",
            jwt_secret="a-production-jwt-secret-with-32-bytes",
            turnstile_secret_key="a-real-turnstile-secret",
            smtp_host="smtp.example.org",
            cors_origins=["https://app.example.org"],
            _env_file=None,
        )

    assert "file_encryption_key must be configured" in str(exc.value)


def test_non_local_settings_require_db_field_encryption_key() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="production",
            jwt_secret="a-production-jwt-secret-with-32-bytes",
            file_encryption_key=VALID_FILE_ENCRYPTION_KEY,
            turnstile_secret_key="a-real-turnstile-secret",
            smtp_host="smtp.example.org",
            cors_origins=["https://app.example.org"],
            _env_file=None,
        )

    assert "db_field_encryption_key must be configured" in str(exc.value)


def test_file_encryption_key_must_be_valid_base64_in_local() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="local",
            file_encryption_key="not base64!",
            _env_file=None,
        )

    assert "file_encryption_key must be valid base64" in str(exc.value)


def test_file_encryption_key_must_decode_to_32_bytes_in_local() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="local",
            file_encryption_key=base64.b64encode(b"too-short").decode("ascii"),
            _env_file=None,
        )

    assert "file_encryption_key must decode to exactly 32 bytes" in str(exc.value)


def test_db_field_encryption_key_must_be_valid_base64_in_local() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="local",
            db_field_encryption_key="not base64!",
            _env_file=None,
        )

    assert "db_field_encryption_key must be valid base64" in str(exc.value)


def test_db_field_encryption_key_must_decode_to_32_bytes_in_local() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="local",
            db_field_encryption_key=base64.b64encode(b"too-short").decode("ascii"),
            _env_file=None,
        )

    assert "db_field_encryption_key must decode to exactly 32 bytes" in str(exc.value)


def test_local_settings_allow_empty_file_encryption_key() -> None:
    settings = Settings(app_env="local", file_encryption_key="", _env_file=None)

    assert settings.file_encryption_key == ""


def test_local_settings_allow_empty_db_field_encryption_key() -> None:
    settings = Settings(app_env="local", db_field_encryption_key="", _env_file=None)

    assert settings.db_field_encryption_key == ""


def test_gmail_app_password_spaces_are_removed() -> None:
    settings = Settings(
        app_env="local",
        smtp_host="smtp.gmail.com",
        smtp_password="abcd efgh ijkl mnop",
        _env_file=None,
    )

    assert settings.smtp_password == "abcdefghijklmnop"


def test_non_gmail_smtp_password_spaces_are_preserved() -> None:
    settings = Settings(
        app_env="local",
        smtp_host="smtp.example.org",
        smtp_password="keep this space",
        _env_file=None,
    )

    assert settings.smtp_password == "keep this space"


def test_a_generation_ceiling_of_zero_is_refused() -> None:
    """Ollama reads a non-positive num_predict as unlimited, which is the bug."""

    with pytest.raises(ValidationError) as error:
        Settings(app_env="local", scientific_return_llm_num_predict=0, _env_file=None)

    assert "num_predict" in str(error.value)


def test_a_total_llm_timeout_below_the_chunk_timeout_is_refused() -> None:
    """The adapter would raise it silently, honouring a limit nobody asked for."""

    with pytest.raises(ValidationError) as error:
        Settings(
            app_env="local",
            scientific_return_llm_timeout_seconds=600,
            scientific_return_llm_total_timeout_seconds=100,
            _env_file=None,
        )

    assert "scientific_return_llm_total_timeout_seconds" in str(error.value)


def test_a_worker_slice_shorter_than_one_model_call_is_refused() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            app_env="local",
            scientific_return_llm_total_timeout_seconds=300,
            scientific_return_full_agentic_run_deadline_seconds=120,
            _env_file=None,
        )

    assert "run_deadline" in str(error.value)
