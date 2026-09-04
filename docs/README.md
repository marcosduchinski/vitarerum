---
status: current
---

# Documentation Index

Reading paths by audience. Each path lists the documents worth reading **in
order**; everything else is reference material to reach for when needed.

Documents are marked `[PT]` when written in Portuguese.

---

## I want to run the system

1. [Root README](../README.md) — repository layout, local setup, quality gates.
2. [Backend README](../vitarerum-api/README.md) — FastAPI setup, migrations,
   runtime configuration, Compose.
3. [Frontend README](../vitarerum-ui/README.md) — Angular setup, runtime
   frontend configuration, commands.

Once running: interactive OpenAPI at `http://localhost:8000/docs`.

## I am new to this codebase

1. [Architecture overview](./architecture/README.md) — architecture position and
   context map.
2. [Module boundaries](./architecture/module-boundaries.md) — what each bounded
   context owns.
3. [Backend agent guide](../vitarerum-api/AGENTS.md) — canonical rules for
   layering, security, testing, and code quality. Written for coding agents, but
   it is the developer contract too.
4. [Architecture decisions](./architecture/adr/README.md) — durable decisions
   and their rationale.

## I need to understand the domain

1. [Specifications](./specs/README.md) `[PT]` — what the system guarantees:
   numbered requirements (`RF-nnn`), invariants (`INV-nnn`), and acceptance
   criteria (`CA-nnn`), each traced to the test that verifies it. **This is the
   authoritative description of implemented behaviour.**
2. [Business flows](./architecture/business-flows.md) — end-to-end flows with
   their diagrams.
3. [User manual](./manual/user-manual.md) `[PT]` — the workflow as institutional
   staff experience it. Draft.

## I am consuming the API

1. [Cross-cutting API contract](./api_contracts/README.md) — session headers and
   the acting-role model, the `401`/`403` rule, the error envelope, pagination,
   and every typed error code the application can return. Shared by all
   endpoints; read it once before anything else.
2. `/openapi.json`, or `/docs` in a running instance — schemas, request and
   response shapes, status codes. Generated from code, so never stale. Note
   both sit at the application root, not under `/api/v1`.
3. [Specifications](./specs/README.md) `[PT]` — per context, what OpenAPI cannot
   express: authorisation and visibility rules, state transitions, side effects,
   invariants, and the tests that verify them.

## I run it in production, or answer for compliance

1. [Cloud Run deployment](./cloud/migracao-nova-conta.md) `[PT]` — recreating the
   full production environment, with
   [env example](./cloud/vitarerum-cloudrun.env.example.yaml).
2. [Encryption contracts](./architecture/encryption-contracts.md) — the strings
   encryption authenticates; changing them breaks stored data.
3. [GDPR and AI Act compliance report](./legal/relatorio-conformidade-rgpd-ia.md)
   `[PT]` — technical assessment against Regulation (EU) 2016/679 and
   Regulation (EU) 2024/1689.
4. [SPEC-022 — encryption and storage](./specs/022-cifragem-e-armazenamento/spec.md)
   `[PT]`.

## I am a coding agent

1. [Backend agent guide](../vitarerum-api/AGENTS.md).
2. [Frontend agent guide](../vitarerum-ui/AGENTS.md).
3. [Specifications](./specs/README.md) `[PT]` — before changing behaviour, read
   the invariants it must preserve.

---

## Document status

| Directory | Status | Versioned |
| --- | --- | --- |
| `specs/` | Current — implemented behaviour, traced to tests | yes |
| `api_contracts/` | Current — the single cross-cutting HTTP contract. Per-endpoint schemas come from OpenAPI, per-context rules from `specs/` | yes |
| `architecture/` | Current — position, boundaries, ADRs | yes |
| `manual/` | Current — draft | yes |
| `legal/` | Current | yes |
| `cloud/` | Current | yes |
| `diagrams/` | Current — rendered SVG plus PlantUML sources | yes |
| `evaluation/` | Current — published, re-runnable baselines cited by SPEC-006 | yes |
| `templates/` | Current — MUHNAC source document templates | yes |
| `proposals/` | **Proposed — not implemented.** Design documents for behaviour that does not exist yet | yes |
| `paper/` | Dissertation manuscript in progress (LaTeX sources) | no — ignored by Git |

Every tracked document declares its own status, so a directory move can never
silently change what a document claims. Specifications carry it in their `Estado`
metadata row; every other document carries it as YAML front-matter:

```yaml
---
status: current
---
```

One source of truth per document — never both — and `scripts/check_docs.py`
fails when a document declares nothing, declares an unknown value, or disagrees
with the directory it sits in.

A document under `proposals/` describes intent, never current behaviour. Do not
implement against it without checking the matching spec first.

## Regenerating diagrams

```bash
java -jar /path/to/plantuml.jar -tsvg docs/architecture docs/diagrams
```
