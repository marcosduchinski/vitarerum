import pytest
from pydantic import ValidationError

from app.config import Settings


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
        turnstile_secret_key="a-real-turnstile-secret",
        smtp_host="smtp.example.org",
        cors_origins=["https://app.example.org"],
    )

    assert settings.app_env == "production"
