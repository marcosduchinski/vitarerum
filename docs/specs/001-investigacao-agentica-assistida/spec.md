# SPEC-001 — Assisted agentic investigation for scientific return

| Field | Value |
| --- | --- |
| Identifier | SPEC-001 |
| Status | Implemented (legacy assisted flow, with declared tenant-isolation, concurrency, mode-boundary, provenance, and UI gaps) |
| Bounded context | `app.scientific_return` |
| Execution mode | Synchronous, with manual API entry points and a scheduled enrichment caller |
| Decision posture | Advisory; human-in-the-loop |
| Derived from | Domain model, use cases, policies, persistence, API, scheduler, Angular interface, migrations, configuration, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md), [SPEC-003](../003-pipeline-deterministico-bibliografico/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-005](../005-analise-agentica-de-candidato/spec.md), [SPEC-016](../016-prompts-versionados/spec.md), [SPEC-022](../022-cifragem-e-armazenamento/spec.md), and [SPEC-024](../024-investigacao-agentica-autonoma/spec.md) |
| Related documents | [API contracts](../../api_contracts/README.md) |

---

## 1. Problem

The deterministic scientific-return pipeline searches bibliographic sources
with fixed combinations of author, inventory number, and object name. It can
miss a publication when an inventory number appears in a form that the original
query did not use, such as `MUHNAC/MB11-001283` versus `MB11-001283`. It can
also leave a pending candidate with insufficient inventory evidence, forcing a
curator to repeat searches manually.

A model can help choose the next bounded action, but publication text and model
output are untrusted. Neither may define queries, select arbitrary sources,
change evidence rules, or decide whether a publication becomes an institutional
scientific-return record.

## 2. Goal

Run one synchronous, bounded investigation over an active monitoring watch or a
pending candidate. The cycle observes recorded facts, asks a model for one typed
action, subjects that action to deterministic policy, executes only a
system-derived search, recalculates evidence through the deterministic pipeline,
and closes with an auditable typed reason.

The cycle may create a pending candidate or append verified evidence. It never
confirms, corrects, dismisses, or writes a publication to the collection-use
publication log.

This specification describes the legacy assisted flow. The durable autonomous
flow is specified separately in
[SPEC-024](../024-investigacao-agentica-autonoma/spec.md).

## 3. Actors

| Actor | Responsibility |
| --- | --- |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION` | Start manual investigations through the API and decide resulting candidates |
| Other staff, including `SYS_ADMIN` | Read assisted-investigation endpoints; cannot start them |
| Scheduler | Starts bounded candidate-enrichment cycles after an autonomous investigation completes |
| Planning model | Proposes one typed action and, when required, one object already present in the observation |
| Reflection model | Interprets measured progress; cannot choose the terminal outcome |
| Action policy | Authorizes or rejects the proposal and derives every executable argument |
| Stop policy | Selects the typed terminal reason and whether human review is appropriate |
| Bibliographic source | Executes an exact-phrase search through a registered adapter |

The implementation does not yet enforce institutional ownership on assisted
investigation entry points or reads. That critical limitation is declared in
GAP-001.

## 4. Ubiquitous language and domain model

- **Assisted investigation**: aggregate root for one bounded cycle over a watch
  and, optionally, one candidate.
- **Discovery**: `DISCOVER_CANDIDATE`; searches from a watch without an initial
  candidate and may create pending candidates.
- **Enrichment**: `ENRICH_CANDIDATE`; searches for additional evidence for one
  existing pending candidate and does not replace its bibliographic metadata.
- **Iteration**: entity representing one observe, plan, validate, execute, and
  reflect pass.
- **Observation**: immutable factual input assembled by the application for the
  planner.
- **Proposed action**: typed model output containing an action kind and, for a
  search, an optional consulted-object identifier. It cannot contain a query,
  source, URL, or inventory string.
- **Authorized execution**: value object created by deterministic policy with
  the exact queries, sources, result limit, and object identifier the tool may
  use.
- **Execution budget**: value object tracking maximum and consumed iterations,
  actions, queries, results per query, and newly created candidates.
- **Evidence delta**: deterministic difference between evidence before and
  after execution, including stable hashes of both states.
- **Trajectory**: persisted aggregate, iterations, policy decisions, tool
  execution summaries, evidence deltas, reflections, and telemetry.
- **Stop reason**: typed explanation for a terminal outcome.
- **Abandoned investigation**: non-terminal synchronous cycle whose heartbeat
  has remained unchanged past the configured operational threshold.

### 4.1 Aggregate lifecycle

```text
CREATED -> OBSERVING -> PLANNING -> VALIDATING -> EXECUTING -> REFLECTING
                                              \-> REFLECTING (rejected action)

REFLECTING -> AWAITING_HUMAN_REVIEW
           -> STOPPED
           -> OBSERVING (supported by the aggregate, unused by current defaults)

any non-terminal state -> FAILED
```

`AWAITING_HUMAN_REVIEW`, `STOPPED`, and `FAILED` are terminal. A running
iteration is marked `COMPLETED` on a normal close and `FAILED` on aggregate
failure. Terminal aggregates cannot reopen.

## 5. Scope

### In scope

- Watch-scoped candidate discovery.
- Pending-candidate enrichment.
- One implemented executable action: `SEARCH_INVENTORY_VARIANTS`.
- Terminal actions `PRESENT_FOR_REVIEW` and
  `STOP_INSUFFICIENT_EVIDENCE`, which contact no source.
- Deterministic action authorization, source routing, query derivation,
  evidence calculation, and stopping.
- Synchronous persistence of the complete or partial trajectory.
- Command and tool-execution idempotency.
- Target locking, optimistic persistence, live-target uniqueness, and stale
  cycle closure.
- Read-only trajectory endpoints and the candidate-history Angular dialog.
- Limited scheduled enrichment after autonomous discovery.

### Out of scope

- The durable asynchronous execution, leases, recovery, independent LLM budget,
  and multi-source planning of SPEC-024.
- Automated candidate decisions or publication-log writes.
- Automated correction of candidate title, authors, DOI, URL, or status.
- Executing `SEARCH_AUTHOR_VARIANTS`, `SEARCH_TAXON_VARIANTS`,
  `SEARCH_FULL_TEXT`, or `DEPRIORITIZE`.
- More than one iteration under the default configuration.

## 6. Functional requirements

### RF-001 — Start discovery for a watch

`POST /api/v1/scientific-return/watches/{watchId}/investigations` requires JWT
authentication, `X-Permission-Id`, and membership in `CURATORIAL`,
`COLLECTIONS_MANAGEMENT`, or `DIRECTION`. It starts
`DISCOVER_CANDIDATE` without a candidate and returns `201 Created` with the
already-terminal trajectory.

The watch must exist, be `ACTIVE`, have a project snapshot, and have at least
one deterministic run. The newest run returned by the repository becomes
`initialRunId`. Invalid preconditions produce `422`; disabled mode produces
`503 SCIENTIFIC_RETURN_AGENT_DISABLED`.

This capability exists in the API but has no start control in the Angular
application.

### RF-002 — Start enrichment for a candidate

`POST /api/v1/scientific-return/candidates/{candidateId}/investigations`
requires the same mutation groups and returns `201 Created`. The route loads
the candidate, derives its watch, and starts `ENRICH_CANDIDATE`.

The candidate must exist and remain `PENDING` when initially loaded. Unknown
candidates return `404 SCIENTIFIC_RETURN_CANDIDATE_NOT_FOUND`; a decided
candidate produces `422`. The use case appends verified evidence only to the
target candidate and does not change its metadata or status.

The Angular service implements this request, but the corresponding “Investigate
missing evidence” button is commented out. Manual enrichment is therefore not
available through the current UI.

### RF-003 — Assemble a constrained observation

The application gives the planner:

- objective, project reference, and researcher;
- consulted objects with identifier, inventory number, and object name;
- distinct queries already attempted for the watch;
- configured actions plus the two always-available terminal actions;
- the complete execution budget;
- for enrichment only, the candidate identifier, title, DOI, and verified
  evidence types.

Candidate title is untrusted external data. The prompt explicitly treats the
whole payload as data rather than instructions. Credentials, source endpoints,
API keys, and arbitrary project records are not part of the observation.

### RF-004 — Obtain one typed plan

The reasoner loads the currently published assisted-plan prompt and asks for
exactly one JSON plan containing:

- an iteration objective;
- one action type;
- an object identifier only when that action requires one;
- a reasoning summary;
- expected evidence types.

Required text is trimmed, non-blank, and limited to 2,000 characters. Lists
contain at most 20 items. A malformed or out-of-contract plan closes the
investigation as `FAILED` with `INVALID_PLAN`; a missing prompt, timeout, or
other planner failure closes it with `REASONER_UNAVAILABLE`.

### RF-005 — Authorize actions deterministically

The model cannot execute a tool. `AgentActionPolicy` evaluates the typed action
and, when authorized, derives the complete `AuthorizedExecution`.

| Condition | Rejection reason |
| --- | --- |
| Investigation is not `VALIDATING` | `INVESTIGATION_NOT_ACTIONABLE` |
| Loaded candidate status is already decided | `CANDIDATE_ALREADY_DECIDED` |
| Action is outside the configured allowlist | `ACTION_NOT_ALLOWED` |
| Allowlisted action has no implemented executor | `ACTION_NOT_ALLOWED` |
| Mode cannot execute tools | `MODE_FORBIDS_EXECUTION` |
| Action or query budget is exhausted | `BUDGET_EXHAUSTED` |
| Candidate ceiling is reached | `CANDIDATE_LIMIT_REACHED` |
| Search has no object identifier | `OBJECT_ID_REQUIRED` |
| Object is absent from the immutable snapshot observation | `OBJECT_NOT_IN_SNAPSHOT` |
| Object has no inventory number | `INVENTORY_MISSING` |
| No configured source supports exact-phrase matching | `SOURCE_NOT_ALLOWED` |
| Every derived inventory variant has already been attempted | `NO_NEW_QUERY_VARIANT` |

`PRESENT_FOR_REVIEW` and `STOP_INSUFFICIENT_EVIDENCE` are always available,
need no allowlist entry, and contact no source. They are still refused when the
loaded candidate status is already decided.

The status check uses the candidate object loaded before the planner call; it
does not reload a concurrently decided candidate. See GAP-002.

### RF-006 — Derive inventory queries and source routing

`SEARCH_INVENTORY_VARIANTS` derives variants from the registered inventory
number in the watch snapshot. Supported variant categories are `EXACT`,
`WITHOUT_INSTITUTION`, `NUMBER_PADDING`, `INSTITUTION_ALIAS`, and `SEPARATOR`.
Queries already recorded for the watch are removed, and the remaining query
budget caps the result.

Every variant is sent as a quoted exact phrase. Source priority is Europe PMC,
Crossref, then OpenAlex, but only sources in the measured exact-match capability
set may be routed. That set currently contains only `EUROPE_PMC`; Crossref is
excluded because it returns relevance-ranked noise for nonexistent specimen
codes, and OpenAlex has not been admitted to this capability.

### RF-007 — Reserve budget before execution

Opening an iteration reserves one iteration. Authorizing a source-contacting
action reserves one action and the number of derived query variants before the
tool runs. A crash may therefore leave reserved work unused, but cannot execute
unbudgeted work.

The default budget is one iteration, one action, four query variants, ten
results per source query, and five newly created candidates. With the current
single exact-match source, the query count also equals the number of external
search calls.

### RF-008 — Execute and persist findings

Before contacting a source, the application persists a tool-execution record
whose idempotency key is derived from investigation, iteration, action, object,
queries, and sources. A previously successful execution is replayed without a
new source call.

The tool searches, normalizes records, deduplicates them, and applies the same
deterministic evidence rules as the scheduled pipeline. Discovery may create a
new `PENDING` candidate or append evidence to an existing candidate with the
same deduplication key. Enrichment discards records that do not match the target
candidate by deduplication key or normalized DOI.

Created evidence records the investigation, iteration, source record, and
content hash. Candidate creation stops at the investigation ceiling. Every
state change is committed before the next model or source call, so the request
does not keep a database transaction open while waiting on an external system.

### RF-009 — Recalculate evidence and reflect

For enrichment, the application records evidence before and after execution,
calculates an order-independent hash of each state, and stores the typed delta
of added, preserved, and removed evidence types. Discovery begins with empty
candidate evidence and records created candidates in the tool summary.

The reflection model receives measured execution facts and the authoritative
delta. It returns progress, a delta summary, remaining gaps, a stop
recommendation, and a reasoning summary. Its recommendation is advisory. If
reflection fails, a deterministic reflection derived from the delta closes the
cycle.

### RF-010 — Stop with a typed outcome

The deterministic stop policy chooses one of:

`EVIDENCE_SUFFICIENT`, `NO_RESULTS`, `NO_EVIDENCE_ADDED`, `NO_PROGRESS`,
`ACTION_REJECTED`, `QUERY_REPEATED`, `BUDGET_EXHAUSTED`,
`ITERATION_LIMIT_REACHED`, `CANDIDATE_LIMIT_REACHED`,
`REASONER_UNAVAILABLE`, `INVALID_PLAN`, `TOOL_UNAVAILABLE`, `TOOL_FAILED`,
`CANDIDATE_ALREADY_DECIDED`, `PRESENTED_FOR_REVIEW`,
`INSUFFICIENT_EVIDENCE`, or `ABANDONED`.

An outcome is `AWAITING_HUMAN_REVIEW` whenever the stop-policy input says a
reviewable candidate exists and was not decided. This state does not by itself
mean that new evidence was added; the `stopReason` explains the result.
Otherwise the normal terminal state is `STOPPED`. Unrecoverable application
failure produces `FAILED`.

### RF-011 — Record model and execution telemetry

Each iteration stores model name, the planning prompt's version label, planning
and reflection latency, response hashes, and their summed model latency. A
trajectory created before telemetry existed, or one that never reached the
planner, may return `telemetry: null`.

The reflection prompt has an independently published version, but that identity
is currently discarded; see GAP-005.

### RF-012 — Apply command idempotency and target exclusivity

`Idempotency-Key` is optional. When present, a unique partial PostgreSQL index
allows only one investigation row with that key. A replay returns the stored
investigation before checking for an existing live target or deterministic-run
precondition and does not contact a source again.

The live-target key is watch, objective, and nullable candidate. The application
checks for an existing non-terminal aggregate, a partial unique database index
enforces the same rule, and a session-scoped PostgreSQL advisory lock spans the
whole synchronous cycle. Discovery and enrichment therefore use different
targets. Optimistic version checks prevent a stale writer from resurrecting a
row closed by the reaper.

Command replay does not verify that the key belongs to the requested target or
caller, and the real advisory-lock exception is not mapped to the documented
`409`; see GAP-003 and GAP-006.

### RF-013 — Close abandoned synchronous cycles

Before a scheduled sweep, the reaper finds non-terminal assisted investigations
whose heartbeat, or start time when no heartbeat exists, is older than 30
minutes. It changes them to `FAILED` with `ABANDONED`. A concurrent save wins
through optimistic version detection, in which case the reaper rolls back and
leaves the active cycle alone.

This is terminal cleanup, not resumption: an abandoned assisted investigation
must be started again as a new cycle.

### RF-014 — Read trajectories without executing work

The following endpoints require a staff identity and are strictly read-only:

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/scientific-return/watches/{watchId}/investigations` | Returns every matching investigation, newest first |
| `GET /api/v1/scientific-return/candidates/{candidateId}/investigations` | Returns every matching candidate investigation, newest first |
| `GET /api/v1/scientific-return/investigations/{investigationId}` | Returns one investigation or `404 SCIENTIFIC_RETURN_INVESTIGATION_NOT_FOUND` |

List endpoints return an empty array for an unknown identifier and have no
pagination or limit. Reads do not continue, retry, or restart a cycle. They are
not institution-scoped; see GAP-001.

The response includes aggregate identity, target, objective, state, mode, stop
reason, partial budget information, timestamps, creator, optional predecessor,
and all iteration details. It omits `maxActions`, `usedActions`, and
`maxResultsPerQuery` even though those values affect execution.

### RF-015 — Expose assisted history in Angular

The scientific-return panel can load candidate investigation history and shows
each trajectory in a modal with outcome, mode, budget used, start time, policy,
tool, evidence, reflection, and telemetry details. The history control is
rendered only for the three review groups, although the backend read endpoint
accepts every staff group.

The UI does not expose watch discovery. Its candidate-enrichment method and API
client exist, but the start button is commented out. There is no UI-generated
idempotency key for this dormant request. Assisted history remains visible for
candidates that were enriched by the scheduler or another API client.

### RF-016 — Run limited scheduled enrichment

After a full-agentic investigation reaches `COMPLETED`, the queue worker selects
up to five oldest `PENDING` candidates from that watch that have no
inventory-bearing evidence. It invokes the assisted enrichment entry point with
the scheduler identity and key `scheduled-proof:{candidateId}`.

The scheduled entry point skips the human-group check but retains the same
preconditions, model, policy, tool, persistence, and budget. It does not require
`SCHEDULED` mode. In `SUPERVISED` mode it may therefore execute unattended, and
its permanent key prevents a later scheduled retry for the same candidate. See
GAP-004.

### RF-017 — Control capability through operating mode

| Mode | Current behavior |
| --- | --- |
| `DISABLED` | Manual and scheduled calls fail before loading the target |
| `SHADOW` | Planner and reflection may run; source-contacting actions are rejected |
| `POLICY_ONLY` | Same effective tool boundary as `SHADOW` in this flow |
| `SUPERVISED` | Source-contacting actions may run for both manual and scheduled callers |
| `SCHEDULED` | Source-contacting actions may also run for both caller types |

The default is `DISABLED`. The code distinguishes whether tools may execute,
but does not enforce the caller/mode distinction implied by the mode names.

## 7. Invariants and actual enforcement

| Invariant | Enforcement |
| --- | --- |
| The cycle never writes to the project publication log | No such port is available to the use case; security test |
| The cycle never decides a candidate | Tool and use case only create pending candidates or append evidence |
| Enrichment does not rewrite candidate metadata or status | Application persistence path and tests |
| Executed queries derive from an observed snapshot object | Proposed-action contract plus deterministic action policy |
| Publication text cannot redefine evidence rules | Deterministic evidence builder and injection tests |
| A source-contacting action must be authorized and budgeted first | Aggregate transition and policy-generated execution |
| Every normally terminal investigation has a typed stop reason | Aggregate and stop policy |
| A terminal investigation cannot reopen | Aggregate transition guard |
| One live investigation exists per target | Application check, database partial unique index, and advisory lock |
| A successful tool execution is not repeated | Unique deterministic tool-execution key and replay |
| A retry is linked to its predecessor | Supported by the model, but not populated by the run use case |
| A candidate decided during an external call stops enrichment | Policy supports it, but the use case does not reload candidate status |
| Assisted investigations remain inside one institution | Not represented or enforced |

## 8. Server configuration

| Setting | Default | Effect |
| --- | --- | --- |
| `SCIENTIFIC_RETURN_AGENT_MODE` | `DISABLED` | Operating mode |
| `SCIENTIFIC_RETURN_AGENT_MAX_ITERATIONS` | `1` | Iteration ceiling |
| `SCIENTIFIC_RETURN_AGENT_MAX_ACTIONS` | `1` | Executable-action ceiling |
| `SCIENTIFIC_RETURN_AGENT_MAX_QUERIES` | `4` | Derived query-variant ceiling |
| `SCIENTIFIC_RETURN_AGENT_MAX_RESULTS` | `10` | Result limit per source query |
| `SCIENTIFIC_RETURN_AGENT_MAX_NEW_CANDIDATES` | `5` | Candidate-creation ceiling |
| `SCIENTIFIC_RETURN_AGENT_ALLOWED_ACTIONS` | `SEARCH_INVENTORY_VARIANTS` | Executable-action allowlist |
| `SCIENTIFIC_RETURN_AGENT_ALLOWED_SOURCES` | `EUROPE_PMC` | Source allowlist, further narrowed by capability policy |

The client and model cannot increase these values. Model and source adapters
also use the shared scientific-return timeout and retry settings; those are not
part of the per-investigation budget returned by this API.

## 9. Acceptance criteria and verification

| Criterion | Evidence |
| --- | --- |
| Discovery creates a pending candidate and awaits a human | `test_run_investigation.py::test_a_discovery_creates_a_candidate_and_awaits_a_human` |
| Created candidate and evidence carry investigation provenance | `test_run_investigation.py::test_the_created_candidate_carries_its_provenance` |
| Enrichment adds evidence without rewriting the candidate | `test_run_investigation.py::test_enrichment_adds_evidence_without_touching_the_candidate` |
| Candidate decisions and publication-log writes remain outside the cycle | `test_run_investigation.py::test_the_candidate_still_requires_a_human_decision`, `test_agent_security.py::test_the_cycle_has_no_route_to_the_publication_log` |
| Invented objects and actions never reach a source | `test_agent_security.py::test_the_model_cannot_investigate_an_object_it_invented`, `::test_an_invented_action_never_reaches_a_source`, `::test_an_action_outside_the_allowlist_never_reaches_a_source` |
| External text cannot move a candidate or change evidence rules | `test_agent_security.py::test_injected_text_cannot_move_a_candidate`, `::test_injected_text_does_not_change_the_evidence_rules`, `::test_an_injection_claiming_an_inventory_number_proves_nothing` |
| Query and candidate ceilings are respected | `test_agent_security.py::test_one_investigation_cannot_exceed_its_query_budget`, `test_run_investigation.py::test_the_candidate_ceiling_is_respected` |
| Budget is reserved before tool execution | `test_investigation_aggregate.py::test_the_budget_is_charged_before_the_tool_runs`, `::test_an_authorized_search_must_reserve_queries` |
| Command replay does not contact a source or create a second candidate | `test_run_investigation.py::test_the_same_client_key_never_contacts_a_source_twice`, `::test_a_repeated_key_creates_no_second_candidate`, `::test_a_command_without_a_key_is_not_deduplicated` |
| Only exact-match-capable sources are routed | `test_run_investigation.py::test_a_source_that_cannot_match_exactly_is_refused`, `test_agent_policies.py::test_only_sources_that_honour_an_exact_phrase_are_routed_to` |
| Planner and source failures close without deciding the queue | `test_run_investigation.py::test_an_unavailable_reasoner_leaves_the_queue_untouched`, `::test_an_unavailable_source_is_audited_without_blocking_review`, `::test_an_authorised_source_without_an_adapter_stops_as_unavailable` |
| Reflection failure uses deterministic fallback | `test_run_investigation.py::test_an_unavailable_reflection_falls_back_to_the_delta` |
| Disabled mode and unauthorized mutation are refused | `test_run_investigation.py::test_a_disabled_mode_refuses_to_start`, `::test_a_caller_outside_the_review_groups_is_refused` |
| Trajectory and telemetry persist step by step | `test_run_investigation.py::test_the_trajectory_is_persisted_step_by_step`, `::test_the_full_trajectory_is_readable_afterwards`, `::test_the_iteration_records_which_model_and_prompt_produced_it` |
| Optimistic persistence rejects a stale writer | `test_investigation_repository.py::test_a_save_is_refused_after_another_writer_moved_the_row` |
| Lock is released on success and failure | `test_run_investigation.py::test_the_lock_is_taken_for_the_target_and_always_released`, `::test_the_lock_is_released_even_when_the_cycle_fails` |
| Stale cycles close as abandoned while live cycles survive | `test_run_investigation.py::test_an_abandoned_cycle_is_closed_with_a_typed_reason`, `::test_a_live_cycle_is_never_closed_by_the_sweep` |
| Angular displays candidate-assisted history | `scientific-return-panel.component.spec.ts::opens each candidate history in its own dialog` |

The suite does not establish institutional isolation, target-bound replay,
candidate decision reload after an external call, real PostgreSQL lock-conflict
HTTP mapping, scheduled-mode separation, automatic retry lineage, complete
reflection-prompt provenance, or safe persisted error redaction.

## 10. Known gaps and required changes

### GAP-001 — Critical: assisted investigations have no tenant boundary

The aggregate and database row contain no `institutionId`. Manual start routes
load watches and candidates by global identifier, and all three read routes
query investigations without validating institutional ownership. A staff member
who knows an identifier can start work against another institution's data or
read its decrypted observation, queries, model reasoning, and evidence.

Required changes:

1. Add institutional ownership to the aggregate, repository, persistence, and
   response or derive it through a mandatory scoped join.
2. Scope watch, candidate, investigation, and history reads to the caller's
   active institution and use opaque `404` responses across the boundary.
3. Backfill existing rows from their watch and make ownership non-null.
4. Add API and PostgreSQL integration tests for cross-tenant start, list,
   direct read, and idempotent replay.

### GAP-002 — High: a candidate decision made during a cycle is not observed

The action policy can reject `CANDIDATE_ALREADY_DECIDED`, but the application
passes the candidate object loaded before the planner call. It never reloads the
candidate before policy evaluation, evidence append, or stop-policy evaluation.
The `candidate_decided` stop-policy input is never set by the use case.

Required changes:

1. Reload or version-check the candidate after each external call and before
   writing evidence.
2. Pass the current decision state into both policies.
3. Define whether evidence discovered concurrently with a human decision may be
   appended, and test both confirmation and dismissal races.

### GAP-003 — High: command idempotency is not bound to target or caller

The idempotency key is globally unique, but replay returns whichever
investigation already has that key without comparing watch, objective,
candidate, institution, or creator. This can disclose another trajectory and
turn an accidental key collision into an incorrect successful response.
Furthermore, the header has no length constraint even though persistence is
limited to 128 characters.

Required changes:

1. Bind replay to the complete target and institutional owner; reject key reuse
   for a different command with a stable `422` or `409` error.
2. Validate, trim, and length-limit the header at the presentation boundary.
3. Keep database uniqueness and translate concurrent uniqueness conflicts into
   replay or a stable conflict response.

### GAP-004 — High: mode names do not enforce manual versus scheduled execution

`execute_scheduled()` skips group authorization in every non-disabled mode.
Both `SUPERVISED` and `SCHEDULED` allow tools, so unattended enrichment may run
when configuration nominally promises staff-supervised execution. Conversely,
manual endpoints can execute tools in `SCHEDULED` mode.

The scheduled key `scheduled-proof:{candidateId}` is permanent. After any first
attempt—even an unavailable source or no result—future sweeps replay the old
terminal trajectory and never retry that candidate with newly available data.

Required changes:

1. Enforce a caller/mode matrix: manual execution only in the intended manual
   mode and scheduled execution only in the intended scheduled mode.
2. Decide whether scheduled proof belongs to this legacy flow or SPEC-024 and
   make the ownership explicit.
3. Include a bounded schedule epoch, source state, or attempt generation in the
   scheduled idempotency contract when retries are legitimate.
4. Add scheduler tests for every operating mode.

### GAP-005 — Medium: reflection prompt provenance is lost

Planning and reflection load independently published prompts. The iteration
stores only the planning prompt label. Reflection contributes latency and a
response hash, but its prompt identifier and version label are discarded. The
API also exposes no prompt version identifier.

Required changes:

1. Persist plan and reflection prompt identifiers and labels separately.
2. Expose both in the trajectory contract.
3. Test that independently published versions remain attributable after a
   database round trip.

### GAP-006 — Medium: real lock contention can become `500`

The application pre-check raises `InvestigationAlreadyRunning`, which the route
maps to `409`. The PostgreSQL advisory-lock adapter instead raises
`InvestigationLocked`. That exception is not translated by the use case or
route, so the race the lock is designed to handle can surface as an internal
error even though live-target integrity remains protected.

Required changes:

1. Translate adapter-level contention into the application conflict type.
2. Translate partial-unique-index conflicts consistently.
3. Add an HTTP integration test using two concurrent PostgreSQL sessions.

### GAP-007 — Medium: retry lineage is representable but never created

`previousInvestigationId` exists in the aggregate, database mapping, and API,
but `RunScientificReturnInvestigation` always constructs a new cycle with the
default `None`. Tests only prove that a manually populated value round-trips.

Required changes:

1. Define what constitutes a retry and select the predecessor deterministically.
2. Populate the link when starting that retry and add a self-referential foreign
   key where migration constraints permit.
3. Add use-case and API tests that prove a real repeated investigation links to
   the previous terminal one.

### GAP-008 — Medium: the UI exposes history but not assisted execution

The watch discovery endpoint has no UI client operation or control. Candidate
enrichment code remains present, but its button is commented out. The history
button is limited to review groups while backend reads allow all staff.

Required changes:

1. Decide whether assisted execution remains a supported user-facing feature or
   should be retired in favor of SPEC-024.
2. If retained, expose explicit readiness/mode information, confirmations,
   idempotency keys, pending states, and accessible feedback for both objectives.
3. If retired, remove dormant client code and keep history as an explicitly
   read-only legacy view.
4. Align UI read authorization with the intended backend policy.

### GAP-009 — Medium: trajectory reads and budget responses are incomplete

Watch and candidate history endpoints return every row with every iteration and
have no pagination. The budget response omits action consumption and the result
limit, so it cannot fully explain why policy accepted or rejected an action.

Required changes:

1. Add bounded pagination with stable newest-first ordering.
2. Expose `maxActions`, `usedActions`, and `maxResultsPerQuery`, or clearly mark
   the response as a summary rather than the execution budget.
3. Add API contract and UI tests for multiple pages and complete budget display.

### GAP-010 — Medium: raw operational errors are persisted and returned

Tool exceptions and source errors are converted to strings and stored in
tool/iteration error fields that are returned by the trajectory API. Logging
tests prove that selected log messages omit project text, but they do not prove
that persisted/API errors are free of query data, upstream URLs, personal data,
or credential fragments.

Required changes:

1. Map failures to typed public diagnostics and store sensitive technical detail
   only in an appropriately protected operational channel.
2. Apply explicit redaction before persistence and API serialization.
3. Add adversarial tests whose exception messages contain query text, URLs,
   tokens, and publication content.

## 11. Non-functional requirements

- **Authorization:** JWT plus `X-Permission-Id`; manual mutations require one of
  the three review groups, subject to GAP-001.
- **Safety:** model output remains advisory; deterministic policies own tool
  arguments, evidence, and stopping.
- **Cost:** server configuration bounds iterations, actions, query variants,
  results, and new candidates; adapter timeouts bound individual external calls.
- **Auditability:** each stage is committed before the next external call, and
  a partial trajectory survives a later failure.
- **Confidentiality:** observation, plan, reflection, and issued queries are
  encrypted at rest with field-specific authenticated context; metadata and
  errors require the controls described above.
- **Concurrency:** PostgreSQL live-target uniqueness, a session advisory lock,
  tool-execution uniqueness, and optimistic aggregate versions protect
  persistence, subject to the error-mapping gaps.
- **Architecture:** domain and application remain independent of FastAPI and
  SQLAlchemy; adapters implement inward-facing ports.

## 12. Traceability

| Specification element | Implementation |
| --- | --- |
| Investigation aggregate and state machine | `vitarerum-api/app/scientific_return/domain/investigation_models.py` |
| Typed contracts and execution budget | `vitarerum-api/app/scientific_return/domain/investigation_contracts.py` |
| Action and stop policies | `vitarerum-api/app/scientific_return/domain/agent_policies.py` |
| Inventory variants | `vitarerum-api/app/scientific_return/domain/inventory_variants.py` |
| Evidence delta and hashes | `vitarerum-api/app/scientific_return/domain/evidence_delta.py` |
| Synchronous orchestration and stale closure | `vitarerum-api/app/scientific_return/application/run_investigation.py` |
| Reasoner composition and prompt use | `vitarerum-api/app/scientific_return/application/investigation_reasoner.py` |
| Search tool and tool idempotency | `vitarerum-api/app/scientific_return/application/agent_tools.py` |
| Repository contracts | `vitarerum-api/app/scientific_return/application/ports.py` |
| SQLAlchemy repository and encryption mapping | `vitarerum-api/app/scientific_return/infrastructure/repositories.py` |
| Persistence records | `vitarerum-api/app/scientific_return/infrastructure/models.py` |
| Advisory lock | `vitarerum-api/app/scientific_return/infrastructure/investigation_lock.py` |
| HTTP routes and response mapping | `vitarerum-api/app/scientific_return/presentation/routes.py` |
| Dependency composition and settings mapping | `vitarerum-api/app/scientific_return/presentation/dependencies.py`, `vitarerum-api/app/config.py` |
| Scheduled enrichment | `vitarerum-api/app/scientific_return/presentation/commands.py` |
| Angular history and dormant start flow | `vitarerum-ui/src/app/features/collections/projects/components/candidate-investigations-modal/`, `investigation-timeline/`, and `scientific-return-panel/` |
| Backend behavior tests | `vitarerum-api/test/scientific_return/test_run_investigation.py`, `test_agent_policies.py`, `test_agent_security.py`, `test_investigation_aggregate.py`, and `test_investigation_repository.py` |

## 13. Open questions

1. Should this assisted flow remain a supported feature now that SPEC-024 owns
   autonomous discovery, or should only its historical trajectories remain?
2. If retained, should scheduled candidate proof move into the durable
   full-agentic lifecycle rather than execute synchronously in the queue worker?
3. What institution-scoped idempotency semantics should apply when the same
   client key is reused for a different objective or candidate?
4. Which candidate changes, if any, may accept evidence discovered concurrently
   with a human decision?
5. Should OpenAlex ever enter the exact-match capability set, and what empirical
   acceptance test would justify that change?
