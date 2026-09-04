# AGENTS.md — vitarerum-api

## Project Overview

`vitarerum-api` is a modular FastAPI backend for Vitarerum.

Core stack:
- Python 3.12+
- FastAPI / Uvicorn
- Pydantic Settings
- SQLAlchemy 2.x async / asyncpg
- PostgreSQL
- Alembic
- pytest / pytest-asyncio / httpx
- Ruff / mypy / import-linter
- uv

Primary bounded contexts:
- `identity`: users, groups, permissions, login, JWT identity.
- `use_of_collections`: proposal and collection-use project workflows.
- `public_submission`: public proposal intake, confirmation, and amendment tokens.
- `collection_object_index`: searchable collection-object source data and snapshots.
- `document_templates`: managed document templates and uploaded template files.
- `museum_questions`: public museum questions and staff responses.
- `scientific_return`: supervised bibliographic monitoring and evidence review
  for scientific outputs from completed collection-use projects.
- `reports.in_situ_visit`: in-situ visit report aggregation across record and narrative contexts.
- `ai.museum_narrative`: AI-assisted (KG-RAG) museum narrative generation.
- `ai.prompts`: versioned prompt templates used by AI-assisted contexts.
- `cidoc_crm.in_situ_visit_mapping`: persisted in-situ visit records for CIDOC-CRM mapping.
- `shared`: exceptions, authorization helpers, and shared kernel value objects.

Context namespaces:
- `app/ai/*` groups AI-assisted contexts (e.g. `museum_narrative`).
- `app/cidoc_crm/*` groups CIDOC-CRM mapping contexts (e.g. `in_situ_visit_mapping`).
- `app/reports/*` groups report aggregation contexts (e.g. `in_situ_visit`).
- `app/ai/in_situ_visit` currently exists only as an empty scaffold with no
  implementation and no import-linter contracts. Do not list it as an active
  bounded context until it has real behavior and architecture contracts.

> This file is the canonical `AGENTS.md`. It complements `CLAUDE.md` and the
> agent memory; when guidance conflicts, prefer the most specific and most
> recently updated source, and keep the three aligned rather than divergent.

## Build & Test Commands

Install dependencies:

```bash
uv sync
```

Configure environment (copy and adjust the template):

```bash
cp .env.example .env
```

Run local PostgreSQL:

```bash
docker compose up -d postgres
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Run API:

```bash
uv run uvicorn app.main:app --reload
```

Run tests and checks:

```bash
uv run pytest
uv run ruff check .
uv run mypy app
uv run lint-imports
```

Optional smoke workflow against a running API:

```bash
./scripts/smoke.sh
```

## Architecture Rules

Use Clean Architecture / Hexagonal Architecture.

Layer intent:
- `domain`: pure domain model, entities, value objects, enums, invariants.
- `application`: use cases, commands/inputs/outputs, ports, authorization policies.
- `infrastructure`: SQLAlchemy records, repositories, file storage, external adapters.
- `presentation`: FastAPI routes, dependencies, request/response schemas, HTTP mapping.

Dependency rules:
- Domain must not import FastAPI, SQLAlchemy, Pydantic, infrastructure, or presentation.
- Application must not import FastAPI or SQLAlchemy.
- Infrastructure may implement application ports.
- Presentation may compose use cases and adapters but must not contain business rules.
- Do not put business logic in FastAPI routes or SQLAlchemy models.
- Keep business invariants on domain objects or application services.

Cross-context rules:
- Other contexts may use Identity only through `app.identity.public`.
- AI contexts may use other contexts only through their published-language modules (`*.public`).
- `app.shared.kernel` must stay stdlib-only.
- Do not bypass published-language modules with direct imports into another context.
- Preserve import-linter contracts in `pyproject.toml`.
- Every bounded context must register its own import-linter contracts in `pyproject.toml`: a `layers` contract for its `presentation > infrastructure > application > domain` ordering, plus coverage in the domain/application purity (`forbidden`) contracts. A new context is not complete until these are added.
- When adding, removing, or changing import-linter contracts between bounded contexts, update `../docs/architecture/vitarerum-context-map.puml` in the same change.

API contract rules:
- Treat `docs/specs/` as the authoritative description of implemented behaviour
  and `docs/api_contracts/README.md` as the cross-cutting HTTP contract.
  Per-endpoint schemas are generated: OpenAPI at `/openapi.json`.
- Preserve response shapes covered by golden contract tests.
- Use existing error envelope patterns from `app/main.py`.

## Testing Rules

Add or update tests with every behavior change.

Preferred test levels:
- Domain invariants: direct domain model tests.
- Use cases: in-memory repository tests.
- API behavior: `httpx.AsyncClient` with FastAPI dependency overrides.
- Contract-sensitive responses: golden contract tests.

Run targeted tests first, then the full suite when behavior spans modules.

Do not require live PostgreSQL for ordinary unit tests unless the task is explicitly integration/database focused.

For migrations or repository mapping changes, add mapping or infrastructure tests and run Alembic-related checks where practical.

## Security Rules

Authentication uses JWT bearer tokens plus `X-Permission-Id`.

Rules:
- `401` is only for authentication failure.
- `403` is for authorization or permission mismatch.
- Never infer acting group from the token alone.
- Always validate that `X-Permission-Id` belongs to the authenticated user.
- Do not log secrets, JWTs, passwords, or raw credentials.
- Passwords must be hashed with bcrypt and never returned.
- Non-local environments must not use default `JWT_SECRET` or wildcard CORS.
- Keep uploaded files under configured `DATA_DIR`; do not introduce unsafe absolute paths.

## Legal Rules

Do not add license headers, copyright notices, or third-party code unless explicitly requested.

Do not commit real personal data, credentials, access tokens, or production database URLs.

Treat museum collection records, requester emails, uploaded documents, and conversation bodies as sensitive application data.

For AI features, preserve the advisory/human-review posture: do not present model output as final authorization, approval, or factual determination.

## Code Quality Rules

Use Python 3.12 typing features and keep mypy strict passing.

Follow existing style:
- dataclasses with `slots=True` for domain/application data objects.
- frozen dataclasses for value objects where appropriate.
- `NewType` identifiers for domain IDs.
- Protocol ports in application layers.
- SQLAlchemy async repositories in infrastructure.
- Pydantic schemas only at the presentation boundary.
- Explicit mapper functions between ORM records and domain objects.

SQLAlchemy ORM classes use the `...Record` suffix. When the domain model already
owns that name (e.g. the CIDOC-CRM mapping context, whose PlantUML names end in
`...Record`), suffix the ORM class with `...Orm` instead to avoid the clash, and
keep the explicit `record_to_orm` / `record_to_domain` mappers in the repository.

Keep names aligned with API contracts, especially camelCase response fields in schemas and documented enum values.

Prefer small vertical changes. Avoid broad refactors unless required by the task.

Do not weaken Ruff, mypy, pytest, or import-linter settings to make a change pass.

## Agent Workflow (3-Phase — Always Follow This Order)

### PHASE 1 — INSPECT

Before editing:
- Check `git status --short`.
- Read the relevant domain, application, infrastructure, presentation, and test files.
- Read related docs in `README.md`, `docs/specs/` and `docs/api_contracts/README.md`.
- Check `pyproject.toml` import-linter contracts before changing imports.
- Identify whether the change crosses bounded contexts.

### PHASE 2 — PLAN

Before coding:
- State the intended boundary for the change.
- Decide which layer owns the behavior.
- Identify tests to add or update.
- For API changes, compare against docs and golden contract tests.
- For persistence changes, plan Alembic migration and mapper updates.

### PHASE 3 — CODE

When coding:
- Make the smallest coherent change.
- Keep domain/application framework-free.
- Compose concrete adapters at the presentation/public-module boundary.
- Update tests alongside behavior.
- Run targeted checks, then broader checks when risk warrants it.
- Report any checks not run.

## Guardrails (Always Active)

- Preserve Clean Architecture boundaries.
- Preserve published-language modules for cross-context access.
- Preserve API response contracts unless explicitly asked to change them.
- Preserve security semantics: `401` authentication, `403` authorization.
- Preserve local developer defaults, but never relax production security validation.
- Respect existing uncommitted user work.
- Do not delete or rewrite migrations casually.
- Do not introduce network calls into tests unless explicitly required and isolated.
- Do not make AI outputs authoritative workflow decisions.

## Do NOT

- Do not import infrastructure into domain or application.
- Do not import FastAPI, SQLAlchemy, or Pydantic into domain models.
- Do not bypass `identity.public` or `use_of_collections.public`.
- Do not put business rules in route handlers.
- Do not change public JSON shapes without updating docs and golden tests.
- Do not store plaintext passwords or secrets.
- Do not hardcode production credentials, absolute local paths, or user-specific paths.
- Do not silence failing tests, mypy errors, Ruff errors, or import-linter violations.
- Do not revert unrelated user changes.
