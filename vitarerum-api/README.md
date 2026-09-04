# vitarerum-api

FastAPI backend for Vitarerum.

This project is a modular monolith. Bounded contexts live under `app/`, follow
Clean Architecture layers, and communicate across context boundaries through
published-language modules or narrow ACL adapters.

## Stack

- Python 3.12+
- FastAPI and Uvicorn
- Pydantic Settings
- SQLAlchemy 2.x async and asyncpg
- Alembic
- PyJWT and bcrypt
- aiosmtplib
- rdflib, pySHACL, owlrl
- LangChain Ollama integration
- openpyxl
- pytest and pytest-asyncio
- Ruff
- mypy
- import-linter
- uv

## Setup

```bash
uv sync
cp .env.example .env
```

## Local Database

Start PostgreSQL with Docker Compose:

```bash
docker compose up -d postgres
```

Default local connection string:

```text
postgresql+asyncpg://vitarerum:vitarerum@localhost:5432/vitarerum
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Bootstrap local identity data:

```bash
docker compose exec -T postgres psql -U vitarerum -d vitarerum < scripts/seed.sql
```

This creates the fixed groups and an initial `SYS_ADMIN` permission,
`perm-sys-admin`, for local user administration.

## Run API

```bash
uv run uvicorn app.main:app --reload
```

Health endpoint:

```text
http://localhost:8000/api/v1/health
```

When a built SPA exists in `static/`, `app.main` also serves it for non-API
paths. In ordinary backend-only development that directory is absent and
non-API paths return 404.

## Configuration

Settings are read from environment variables or a local `.env` file by
`app/config.py`. Variable names are the upper-cased field names; unknown
variables are ignored. Defaults are tuned for local development. Important
settings are listed below; `app/config.py` is the source of truth for advanced
classifier thresholds and other low-level tuning values.

| Variable                                | Default                                                             | Description                                                                                   |
| --------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `APP_NAME`                              | `vitarerum-api`                                                     | Service name reported by the health endpoint and OpenAPI title.                               |
| `APP_ENV`                               | `local`                                                             | Environment name. `local`, `test`, and `development` relax production security checks.        |
| `API_V1_PREFIX`                         | `/api/v1`                                                           | URL prefix for all routers and the health endpoint.                                           |
| `DATABASE_URL`                          | `postgresql+asyncpg://vitarerum:vitarerum@localhost:5432/vitarerum` | Async SQLAlchemy connection string.                                                           |
| `DATA_DIR`                              | `./data`                                                            | Base directory for uploaded files in local disk storage.                                      |
| `MAX_UPLOAD_BYTES`                      | `26214400`                                                          | Maximum upload size, default 25 MiB.                                                          |
| `FILE_ENCRYPTION_KEY`                   | empty                                                               | Base64-encoded 32-byte key for file storage encryption; required outside local/test.           |
| `DB_FIELD_ENCRYPTION_KEY`               | empty                                                               | Base64-encoded 32-byte key for encrypted database fields; required in **every** environment — public submissions and museum questions fail without it. `.env.example` ships a development key. |
| `INSTITUTION_NAME`                      | `Museum`                                                            | Institution operating this deployment. Captured on every exported in-situ visit record, as both its place name and the `dcterms:creator` of the CIDOC-CRM graph; required outside local/test. |
| `CORS_ORIGINS`                          | `["*"]`                                                             | JSON list of allowed CORS origins.                                                            |
| `JWT_SECRET`                            | `change-me-too-local-dev-secret-32b`                                | Signing key for access tokens.                                                                |
| `JWT_ALGORITHM`                         | `HS256`                                                             | JWT signing algorithm.                                                                        |
| `ACCESS_TOKEN_TTL_MINUTES`              | `720`                                                               | Access-token lifetime in minutes.                                                             |
| `OLLAMA_BASE_URL`                       | `http://localhost:11434`                                            | Ollama endpoint. Use `https://ollama.com` for Ollama Cloud.                                   |
| `OLLAMA_API_KEY`                        | empty                                                               | Bearer token for Ollama Cloud; leave empty for local/self-hosted Ollama.                      |
| `NARRATIVE_MODEL`                       | `llama3.1:8b`                                                       | Model used by museum narrative generation.                                                    |
| `NARRATIVE_TIMEOUT_SECONDS`             | `60.0`                                                              | Timeout for narrative model calls.                                                            |
| `TURNSTILE_SECRET_KEY`                  | always-pass test key                                                | Cloudflare Turnstile secret for public submission captcha; must be real outside local/test.   |
| `TURNSTILE_VERIFY_URL`                  | Cloudflare verify URL                                               | Turnstile verification endpoint.                                                              |
| `PUBLIC_ORIGIN`                         | `http://localhost:4200`                                             | Public SPA origin used to build confirmation and reset links.                                 |
| `PUBLIC_CONFIRM_TOKEN_TTL_HOURS`        | `24`                                                                | Public confirmation token validity window.                                                    |
| `PASSWORD_RESET_TOKEN_TTL_MINUTES`      | `60`                                                                | Password reset token validity window.                                                         |
| `PASSWORD_RESET_PUBLIC_PATH`            | `/reset-password`                                                   | Frontend path used to build reset links.                                                      |
| `SMTP_HOST`                             | empty                                                               | SMTP host. Empty means links are logged, not sent, in local/dev. Required outside local/test. |
| `SMTP_PORT`                             | `587`                                                               | SMTP port. The sender uses STARTTLS.                                                          |
| `SMTP_USERNAME`                         | empty                                                               | SMTP auth username.                                                                           |
| `SMTP_PASSWORD`                         | empty                                                               | SMTP auth password.                                                                           |
| `SMTP_FROM_ADDRESS`                     | `no-reply@vitarerum.example`                                        | Sender address.                                                                               |
| `SMTP_USE_TLS`                          | `true`                                                              | Use STARTTLS.                                                                                 |

### Gmail SMTP

Gmail works with the built-in sender. Selection is based on `SMTP_HOST`, so
setting these locally sends real e-mail:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=youraccount@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM_ADDRESS=youraccount@gmail.com
SMTP_USE_TLS=true
```

Gmail requires 2-Step Verification plus an App Password. The normal account
password will not authenticate. Keep the App Password in `.env` only.

### Security Validation Outside Local Environments

When `APP_ENV` is not `local`, `test`, or `development`, startup fails fast
unless:

- `JWT_SECRET` is changed from its default and is at least 32 bytes;
- `FILE_ENCRYPTION_KEY` is set to a base64-encoded 32-byte key;
- `DB_FIELD_ENCRYPTION_KEY` is set to a different base64-encoded 32-byte key;
- `TURNSTILE_SECRET_KEY` is set to a real key;
- `SMTP_HOST` is set;
- `CORS_ORIGINS` does not contain `"*"`.

This prevents shipping development defaults to a real deployment.

## Docker

`vitarerum-api/docker-compose.yml` only defines the local PostgreSQL
dependency described above (`docker compose up -d postgres`); it does not
build or run the API.

`vitarerum-api/Dockerfile` builds a standalone backend image. Its
`ENTRYPOINT` runs database migrations through
`scripts/docker-entrypoint.sh` before handing off to Uvicorn on port 8000:

```bash
docker build -t vitarerum-api:local .
docker run --rm -p 8000:8000 --env-file .env vitarerum-api:local
```

For the production-oriented single image that includes both Angular and FastAPI,
use the root repository [Dockerfile](../Dockerfile). Cloud Build configuration
for that integrated image lives in [cloudbuild.yaml](../cloudbuild.yaml).

## Quality Gates

```bash
uv run ruff check .
uv run mypy app
uv run lint-imports
uv run pytest
```

`lint-imports` runs the import-linter contracts configured in
`pyproject.toml`. Those contracts are architecture fitness checks for layer
direction and allowed cross-context dependencies.

## API Contracts

Contract-sensitive behavior is documented under:

- [cross-cutting API contract](../docs/api_contracts/README.md)
- [specifications](../docs/specs/README.md)
- [backend-local use-of-collections contract](./docs/api_contracts/use_of_collections.md)

## Migrations

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
```

Production deployment should run migrations through the dedicated Cloud Run Job
described in the cloud tutorial, not from the serving container startup.
