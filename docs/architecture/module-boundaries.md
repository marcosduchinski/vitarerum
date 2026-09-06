---
status: current
---

# Module Boundaries

This document is a semantic catalog of active backend bounded contexts. Layering
rules, dependency direction, `public.py` usage, and import-linter requirements
remain documented in [vitarerum-api/AGENTS.md](../../vitarerum-api/AGENTS.md).
Executable dependency contracts live in
[vitarerum-api/pyproject.toml](../../vitarerum-api/pyproject.toml).

## Active Bounded Contexts

### `identity`

Owns users, groups, permissions, login, JWT identity, password management, and
the `CallerPermission` vocabulary exposed to other contexts. Other contexts may
depend on Identity only through `identity.public` or shared authorization
helpers that use that published language.

### `use_of_collections`

Owns the collection-use workflow: authenticated proposals, proposal
conversation, requester and staff documents, requested collection objects,
proposal lifecycle transitions, and collection-use projects. It is the central
workflow context for staff and authenticated users.

### `public_submission`

Owns public proposal intake before authentication exists: captcha, consent,
double opt-in confirmation, public requester data, confirmation tokens, and
document-correction/amendment tokens. It materialises accepted public
submissions into `use_of_collections` proposals through adapter wiring tracked
by import-linter ignores.

### `collection_object_index`

Owns searchable collection-object source data, source files, imported records,
and object search. Other contexts use it for search/snapshot behavior through
narrow ACLs rather than treating its storage model as shared state.

### `document_templates`

Owns managed document templates and their files. It is operationally used by
staff-facing workflows but keeps its own domain/application ports. It reuses
shared storage composition where appropriate.

### `museum_questions`

Owns public questions sent to the museum and staff response workflows. It
uses Identity through the shared authenticated staff helpers. The
`museum_questions.public` Open Host Service is deliberately retained as a
small read-only extension point for future downstream contexts.

### `notifications`

Owns staff-facing in-app notifications and read-state. Workflow contexts publish
notifications through `notifications.public`; the read API hydrates actor labels
through `identity.public` and deliberately stores only small resource snapshots,
not source-context aggregates.

### `reference_numbers`

Owns configurable reference-number masks, policy activation, per-policy
sequences, legacy validation patterns, and the allocation service other contexts
use. Proposal, public-submission, project, and journal workflows request a
number through `reference_numbers.public` instead of building one from a mask.
The generator shares the consumer's database session, so reserving a sequence
and persisting the resource commit or roll back together. Policy administration
is restricted to `SYS_ADMIN`.

### `scientific_return`

Owns monitoring of scientific outputs after a collection-use project is
completed. It stores immutable project snapshots, bibliographic search
trajectories, candidates, evidence, human decisions and curator-validated
textual knowledge about citation variants. Alongside the deterministic and
policy-assisted regimes it owns a separate `FullAgenticInvestigation` aggregate:
an asynchronous LLM planner executes iterative searches, while a tool-free
reader isolates untrusted publication text and human review remains the final
institutional gate. It reads and writes project information only through
`use_of_collections.public`; external bibliographic results never become
publication-log entries without a decision by curatorial,
collections-management or direction staff.

### `reports.in_situ_visit`

Owns the in-situ visit report aggregation surface. It assembles data from
published CIDOC-CRM and museum-narrative interfaces so consumers can read a
single report view without coupling directly to those contexts' internals.

### `cidoc_crm.in_situ_visit_mapping`

Owns persisted in-situ visit records shaped for CIDOC-CRM mapping and export.
It reads source project data through `use_of_collections.public` and publishes
its record vocabulary through `cidoc_crm.public`.

### `ai.museum_narrative`

Owns AI-assisted narrative generation for museum/in-situ material. It consumes
CIDOC-CRM records through `cidoc_crm.public`, resolves prompt templates through
`ai.prompts.public`, and keeps generated outputs in a human-review posture.

### `ai.prompts`

Owns versioned prompt templates for AI-assisted contexts. Consumers depend on
the published prompt interface, not on prompt persistence or draft-management
internals.

### `external_publications`

Owns revocable grants that expose a selected resource outside the authenticated
application: opaque token generation and resolution, content-profile projection
(`SUMMARY`, `DETAIL`, `JSON_LD`), access-attempt records, and the
system-administration registry. It owns no proposal, project, report, narrative,
or CIDOC record. Every resolution re-reads the current resource through the
owning context's published language, so a grant exposes live data rather than a
frozen export.

### `shared`

Contains shared exceptions, authorization/dependency helpers, upload helpers,
persistence helpers, and the stdlib-only shared kernel. It must remain small and
must not become a dumping ground for domain behavior that belongs to a bounded
context.

## Inactive Scaffolds

`app/ai/in_situ_visit` currently contains only empty `__init__.py` files under
the expected layer directories and has no import-linter contracts. It should not
be treated as an active bounded context until it has real behavior and the
corresponding architecture contracts.

`app/ai/museum_question_triage` is the remnant of a removed feature. It holds
only the ORM metadata of two tables that still exist in the schema
(`museum_question_triages`, `museum_question_triage_classifications`), imported
by `app/orm_registry.py` so that `alembic revision --autogenerate` does not
propose dropping them. It has no domain, application, presentation, or
import-linter contract, and no specification owns the retained data. It is not a
bounded context: either drop the tables with a deliberate data-retention
migration or record the retention decision and its owning specification
([SPEC-023](../specs/023-fronteiras-e-envelope-de-erro/spec.md), gap 9).
