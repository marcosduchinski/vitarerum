# SPEC-004 — Curatorial candidate decision and publication recording

| Field | Value |
| --- | --- |
| Identifier | SPEC-004 |
| Status | Implemented |
| Bounded context | `app/scientific_return`, writing to `use_of_collections` through its published language |
| Derived from | Candidate domain models, decision use case, repository mappings, cross-context ACL, public writer, HTTP schemas/routes, Angular review surfaces, and scientific-return tests |
| Related specs | [SPEC-003](../003-pipeline-deterministico-bibliografico/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-024](../024-investigacao-agentica-autonoma/spec.md) |

## 1. Problem

A bibliographic candidate is a hypothesis, not an institutional fact. Turning
it into the statement “this publication resulted from this collection-use
project” affects reporting, institutional indicators, and the museum's
long-term record. That transition must remain a deliberate human act with a
durable audit trail.

## 2. Goal

Define and enforce the boundary between machine-assisted discovery and human
curatorial authority. Automated processes may create or enrich candidates, but
only an authorised person may confirm one and create a publication-log entry,
or dismiss it as not representing scientific return.

## 3. Actors and authorisation

| Actor | Current capability |
| --- | --- |
| `CURATORIAL` | Read queues and history; confirm, correct and confirm, or dismiss candidates |
| `COLLECTIONS_MANAGEMENT` | Same decision capability as `CURATORIAL` |
| `DIRECTION` | Same decision capability as `CURATORIAL` |
| Other authenticated staff, including `SYS_ADMIN` | Read queues and decision history; no candidate decision |
| Deterministic pipeline | Create candidates; never decide them |
| Autonomous/LLM workflows | Create or enrich candidates and recommendations; never decide them |

The scientific-return use case checks the three review groups before loading
the candidate. The downstream publication-log use case independently checks
that the project is `COMPLETED` and the caller belongs to one of the same
groups. Neither boundary currently enforces institution ownership consistently;
see GAP-001.

## 4. Domain and context boundary

| DDD role | Element | Responsibility |
| --- | --- | --- |
| Aggregate root | `CandidatePublication` | Owns candidate status and the link to a confirmed publication entry |
| Entity | `CandidateEvidence` | Records structured evidence associated with the candidate |
| Entity | `CandidateDecision` | Preserves the human act, actor, time, evidence snapshot, optional correction, and optional reader context |
| Value object | `CandidateCorrection` | Carries the candidate fields proposed for correction |
| Application service | `DecideCandidate` | Authorises, validates, materialises, snapshots, and persists the decision |
| Outbound port | `ConfirmedPublicationWriter` | Expresses the capability to record a confirmed publication |
| Anti-corruption adapter | `UseOfCollectionsPublicationWriter` | Converts candidate metadata into the published `use_of_collections` command language |
| Downstream aggregate | `PublicationLog` | Owns the project's publication-log entries |

`scientific_return` does not import the downstream repository or table model.
Its infrastructure adapter calls `PublishedPublicationEntryWriter` from
`use_of_collections.public`. Both writes use the same SQLAlchemy session and are
committed by the route, which currently provides atomicity in the modular
monolith.

## 5. Ubiquitous language

- **Candidate**: a proposed publication in `PENDING`, `CONFIRMED`, or
  `DISMISSED` state.
- **Decision**: a typed human act: `CONFIRM`, `CORRECT_AND_CONFIRM`, or
  `DISMISS`.
- **Correction**: replacement values for title, DOI, URL, or authors supplied
  during `CORRECT_AND_CONFIRM`.
- **Evidence snapshot**: selected structured evidence fields copied when the
  decision executes.
- **Decision context**: an optional, encrypted snapshot derived from the latest
  completed full-agentic reader analysis.
- **Publication log entry**: a free-text journal entry in the project's
  `PublicationLog`.
- **Final candidate**: a candidate in `CONFIRMED` or `DISMISSED` state.

There is no `SNOOZED` state and no defer decision in the current domain.

## 6. Candidate lifecycle

```text
                    CONFIRM
                  ┌──────────> CONFIRMED
                  │
PENDING ──────────┤
                  │
                  └──────────> DISMISSED
                     DISMISS

CORRECT_AND_CONFIRM also transitions PENDING to CONFIRMED.
```

Only `PENDING` is decidable. Both terminal states reject another decision.
There is no reopening, correction-after-confirmation, or supervised reversal in
the scientific-return context.

## 7. Public API

| Method and route | Purpose | Access |
| --- | --- | --- |
| `GET /api/v1/scientific-return/projects/{projectId}/candidates` | Paginated candidates for one project | Staff |
| `GET /api/v1/scientific-return/candidates` | Global review queue with operational filters and reader projection | Staff |
| `POST /api/v1/scientific-return/candidates/{candidateId}/decision` | Record a final human decision | Review groups |
| `GET /api/v1/scientific-return/candidates/{candidateId}/decisions` | Read chronological decision history | Staff |

Pagination uses `page >= 0` and `1 <= size <= 100`.

## 8. Functional requirements

### FR-001 — Project candidate list

The project route accepts optional `status` and defaults to all statuses. It
returns newest candidates first, ordered by `createdAt` and then ID descending.
Each candidate includes:

- bibliographic metadata and source identity;
- status and `confirmedPublicationEntryId`;
- first-seen time and discovery kind;
- whether an autonomous flow created or rediscovered it;
- structured evidence sorted `PRIMARY`, `SUPPORTING`, then `WEAK`.

Each evidence item exposes type, strength, value, source field, explanation,
and optional `objectId`.

### FR-002 — Global review queue

The global route defaults to `status=PENDING` and accepts optional filters:

| Query parameter | Meaning |
| --- | --- |
| `status` | `PENDING`, `CONFIRMED`, `DISMISSED`, or omitted for all |
| `projectId` | Exact project identifier |
| `source` | Exact candidate source string |
| `evidenceStrength` | Candidate has at least one evidence row of this strength |
| `page`, `size` | Pagination |

In addition to the base candidate, each review item includes `projectId` and a
projection from the latest completed full-agentic reader analysis when one
exists:

- discovery basis, search intent, and search strategy;
- inventory-evidence status and grounded inventory forms;
- grounded passages;
- rejected passage and inventory-form counts;
- number of distinct consulted objects whose investigations linked to the
  candidate.

Evidence strength is information for human review, not an automated confidence
score. The queue remains reviewable when evidence is `NOT_OBSERVED` or
`UNAVAILABLE`.

### FR-003 — Decision request

`POST /candidates/{candidateId}/decision` accepts:

```json
{
  "decision": "DISMISS",
  "justification": "The author is a homonym.",
  "correction": null
}
```

`justification` is optional except for dismissal and has a maximum API length
of 2,000 characters. `correction` is required by the use case only for
`CORRECT_AND_CONFIRM`. The response is the updated candidate, not the created
decision record.

An unknown candidate returns `404`. A final candidate, missing dismissal
justification, or missing correction for `CORRECT_AND_CONFIRM` returns `422`.

### FR-004 — Decision effects

| Decision | Required input | Candidate effect | Publication-log effect |
| --- | --- | --- | --- |
| `CONFIRM` | none | Set `CONFIRMED` and store entry ID | Create one entry from current candidate metadata |
| `CORRECT_AND_CONFIRM` | `correction` object | Apply supported replacements, set `CONFIRMED`, store entry ID | Create one entry from corrected candidate metadata |
| `DISMISS` | Non-blank `justification` | Set `DISMISSED` | None |

The current server does not reject an irrelevant correction supplied with
`CONFIRM` or `DISMISS`; it stores that correction on the audit decision without
applying it. This is documented as GAP-003 rather than intended behaviour.

### FR-005 — Correction semantics

The correction schema exposes `title`, `doi`, `url`, and `authors`.

| Field | `null`/omitted | Empty value | Non-empty value |
| --- | --- | --- | --- |
| `title` | Preserve current title | Preserve current title because the use case uses truthiness | Replace title |
| `doi` | Preserve current DOI | Replace with an empty string | Replace DOI |
| `url` | Preserve current URL | Replace with an empty string | Replace URL |
| `authors` | Preserve current authors | Replace with an empty author tuple | Replace authors |

The Angular form trims text, converts blank DOI/URL to `null`, removes blank
author elements, and requires a non-blank corrected title. These client checks
are not equivalent to server validation; see GAP-004.

### FR-006 — Publication-log materialisation

For confirmation, the adapter resolves the candidate's project through its
watch and calls the downstream published writer. The downstream use case:

1. verifies that the project exists;
2. authorises publication entry creation for its current phase;
3. lazily creates the project's `PublicationLog` and reference number if none
   exists;
4. adds an entry attributed to the deciding permission.

The entry is not a structured bibliographic record. Its `note` is assembled as
period-separated text from:

1. title;
2. comma-separated authors, or `Unknown authors`;
3. publication date when present;
4. `DOI: {doi}` when present;
5. URL when present.

No `collectionUseObjectId` is attached, even when candidate evidence identifies
consulted objects.

### FR-007 — Transaction boundary

Publication-log entry creation, candidate status/link update, and decision-row
creation occur through one database session. The HTTP route commits only after
the decision use case completes. An exception before that commit rolls back all
three writes.

This atomicity depends on the current shared-database deployment. It is not a
distributed transaction contract for independently deployed contexts.

### FR-008 — Finality

The use case rejects a decision when the loaded candidate is already
`CONFIRMED` or `DISMISSED`. A dismissed candidate remains dismissed when later
deterministic runs rediscover its deduplication key. Automated investigations
also treat a human-decided candidate as terminal.

The read-check-write sequence has no row lock, version, or one-decision unique
constraint, so finality is not safe under concurrent requests; see GAP-002.

### FR-009 — Structured evidence snapshot

Every decision stores the candidate's evidence as observed by the server when
the decision use case loads it. For each evidence row, the snapshot copies:

- `type`;
- `strength`;
- `value`;
- `sourceField`;
- `explanation`.

It does not copy `objectId`, evidence creation time, or autonomous provenance
identifiers. The snapshot is stored as plaintext JSON. These limitations are
covered by GAP-005 and GAP-008.

### FR-010 — Optional reader decision context

The use case reads candidate analyses newest first and selects the latest item
whose result exists and whose prompt-version ID starts with the full-agentic
reader prefix. When found, it stores decision-context version 2 with:

- passages, inventory forms, queries, and sources;
- reader explanation, confidence, and contradictions;
- curatorial knowledge-item IDs;
- discovery basis, search intent, and search strategy when available;
- inventory-evidence status and grounded inventory forms when valid;
- the current count of distinct cited objects.

Malformed optional enum or grounded-form values are ignored rather than
failing the decision. The context is encrypted at rest. When no eligible reader
analysis exists, `decisionContext` is `null`.

This captures the latest server state at decision time. It does not prove which
screen content the person actually viewed; see GAP-005.

### FR-011 — Decision history

The history route returns decisions in ascending `decidedAt`, then ID order.
Each response contains decision ID, candidate ID, type, justification, actor,
time, structured evidence snapshot, correction, and optional reader context.

The route does not first verify that the candidate exists. An unknown candidate
ID therefore returns `200` with an empty list instead of `404`; see GAP-007.

### FR-012 — User-interface workflow

The global Scientific Return Review page displays the enriched review dossier
and links to the candidate within its project record. Decisions are performed
in the project scientific-return panel.

For a pending candidate and review-group user, the panel offers:

- **Confirm** without an additional note field;
- **Correct** with title, DOI, URL, authors, and optional note;
- **Dismiss** with a required note;
- decision history toggle.

The panel shows only decision type, time, and justification in its inline
history, even though the API returns corrections, evidence snapshots, actors,
and reader context. There are no focused component tests for submitting the
three decision variants; see GAP-009.

### FR-013 — Optional knowledge proposal after a decision

After a decision succeeds, the Angular panel separately calls the knowledge
proposal endpoint whenever the submitted justification/note is non-blank. A
dismissal therefore always attempts this follow-up; a corrected confirmation
does so only when a note was supplied.

This second call uses the latest stored candidate decision and proposes a
reusable lesson for later curator validation. Failure does not undo the
decision: the UI reports that the decision was saved but the lesson was not
proposed.

## 9. Enforced invariants

| ID | Invariant | Enforcement |
| --- | --- | --- |
| INV-001 | Automated discovery and investigation code has no capability to write a publication-log entry | Port exclusion and structural tests |
| INV-002 | Only the three review groups reach the decision use case | Application authorisation |
| INV-003 | Dismissal requires a non-blank justification | Decision use case |
| INV-004 | A sequential second decision on a final candidate is rejected | Candidate-state check |
| INV-005 | Confirmation creates the publication entry, candidate link, and decision in one local database transaction | Shared session and route commit |
| INV-006 | Every stored decision contains a structured evidence snapshot, possibly empty | Decision construction and non-null JSON column |
| INV-007 | The optional full-agentic reader context is encrypted at rest | Repository field encryption |

The stronger claims “exactly one decision under concurrency”, “the snapshot is
exactly what the human viewed”, and “all decision audit data is encrypted” are
not enforced by the current implementation.

## 10. Acceptance evidence

| ID | Behaviour | Automated evidence |
| --- | --- | --- |
| AC-001 | Confirmation materialises a publication entry and stores evidence | `test_scientific_return.py::test_confirm_materializes_publication_and_audits_evidence` |
| AC-002 | The latest full-agentic reader analysis becomes the decision context | `test_scientific_return.py::test_decision_context_uses_latest_full_agentic_reader_only` |
| AC-003 | A rolled-back reader prompt version still supplies context | `test_scientific_return.py::test_a_rolled_back_reader_version_still_yields_a_decision_context` |
| AC-004 | Unrelated analyses do not become decision context | `test_scientific_return.py::test_non_reader_analysis_does_not_create_agentic_decision_context` |
| AC-005 | Dismissed status survives deterministic rediscovery | `test_scientific_return.py::test_dismissed_candidate_is_remembered_on_later_run` |
| AC-006 | Autonomous discovery leaves candidates pending | `test_run_investigation.py::test_the_candidate_still_requires_a_human_decision` |
| AC-007 | Autonomous code has no publication writer and creates no candidate decisions | `test_agent_security.py::test_the_cycle_has_no_route_to_the_publication_log`, `::test_no_candidate_is_ever_decided_by_the_cycle` |
| AC-008 | Decision context fields are exposed through the API contract | `test_provenance_contract.py::test_the_decision_snapshot_keeps_what_the_curator_was_shown` |
| AC-009 | The review page renders grounded and unavailable evidence states | `scientific-return-queue-page.component.spec.ts` |
| AC-010 | The Angular service sends decisions through a separate endpoint | `scientific-return-api.service.spec.ts::sends a human decision separately from candidate discovery` |

## 11. Known implementation gaps

### GAP-001 — Institution isolation is not enforced

**Severity: critical.** Candidate lists, the global queue, candidate lookup,
decision history, and decision mutation are selected by global identifiers and
do not constrain the caller's institution. The downstream publication writer
checks project phase and group but not institution ownership. A staff user who
knows an identifier may observe or decide another institution's candidate.

**Required change:** propagate an authoritative institution ID from the project,
scope every repository operation and downstream command, and add negative
cross-institution API tests. This must be resolved together with SPEC-002
GAP-001.

### GAP-002 — Concurrent decisions can create multiple publications

**Severity: critical.** Decision finality is a read-check-write sequence without
a row lock, optimistic version, idempotency key, or unique decision constraint.
Two requests can both observe `PENDING`, create separate publication-log
entries, add separate decision rows, and race to store one linked entry ID on
the candidate.

**Required change:** serialise decisions per candidate, enforce one terminal
decision at database level, and make publication materialisation idempotent.
Test confirm/confirm, confirm/dismiss, and retry-after-timeout races.

### GAP-003 — Irrelevant correction payloads are accepted and audited

**Severity: high.** The server requires a correction for
`CORRECT_AND_CONFIRM`, but does not forbid one on `CONFIRM` or `DISMISS`. In
those cases the candidate and publication entry ignore the correction while
the decision row records it, producing a misleading audit trail.

**Required change:** use a discriminated request union with decision-specific
payloads and reject fields that do not apply.

### GAP-004 — Corrected bibliographic fields lack server validation

**Severity: high.** An empty correction object satisfies
`CORRECT_AND_CONFIRM`; an empty title silently preserves the original; an empty
DOI or URL may be stored; an empty author list becomes `Unknown authors`; and
the server validates neither DOI syntax, URL syntax, author content, nor field
lengths compatible with persistence.

**Required change:** introduce validated bibliographic value objects, require at
least one actual change, normalise blank/null semantics, and enforce constraints
in both request and domain layers.

### GAP-005 — The audit snapshot is incomplete and not a view receipt

**Severity: high.** Structured evidence omits `objectId`, time, and agentic
provenance. Reader context is independently reselected as the newest eligible
analysis during the decision; it may not be the analysis the user opened. The
server accepts no signed/versioned review token tying the command to the queue
representation actually displayed.

**Required change:** persist a versioned review dossier with all relevant
provenance, return its immutable ID/hash to the client, and require that receipt
when deciding or explicitly record that the user chose newer evidence.

### GAP-006 — Correcting a DOI does not update candidate identity

**Severity: high.** `CORRECT_AND_CONFIRM` changes the candidate DOI but leaves
its deduplication key unchanged. A metadata-keyed candidate corrected to a DOI,
or a candidate whose DOI is corrected, can later coexist with another candidate
using the canonical DOI key.

**Required change:** define whether identity is immutable after discovery. If
correction changes identity, migrate/merge under the watch-local uniqueness
constraint atomically and preserve aliases in the audit trail.

### GAP-007 — Decision-history absence is ambiguous

**Severity: medium.** `GET /candidates/{id}/decisions` returns the same empty
array for a missing candidate and for an existing pending candidate. This
differs from mutation and analysis routes that return typed `404` errors.

**Required change:** verify candidate existence first or formally document an
existence-hiding contract and apply it consistently.

### GAP-008 — Most decision audit fields are plaintext

**Severity: medium.** Reader context is encrypted, but justification, evidence
snapshot, correction, deciding permission, and timestamps are plaintext.
Evidence values may contain inventory identifiers and justification may contain
personal or sensitive narrative.

**Required change:** complete a data-classification and retention review,
encrypt sensitive JSON/text fields where required, and keep only indexed audit
metadata in plaintext.

### GAP-009 — Decision UX and tests expose only part of the audit

**Severity: medium.** The project panel's history hides actor, correction,
evidence snapshot, and reader context. Its component tests cover investigation
and watch behaviour but not confirm, correct-and-confirm, dismissal validation,
or post-decision reload. The backend likewise has only one direct happy-path
confirmation test and no focused dismissal/correction/finality matrix.

**Required change:** present a complete accessible decision-detail view and add
backend plus Angular tests for every command, validation failure, and final
state.

### GAP-010 — Publication materialisation is an unstructured note

**Severity: medium.** Confirmation reduces bibliographic metadata to one
period-separated string. The publication log has no candidate ID, DOI field, or
object association, while the candidate only points back by entry ID. Editing
the downstream note can make the two records diverge semantically.

**Required change:** add structured provenance to the publication entry or a
dedicated link entity, retain the human-readable note as a projection, and
define edit/delete rules for scientifically confirmed entries.

### GAP-011 — Local atomicity couples the contexts to one database

**Severity: low.** Atomic confirmation currently works because both bounded
contexts share one session and transaction. If they are deployed separately,
the published writer contract offers no idempotency key, durable command, or
compensation protocol.

**Required change:** keep the modular-monolith assumption explicit or design an
outbox/saga and idempotent downstream command before separating deployments.

## 12. Non-functional requirements

- **Human authority:** no pipeline, model, or autonomous policy may produce a
  terminal candidate decision.
- **Auditability:** retain who decided, when, which command was chosen, the
  justification, correction, structured evidence, and available reader context.
- **Atomicity:** within the current modular monolith, publication entry,
  candidate state, and decision history commit together.
- **Confidentiality:** protect decision material according to its data
  classification and expose it only to authorised staff.
- **Accessibility:** decision controls and audit detail must remain operable and
  understandable without relying on colour or evidence-strength shorthand.
- **Boundary discipline:** cross-context writes must use
  `app.use_of_collections.public`, not downstream repositories or ORM models.

## 13. Traceability

| Concern | Implementation |
| --- | --- |
| Candidate state, correction, and decision entities | `vitarerum-api/app/scientific_return/domain/models.py` |
| Reader decision-context value object | `vitarerum-api/app/scientific_return/domain/full_agentic_models.py` |
| Decision orchestration and snapshot construction | `vitarerum-api/app/scientific_return/application/use_cases.py` |
| Publication-writer port | `vitarerum-api/app/scientific_return/application/ports.py` |
| Cross-context adapter | `vitarerum-api/app/scientific_return/infrastructure/acls.py` |
| Decision and queue persistence | `vitarerum-api/app/scientific_return/infrastructure/{models,repositories}.py` |
| HTTP schemas and routes | `vitarerum-api/app/scientific_return/presentation/{schemas,routes}.py` |
| Published downstream command | `vitarerum-api/app/use_of_collections/public.py` |
| Publication-log policy and entry creation | `vitarerum-api/app/use_of_collections/application/use_cases/publication.py` |
| Review queue | `vitarerum-ui/src/app/features/collections/projects/pages/scientific-return-queue/` |
| Decision panel and inline history | `vitarerum-ui/src/app/features/collections/projects/components/scientific-return-panel/` |
| Backend evidence | `vitarerum-api/test/scientific_return/` |
| UI evidence | Scientific-return service, queue, and panel `*.spec.ts` files |

## 14. Open product decisions

1. Should an erroneous confirmation be reversed in a supervised workflow, or
   corrected only in the publication-log context with an immutable amendment?
2. Should dismissal reasons become a controlled taxonomy such as out of scope,
   author homonym, wrong specimen, duplicate, or insufficient evidence?
3. Must a confirmer explicitly acknowledge `NOT_OBSERVED` or `UNAVAILABLE`
   inventory evidence before recording scientific return?
4. Should a confirmed publication be linked to every cited consulted object,
   selected objects, or only the project as a whole?
5. Should a decision note automatically propose reusable knowledge, or should
   that remain a separate explicit user choice?
