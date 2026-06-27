# vitarerum-api

Backend API for Vitarerum.

This project is a modular FastAPI backend foundation. 

## Technology Stack

- Python 3.12+
- FastAPI
- Uvicorn
- Pydantic Settings
- SQLAlchemy 2.x async
- asyncpg
- Alembic
- pytest
- Ruff
- mypy
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

The default local connection string is:

```text
postgresql+asyncpg://vitarerum:vitarerum@localhost:5432/vitarerum
```

Apply database migrations:

```bash
uv run alembic upgrade head
```

Bootstrap local identity data:

```bash
docker compose exec -T postgres psql -U vitarerum -d vitarerum < scripts/seed.sql
```

This creates the fixed groups and an initial `SYS_ADMIN` permission,
`perm-sys-admin`, for local user administration.

## Configuration

Settings are read from environment variables (or a local `.env` file) by
`app/config.py`. Variable names are the upper-cased field names; unknown
variables are ignored. Defaults are tuned for local development.

| Variable                   | Default                                  | Description                                                                 |
| -------------------------- | ---------------------------------------- | --------------------------------------------------------------------------- |
| `APP_NAME`                 | `vitarerum-api`                          | Service name reported by the health endpoint and OpenAPI title.             |
| `APP_ENV`                  | `local`                                  | Environment name. Values `local`/`test`/`development` relax the security checks below; any other value (e.g. `production`) enforces them. |
| `API_V1_PREFIX`            | `/api/v1`                                | URL prefix for all routers and the health endpoint.                         |
| `DATABASE_URL`             | `postgresql+asyncpg://vitarerum:vitarerum@localhost:5432/vitarerum` | Async SQLAlchemy connection string (asyncpg driver). |
| `DATA_DIR`                 | `./data`                                 | Base directory for uploaded files, organised into readable subfolders (`proposals/`, `log-entries/`, `occurrence-entries/`, `publication-entries/`). |
| `INSTITUTION_NAME`         | `Museum`                                 | Institution name used as `placeName` when exporting an in-situ visit record from a project. |
| `MAX_UPLOAD_BYTES`         | `26214400` (25 MiB)                      | Maximum accepted upload size; larger uploads return `413 FILE_TOO_LARGE`. |
| `CORS_ORIGINS`             | `["*"]`                                  | JSON list of allowed CORS origins, e.g. `["https://app.example.com"]`.      |
| `JWT_SECRET`               | `change-me-too-local-dev-secret-32b`     | Signing key for access tokens.                                              |
| `JWT_ALGORITHM`            | `HS256`                                  | JWT signing algorithm.                                                      |
| `ACCESS_TOKEN_TTL_MINUTES` | `720`                                    | Access-token lifetime in minutes (default 12 hours).                        |
| `OLLAMA_BASE_URL`          | `http://localhost:11434`                 | Base URL of the Ollama server. For Ollama Cloud use `https://ollama.com`.    |
| `OLLAMA_API_KEY`           | _(empty)_                                | Bearer token for Ollama Cloud; leave empty for a local/self-hosted server.   |

### Security validation outside local environments

When `APP_ENV` is **not** `local`/`test`/`development`, startup fails fast
(`validate_non_local_security`) unless:

- `JWT_SECRET` is changed from its default **and** is at least 32 bytes;
- `CORS_ORIGINS` does not contain `"*"`.

This prevents shipping development defaults to a real deployment. See the
[production configuration](#production-configuration) example under *Run with
Docker*.

## Run API

```bash
uv run uvicorn app.main:app --reload
```

Health endpoint:

```text
http://localhost:8000/api/v1/health
```

## Run with Docker

The full stack (API + PostgreSQL) is containerized. The `api` image is a
multi-stage, non-root build; its entrypoint runs `alembic upgrade head` before
starting Uvicorn, so the schema is migrated automatically on boot.

```bash
docker compose up --build
```

This starts PostgreSQL, waits for it to become healthy, then builds and runs the
API on [http://localhost:8000](http://localhost:8000). Uploaded files are stored
on disk under `DATA_DIR` (`/app/data` in the container), kept on the
`vitarerum_data` volume so they survive container restarts.

Bootstrap identity data once Postgres is up (same as local):

```bash
docker compose exec -T postgres psql -U vitarerum -d vitarerum < scripts/seed.sql
```

### Production configuration

Outside `local`/`test`/`development`, the app refuses to start with default
secrets or wildcard CORS (see `validate_non_local_security` in `app/config.py`).
Provide real values via the environment:

| Variable         | Required | Notes                                                        |
| ---------------- | -------- | ------------------------------------------------------------ |
| `APP_ENV`        | yes      | Set to `production` to enforce the security checks below.    |
| `DATABASE_URL`   | yes      | `postgresql+asyncpg://USER:PASS@HOST:5432/DB`.               |
| `JWT_SECRET`     | yes      | Long random string, **≥ 32 bytes**.                          |
| `CORS_ORIGINS`   | yes      | Explicit JSON list, e.g. `["https://app.example.com"]`.      |

Example:

```bash
APP_ENV=production \
JWT_SECRET="$(openssl rand -base64 48)" \
docker compose up --build -d
```

In production, point `DATABASE_URL` at a managed PostgreSQL instance and run the
container behind a TLS-terminating reverse proxy (add `--proxy-headers` to the
Uvicorn command if so). Scale out with replicas or Uvicorn `--workers`.

## Tests

```bash
uv run pytest
```

## Lint

```bash
uv run ruff check .
```

## Type Check

```bash
uv run mypy app
```
