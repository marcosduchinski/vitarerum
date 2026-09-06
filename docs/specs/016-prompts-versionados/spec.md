# SPEC-016 — Versioned Prompts for AI-Assisted Contexts

| Field | Value |
| --- | --- |
| Identifier | SPEC-016 |
| Status | Implemented (with declared governance, concurrency, validation, and preview gaps) |
| Bounded context | `app/ai/prompts` |
| Derived from | Backend, frontend, migrations, architecture contracts, consumers, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-005](../005-analise-agentica-de-candidato/spec.md), [SPEC-015](../015-relatorio-visita-in-situ/spec.md), [SPEC-017](../017-narrativa-museologica/spec.md) |

## 1. Problem

The behaviour of an AI-assisted workflow depends on both the model and its
instructions. When prompts exist only as constants in application code,
changing behaviour requires a deployment and a past output cannot be reliably
attributed to the exact instruction that produced it.

Prompt changes are production configuration changes. They require stable
identity, immutable historical content, controlled activation, and enough
provenance for consumers to explain generated results.

## 2. Goal and scope

This bounded context stores institutional prompts as templates with numbered
versions. It allows staff to inspect templates, create drafts, publish one
active version, archive unused drafts, and retrieve an exact historical
version.

It publishes read operations used by:

- the in-situ museum-narrative pipeline; and
- supervised and full-agentic scientific-return workflows.

Template creation and metadata editing are not exposed at runtime. Templates
and initial published versions are installed and evolved by database
migrations. Proposal- and project-assistance purposes exist in the domain enum
but have no current consumers or seeded templates.

## 3. Strategic context

`ai.prompts` is a supporting configuration context and an upstream supplier to
AI-assisted contexts. Consumers use `app.ai.prompts.public` rather than reading
prompt tables or importing infrastructure repositories.

| Consumer | Purpose | Resolution |
| --- | --- | --- |
| Museum Narrative | `in_situ_narrative` | Published prompt selected by narrative-type key; preview may select an exact version. |
| Scientific Return | `scientific_return_analysis` | Published planner, reader, reflector, and learner prompts selected by key. |

The consumer remains responsible for translating a missing prompt into its own
operational error vocabulary and for persisting prompt provenance with the
generated output or call telemetry.

## 4. Ubiquitous language and domain model

### 4.1 Prompt template

`PromptTemplate` is the stable aggregate root for one prompt role. It contains:

- identifier;
- purpose and key, unique as a pair;
- name and description;
- a canonical JSON object describing expected variables;
- creation timestamp; and
- the identifier of the active version, used as a cached pointer.

There is no runtime endpoint to create, rename, describe, or remove a template,
or to update its variables schema.

### 4.2 Prompt version

`PromptTemplateVersion` is an immutable value-bearing entity with:

- generated identifier and sequential number within the template;
- unique version label within the template;
- status `draft`, `published`, or `archived`;
- trimmed prompt content and default temperature;
- creation actor and timestamp;
- optional publication actor and timestamp; and
- optional archive timestamp.

The domain creates new values for lifecycle transitions instead of mutating
content. Identifiers and timestamps are generated directly by domain factories;
there is no injected clock or ID provider.

### 4.3 Supported purposes

The implemented domain enum contains:

- `in_situ_narrative`;
- `scientific_return_analysis`;
- `proposal_assistance`; and
- `project_assistance`.

The Angular purpose filter intentionally displays only Narrative and Scientific
Return because those are the purposes with currently installed prompts.

## 5. Authorisation

Every management endpoint applies `require_staff`. `EXTERNAL` callers receive
`403`; all other groups, including `DIRECTION`, `CURATORIAL`,
`COLLECTIONS_MANAGEMENT`, and `SYS_ADMIN`, have the same backend capability to:

- read every template and complete prompt version;
- create drafts;
- publish drafts into production; and
- archive non-published versions.

There is no separate reader, editor, reviewer, or publisher permission and no
four-eyes approval rule. The Angular menu exposes Prompts to collection
management, curatorial, and direction groups, but not to `SYS_ADMIN`;
`SYS_ADMIN` can still access the routes directly because the backend permits
it. The prompt routes themselves have no dedicated staff route guard, so the
API remains the security boundary.

## 6. Functional requirements

### FR-001 — List templates

`GET /api/v1/ai/prompts` returns an unpaginated list ordered by purpose and key.
It accepts optional enum filters:

- `purpose`; and
- `status`.

An invalid enum value returns framework validation error `422`.

The status filter represents a template's current operational state. It uses
the active version's status when `activeVersionId` exists; otherwise it uses
the latest version by number and creation time. Archived historical versions
therefore do not make a template with an active published version match the
`archived` filter.

The Angular index loads every returned template and then requests each
template's complete version history in parallel to calculate current status,
active label, last publication date, and publishing actor.

### FR-002 — List a template's versions

`GET /api/v1/ai/prompts/{templateId}/versions` returns all versions ordered by
ascending numeric version. An unknown template returns `404
PROMPT_TEMPLATE_NOT_FOUND`. The response is unpaginated and includes full
prompt content and lifecycle metadata.

### FR-003 — Read an exact version

`GET /api/v1/ai/prompts/versions/{versionId}` returns a draft, published, or
archived version by identity. An unknown version returns `404
PROMPT_VERSION_NOT_FOUND`.

This endpoint supports audit links: republishing a replacement does not alter
the previous version's content, label, creation metadata, or publication
metadata. The Angular exact-version route is read-only.

### FR-004 — Create a draft

`POST /api/v1/ai/prompts/{templateId}/versions` accepts:

| Field | Rule |
| --- | --- |
| `version_label` | Required, trimmed, and non-blank |
| `content` | Required, trimmed, and non-blank |
| `default_temperature` | Required, from `0.0` to `1.0` inclusive |
| `source_version_id` | Optional exact version belonging to the same template |

The next number is calculated as `max(version) + 1`. The new version starts as
`draft` and records the calling permission as `createdBy`.

When `source_version_id` is supplied, the source version's content and default
temperature replace the values supplied in the request. The endpoint still
requires `content` and `default_temperature` in its request schema. The source
identifier is not persisted as provenance on the new version.

Blank content or label and an out-of-range temperature return `422` without
persisting a version. An unknown template or an absent/cross-template source
version returns the corresponding `404`.

### FR-005 — Publish a draft

`POST /api/v1/ai/prompts/versions/{versionId}/publish`:

1. reads the target version;
2. locks its template row;
3. finds and archives the currently published version, if present;
4. changes the target draft to `published`;
5. updates the template's `activeVersionId`; and
6. commits the transaction in the route.

Only a draft can be published. Publishing a published or archived version
returns `409 PROMPT_PUBLICATION_CONFLICT`. An unknown version or template
returns `404`.

The template lock serialises publication attempts. Two concurrent publications
may therefore complete sequentially, with the later transaction replacing the
earlier one, rather than one necessarily receiving `409`. The partial unique
index remains the final guarantee that at most one row per template has status
`published`.

### FR-006 — Archive a non-published version

`POST /api/v1/ai/prompts/versions/{versionId}/archive` archives a draft and
records `archivedAt`. A published version cannot be archived directly and
returns `409 PUBLISHED_PROMPT_REQUIRED`; it leaves service only when publishing
its replacement.

The backend also accepts archiving an already archived version and refreshes
its archive timestamp. The UI exposes Archive only for drafts. No `archivedBy`
or reason is recorded.

### FR-007 — Immutable content history

There is no endpoint for editing version content. Publishing and archiving
preserve content and default temperature. To change a prompt, a user creates a
new draft and publishes it, leaving the replaced version archived and
readable.

Runtime APIs do not delete versions. Database migrations can add, replace, or
remove installed templates and versions as part of application evolution.

### FR-008 — Published-version uniqueness and active pointer

The database enforces:

- unique `(purpose, key)` per template;
- unique numeric version within a template;
- unique version label within a template; and
- at most one `published` version within a template through a partial unique
  index.

`activeVersionId` is updated during publication but is not a database foreign
key. Consumer resolution queries the version with `published` status by
purpose and key; it does not trust the active pointer alone.

### FR-009 — Missing published prompt

`get_published_prompt(session, purpose, key)` raises `ActivePromptNotFound` when
no published version exists. There is no embedded fallback prompt in this
context.

Museum Narrative translates this into `NarrativePromptUnavailable`; report and
narrative endpoints expose it as `503 NARRATIVE_PROMPT_UNAVAILABLE`.
Scientific Return translates it into `AgentPromptUnavailable` according to its
own operation contract.

### FR-010 — Consumer provenance

Museum Narrative stores the selected prompt version identifier and label with
the generated narrative, together with the model-response hash and generation
metadata. Scientific Return stores version identity/label in analysis records
or agent-call telemetry where those consumers invoke managed prompts.

This context makes exact attribution possible but cannot guarantee it for every
AI output by itself. Each consumer must persist the returned identity. Ad-hoc
previews deliberately have no managed prompt-version identity.

### FR-011 — Narrative prompt preview

The Angular management page can invoke the Museum Narrative preview endpoint
without creating a narrative, fact snapshot, or prompt version. Preview still
invokes the configured model and performs CIDOC/factual validation.

For an `in_situ_narrative` template, staff may preview:

- any persisted version — including draft or archived — when it belongs to the
  expected narrative-type template; or
- ad-hoc editor content that has not been saved as a draft.

The result identifies version/ad-hoc source, model, temperature, response hash,
validation outcome, and generated text. It is transient and is not an approval
or publication gate.

The UI maps known narrative template keys to the five narrative types. It has
no equivalent preview for `scientific_return_analysis` prompts.

### FR-012 — Preview record selection

Preview requires an existing in-situ visit record identifier. The management
page also lists up to 100 completed in-situ projects and submits a selected
project ID as if it might be a record ID. On the first `404`, the Angular
service looks up that project's latest report and retries using its
`inSituVisitRecordId`.

Consequently, selecting a completed project succeeds only when the ID already
is a valid visit-record ID or the project has at least one generated report.
The preview flow does not export a new record.

### FR-013 — Angular management experience

The Angular feature uses standalone, `OnPush`, signal-based pages and typed HTTP
mapping. It provides:

- template list with purpose/status filters and row actions;
- active-version and publication summaries;
- template history and exact-version read-only views;
- draft editor prefilled from active installed (`ptpl-...`) templates;
- client-side duplication of any version into the editor;
- publish and archive actions;
- narrative preview and ad-hoc test bench; and
- loading, empty, and API-error states.

Publishing and archiving are immediate actions without a confirmation dialog,
review checklist, content diff, approval workflow, or mandatory successful
preview. The index page starts asynchronous loading from its constructor rather
than using Angular's declarative `resource()` API.

## 7. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | Runtime lifecycle operations preserve version content and default temperature; migrations can change or remove installed versions as described in FR-007. |
| INV-002 | At most one version per template has `published` status. |
| INV-003 | Publishing a draft archives the current published version in the same transaction. |
| INV-004 | A published version cannot be archived without publishing a replacement. |
| INV-005 | Consumers resolve managed prompts through the published language. |
| INV-006 | A missing published prompt is an explicit operational error, not a hidden code fallback. |
| INV-007 | Runtime publication/archive operations preserve exact historical reads; versions removed by migrations are no longer available. |
| INV-008 | Preview does not persist a prompt version or generated narrative. |

## 8. Error contract

| Condition | Response |
| --- | --- |
| `EXTERNAL` caller | `403` |
| Unknown template | `404 PROMPT_TEMPLATE_NOT_FOUND` |
| Unknown or cross-template source version | `404 PROMPT_VERSION_NOT_FOUND` |
| Unknown exact/publish/archive version | `404 PROMPT_VERSION_NOT_FOUND` |
| Blank draft label/content or invalid temperature | `422` request validation or `INVALID_PROMPT_DRAFT` |
| Publish target is not a draft | `409 PROMPT_PUBLICATION_CONFLICT` |
| Publication persistence conflict | `409 PROMPT_PUBLICATION_CONFLICT` when translated by `save_version` |
| Direct archive of published version | `409 PUBLISHED_PROMPT_REQUIRED` |
| Missing published prompt requested by a consumer | Consumer-specific operational error |

Duplicate labels and concurrent `max(version)+1` draft creation can raise a raw
database integrity error because `add_version` does not translate it to the
prompt error vocabulary.

## 9. Acceptance and test traceability

| Capability | Automated evidence |
| --- | --- |
| Published resolution, uniqueness, and current-state filters | `test/ai/prompts/test_repository.py` |
| Publish replacement, archive guard, copy semantics, and missing active prompt | `test/ai/prompts/test_use_cases.py` |
| Staff access, immutable historical read, and draft validation | `test/ai/prompts/test_api.py` |
| Angular HTTP wire contract and preview fallback | `ai-prompt-management.service.spec.ts` |
| Angular list, detail, editor, lifecycle actions, and preview bench | `ai-prompts-page.component.spec.ts` |
| Consumer resolution and provenance | Museum Narrative and Scientific Return prompt-adapter/use-case tests |

### Acceptance scenarios

1. Given a template with a published version and a new draft, when staff
   publishes the draft, then the old version becomes archived, the draft
   becomes the sole published version, and the active pointer identifies it.
2. Given a published version, when staff tries to archive it directly, then the
   API returns `409 PUBLISHED_PROMPT_REQUIRED` and the version remains active.
3. Given a source version from the same template, when a draft is copied, then
   its content and temperature equal the source while its identity, number,
   label, actor, and timestamp are new.
4. Given a version replaced by a later publication, when its exact endpoint is
   read, then its original content and publication metadata remain available.
5. Given no published prompt for a consumer's purpose/key, when generation is
   attempted, then the consumer receives an explicit operational error and no
   fallback content is substituted.
6. Given an exact in-situ narrative prompt version and valid visit record, when
   staff previews it, then the model result contains prompt provenance but no
   narrative or prompt version is persisted.
7. Given ad-hoc editor content, when staff tests it, then the result declares
   `adhoc` source and has no managed prompt-version identity.
8. Given an external caller, when it attempts any prompt management endpoint,
   then the API returns `403`.

## 10. Non-functional characteristics

- Template and version lists are unpaginated; the Angular index adds one
  version-history request per template.
- Publishing relies on a template row lock and a partial unique index.
- Draft numbering uses a non-locked `max + 1` query.
- Prompt content may contain security boundaries and operational instructions;
  complete content is disclosed to every staff role.
- Preview calls the language model synchronously and can incur cost even though
  it persists no result.
- Variables-schema JSON is validated as a JSON object when a template is
  constructed, but it is not used at runtime to validate prompt placeholders or
  consumer payloads and is hidden by the current UI.
- Architecture contracts enforce inward layers and require Museum Narrative and
  Scientific Return to enter through `app.ai.prompts.public`.

## 11. Known gaps and required improvements

| ID | Priority | Gap | Required change |
| --- | --- | --- | --- |
| GAP-001 | High | Every staff permission can change production prompts, including direction and ordinary curatorial users. | Introduce explicit prompt reader/editor/publisher permissions and enforce them in backend use cases, routes, menus, and tests. |
| GAP-002 | High | Publication has no approval, separation of duties, confirmation, reason, diff, or mandatory evaluation evidence. | Define a governed review/publish workflow with actor separation, content diff, approval evidence, and rollback procedure. |
| GAP-003 | High | Concurrent publications are serialised and may both succeed, so a later request can immediately replace the first without a conflict. | Add expected-active-version or optimistic concurrency input and reject stale publication attempts with `409`. |
| GAP-004 | High | Draft numbering uses `max + 1` without locking, and label/number integrity errors are not translated. | Allocate versions under the template lock or database sequence and map uniqueness conflicts to a stable `409` error. |
| GAP-005 | Medium | Archive records no actor or reason, and re-archiving changes its timestamp. | Add `archivedBy`/reason, define idempotent or conflict semantics, and preserve the first lifecycle event. |
| GAP-006 | Medium | Exact source-copy provenance is discarded after draft creation. | Persist `sourceVersionId` when auditability of derived prompts is required. |
| GAP-007 | Medium | `version_label` and content have no API maximum; an oversized label can fail at the 96-character database column. | Align Pydantic/domain limits with persistence and define a safe maximum prompt size. |
| GAP-008 | Medium | Preview against a selected completed project requires a pre-existing report and silently retries after a `404`. | Provide an explicit project-to-record selection API or safely prepare a preview record, and distinguish project IDs from record IDs in the UI. |
| GAP-009 | Medium | Scientific-return prompts cannot be previewed or evaluated from the management UI. | Add consumer-specific fixtures/evaluations before allowing publication, rather than reusing the narrative preview contract. |
| GAP-010 | Medium | Variables schemas are stored but not enforced. | Validate declared variables/placeholders against consumer input or remove the unused metadata to avoid false assurance. |
| GAP-011 | Medium | Prompt lists are unpaginated and the UI performs an N+1 version-history fan-out. | Add summary fields/read model and pagination before the catalogue grows materially. |
| GAP-012 | Medium | Consumer attribution is contractual rather than centrally enforced. | Add consumer contract tests requiring version ID/label persistence for every managed-prompt invocation. |
| GAP-013 | Low | `proposal_assistance` and `project_assistance` are unused enum values. | Either implement and seed those consumers or remove/deprecate the unsupported purposes. |
| GAP-014 | Low | `SYS_ADMIN` is permitted by the API but lacks the AI Prompts menu entry. | Align menu visibility with the decided permission model. |
| GAP-015 | Low | The Angular index performs side effects in its constructor and manage/view pages depend on seeded `ptpl-` ID conventions for parts of the UX. | Move loading to declarative resources and replace identifier-prefix checks with explicit server capabilities. |

## 12. Traceability

| Element | Location |
| --- | --- |
| Templates, versions, purposes, statuses, and invariants | `vitarerum-api/app/ai/prompts/domain/` |
| List, draft, publish, archive, and exact-read use cases | `vitarerum-api/app/ai/prompts/application/` |
| SQLAlchemy repository and uniqueness constraints | `vitarerum-api/app/ai/prompts/infrastructure/` |
| Management API | `vitarerum-api/app/ai/prompts/presentation/` |
| Published language | `vitarerum-api/app/ai/prompts/public.py` |
| Museum Narrative consumer adapter | `vitarerum-api/app/ai/museum_narrative/infrastructure/prompt_acl.py` |
| Scientific Return consumer adapter | `vitarerum-api/app/scientific_return/infrastructure/prompt_acl.py` |
| Angular prompt management | `vitarerum-ui/src/app/features/ai/prompts/` |
| Backend tests | `vitarerum-api/test/ai/prompts/` |
| Lifecycle diagram | `docs/diagrams/ai-prompts-life-cycle.puml` and generated SVG |

## 13. Open product decisions

1. Which roles may read sensitive prompt content, create drafts, review, and
   publish production instructions?
2. Must the publisher be different from the draft author?
3. What evaluation dataset and quality/security thresholds are required before
   publication for each consumer?
4. Should stale concurrent publication attempts fail or may the last writer
   intentionally win?
5. Must archived prompts remain indefinitely available for audits, even when a
   migration removes an obsolete template?
6. Should prompt variables schemas become executable contracts?
