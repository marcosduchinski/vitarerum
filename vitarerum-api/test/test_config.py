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
