# SPEC-019 — Configurable Reference-Number Policies

| Field | Value |
| --- | --- |
| Identifier | SPEC-019 |
| Status | Implemented (with declared uniqueness, storage-width, lifecycle, audit, and historical-validation gaps) |
| Bounded context | `app/reference_numbers` |
| Derived from | Backend, frontend, migrations, consumers, architecture contracts, diagrams, user documentation, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-010](../010-submissao-publica/spec.md) |

## 1. Problem

Institutional records need readable identifiers such as
`PP-MUHNAC/COL/2026/0001`. Their format is an administrative convention that
can change over time. A format change must affect future allocation without
renumbering existing proposals, projects, or operational logs.

The allocator must also remain safe under concurrent creation and preserve the
ability to recognise references emitted by earlier policies and declared legacy
formats.

## 2. Goal and scope

This context owns configurable masks, policy activation, per-policy sequences,
legacy validation patterns, and the generation service used by other bounded
contexts.

It supports administrative preview, draft creation, activation, deactivation,
listing, and exact reads. It does not edit a mask after creation, renumber
existing resources, expose issued-number history, or manage legacy patterns at
runtime.

## 3. Strategic context

Reference Numbers is a generic supporting context. Production consumers request
a number through `app.reference_numbers.public` and do not construct one from a
mask themselves.

| Consumer | Kind |
| --- | --- |
| Proposal and public-submission workflows | `PROPOSAL` |
| Collection-use project workflows | `COLLECTION_USE_PROJECT` |
| Object access journal | `OBJECT_ACCESS_LOG` |
| Object occurrence journal | `OBJECT_OCCURRENCE_LOG` |
| Publication journal | `PUBLICATION_LOG` |

The generator shares the consumer's database session. Reserving a sequence and
persisting the resource therefore normally commit or roll back together.
Test-only fallbacks in `use_of_collections` still generate legacy random
references when use cases are constructed without the production dependency;
production routes explicitly inject this context's generator.

## 4. Ubiquitous language and domain model

### 4.1 Reference mask

`ReferenceMask` is an immutable value object. A valid mask:

- is trimmed and non-empty;
- contains only ASCII letters, digits, `/`, `_`, and `-`;
- contains exactly one uppercase `X` run;
- places that run at the absolute end; and
- uses between one and 12 `X` characters.

The sequence is decimal, positive, zero-padded, and limited by the number of
`X` characters. Lowercase `x` is ordinary literal text.

### 4.2 Conservative date-token parsing

The non-sequence prefix is split into maximal ASCII letter runs. A run becomes
date tokens only when the complete run can be decomposed into `YYYY`, `YY`,
`MM`, and/or `DD`. Otherwise the whole run is literal.

Consequently:

- `VRP-YYYYMMDD-XXXX` recognises three date tokens;
- `COMM-XXXX` keeps `COMM` literal rather than reading its `MM` as a month; and
- `REFYYYY-XXXX` keeps the complete `REFYYYY` run literal because fixed
  letters and a date token are not separated.

An uppercase `X` cannot appear in the literal prefix: `PREFIXYYYY-XXXX` is
invalid because it contains two sequence runs, before date parsing even starts.

### 4.3 Sequence scope

Scope is derived from the finest recognised token:

| Tokens present | Scope key |
| --- | --- |
| `DD` | Full `YYYY-MM-DD` day |
| Otherwise `MM` | Full `YYYY-MM` month |
| Otherwise `YYYY` or `YY` | Four-digit year |
| No date token | `GLOBAL` |

The scope key always contains the full calendar context even when the rendered
mask omits it. The grammar does not require `DD` to be accompanied by month and
year, or `MM` by year; such masks can render the same value again in a later
month or year.

### 4.4 Reference policy aggregate

`ReferencePolicy` is an immutable aggregate root with identity, kind, mask,
derived scope, status, activation interval, creation metadata, last-update
metadata, and latest activation metadata.

Runtime transitions are:

| From | To | Supported |
| --- | --- | --- |
| `DRAFT` | `ACTIVE` | Yes |
| `INACTIVE` | `ACTIVE` | Yes |
| `ACTIVE` | `INACTIVE` | Yes |
| `ACTIVE` | `ACTIVE` | No |
| `DRAFT` | `INACTIVE` | No |
| `RETIRED` | `ACTIVE` | Rejected by the domain |

`RETIRED` and event type `RETIRED` exist in enums, but no retire method, use
case, repository operation, or endpoint is implemented. Runtime retirement is
therefore not part of the current lifecycle.

Reactivation replaces `active_from`, `activated_by`, and `activated_at` with the
latest activation; earlier values are recoverable only from event rows.

### 4.5 Sequence repository state

A sequence row is identified by policy plus scope key. `next_value` contains the
next decimal integer to allocate. Existing rows are locked with `FOR UPDATE`;
creation races use a nested transaction and retry up to three times after the
unique `(policy_id, scope_key)` constraint rejects a duplicate row.

Sequences belong to a policy, not merely to a kind. Activating a different
policy starts new sequence rows even when its mask is identical to an earlier
policy.

### 4.6 Legacy reference format

`LegacyReferenceFormat` contains a kind, name, and unrestricted regular
expression. Seeded formats accept the earlier `VRP` daily pattern and legacy
eight-character `CUP`, `OAL`, `OOL`, and `PUB` alphanumeric forms.

Legacy formats are migration-managed. There is no administrative list, create,
update, test, or removal API.

## 5. Authorisation

Policy list, exact read, preview, create, activate, and deactivate use cases all
require the active group to be `SYS_ADMIN`. Other staff and external callers
receive `403` through the shared authorisation boundary.

The Angular route applies `sysAdminGuard`, and the menu entry appears only in
the system-administration menu. The backend remains the security boundary.

Generated references are requested internally by business workflows and do not
require a separate admin caller.

## 6. Functional requirements

### FR-001 — Generate through the Published Language

Consumers obtain `ReferenceNumberGenerator` from
`app.reference_numbers.public` and call `generate(kind, on_date)`. The use case:

1. resolves the currently `ACTIVE` policy for the kind;
2. reserves the next value for that policy and derived scope;
3. renders the date tokens and padded decimal sequence; and
4. returns the shared-kernel `ReferenceNumber` value object.

If no active policy exists, `ActiveReferencePolicyNotFound` propagates to the
consumer. The public module exports neither this exception nor the independent
validation use case.

The active-policy query does not require `active_from <= on_date`; it selects the
currently active row and renders any date supplied by the consumer. Production
callers normally supply their operation's current date.

### FR-002 — Render and validate mask structure

Rendering replaces recognised date tokens with values from `on_date` and
appends the decimal sequence. A sequence below one is invalid. A sequence above
`10^width - 1` raises typed `SequenceOverflow`; it is never truncated.

Mask structure errors return `422 INVALID_REFERENCE_MASK` from preview and
create endpoints.

### FR-003 — Preview a mask without persistence

`POST /api/v1/admin/reference-number-policies/preview` accepts kind, mask, and
`sampleDate`. It returns the normalised mask, derived scope, parsed tokens, and
an example rendered with sequence one. It writes no policy or sequence.

Preview checks syntax and rendering only. It does not simulate collision with
existing resources, storage-column compatibility, sequence exhaustion,
historical validation, or concurrent activation.

### FR-004 — Create an immutable draft

`POST /api/v1/admin/reference-number-policies` creates a `DRAFT`, records the
calling permission as creator, inserts a `CREATED` event, and returns `201`.
The repository flushes the policy before its event to satisfy the event foreign
key.

Multiple drafts with the same kind and mask are allowed. There is no edit or
delete endpoint.

### FR-005 — List and read policies

| Endpoint | Behaviour |
| --- | --- |
| `GET /api/v1/admin/reference-number-policies?kind=...` | Unpaginated list, optionally filtered by kind, ordered by kind and newest creation first. |
| `GET /api/v1/admin/reference-number-policies/{policyId}` | Exact policy or `404 REFERENCE_POLICY_NOT_FOUND`. |

Responses expose raw permission identifiers for creation, update, and latest
activation; they do not resolve actor names. Events, sequences, and legacy
formats are not included.

### FR-006 — Activate a policy

`POST /api/v1/admin/reference-number-policies/{policyId}/activate` first updates
all active policies of the same kind to `INACTIVE`, then activates the loaded
`DRAFT` or `INACTIVE` policy and inserts its `ACTIVATED` event in the same
transaction.

The automatic bulk deactivation does not insert `DEACTIVATED` events for the
replaced policies. Explicitly deactivating an active policy does create one.

There is currently no unique database constraint enforcing one active policy
per kind and no row/advisory lock around replacement. Concurrent activations
can therefore commit more than one active policy. Although the repository maps
an `IntegrityError` to `ACTIVE_REFERENCE_POLICY_CONFLICT`, no active-policy
uniqueness constraint exists to reliably raise that conflict.

### FR-007 — Deactivate an active policy

`POST /api/v1/admin/reference-number-policies/{policyId}/deactivate` changes an
`ACTIVE` policy to `INACTIVE`, closes its active interval, records update
metadata, and inserts a `DEACTIVATED` event. Other source states return `409
INVALID_REFERENCE_POLICY_TRANSITION`.

Deactivation is permitted even when it leaves the kind without an active
policy, causing future generation for that kind to fail.

### FR-008 — Validate historical syntax internally

`ValidateReferenceNumber` returns true when the value matches:

- any policy of the requested kind whose current status is not `DRAFT`; or
- any seeded legacy regular expression of that kind.

Validation is syntax recognition, not proof that the number was issued. It does
not parse or validate calendar values, compare embedded dates with activation
intervals, inspect allocated sequences, or query consumer records. For example,
`MM` and `DD` tokens compile to arbitrary two-digit patterns.

The use case exists internally but is absent from the Published Language and
HTTP API, so application users and other contexts cannot currently invoke this
validation through a supported boundary.

### FR-009 — Allocate under sequence-row concurrency

An existing sequence row is locked before increment. A first-allocation race is
resolved by the unique policy/scope constraint and at most three nested-
transaction attempts.

This protects the counter row. Consumer tables also use unique reference
columns, but retry behaviour is consumer-specific. Public submission has a
unique-conflict retry path; the reference-number context itself does not retry
an entire consumer operation.

### FR-010 — Present policy administration in Angular

The system-admin page:

- groups all policies by the five kinds;
- sorts active, draft, inactive, then retired policies in each group;
- offers default example masks per kind;
- previews a mask and sample date;
- creates a draft;
- activates every non-active row; and
- deactivates an active row.

Actions display API errors and reload the list after success. There is no
confirmation, impact analysis, event history, legacy-format view, sequence
state, or warning that deactivation can stop number generation. A `RETIRED` row
would display an Activate button even though the backend rejects that action.

## 7. HTTP surface and failures

| Endpoint | Method |
| --- | --- |
| `/api/v1/admin/reference-number-policies` | `GET`, `POST` |
| `/api/v1/admin/reference-number-policies/preview` | `POST` |
| `/api/v1/admin/reference-number-policies/{policyId}` | `GET` |
| `/api/v1/admin/reference-number-policies/{policyId}/activate` | `POST` |
| `/api/v1/admin/reference-number-policies/{policyId}/deactivate` | `POST` |

| Situation | Result |
| --- | --- |
| Caller is not `SYS_ADMIN` | `403` |
| Unknown kind or malformed request | `422` validation envelope |
| Invalid mask | `422 INVALID_REFERENCE_MASK` |
| Unknown policy | `404 REFERENCE_POLICY_NOT_FOUND` |
| Invalid lifecycle transition | `409 INVALID_REFERENCE_POLICY_TRANSITION` |
| Repository integrity conflict during activation | `409 ACTIVE_REFERENCE_POLICY_CONFLICT` |

Generation failures are internal exceptions interpreted by each consuming
workflow rather than responses from a reference-number HTTP endpoint.

## 8. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | A mask contains one final uppercase sequence run of at most 12 characters. |
| INV-002 | A letter run becomes date tokens only when the complete run decomposes into supported tokens. |
| INV-003 | Sequence scope derives from the finest recognised date token. |
| INV-004 | Sequence reservation is unique per policy and scope key. |
| INV-005 | A never-activated `DRAFT` is ignored by historical syntax validation. |
| INV-006 | A `RETIRED` policy cannot be activated through the domain method. |
| INV-007 | Sequence overflow raises an error instead of truncating or wrapping. |
| INV-008 | Only `SYS_ADMIN` can inspect or mutate policies through the admin boundary. |

“At most one active policy per kind” is an intended rule but is not currently a
database-enforced invariant under concurrent transactions.

## 9. Acceptance and test traceability

| Behaviour | Representative automated evidence |
| --- | --- |
| Rendering and scope derivation | `test/reference_numbers/test_domain.py::test_mask_renders_and_derives_year_scope` |
| Final sequence and width | `test/reference_numbers/test_domain.py::test_mask_rejects_sequence_that_is_not_final_token`, `test/reference_numbers/test_domain.py::test_mask_sequence_width_is_hard_ceiling` |
| Conservative token parsing | `test/reference_numbers/test_domain.py::test_literal_text_containing_a_date_token_substring_is_not_misparsed`, `test/reference_numbers/test_domain.py::test_concatenated_date_tokens_still_parse_correctly` |
| Legacy format distinction and shared wrapper | `test/reference_numbers/test_domain.py::test_numeric_mask_does_not_validate_legacy_hex_without_legacy_format`, `test/reference_numbers/test_domain.py::test_reference_number_wrapper_allows_policy_valid_long_values` |
| Lifecycle checks | `test/reference_numbers/test_domain.py::test_inactive_policy_can_be_reactivated_but_active_cannot_be_activated_again`, `test/reference_numbers/test_domain.py::test_cannot_activate_a_retired_policy`, `test/reference_numbers/test_domain.py::test_cannot_deactivate_a_draft_policy` |
| Ignore never-active drafts | `test/reference_numbers/test_application.py::test_validate_reference_number_ignores_never_activated_draft_policy` |
| Event foreign-key ordering | `test/reference_numbers/test_application.py::test_add_policy_does_not_violate_the_event_foreign_key`, `test/reference_numbers/test_application.py::test_activate_and_deactivate_do_not_violate_the_event_foreign_key` |
| Admin authorisation and HTTP preview/create | `test/reference_numbers/test_api.py::test_sys_admin_can_preview_and_create_reference_policy`, `test/reference_numbers/test_api.py::test_staff_cannot_read_or_mutate_reference_policies`, `test/reference_numbers/test_application.py::test_preview_reference_policy_requires_sys_admin` |
| Angular page and API adapter | `reference-number-policies-page.component.spec.ts`, `reference-number-policy.service.spec.ts`, `sys-admin.guard.spec.ts` |

There are no PostgreSQL concurrency tests for sequence reservation or policy
activation, and API tests do not cover activation, deactivation, exact reads,
invalid masks, missing policies, or conflict mapping.

## 10. Non-functional requirements

- **Architecture:** production consumers depend on the Published Language;
  policies and sequences remain internal implementation details.
- **Transactionality:** sequence reservation participates in the consumer's
  transaction, avoiding committed gaps on normal rollback.
- **Auditability:** event rows retain create and explicit lifecycle operations,
  but no supported read API exposes them.
- **Capacity:** masks allow 12 sequence digits, while the database counter uses
  a 32-bit `Integer` and cannot represent that full domain range.
- **Compatibility:** the shared `ReferenceNumber` permits 128 characters, while
  consumer columns use smaller limits.
- **Performance:** policy lists are unpaginated; normal generation performs an
  active-policy lookup and a locked sequence lookup/update.

## 11. Known gaps and recommended changes

| ID | Priority | Finding | Recommended change |
| --- | --- | --- | --- |
| GAP-001 | Critical | No unique partial constraint or serialization mechanism enforces one `ACTIVE` policy per kind; concurrent activations can leave multiple active rows. | Add a PostgreSQL partial unique index, lock activation by kind, and test two concurrent transactions. |
| GAP-002 | High | Masks up to 128 characters can be activated although proposal/project columns allow 64 and log columns allow 32. | Define per-kind rendered-length limits from consumer contracts, align database columns, and reject incompatible drafts before activation. |
| GAP-003 | High | `DD` without month/year or `MM` without year can reset a hidden scope while rendering indistinguishable references in later periods. | Require hierarchical date tokens (`DD` with month/year, `MM` with year) or include the complete scope in rendered output. |
| GAP-004 | High | Sequence width allows 10–12 digits but `next_value` is a PostgreSQL 32-bit integer. | Migrate to `BIGINT` or lower the width ceiling consistently before production approaches integer capacity. |
| GAP-005 | High | Automatic replacement does not emit `DEACTIVATED` events, and events cannot be read through admin boundaries. | Record both sides of replacement and expose a paginated audit history with resolved actors. |
| GAP-006 | Medium | `RETIRED` is only a dormant enum state with no supported transition, yet the UI would offer to activate it. | Implement complete retirement semantics or remove the unused state/event and hide invalid UI actions. |
| GAP-007 | Medium | Historical validation accepts syntactically matching but never-issued references and invalid calendar components. | Rename it to format recognition or validate parsed dates, activation interval, and issuance records according to the business need. |
| GAP-008 | Medium | Validation and legacy formats are inaccessible through the Published Language/admin API. | Expose the capability if consumers need it, and add governed legacy-format management or document migrations as the sole mechanism. |
| GAP-009 | Medium | Deactivation may leave a kind without an active policy and stop downstream creation. | Require replacement activation, an explicit emergency confirmation, or a health check/alert for missing active policies. |
| GAP-010 | Medium | Identical policies are allowed and each restarts its own sequence, increasing collision risk. | Detect duplicate masks and perform an impact/collision simulation before activation. |
| GAP-011 | Medium | `get_active(kind, on_date)` ignores whether the supplied date precedes `active_from`. | Decide whether generation is current-policy-only or effective-dated, then enforce and name the contract accordingly. |
| GAP-012 | Medium | Activation/deactivation are one-click actions without confirmation or preview linkage. | Add confirmation showing kind, sample output, reset scope, current replacement, and downstream impact. |
| GAP-013 | Medium | Sequence overflow has no public error contract and consumer retry behaviour is inconsistent. | Publish typed allocation failures and standardise safe retry/mapping across all consumers. |
| GAP-014 | Low | The diagram lists `PROJECT` instead of implemented `COLLECTION_USE_PROJECT` and shows only `GLOBAL`/`YEAR` scopes. | Update PlantUML with all implemented kinds, statuses, scopes, legacy formats, and concurrency boundaries. |
| GAP-015 | Low | Raw actor permission IDs are shown without user names. | Resolve audit actors through Identity for the admin response or dedicated history view. |

## 12. Traceability

| Element | Location |
| --- | --- |
| Mask, policy, legacy format, enums, and transitions | `vitarerum-api/app/reference_numbers/domain/models.py` |
| Admin, generation, and validation use cases | `vitarerum-api/app/reference_numbers/application/use_cases.py` |
| Policy, sequence, event, and legacy persistence | `vitarerum-api/app/reference_numbers/infrastructure/` |
| Admin HTTP API | `vitarerum-api/app/reference_numbers/presentation/` |
| Published generator | `vitarerum-api/app/reference_numbers/public.py` |
| Initial policies, sequences, and legacy formats | `vitarerum-api/alembic/versions/00000041_0041_reference_number_policies.py` |
| Angular administration | `vitarerum-ui/src/app/features/admin/reference-number-policies/` |
| Production consumers | `vitarerum-api/app/public_submission/` and `app/use_of_collections/` |
| Automated tests | `vitarerum-api/test/reference_numbers/` and corresponding Angular specs |
| Policy diagram | `docs/diagrams/reference-number-policies.puml` and generated SVG |

## 13. Open product decisions

1. Must a kind always have an active policy, or is deliberate generation
   shutdown a supported administrative action?
2. Should numbering be current-policy-only or effective-dated for backdated
   resource creation?
3. Which maximum rendered length applies to each kind, and may consumer schemas
   be expanded to one common limit?
4. Does “valid reference” mean syntactically recognised or demonstrably issued?
5. Should reactivating a previous policy continue its earlier sequence or start
   a new activation-specific range?
6. Is irreversible retirement required for regulatory/audit reasons?
