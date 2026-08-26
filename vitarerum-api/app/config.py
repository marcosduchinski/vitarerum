import base64
import binascii
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    # File encryption key: 32 bytes encoded as base64. Empty local/test means
    # file storage runs without encryption.
    file_encryption_key: str = ""
    # Database field encryption key: 32 bytes encoded as base64.
    db_field_encryption_key: str = ""
    # Institution operating this deployment. Captured on every exported in-situ
    # visit record, as both its place_name and the dcterms:creator of the CIDOC
    # graph. The default is a placeholder and is rejected outside local/test.
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
    # Scientific-return bibliographic discovery. Crossref is queried only with
    # the minimal author/inventory/object terms stored in the project snapshot.
    crossref_base_url: str = "https://api.crossref.org"
    crossref_timeout_seconds: float = 20.0
    crossref_mailto: str = ""
    crossref_max_retries: int = 3
    crossref_retry_base_seconds: float = 1.0
    crossref_min_interval_seconds: float = 0.25
    openalex_base_url: str = "https://api.openalex.org"
    openalex_api_key: str = ""
    openalex_timeout_seconds: float = 20.0
    openalex_max_retries: int = 3
    openalex_retry_base_seconds: float = 1.0
    europe_pmc_enabled: bool = False
    europe_pmc_base_url: str = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    europe_pmc_timeout_seconds: float = 30.0
    europe_pmc_max_retries: int = 3
    europe_pmc_retry_base_seconds: float = 1.0
    europe_pmc_full_text_result_limit: int = 10
    europe_pmc_email: str = ""
    scientific_return_result_limit: int = 20
    scientific_return_max_queries_per_run: int = 40
    # Phase 3B: advisory candidate reasoning only. The model cannot execute
    # tools or make candidate decisions while operating in shadow mode.
    scientific_return_llm_model: str = "llama3.1:8b"
    # Measured against llama3.1:8b on developer hardware: planning took ~40s and
    # reflecting 100-140s, so 60s would have made the deterministic fallback the
    # normal path rather than the exception.
    scientific_return_llm_timeout_seconds: float = 180.0
    # Agentic investigation (E1). SUPERVISED runs a tool only when staff start
    # the cycle explicitly; the server limits always win over any client value.
    scientific_return_agent_mode: str = "DISABLED"
    scientific_return_agent_max_iterations: int = 1
    scientific_return_agent_max_actions: int = 1
    scientific_return_agent_max_queries: int = 4
    scientific_return_agent_max_results: int = 10
    scientific_return_agent_max_new_candidates: int = 5
    scientific_return_agent_allowed_actions: str = "SEARCH_INVENTORY_VARIANTS"
    # Only sources that answer an exact phrase are useful for an inventory
    # lookup; see EXACT_MATCH_SOURCES in the action policy.
    scientific_return_agent_allowed_sources: str = "EUROPE_PMC"
    # Independent, real agentic flow. Its switch and budgets intentionally do
    # not reuse the legacy shadow/policy agent configuration above.
    scientific_return_full_agentic_enabled: bool = False
    scientific_return_full_agentic_sources: str = "CROSSREF,EUROPE_PMC,OPENALEX"
    scientific_return_full_agentic_max_iterations: int = 4
    scientific_return_full_agentic_max_queries: int = 12
    scientific_return_full_agentic_max_results: int = 40
    scientific_return_full_agentic_max_candidates: int = 5
    scientific_return_full_agentic_max_llm_calls: int = 20
    scientific_return_full_agentic_circuit_min_decisions: int = 0
    scientific_return_full_agentic_circuit_min_precision: float = 0.0
    scientific_return_full_agentic_dispatcher: str = "DATABASE"
    scientific_return_cloud_tasks_queue_url: str = ""
    scientific_return_cloud_tasks_worker_url: str = ""
    scientific_return_cloud_tasks_service_account: str = ""
    scientific_return_full_agentic_worker_token: str = ""
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
    def normalize_gmail_app_password(self) -> "Settings":
        # Google displays app passwords in 4-character groups separated by
        # spaces, but SMTP authentication expects the 16 characters only.
        if (
            self.smtp_host.lower() in {"smtp.gmail.com", "smtp.googlemail.com"}
            and self.smtp_password
        ):
            self.smtp_password = "".join(self.smtp_password.split())
        return self

    @model_validator(mode="after")
    def validate_file_encryption_key_format(self) -> "Settings":
        self._validate_optional_base64_32(
            self.file_encryption_key,
            setting_name="file_encryption_key",
        )
        return self

    @model_validator(mode="after")
    def validate_db_field_encryption_key_format(self) -> "Settings":
        self._validate_optional_base64_32(
            self.db_field_encryption_key,
            setting_name="db_field_encryption_key",
        )
        return self

    def _validate_optional_base64_32(self, value: str, *, setting_name: str) -> None:
        if not value:
            return
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError(f"{setting_name} must be valid base64") from None
        if len(raw) != 32:
            raise ValueError(f"{setting_name} must decode to exactly 32 bytes")

    @model_validator(mode="after")
    def validate_non_local_security(self) -> "Settings":
        if self.app_env.lower() in _LOCAL_ENVS:
            return self
        errors: list[str] = []
        if self.jwt_secret == "change-me-too-local-dev-secret-32b":
            errors.append("jwt_secret must be configured outside local/test")
        if len(self.jwt_secret.encode()) < 32:
            errors.append("jwt_secret must be at least 32 bytes")
        if not self.file_encryption_key:
            errors.append("file_encryption_key must be configured outside local/test")
        if not self.db_field_encryption_key:
            errors.append(
                "db_field_encryption_key must be configured outside local/test"
            )
        if self.turnstile_secret_key.startswith("1x0000"):
            errors.append("turnstile_secret_key must be configured outside local/test")
        if not self.smtp_host:
            errors.append(
                "smtp_host must be configured outside local/test "
                "(otherwise confirmation e-mails are only logged, not sent)"
            )
        if "*" in self.cors_origins:
            errors.append("cors_origins cannot contain '*' outside local/test")
        if self.institution_name.strip() in {"", "Museum"}:
            errors.append(
                "institution_name must be configured outside local/test "
                "(it is published as the creator of exported CIDOC-CRM graphs)"
            )
        if errors:
            raise ValueError("; ".join(errors))
        return self


settings = Settings()
