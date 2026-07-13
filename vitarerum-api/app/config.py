from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai.museum_question_triage.domain.models import UseCategory

_LOCAL_ENVS = {"local", "test", "development"}


class Settings(BaseSettings):
    app_name: str = "vitarerum-api"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+asyncpg://vitarerum:vitarerum@localhost:5432/vitarerum"
    )
    data_dir: Path = Path("./data")
    # Maximum accepted upload size in bytes (default 25 MiB); larger uploads 413.
    max_upload_bytes: int = 25 * 1024 * 1024
    # Institution name used as the place_name when exporting in-situ visit records.
    institution_name: str = "Museum"
    cors_origins: list[str] = ["*"]
    jwt_secret: str = "change-me-too-local-dev-secret-32b"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12
    # Ollama (shared by the AI-assisted contexts).
    # For Ollama Cloud, set OLLAMA_BASE_URL=https://ollama.com and provide
    # OLLAMA_API_KEY; an empty key targets a local/self-hosted Ollama.
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = ""
    # KG-RAG museum-narrative generation (local Llama via Ollama).
    narrative_model: str = "llama3.1:8b"
    narrative_timeout_seconds: float = 60.0
    # Museum-question triage (in/out-of-scope classification + object
    # extraction, local Llama via Ollama).
    triage_model: str = "llama3.1:8b"
    triage_timeout_seconds: float = 60.0
    use_category_classification_enabled: bool = False
    use_category_embedding_shadow_enabled: bool = False
    use_category_embedding_model: str = "nomic-embed-text"
    use_category_embedding_low_threshold: float = 0.58
    use_category_embedding_high_threshold: float = 0.74
    use_category_embedding_long_message_words: int = 80
    use_category_embedding_profile_version: str = "embedding-prototypes-v1"
    use_category_embedding_prototype_source: Literal["PROMOTED", "JSON_SEED"] = (
        "PROMOTED"
    )
    use_category_operational_classifier: Literal[
        "LLM", "CASCADE_SEED", "CASCADE_CALIBRATED"
    ] = "LLM"
    use_category_cascade_enabled: bool = False
    use_category_cascade_margin_delta: float = 0.08
    use_category_cascade_classifier_version: str = "cascade-v1"
    use_category_cascade_category_high_thresholds: dict[str, float] = {}
    # Public proposal submission (unauthenticated citizen intake, double opt-in).
    # Default is Cloudflare's always-passing test secret key; override in prod.
    turnstile_secret_key: str = "1x0000000000000000000000000000000AA"
    turnstile_verify_url: str = (
        "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    )
    public_origin: str = "http://localhost:4200"
    public_confirm_token_ttl_hours: int = 24
    # Self-service password reset (identity). Short TTL narrows the attack
    # window for a leaked link; the path is configurable so the backend isn't
    # coupled to a fixed frontend route.
    password_reset_token_ttl_minutes: int = 60
    password_reset_public_path: str = "/reset-password"
    # SMTP for confirmation e-mails. Empty smtp_host ⇒ confirmation links are
    # logged instead of sent (local/dev).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str = "no-reply@vitarerum.example"
    smtp_use_tls: bool = True
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_use_category_operational_classifier(self) -> "Settings":
        if (
            self.use_category_operational_classifier != "LLM"
            and not self.use_category_cascade_enabled
        ):
            raise ValueError(
                "use_category_cascade_enabled must be true when "
                "use_category_operational_classifier uses CASCADE"
            )
        if (
            self.use_category_operational_classifier == "CASCADE_SEED"
            and self.use_category_embedding_prototype_source != "JSON_SEED"
        ):
            raise ValueError(
                "CASCADE_SEED requires "
                "use_category_embedding_prototype_source='JSON_SEED'"
            )
        if (
            self.use_category_operational_classifier == "CASCADE_CALIBRATED"
            and self.use_category_embedding_prototype_source != "PROMOTED"
        ):
            raise ValueError(
                "CASCADE_CALIBRATED requires "
                "use_category_embedding_prototype_source='PROMOTED'"
            )
        return self

    @model_validator(mode="after")
    def validate_triage_cascade_thresholds(self) -> "Settings":
        errors: list[str] = []
        for (
            category_value,
            threshold,
        ) in self.use_category_cascade_category_high_thresholds.items():
            try:
                UseCategory(category_value)
            except ValueError:
                errors.append(f"unknown use category {category_value!r}")
            if not 0 <= threshold <= 1:
                errors.append(
                    f"use category {category_value!r} threshold must be between 0 and 1"
                )
        if errors:
            raise ValueError("; ".join(errors))
        return self

    @model_validator(mode="after")
    def validate_non_local_security(self) -> "Settings":
        if self.app_env.lower() in _LOCAL_ENVS:
            return self
        errors: list[str] = []
        if self.jwt_secret == "change-me-too-local-dev-secret-32b":
            errors.append("jwt_secret must be configured outside local/test")
        if len(self.jwt_secret.encode()) < 32:
            errors.append("jwt_secret must be at least 32 bytes")
        if self.turnstile_secret_key.startswith("1x0000"):
            errors.append("turnstile_secret_key must be configured outside local/test")
        if not self.smtp_host:
            errors.append(
                "smtp_host must be configured outside local/test "
                "(otherwise confirmation e-mails are only logged, not sent)"
            )
        if "*" in self.cors_origins:
            errors.append("cors_origins cannot contain '*' outside local/test")
        if errors:
            raise ValueError("; ".join(errors))
        return self


settings = Settings()
