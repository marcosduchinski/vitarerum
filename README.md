# Vitarerum

Vitarerum is a modular application for museum collection-use workflows. It
combines a FastAPI backend, an Angular SPA, and shared documentation for
architecture, API contracts, diagrams, deployment, and document templates.

The current application covers proposal intake, collection-use projects,
public proposal submission, public museum questions, in-situ visit records,
CIDOC-CRM mapping, reports, object data sources, document templates, external
publication links, notifications, identity/permissions, dashboards, and
AI-assisted narrative workflows.

## Repository Layout

- [vitarerum-api](./vitarerum-api/README.md): FastAPI modular monolith,
  database migrations, local PostgreSQL Compose setup, backend tests and
  architecture fitness checks.
- [vitarerum-ui](./vitarerum-ui/README.md): Angular 21 SPA, public and
  authenticated routes, runtime frontend configuration, unit and e2e tests.
- [docs](./docs/README.md): documentation index with reading paths by audience,
  covering specifications, architecture, API contracts, diagrams, deployment,
  compliance, and source document templates.
- [Dockerfile](./Dockerfile): production-oriented image that builds the
  Angular UI and serves it from the FastAPI runtime.
- [cloudbuild.yaml](./cloudbuild.yaml): Cloud Build pipeline for image build,
  migration job execution, and Cloud Run deployment.
- [cloudbuild.image.yaml](./cloudbuild.image.yaml): image-only Cloud Build
  pipeline for manual tags.

## Architecture At A Glance

The backend is a modular monolith. Bounded contexts live in one FastAPI process
and follow Clean Architecture layers. Cross-context communication is
synchronous through published-language modules and narrow ACLs, with dependency
rules enforced by import-linter contracts.

The production image is integrated: the Angular app is built first, copied into
`/app/static`, and served by FastAPI. API routes live under `/api/v1/*`; other
paths fall back to the Angular SPA when the static build is present.

![Vitarerum simplified context map](./docs/architecture/vitarerum-context-map-simplified.svg)

## Local Development

Backend:

```bash
cd vitarerum-api
uv sync
cp .env.example .env
docker compose up -d postgres
uv run alembic upgrade head
docker compose exec -T postgres psql -U vitarerum -d vitarerum < scripts/seed.sql
uv run uvicorn app.main:app --reload
```

Frontend:

```bash
cd vitarerum-ui
npm ci
npm start
```

Default local URLs:

- API health: http://localhost:8000/api/v1/health
- Angular dev server: http://localhost:4200

Detailed setup and configuration live in the subproject READMEs linked above.

## Quality Gates

Backend:

```bash
cd vitarerum-api
uv run ruff check .
uv run mypy app
uv run lint-imports
uv run pytest
```

Frontend:

```bash
cd vitarerum-ui
npm run lint
npm test
npm run test:e2e
npm run build
```

`npm run test:e2e` starts its own Angular dev server on
`http://127.0.0.1:4201` through Playwright.

Documentation:

```bash
python3 scripts/check_docs.py
```

Six checks over the tracked Markdown, the diagrams and the backend routes:

| Check | Fails when |
| --- | --- |
| `--links` | A relative link points at a file that is not there |
| `--tests` | A spec's acceptance criterion cites a test that no longer exists |
| `--status` | A document does not declare whether it describes current behaviour |
| `--diagrams` | A diagram has no source, renders to a different name than its file, or nothing references it |
| `--citations` | A document cites a source file that does not exist, or a line past its end |
| `--routes` | The backend declares an HTTP route that no specification names |

Standard library only — the route check reads the decorators statically rather
than importing the application. Runs on every push and pull request through
[.github/workflows/docs.yml](./.github/workflows/docs.yml).

## Build And Deployment

For local backend-only container work, use the Compose setup in
[vitarerum-api](./vitarerum-api/README.md).

For the deployable application artifact, use the root [Dockerfile](./Dockerfile).
It builds both subprojects and serves the Angular build from FastAPI:

```bash
docker build -t vitarerum:local .
docker run --rm -p 8080:8080 -e APP_ENV=local vitarerum:local
```

Cloud Build configuration for the integrated image lives in
[cloudbuild.yaml](./cloudbuild.yaml), with runtime environment examples under
[docs/cloud](./docs/cloud/).

## Documentation

[docs/README.md](./docs/README.md) is the documentation index: reading paths by
audience, and which directories describe current behaviour as opposed to
proposals for behaviour that does not exist yet.

Most direct entry points:

- [Architecture overview](./docs/architecture/README.md)
- [Specifications](./docs/specs/README.md): implemented behaviour, with
  numbered requirements and invariants traced to the tests that verify them
- [Cross-cutting API contract](./docs/api_contracts/README.md): session headers,
  error envelope, pagination and the full catalogue of typed error codes —
  alongside the OpenAPI schema generated from code at `/docs` in a running
  instance
- [User manual](./docs/manual/user-manual.md)
- [GDPR and AI Act compliance report](./docs/legal/relatorio-conformidade-rgpd-ia.md)

## Operational Notes

The current deployment convention is one application instance per institution.
Do not document multi-institution behavior as a guaranteed domain invariant
unless the implementation is changed to enforce it.
