# SPEC-025 — Curatorial knowledge base

| Field | Value |
| --- | --- |
| Identifier | SPEC-025 |
| Status | Implemented (with declared tenant-isolation, lineage-integrity, search-completeness, and provenance gaps) |
| Bounded context | `app.scientific_return` |
| Decision posture | Model-proposed memory, activated only after human validation |
| Derived from | Domain model, use cases, persistence, API, Angular interface, migrations, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-022](../022-cifragem-e-armazenamento/spec.md), and [SPEC-024](../024-investigacao-agentica-autonoma/spec.md) |
| Related documents | [API contracts](../../api_contracts/README.md) |

---

## 1. Problem

A scientific-return agent can repeat institution-specific mistakes. For
example, it may not know that the registered number `MB 12-345` also appears as
`MB12.345` in publications, or why a curator rejected a similar candidate in a
previous investigation. Without memory, each investigation starts from zero and
the institution cannot reuse reviewed knowledge.

Allowing a model to write directly into operational memory would turn a model
error into an input for future investigations. The knowledge base therefore
needs a human-validation boundary, institutional isolation, auditable state
changes, and correction without destructive rewriting.

## 2. Goal

Maintain institution-scoped curatorial memory that can inform future autonomous
investigations only while it is `ACTIVE`. Human-authored items are active on
creation; model-authored lessons remain `PROPOSED` until an authorized person
validates them. Corrections and withdrawals preserve the historical record.

This specification distinguishes current behavior from guarantees that the
implementation does not yet enforce. The latter are listed in Section 9.

## 3. Actors

| Actor | Responsibility |
| --- | --- |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION` | Create, correct, validate, discard, and retire knowledge |
| Other staff groups | Read the catalogue and lineage; cannot mutate it |
| Learning model | Propose a lesson from a recorded human decision; cannot activate it |
| Investigation agent | Retrieve active knowledge for the investigation institution |

## 4. Ubiquitous language and domain model

- **Knowledge item**: one durable unit of institutional memory.
- **Inventory variation example**: an `INVENTORY_VARIATION_EXAMPLE` containing
  a registered collection number, an observed publication form, and an
  explanation. Both number fields are mandatory for this kind.
- **Curatorial lesson**: a `CURATORIAL_LESSON` containing free-text guidance and
  no mandatory inventory-number pair.
- **Proposal**: a model-derived item awaiting human review.
- **Validation**: the transition that makes a proposal available to future
  investigations.
- **Retirement**: a non-destructive transition that removes an item from agent
  retrieval. Retiring a proposal is presented in the UI as discarding it.
- **Replacement**: a new active item linked to the item it corrects through
  `supersedesId`; the predecessor is retired.
- **Lineage**: the ordered predecessor/successor history reconstructed from
  `supersedesId`.

### 4.1 Lifecycle

```text
human creation ───────────────────────────────> ACTIVE ──retire──> RETIRED
                                                   │
model proposal ──> PROPOSED ──validate/activate───┘
                       │
                       └──discard/retire──────────> RETIRED

any existing item ──replace──> new ACTIVE successor
                    └────────> existing item becomes/remains RETIRED
```

`POST .../activate` approves a `PROPOSED` item. Calling it for an `ACTIVE` item
is an idempotent no-op that preserves its original validation metadata. A
`RETIRED` item cannot be reactivated and produces `422`; replacement is the
available route for creating a new active version.

## 5. Scope

### In scope

- Human creation of active knowledge.
- Model proposals derived from candidate decisions.
- Status and kind filtering, text search, paging, and status counts.
- Human validation, retirement, replacement, and lineage reads.
- Retrieval of active institutional memory by the autonomous agent.
- Encryption and institutional scoping of stored knowledge.
- The knowledge-base Angular page and its management workflow.

### Out of scope

- The candidate decision itself, defined by
  [SPEC-004](../004-decisao-candidato-publicacao/spec.md).
- Autonomous investigation execution, defined by
  [SPEC-024](../024-investigacao-agentica-autonoma/spec.md).
- Periodic review, expiry, deduplication, import, or export of knowledge.
- Restoring a retired item to active status.

## 6. Functional requirements

### RF-001 — Create human-authored knowledge

`POST /scientific-return/knowledge-items` requires JWT authentication,
`X-Permission-Id`, an active institution, and membership in `CURATORIAL`,
`COLLECTIONS_MANAGEMENT`, or `DIRECTION`. It returns `201 Created`.

A human-authored item is created directly as `ACTIVE`. The caller is recorded
as both creator and validator, and both timestamps are set to the same instant.
`content` is trimmed and must contain 1 to 4,000 characters. For an inventory
variation example, both `registeredNumber` and `observedForm` are required; each
is limited to 255 characters.

The API accepts both knowledge kinds. The current Angular create flow only
offers an inventory-example form; manually creating a free-text curatorial
lesson is therefore an API-only capability.

### RF-002 — Propose knowledge from a candidate decision

`POST /scientific-return/candidates/{candidateId}/knowledge-proposals` is
restricted to the three mutation groups and returns `201 Created`. The caller
supplies a non-blank `explanation` of at most 2,000 characters. The route loads
the candidate's decisions in ascending `decidedAt` and identifier order, then
uses the last decision. When no decision exists, it returns `404
SCIENTIFIC_RETURN_DECISION_NOT_FOUND`.

The learning model receives the human outcome, explanation, and persisted
decision context: inventory forms, queries, sources, prior explanation, and
contradictions. The generated item is `INVENTORY_VARIATION_EXAMPLE` only when
the proposal contains both number fields; otherwise it is a
`CURATORIAL_LESSON`.

The item is stored as `PROPOSED`, without validation metadata, and records the
source candidate, source decision, caller, model name, and a prompt-version
label. It cannot inform an investigation before RF-005 validation.

The current route does not verify that the source candidate or decision belongs
to the caller's institution. This is a critical gap, not an intended part of
the contract; see GAP-001.

### RF-003 — List, filter, search, and count knowledge

`GET /scientific-return/knowledge-items` is available to staff with an active
institutional permission. It returns only rows whose `institutionId` equals the
caller's institution.

| Parameter | Behavior |
| --- | --- |
| `status` | Optional `PROPOSED`, `ACTIVE`, or `RETIRED` filter |
| `kind` | Optional knowledge-kind filter |
| `q` | Optional content and inventory-citation search |
| `inventoryNumber` | Deprecated fallback used only when `q` is absent |
| `page` | Zero-based; minimum 0; default 0 |
| `size` | From 1 to 100; default 25 |

Without search text, paging and the filtered total are evaluated in SQL, newest
first with an identifier tie-breaker. With search text, the repository decrypts
at most the newest 2,000 rows matching the institution, status, and kind; it
then matches and paginates in memory. Content matching is a normalized
substring search. Inventory citations require an exact normalized value.
Normalization ignores case, accents, and whitespace differences.

`totalElements` and `totalPages` represent all filtered rows only when `q` is
absent. With `q`, they represent matches found inside the 2,000-row scan, and
the response does not report whether older rows were omitted. Status counts are
institution-wide and intentionally ignore the current status, kind, and search
filters.

Listing without an active institution returns `422`.

### RF-004 — Replace instead of overwriting

`PUT /scientific-return/knowledge-items/{itemId}` is restricted to the mutation
groups. It creates a new `ACTIVE` item of the same kind, copies the original
candidate and decision references, links the new item through `supersedesId`,
and records the caller as creator and validator. The predecessor is retired at
the same timestamp, and both changes are committed in one request transaction.

The use case currently accepts a predecessor in any status. The Angular UI only
offers editing for an `ACTIVE` item. Persistence does not prevent two concurrent
requests from creating different successors for the same predecessor; see
GAP-002.

### RF-005 — Validate, discard, and retire

| Operation | Current result |
| --- | --- |
| `POST /knowledge-items/{itemId}/activate` on `PROPOSED` | Changes it to `ACTIVE` and records validator and time |
| The same operation on `ACTIVE` | Returns the unchanged active item |
| The same operation on `RETIRED` | Returns `422`; retired knowledge cannot be reactivated |
| `DELETE /knowledge-items/{itemId}` | Changes a proposed or active item to `RETIRED` |
| `DELETE` on `RETIRED` | Returns the unchanged retired item |

No operation physically deletes a knowledge item. `DELETE` returns the item in
its resulting state rather than `204 No Content`. The Angular UI labels
retirement of a proposal as “Discard proposal” and retirement of active
knowledge as “Retire knowledge.”

### RF-006 — Read complete lineage

`GET /scientific-return/knowledge-items/{itemId}/history` is available to staff
and returns the institutional lineage in oldest-to-newest order. Access to an
item from another institution is hidden behind the same `404` used for an
unknown identifier.

The repository walks backward through `supersedesId`, then selects one successor
at each step. This yields a complete chain only while the lineage is linear and
its references are intact. The database does not currently enforce either
condition; see GAP-002.

### RF-007 — Retrieve memory for the investigation agent

The full-agentic investigation supplies its institution when retrieving
knowledge. The repository considers only `ACTIVE` rows from that institution.
For each target inventory number, exact keyed-hash matches are collected first;
additional recent active items are then ranked by structural similarity of
letters, digit-group widths, and separators.

The configured `memory_limit` defaults to 30 and is a global result ceiling,
not a per-object allowance. Duplicate items are removed. `PROPOSED` and
`RETIRED` items cannot reach the investigation prompt.

The repository port also permits an unscoped `institution_id = None` call, but
the inspected production full-agentic path passes the investigation institution.

### RF-008 — Enforce institutional access

Create, list, replace, validate, retire, and history use the institution from
the caller's active permission. Item-specific operations return `404` when the
stored institution differs, so another tenant's item existence is not revealed.

New application writes require a non-blank institution. The persistence column
remains nullable for migrated legacy rows, and source candidate/decision links
have no foreign-key constraint. Proposal-source isolation is incomplete as
declared in GAP-001.

### RF-009 — Protect content and identifiers at rest

Knowledge content, registered number, and observed form are encrypted with
field-specific additional authenticated data. Registered and observed numbers
also have keyed lookup hashes for exact matching. Status, kind, institutional
identifier, lineage identifiers, source identifiers, model and prompt labels,
and audit metadata remain queryable plaintext.

Text search requires application-side decryption because ciphertext uses a
random nonce. This design causes the search-completeness limitation in GAP-003.

### RF-010 — Present the workflow in Angular

The knowledge-base page uses the caller's active permission, loads pages of 25
items, and exposes status and kind filters, search, institution-wide counts,
pagination, audit metadata, and lineage. Mutation controls are rendered only
for the three curatorial groups.

Proposals offer validate or discard actions. Active items offer replace or
retire actions. Retired items expose history only. All consequential mutations
use confirmation dialogs, refresh the catalogue on success, and display
feedback or a normalized API error.

The page currently has no form for creating a human-authored
`CURATORIAL_LESSON`, even though it can list and filter such items.

## 7. Invariants and actual enforcement

| Invariant | Enforcement |
| --- | --- |
| A human-authored item starts active and validated | Domain constructor and create use case |
| A model proposal starts proposed and unvalidated | Proposal use case and domain constructor |
| Only active knowledge is retrieved by the production agent path | Repository filter and application call |
| A retired item cannot be activated | Domain transition |
| Retirement never physically deletes a row | State transition and repository save |
| Item mutations and history are scoped to the caller's institution | Application access checks |
| An inventory example contains both number fields | Domain validation |
| A replacement preserves its predecessor and retires it | Application transaction; not protected against concurrent branching |
| Every item belongs to exactly one institution | Enforced for new application writes, but not by the nullable database column |
| Proposal provenance identifies the prompt that actually ran | Not enforced; the stored label is hard-coded |

## 8. Acceptance criteria and verification

| Criterion | Evidence |
| --- | --- |
| Human creation produces an active, human-validated inventory example | `test_full_agentic_knowledge.py::test_curator_creates_active_textual_inventory_example` |
| Replacement retires the predecessor and links the successor | `::test_replacement_retires_previous_and_preserves_supersession` |
| Retired and discarded proposed items are not retrieved | `::test_retired_memory_is_not_retrieved`, `::test_discarded_proposal_stays_unvalidated_and_unretrieved` |
| Calling activate on an already active item preserves original validation | `::test_reactivating_active_knowledge_keeps_the_original_validation` |
| The global memory limit and structural ranking are applied | `::test_memory_limit_is_global_across_multiple_objects`, `::test_structurally_similar_memory_precedes_unrelated_recent_item` |
| Search covers lesson words and exact normalized citations | `::test_search_finds_an_agent_lesson_by_its_own_words`, `::test_search_still_matches_an_inventory_citation`, `::test_search_matches_lesson_content_ignoring_case_and_accents`, `::test_search_ignores_a_citation_fragment_that_matches_nothing` |
| Listing, retrieval, and item mutations use institutional scope | `::test_knowledge_page_is_scoped_to_the_callers_institution`, `::test_retrieval_uses_only_active_knowledge_from_the_institution`, `::test_mutation_hides_another_institutions_knowledge` |
| Listing requires an active institution | `::test_institutional_listing_requires_an_active_institution` |
| Linear replacement history is returned in full | `::test_history_returns_the_complete_supersession_chain` |
| The public API exposes operational knowledge endpoints | `test_api_contract.py::test_openapi_excludes_bench_and_keeps_operational_scientific_return` |
| Angular renders catalogue actions, inventory editor, proposal discard, filtering, and search | `scientific-return-knowledge-base-page.component.spec.ts` |

The current suite does not establish cross-tenant isolation for proposal
creation, retired-item activation rejection at the HTTP boundary, concurrent
replacement safety, detection of a truncated search, or actual learning-prompt
provenance.

## 9. Known gaps and required changes

### GAP-001 — Critical: proposal creation can cross the tenant boundary

The proposal route loads decisions solely by `candidateId` before any
institutional ownership check. A curator who knows another tenant's candidate
identifier can cause that decision context to be sent to the learning model and
persist a derived lesson in the caller's institution.

Required changes:

1. Load the candidate through an institution-scoped repository operation before
   reading its decisions.
2. Return an opaque `404` when the candidate does not belong to the caller's
   active institution.
3. Enforce and test that the chosen decision belongs to that candidate and
   institution.
4. Add foreign keys or equivalent validated references for source candidate and
   decision identifiers where migration constraints permit.

### GAP-002 — High: lineage can branch or contain broken references

`supersedes_id` has neither a foreign key nor a uniqueness constraint, and
replacement has no row lock or optimistic version check. Concurrent requests
can create multiple successors. History silently follows the first successor
in repository order and ignores the others.

Required changes:

1. Add a self-referential foreign key and a uniqueness constraint or partial
   unique index that permits at most one successor.
2. Lock or version-check the predecessor during replacement and translate a
   conflict to a stable API error.
3. Decide whether only `ACTIVE` predecessors may be replaced and enforce that
   policy consistently in API and UI.
4. Detect cycles and branches defensively when reading legacy lineage.

### GAP-003 — High: encrypted text search is silently incomplete

When `q` is present, only the newest 2,000 filtered rows are scanned.
`totalElements` counts matches in that window as though it were the complete
result set, with no truncation indicator.

Required changes:

1. Return explicit search coverage metadata, or adopt a complete searchable
   encryption/indexing strategy appropriate to the sensitivity of the data.
2. Ensure totals and pagination communicate whether results are exact or
   truncated.
3. Add a test with more than 2,000 eligible rows and matches outside the scan.

### GAP-004 — Medium: recorded prompt provenance is not authoritative

The reasoner fetches the currently published learning prompt, but its
`LearningProposal` result carries no prompt identity. The use case stores the
hard-coded label `scientific-return-full-agentic-learning-v1`, which can diverge
from the prompt version that actually ran.

Required changes:

1. Return prompt version identifier and label with the learning result.
2. Persist those returned values rather than a constant.
3. Add an adapter/use-case test proving that a newly published prompt version is
   recorded on the proposal.

### GAP-005 — Medium: database ownership permits institution-less legacy rows

`sr_knowledge_items.institution_id` remains nullable and has no institutional
foreign key. New use cases reject missing institutions, but unresolved migrated
rows may remain inaccessible and the database cannot uphold the ownership
invariant independently.

Required changes:

1. Audit and reconcile null institutional identifiers created by the backfill.
2. Add the appropriate foreign key and change the column to non-null after data
   remediation.
3. Add migration tests for both resolvable and unresolved legacy ownership.

### GAP-006 — Medium: UI cannot manually create curatorial lessons

The API supports human-authored `CURATORIAL_LESSON` items, and the UI can list
them, but the create modal always calls `createInventoryExample` and requires
the inventory-number pair.

Required changes:

1. Add a kind selector or a dedicated lesson form.
2. Apply kind-specific validation and explanatory copy.
3. Add component tests for creating and replacing a curatorial lesson.

### GAP-007 — Medium: proposal generation has no request idempotency

Repeated submissions invoke the model again and create independent proposals
for the same decision and explanation. The route exposes no idempotency key,
duplicate check, or durable model-call accounting comparable to autonomous
investigations.

Required changes:

1. Define an idempotency contract for proposal generation.
2. Persist the request identity before the external model call and make replay
   return the same proposal.
3. Record model latency, failure, and usage if this operation must participate
   in operational cost reporting.

## 10. Non-functional requirements

- **Authorization:** JWT plus `X-Permission-Id`; mutations restricted to the
  three curatorial groups and reads restricted to staff.
- **Confidentiality:** sensitive knowledge text and inventory forms encrypted at
  rest with field-specific authenticated context.
- **Auditability:** creator, validator, retiree, timestamps, model label, source
  identifiers, and replacement relationship are returned by the API.
- **Atomicity:** replacement retirement and successor creation commit together
  in the request transaction.
- **Architecture:** domain and application code remain independent of FastAPI
  and SQLAlchemy; identity details are read through `identity.public`.
- **Usability:** destructive or activating UI actions require confirmation and
  retained records remain visible through status filters and history.

## 11. Traceability

| Specification element | Implementation |
| --- | --- |
| Item aggregate, validation, transitions, and matching | `vitarerum-api/app/scientific_return/domain/full_agentic_models.py` |
| Kinds and statuses | `vitarerum-api/app/scientific_return/domain/enums.py` |
| Create, list, proposal, replacement, state, and history use cases | `vitarerum-api/app/scientific_return/application/knowledge.py` |
| Learning contract and adapter | `vitarerum-api/app/scientific_return/application/full_agentic_ports.py`, `infrastructure/full_agentic_reasoner.py` |
| Encryption, search, paging, retrieval, and lineage | `vitarerum-api/app/scientific_return/infrastructure/full_agentic_repository.py` |
| Persistence model | `vitarerum-api/app/scientific_return/infrastructure/models.py` |
| HTTP endpoints and actor enrichment | `vitarerum-api/app/scientific_return/presentation/routes.py` |
| Agent retrieval | `vitarerum-api/app/scientific_return/application/full_agentic.py` |
| Angular catalogue workflow | `vitarerum-ui/src/app/features/collections/projects/scientific-return/pages/knowledge-base/` |
| Angular item, history, and editor components | `vitarerum-ui/src/app/features/collections/projects/scientific-return/components/knowledge-*` |
| Backend acceptance tests | `vitarerum-api/test/scientific_return/test_full_agentic_knowledge.py` |
| UI acceptance tests | `vitarerum-ui/src/app/features/collections/projects/scientific-return/pages/knowledge-base/scientific-return-knowledge-base-page.component.spec.ts` |

## 12. Open questions

1. Should unreviewed model proposals expire or remain indefinitely in the
   validation queue?
2. Should active knowledge require periodic review or an explicit validity
   interval?
3. Should `memory_limit` vary by collection size, target count, or prompt-token
   budget instead of using a fixed global default?
4. Should replacement be restricted to active items, or may a retired/proposed
   item intentionally start a new active branch?
5. Which search design offers acceptable completeness without exposing
   sensitive curatorial text through a plaintext full-text index?
