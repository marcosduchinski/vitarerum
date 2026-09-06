# SPEC-024 — Autonomous agentic investigation (full-agentic)

| Field | Value |
| --- | --- |
| Identifier | SPEC-024 |
| Status | Implemented (with declared tenant-isolation and manual-targeting gaps) |
| Bounded context | `app.scientific_return` |
| Execution mode | Asynchronous, outside the initiating HTTP request |
| Decision posture | Autonomous discovery; mandatory human decision |
| Derived from | Domain model, use cases, source adapters, worker commands, migrations, API, Angular interface, deployment configuration, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-022](../022-cifragem-e-armazenamento/spec.md), and [SPEC-025](../025-base-de-conhecimento-curatorial/spec.md) |

---

## 1. Problem

The assisted cycle in [SPEC-001](../001-investigacao-agentica-assistida/spec.md)
runs while a person waits for an HTTP request. A scientific-return sweep over
the consulted objects of a project can take longer than one request and does
not require a person to watch every search happen.

Moving work outside the request creates additional risks: authorization must be
captured before enqueueing, duplicate executions must be prevented, model and
source cost must be bounded, a dead worker must not hold a target forever, and
untrusted publication text must not acquire decision-making authority.

## 2. Goal

Run resumable autonomous discovery with durable state, bounded cost, explicit
source readiness, evidence grounding, and an auditable trajectory. The system
may search, read, and propose candidates; only an authorized person may decide
whether a candidate becomes an institutional scientific-return record.

This specification distinguishes implemented safeguards from guarantees that
the current API does not yet enforce. The latter are listed in Section 9.

## 3. Actors

| Actor | Responsibility |
| --- | --- |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION` | Start and cancel investigations; review candidates |
| Other staff groups | Read monitoring state and autonomous trajectories |
| Scheduler | Starts object-scoped investigations after a scheduled deterministic sweep |
| Worker | Claims queued work under a time-limited lease and persists progress |
| Planner model | Proposes structured searches within the allowed source capabilities |
| Reader model | Assesses one bibliographic record without access to tools |
| Grounding validator | Accepts only claims found in fields actually delivered by a source |

## 4. Ubiquitous language and domain model

- **Full-agentic investigation**: aggregate root that owns target identity,
  lifecycle, budget, usage, lease, recovery count, and terminal outcome.
- **Target**: tuple of watch, objective, optional candidate, and optional
  consulted object. The current supported objective is discovery and therefore
  requires no candidate.
- **Lease**: temporary right of one worker to advance an investigation.
- **Recovery**: takeover after a running lease expires. It is counted separately
  from a healthy worker voluntarily yielding its execution slice.
- **Execution slice**: application deadline shorter than the hosting platform's
  termination window. Work yields to the queue before the platform kills it.
- **Deterministic floor**: bounded first plan derived from recorded inventory,
  object, and researcher data without a model call.
- **Readiness**: configuration diagnostic for requested, operational, and
  inspectable-evidence sources. It is not a live connectivity or credential
  validity check.
- **Circuit breaker**: admission guard based on the precision of human decisions
  over candidates linked to full-agentic investigations.
- **Trajectory**: ordered sequence of typed, persisted events describing plans,
  calls, searches, assessments, fallbacks, candidates, and termination.
- **Degraded completion**: terminal `COMPLETED` investigation that finished on
  incomplete capability, such as the deterministic floor after planner failure.
  It may contain candidates; zero candidates is not proof of absence.
- **Grounded claim**: reader passage or inventory form found literally, after
  Unicode, case, and whitespace normalization, in a delivered title, abstract,
  or indexed-text field.

### 4.1 Lifecycle

```text
QUEUED ──claim──> RUNNING ──complete──> COMPLETED
   │                 │  │
   │                 │  ├──failure/recovery ceiling──> FAILED
   │                 │  └──cancel request──> CANCEL_REQUESTED ──worker/reaper──> CANCELLED
   │                 └──slice exhausted──> QUEUED
   └──cancel request──> CANCELLED
```

`COMPLETED`, `FAILED`, and `CANCELLED` are terminal. Requesting cancellation of
an already terminal investigation is currently a no-op that returns its
unchanged state.

## 5. Scope

### In scope

- Admission, idempotency, queueing, leasing, recovery, yielding, and reaping.
- Deterministic and model-planned searches over allowed bibliographic sources.
- Tool-call replay, budgets, deadlines, grounding, and publication deduplication.
- Candidate provenance, trajectory, readiness, health metrics, and Angular
  presentation.
- Scheduled fan-out by consulted object.

### Out of scope

- Human candidate decisions, defined by
  [SPEC-004](../004-decisao-candidato-publicacao/spec.md).
- Watch cadence and deterministic sweeps, defined by
  [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md).
- Curatorial-knowledge lifecycle, defined by
  [SPEC-025](../025-base-de-conhecimento-curatorial/spec.md).
- Autonomous writing to the collection-use publication log.

---

## 6. Functional requirements

### FR-001 — Start an autonomous discovery

`POST /scientific-return/watches/{watchId}/full-agentic-investigations`
requires JWT authentication, `X-Permission-Id`, `Idempotency-Key`, and a JSON
body. It is restricted to `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, and
`DIRECTION`, persists a `QUEUED` investigation, and returns `202 Accepted`.

The public API currently supports only:

```json
{ "objective": "DISCOVER_CANDIDATE" }
```

`objective` defaults to `DISCOVER_CANDIDATE`. Although the request schema still
exposes optional `candidateId` and the enum contains `ENRICH_CANDIDATE`, either a
non-null candidate or the enrichment objective is rejected with `422`.

The manual endpoint does not accept `objectId`; it creates a legacy
project-scoped target with `objectId = null`.

### FR-002 — Ordered admission guards

The start use case evaluates these guards before creating a new row, in this
order:

| Order | Condition | Result |
| --- | --- | --- |
| 1 | Same idempotency key and same target | Return the existing investigation |
| 1 | Same idempotency key and a different target | `422` |
| 2 | Objective is not discovery, or a candidate is supplied | `422` |
| 3 | Feature switch is disabled | `409 FULL_AGENTIC_DISABLED` |
| 4 | No requested operational source can supply inspectable evidence | `503 FULL_AGENTIC_SOURCE_CONFIGURATION_INVALID` |
| 5 | Human-decision precision is below the configured threshold | `503 FULL_AGENTIC_CIRCUIT_OPEN` |
| 6 | Watch does not exist | `404 SCIENTIFIC_RETURN_WATCH_NOT_FOUND` |
| 7 | Caller and watch have different non-null institutions | `422` |
| 8 | Candidate or object does not belong to the watch snapshot | `422` |
| 9 | Another investigation is live for the same target | `409 FULL_AGENTIC_ALREADY_RUNNING` |

The institution, candidate, and object checks occur after feature, source, and
circuit checks. The object branch is used by scheduled starts; the public route
does not currently pass an object.

Admission does not require the watch to be `ACTIVE` or due, and the worker does
not recheck watch status before searching. Pausing or closing a watch therefore
does not cancel queued autonomous work or prevent a direct manual start. This
differs from deterministic/assisted starts; see GAP-010.

### FR-003 — Durable idempotency and dispatch

An idempotency key is globally unique in persistence and bound to one complete
target. The investigation row is committed before dispatch. If dispatch fails,
the durable `QUEUED` row remains available to the database-polling worker; the
initiating request may still fail because dispatch occurs after the commit.

The `DATABASE` dispatcher treats the row itself as the queue. The optional
`CLOUD_TASKS` dispatcher sends an OIDC-authenticated task containing the
investigation identifier and `X-Worker-Token`.

### FR-004 — One live investigation per target

At most one row in `QUEUED`, `RUNNING`, or `CANCEL_REQUESTED` may exist for the
same watch, objective, candidate, and object. The application checks first and
PostgreSQL enforces the invariant through the partial unique index
`uq_sr_fa_live_target`.

Different object identifiers are independent targets. A null object is also a
distinct target, so a manual project-scoped investigation can currently coexist
with scheduled object-scoped investigations.

### FR-005 — Circuit breaker uses human outcomes

When at least `circuit_min_decisions` linked candidates have a human outcome,
precision is:

```text
confirmed full-agentic candidates / (confirmed + dismissed full-agentic candidates)
```

Admission is refused when this value is below `circuit_min_precision`. Pending
candidates and model self-assessment do not enter the calculation. Both
thresholds default to zero, which disables the breaker until explicitly
configured. The metric is currently global rather than institution-scoped.

### FR-006 — Source readiness

`GET /scientific-return/full-agentic-readiness` is available to staff and
returns:

- whether the feature is enabled;
- requested, operational, unavailable, and inspectable-evidence source names;
- whether the combination is valid and a diagnostic message when it is not.

No key, token, endpoint, or credential fragment is returned. “Operational” is
derived from local configuration: Crossref is always registered, OpenAlex
requires a configured API key, and Europe PMC requires its enable flag.
Readiness does not call the upstream providers.

### FR-007 — Object-scoped scheduled fan-out

After a deterministic scheduled run, the sweep creates one discovery
investigation per consulted object, up to `max_objects`. Each key contains the
deterministic run and object identifiers, so replaying a sweep does not buy the
same work twice.

Failure or an already-live target for one object does not stop other objects.
When the object ceiling truncates coverage, every created investigation receives
a `COVERAGE_TRUNCATED` event containing covered count, total count, and uncovered
object identifiers.

### FR-008 — Lease, recovery, and execution slices

A worker atomically claims either a queued row or a live row whose lease has
expired. A live lease cannot be taken by a second worker. Lease renewal and LLM
reservation require the current owner and an unexpired lease.

Taking over an expired live lease increments `recoveryCount`. A voluntary slice
yield returns the aggregate to `QUEUED`, records
`EXECUTION_SLICE_EXHAUSTED`, and does not consume recovery allowance. A
push-queue dispatcher is notified of the continuation; failure to announce it
does not remove the durable queued row.

If `recoveryCount` becomes greater than `max_recoveries`, the worker marks the
investigation `FAILED`. Before each queue drain, a reaper terminates live rows
older than `max_age_seconds`, measured from creation rather than heartbeat, and
closes any associated search run.

Configuration rejects deadline combinations in which an external call cannot
fit inside a lease or an execution slice plus the longest call cannot fit inside
the platform window.

### FR-009 — Cancellation

`POST /scientific-return/full-agentic-investigations/{investigationId}/cancel`
is restricted to the three mutation groups.

- `QUEUED` becomes `CANCELLED` immediately;
- `RUNNING` becomes `CANCEL_REQUESTED` until a worker or reaper closes it;
- repeated cancellation while requested is idempotent;
- terminal investigations are returned unchanged.

### FR-010 — State and trajectory reads

| Endpoint | Response |
| --- | --- |
| `GET /scientific-return/full-agentic-investigations/{investigationId}` | Target, lifecycle, budget, usage, recovery details, degradation, and lease expiry |
| `GET /scientific-return/watches/{watchId}/full-agentic-investigations` | Newest-first list, with `limit` from 1 to 100 and default 20 |
| `GET /scientific-return/full-agentic-investigations/{investigationId}/trajectory` | Events ordered by sequence |

All three require a staff identity. Individual state returns `404` for an
unknown investigation. The list returns an empty array for an unknown watch,
and trajectory returns an empty array for an unknown investigation. Current
tenant-authorization gaps are declared in Section 9.

### FR-011 — Deterministic floor and constrained planning

The first iteration uses a deterministic floor rather than the planner. It
interleaves author-plus-object and bare-inventory searches, uses at most half of
the query budget, and leaves capacity for subsequent model planning.

Later iterations ask the planner for structured search specifications. Unknown
sources and strategies unsupported by a source's declared capabilities are
filtered before execution. A malformed planner response is retried once. If it
still fails, or the remaining model-call budget cannot fund a plan, the
investigation completes as degraded on its deterministic floor.

### FR-012 — Bounded, replayable external work

Budgets independently cap iterations, queries, accepted results, candidate
links, and LLM calls. Every model call is reserved and committed before leaving
the process. A worker killed during that call therefore consumes the reservation
instead of repeating calls indefinitely.

Each search tool invocation has a normalized idempotency key and a persisted,
encrypted invocation/result record. A completed call is replayed after resume;
an already paid result is not silently discarded. Duplicate searches and
records already assessed are skipped. Metadata-only sources receive a smaller
per-query result allowance.

### FR-013 — Reader isolation and evidence grounding

The reader receives one bibliographic record plus trusted project, search, and
curatorial context. It has no tool registry and cannot select system-derived
identifiers, write decisions, or publish to the collection-use log.

Reader passages and inventory forms are checked against the fields actually
delivered by the source. Unsupported, duplicate, and empty claims are rejected
and counted. Inventory evidence is:

| Status | Meaning |
| --- | --- |
| `VERIFIED` | At least one claimed form occurs in a delivered field |
| `NOT_OBSERVED` | Inspectable full text was delivered, but no reader-submitted inventory form survived grounding |
| `UNAVAILABLE` | The delivered material cannot establish absence |

Grounding filters factual claims but does not silently rewrite the reader's
relevance verdict. The curator sees provenance and rejection counts when making
the separate human decision.

Literal occurrence does not establish that a claimed form denotes the watched
object; the grounding function does not compare it with the registered number.
Nor is `NOT_OBSERVED` an exhaustive absence finding: the reader may submit no
forms even when the text contains an inventory number.

### FR-014 — Candidate identity and provenance

Records are deduplicated by publication identity so figures, tables, and other
components do not consume the candidate ceiling as separate publications. The
investigation links a candidate as `CREATED` or `REDISCOVERED`, preserving
source, query, search intent, search strategy, grounded passages, grounded
inventory forms, prompt identity, and knowledge identifiers.

The later decision snapshot preserves the latest eligible reader context
selected by the server when deciding. It does not prove which analysis the
reviewer actually saw; the review-receipt gap is documented in SPEC-004,
GAP-005. Only the separate human decision use case may confirm,
correct-and-confirm, or dismiss a candidate.

### FR-015 — Internal worker entry point

`POST /scientific-return/internal/full-agentic/execute` executes one queued
investigation. It requires `X-Worker-Token`, compared with the configured secret
using constant-time comparison, and is excluded from OpenAPI.

When a newly completed run produced candidates, the route attempts to notify
the watch creator. Notification failure is logged and rolled back independently
without undoing the investigation. OpenAPI exclusion is discoverability control,
not network isolation; see Section 9.

### FR-016 — Angular operational experience

The project scientific-return panel uses standalone, signal-based Angular
components and resources to:

- disable manual start and explain when readiness is unavailable or invalid;
- start the discovery objective with a fresh browser-generated idempotency key;
- list and manually refresh investigation and candidate state;
- label object-scoped investigations with inventory number and object name;
- show partial object coverage, degraded completion, recovery count, recovery
  ceiling, and last recovery reason;
- render trajectory payloads in iterations and distinguish information sent to
  the model from information produced by it;
- allow authorized review groups to start and cancel work.

The interface does not poll automatically. A user must refresh to observe work
completed after the initial request.

### FR-017 — Operational metrics

The staff metrics response includes full-agentic run and candidate counts plus
LLM timeouts, rejected source waits, recoveries, exhausted recoveries, live
investigations, expired leases, and the oldest live age. These are global
operational values in the current repository.

---

## 7. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | Aggregate operations do not move a terminal investigation back to a live state |
| INV-002 | PostgreSQL permits at most one live row for an exact target tuple |
| INV-003 | One idempotency key is bound to one target |
| INV-004 | A model call is durably charged before it begins |
| INV-005 | No model call starts after its budget is exhausted |
| INV-006 | A worker without the current live lease cannot reserve model budget or persist normal progress |
| INV-007 | A yielded execution slice does not count as a worker recovery |
| INV-008 | Under a recurring queue/reaper process, stale live work reaches a terminal state |
| INV-009 | Readiness responses contain source diagnostics but no credentials |
| INV-010 | Autonomous output remains a candidate until a separate human decision |
| INV-011 | Grounded passages and inventory forms occur in material delivered by the source |

## 8. Data protection and trust boundaries

- Trajectory payloads and tool invocation/result documents are encrypted at
  rest; identifiers, lifecycle fields, budgets, usage, failure reasons, and
  degradation reasons remain queryable plaintext metadata.
- LLM prompts are resolved through the published prompt interface, and plan and
  assessment events retain the prompt identity that actually ran.
- External publication text is untrusted input. It is read by a tool-free reader
  and cannot define actions, object identifiers, evidence policy, or candidate
  decisions.
- Logs should identify investigations and failure types without reproducing
  project content, publication text, credentials, or prompt payloads.
- Scientific Return accesses project snapshots and publication writing only
  through `use_of_collections.public`, and prompt templates through
  `ai.prompts.public`.

## 9. Declared implementation gaps

1. **GAP-001** — **Critical — tenant authorization is missing from operational reads and
   cancellation.** Individual read, list, trajectory, and cancel operations
   require staff or an allowed group but do not compare the caller's institution
   with `FullAgenticInvestigation.institution_id` or the watch. A staff member
   who knows another tenant's identifiers can read its state/trajectory or, in
   an allowed group, cancel its work.
2. **GAP-002** — **Critical — idempotency lookup precedes watch and tenant validation.** A
   mutation-group caller presenting the exact key and target of another tenant
   receives that existing investigation before institutional ownership is
   checked. The globally unique key also makes collisions cross-tenant.
3. **GAP-003** — **High — manual and scheduled target models differ.** The public request has
   no `objectId`, so the Angular button starts a legacy whole-project
   investigation while scheduled sweeps create one investigation per object.
   Null and object-scoped targets may run concurrently and spend overlapping
   budgets.
4. **GAP-004** — **High — the Angular coverage indicator ignores project-scoped rows.** It
   counts only distinct non-null `objectId` values, so a manual investigation
   that searched the full snapshot can still be displayed as zero objects
   reached.
5. **GAP-005** — **Medium — advertised request fields exceed implemented capability.** The
   API schema exposes `candidateId` and `ENRICH_CANDIDATE`, but the start use
   case rejects both. Either remove these inputs until implemented or document
   them as reserved compatibility fields in generated API guidance.
6. **GAP-006** — **Medium — the worker route is hidden, not intrinsically private.** The
   application verifies only `X-Worker-Token`; OIDC/IAM and network restriction
   depend on deployment configuration outside FastAPI. OpenAPI exclusion alone
   is not an access-control boundary.
7. **GAP-007** — **Medium — route-level contract tests are incomplete.** Most lifecycle,
   lease, idempotency, and isolation assertions exercise use cases or in-memory
   repositories. There are no focused API tests for start-group authorization,
   worker-token rejection, read/cancel tenant isolation, unknown list/trajectory
   semantics, or terminal cancellation.
8. **GAP-008** — **Medium — circuit and operational metrics are global.** One institution's
   reviewer outcomes can open the circuit for every institution, and the staff
   metrics response is not tenant-scoped.
9. **GAP-009** — **Low — completion is manually refreshed.** The Angular panel has no polling,
   server-sent event, or push update, so status and candidate results remain
   stale until the user presses Refresh or revisits the page.
10. **GAP-010** — **High — watch status does not gate autonomous work.** Start
    checks watch existence and conditional institutional equality, but not
    `ACTIVE` status. Execution loads the snapshot without rechecking watch
    state. A direct start may run against a paused/closed watch, and closing a
    watch does not stop previously queued work. Define whether watch suspension
    stops only scheduled discovery or all autonomous work, enforce the chosen
    rule at admission/resume, and test pause/close races. Current acceptance
    evidence does not establish this policy.

## 10. Acceptance criteria

### AC-001 — Impossible source configuration is refused before enqueue

Given no operational requested source capable of inspectable evidence, starting
an investigation returns `503` and creates no work.

→ `test/scientific_return/test_full_agentic_flow.py::test_invalid_operational_source_configuration_fails_before_enqueue`

→ `test/scientific_return/test_provenance_contract.py::test_an_impossible_source_configuration_is_refused_before_enqueue`

### AC-002 — Idempotency is bound to the target

Given a key already used for one target, reusing it for another target is
rejected.

→ `test/scientific_return/test_full_agentic_flow.py::test_idempotency_key_cannot_be_reused_for_another_target`

### AC-003 — Circuit breaker uses only human full-agentic outcomes

→ `test/scientific_return/test_full_agentic_flow.py::test_circuit_breaker_uses_only_full_agentic_human_outcomes`

### AC-004 — Lease ownership and bounded recovery

Given a live lease, a second worker cannot take it; repeated expired-lease
recoveries and over-age live work eventually terminate.

→ `test/scientific_return/test_full_agentic_flow.py::test_second_worker_cannot_take_a_live_lease`

→ `test/scientific_return/test_full_agentic_flow.py::test_a_repeatedly_recovered_investigation_is_terminated`

→ `test/scientific_return/test_full_agentic_flow.py::test_the_reaper_closes_only_investigations_past_their_age`

### AC-005 — Model budget is charged before each call

→ `test/scientific_return/test_full_agentic_flow.py::test_every_model_call_is_charged_and_committed_before_it_starts`

→ `test/scientific_return/test_full_agentic_flow.py::test_a_hard_death_leaves_the_reserved_call_spent`

→ `test/scientific_return/test_full_agentic_flow.py::test_an_exhausted_budget_never_reaches_the_model`

### AC-006 — A healthy slice yields without spending recovery allowance

→ `test/scientific_return/test_full_agentic_flow.py::test_the_worker_hands_the_slice_back_instead_of_being_killed`

→ `test/scientific_return/test_full_agentic_flow.py::test_a_yielded_slice_is_not_charged_as_a_recovery`

→ `test/scientific_return/test_full_agentic_flow.py::test_a_handed_back_slice_is_announced_to_a_push_queue`

### AC-007 — Terminal work closes its search run

→ `test/scientific_return/test_full_agentic_flow.py::test_no_failure_mode_keeps_an_investigation_alive_forever`

→ `test/scientific_return/test_full_agentic_flow.py::test_a_terminated_investigation_never_leaves_its_run_open`

### AC-008 — Readiness discloses no credential

→ `test/scientific_return/test_provenance_contract.py::test_readiness_reports_operational_sources_without_credentials`

→ `test/scientific_return/test_provenance_contract.py::test_readiness_reports_a_source_that_is_requested_but_not_operational`

### AC-009 — Scheduled fan-out is object-scoped and truncation is visible

→ `test/scientific_return/test_sweep_fan_out.py::test_one_investigation_per_object_with_a_key_of_its_own`

→ `test/scientific_return/test_sweep_fan_out.py::test_objects_beyond_the_ceiling_are_recorded_not_dropped`

→ `test/scientific_return/test_sweep_fan_out.py::test_one_object_already_live_does_not_stop_the_others`

### AC-010 — One investigation sees only its selected object

→ `test/scientific_return/test_full_agentic_flow.py::test_an_investigation_sees_only_its_own_object`

→ `test/scientific_return/test_full_agentic_flow.py::test_an_object_outside_the_snapshot_is_refused`

→ `test/scientific_return/test_full_agentic_flow.py::test_two_objects_of_one_project_are_two_targets`

### AC-011 — Planner failure retains deterministic discovery and is visible

→ `test/scientific_return/test_full_agentic_flow.py::test_discovery_floor_never_spends_the_whole_query_budget`

→ `test/scientific_return/test_full_agentic_flow.py::test_planner_failure_degrades_after_discovery_floor`

→ frontend: `vitarerum-ui/src/app/features/collections/projects/components/scientific-return-panel/scientific-return-panel.component.spec.ts`

### AC-012 — Reader claims are grounded in delivered fields

→ `test/scientific_return/test_full_agentic_grounding.py::test_grounding_rejects_hallucinated_claims_without_changing_relevance`

→ `test/scientific_return/test_full_agentic_grounding.py::test_a_source_without_inspectable_body_reports_unavailable`

→ `test/scientific_return/test_agent_security.py::test_injected_text_cannot_move_a_candidate`

→ `test/scientific_return/test_agent_security.py::test_no_candidate_is_ever_decided_by_the_cycle`

### AC-013 — Trajectory and provenance survive persistence

→ `test/scientific_return/test_full_agentic_flow.py::test_plan_events_record_the_prompt_version_that_ran`

→ `test/scientific_return/test_full_agentic_repository_postgres.py::test_tool_result_round_trips_encrypted_replay_text_and_unique_key`

→ `test/scientific_return/test_provenance_contract.py::test_the_queue_exposes_the_provenance_of_every_candidate`

→ `test/scientific_return/test_provenance_contract.py::test_the_decision_snapshot_keeps_what_the_curator_was_shown`

The PostgreSQL test establishes encrypted tool replay, while the provenance
tests establish response fields using repository doubles. They do not prove a
complete autonomous-trajectory database round trip or what a human viewed.
`test/scientific_return/test_investigation_repository.py::test_the_whole_trajectory_survives_the_database`
belongs to the separate assisted flow and is not autonomous persistence evidence.

### AC-014 — Publication components do not fill the candidate queue

→ `test/scientific_return/test_full_agentic_flow.py::test_the_parts_of_one_publication_do_not_fill_the_queue`

### AC-015 — Internal worker route is absent from OpenAPI

→ `test/scientific_return/test_api_contract.py::test_openapi_excludes_bench_and_keeps_operational_scientific_return`

### AC-016 — Angular exposes readiness and autonomous audit state

The panel queues explicitly, blocks invalid readiness, warns on degradation,
shows recovery/object coverage, and renders the model boundary in the trajectory.

→ `vitarerum-ui/src/app/features/collections/projects/components/scientific-return-panel/scientific-return-panel.component.spec.ts`

→ `vitarerum-ui/src/app/features/collections/projects/services/scientific-return-api.service.spec.ts`

## 11. Non-functional requirements

- **Bounded cost**: server budgets and per-source result ceilings override any
  model proposal.
- **Transactional isolation**: no database transaction remains open while an
  LLM or bibliographic provider responds.
- **Recoverability**: progress required for replay is committed step by step.
- **Auditability**: trajectory events identify the executed prompt, search,
  source, grounding result, and terminal reason.
- **Security**: public operational routes require JWT plus acting permission;
  the worker has a separate secret and must also be protected at deployment.
- **Architecture**: domain and application remain free of FastAPI and
  SQLAlchemy; cross-context access uses published languages.
- **Human authority**: autonomous discovery never becomes an institutional
  publication decision without the review workflow.

## 12. Traceability

| Spec element | Location |
| --- | --- |
| Aggregate, budget, trajectory, and lifecycle | `vitarerum-api/app/scientific_return/domain/full_agentic_models.py`, `domain/enums.py` |
| Admission, execution, lease, grounding orchestration, and reaper | `vitarerum-api/app/scientific_return/application/full_agentic.py` |
| Deterministic floor and source capability policy | `vitarerum-api/app/scientific_return/application/full_agentic_strategy.py` |
| Grounding validator | `vitarerum-api/app/scientific_return/application/full_agentic_grounding.py` |
| Ports | `vitarerum-api/app/scientific_return/application/full_agentic_ports.py` |
| SQL persistence and encrypted replay documents | `vitarerum-api/app/scientific_return/infrastructure/full_agentic_repository.py`, `infrastructure/models.py` |
| Database and Cloud Tasks dispatch | `vitarerum-api/app/scientific_return/infrastructure/full_agentic_dispatcher.py` |
| Scheduled fan-out, queue drain, and reaper invocation | `vitarerum-api/app/scientific_return/presentation/commands.py` |
| HTTP routes and response mapping | `vitarerum-api/app/scientific_return/presentation/routes.py`, `presentation/schemas.py` |
| Composition and source readiness | `vitarerum-api/app/scientific_return/presentation/dependencies.py` |
| Configuration | `vitarerum-api/app/config.py`, `vitarerum-api/.env.example`, `deploy/provision.sh` |
| Initial and hardening migrations | `vitarerum-api/alembic/versions/00000067_*.py`, `00000068_*.py`, `00000070_*.py`, `00000073_*.py`, `00000079_*.py`, `00000081_*.py`, `00000084_*.py` |
| Angular model and API adapter | `vitarerum-ui/src/app/features/collections/projects/models/scientific-return.model.ts`, `services/scientific-return-api.service.ts` |
| Angular operational panel | `vitarerum-ui/src/app/features/collections/projects/components/scientific-return-panel/` |

## 13. Open questions

1. Should every investigation route resolve the watch and return an opaque
   `404` when the caller's institution does not own it?
2. Should idempotency uniqueness be scoped by institution and checked only
   after tenant authorization?
3. Should manual start accept one explicit `objectId`, fan out all eligible
   objects server-side, or be removed in favor of the scheduled model?
4. Should the circuit breaker and operational metrics be institution-scoped?
5. Should terminal cancellation remain a successful no-op or return a typed
   conflict to reveal that no cancellation occurred?
6. Does the worker deployment require both Cloud Run IAM/OIDC and the worker
   token in every environment, and is that policy tested outside application
   code?
