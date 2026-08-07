import base64

import pytest
from pydantic import ValidationError

from app.config import Settings

VALID_FILE_ENCRYPTION_KEY = base64.b64encode(b"a" * 32).decode("ascii")
VALID_DB_FIELD_ENCRYPTION_KEY = base64.b64encode(b"b" * 32).decode("ascii")


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


def test_settings_reject_invalid_cascade_category_threshold_key() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="local",
            use_category_cascade_category_high_thresholds={"UNKNOWN": 0.7},
            _env_file=None,
        )

    assert "unknown use category 'UNKNOWN'" in str(exc.value)


def test_settings_reject_out_of_range_cascade_category_threshold() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="local",
            use_category_cascade_category_high_thresholds={"RESEARCH_PROJECTS": 1.2},
            _env_file=None,
        )

    assert "threshold must be between 0 and 1" in str(exc.value)


def test_settings_reject_cascade_operational_mode_without_cascade_enabled() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="local",
            use_category_operational_classifier="CASCADE_CALIBRATED",
            _env_file=None,
        )

    assert "use_category_cascade_enabled must be true" in str(exc.value)


def test_settings_reject_cascade_seed_with_promoted_prototype_source() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="local",
            use_category_cascade_enabled=True,
            use_category_operational_classifier="CASCADE_SEED",
            use_category_embedding_prototype_source="PROMOTED",
            _env_file=None,
        )

    assert "CASCADE_SEED requires" in str(exc.value)


def test_settings_accept_cascade_calibrated_operational_mode() -> None:
    settings = Settings(
        app_env="local",
        use_category_cascade_enabled=True,
        use_category_operational_classifier="CASCADE_CALIBRATED",
        use_category_embedding_prototype_source="PROMOTED",
        _env_file=None,
    )

    assert settings.use_category_operational_classifier == "CASCADE_CALIBRATED"
