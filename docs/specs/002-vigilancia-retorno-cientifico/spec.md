# SPEC-002 — Scientific-return watches and review cadence

| Field | Value |
| --- | --- |
| Identifier | SPEC-002 |
| Status | Implemented |
| Bounded context | `app/scientific_return` |
| Derived from | `domain/models.py`, `application/use_cases.py`, `infrastructure/{models,repositories}.py`, `presentation/{routes,schemas,commands}.py`, UI watch components, and scientific-return tests |
| Related specs | [SPEC-003](../003-pipeline-deterministico-bibliografico/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md) |

This specification describes the implemented behaviour and marks places where
the implementation does not yet provide a safe or coherent product guarantee.

## 1. Problem

A collection-use project may finish months or years before the researcher
publishes its results. Without an explicit responsibility and review cadence,
the museum can miss publications that document the scientific return generated
by its collections.

## 2. Goal

Allow authorised staff to create a **watch** for a completed project, preserve
the project facts used by the search, and run bibliographic discovery on a
predictable schedule. This spec describes the watch lifecycle and scheduling
boundary; search behaviour belongs to SPEC-003 and human decisions to SPEC-004.

## 3. Actors and authorisation

| Actor | Current capability |
| --- | --- |
| `CURATORIAL` | Create, start, pause, close, reschedule, and run watches |
| `COLLECTIONS_MANAGEMENT` | Same watch-management capabilities as `CURATORIAL` |
| `DIRECTION` | Same watch-management capabilities as `CURATORIAL` |
| Other authenticated staff, including `SYS_ADMIN` | Read watches, perform bulk lookup, and read metrics; no curatorial mutation |
| Scheduled job | Select and process due active watches without an interactive user |

The API identifies the caller through JWT authentication and
`X-Permission-Id`. The implementation records the caller's permission as
`createdBy` and copies its institution identifier into the watch when one is
available. Institution isolation is not yet enforced consistently; see
[GAP-001](#gap-001--institution-isolation-is-not-enforced).

## 4. Ubiquitous language

- **Watch**: the commitment to search periodically for publications associated
  with one completed project.
- **Project snapshot**: the researcher, project reference, and consulted
  objects frozen when the watch is created.
- **Review interval**: the number of days between points on the review grid.
- **Schedule anchor**: the instant from which that grid is calculated.
- **Due watch**: an `ACTIVE` watch whose `nextRunAt` is not later than now.
- **Sweep**: a scheduled pass that selects and processes due watches.
- **Run**: one deterministic search execution for a watch.

## 5. Lifecycle and cadence model

### 5.1 Watch states

```text
ACTIVE <────────────> PAUSED
   │                     │
   └──────────┬──────────┘
              ▼
            CLOSED
```

- `ACTIVE` and `PAUSED` may transition to each other.
- Either non-terminal state may transition to `CLOSED`.
- `CLOSED` is terminal. Repeating `CLOSED` is harmless, but a closed watch
  cannot be reopened, re-anchored, or assigned another interval.
- Pausing does not replace or move `nextRunAt`. Resuming an overdue watch makes
  it immediately eligible for the next scheduled sweep.

### 5.2 Fixed review grid

The schedule is a fixed grid:

```text
scheduleAnchorAt + n × reviewIntervalDays
```

After a run, `nextRunAt` becomes the first grid point strictly later than the
run completion time. A late run therefore does not shift the series, and a
long outage skips missed points instead of replaying them one by one.

Changing the anchor or interval recalculates the grid. For a watch that has
never run, `nextRunAt` is the anchor itself. For a watch that has run,
`lastRunAt` is the scheduling reference and the next strictly later grid point
is selected.

## 6. Public API

| Method and route | Purpose | Access |
| --- | --- | --- |
| `POST /api/v1/scientific-return/projects/{projectId}/watch` | Create or return the project's watch | Review groups |
| `GET /api/v1/scientific-return/projects/{projectId}/watch` | Read one project watch and its consulted objects | Staff |
| `POST /api/v1/scientific-return/watches/lookup` | Resolve watches and eligibility for 1–100 projects | Staff |
| `PATCH /api/v1/scientific-return/watches/{watchId}` | Change status, interval, and/or anchor | Review groups |
| `POST /api/v1/scientific-return/watches/{watchId}/runs` | Start a deterministic run manually | Review groups |
| `GET /api/v1/scientific-return/watches/{watchId}/runs` | Read paginated run history | Staff |
| `GET /api/v1/scientific-return/metrics` | Read deterministic and autonomous-flow metrics | Staff |

## 7. Functional requirements

### FR-001 — Creation request

The creation body accepts:

| Field | Type | Default | Rule |
| --- | --- | --- | --- |
| `reviewIntervalDays` | integer | `90` | Between 1 and 365, inclusive |
| `scheduleAnchorAt` | date-time or null | Current UTC instant | Defines the fixed review grid |
| `startImmediately` | boolean | `true` | `true` creates `ACTIVE`; `false` creates `PAUSED` |

Example:

```json
{
  "reviewIntervalDays": 90,
  "scheduleAnchorAt": "2026-03-01T00:00:00Z",
  "startImmediately": false
}
```

The route returns `201`, including when it resolves an already existing watch.

### FR-002 — Eligibility

All of the following conditions are required when a new watch is created:

1. the project exists and is `COMPLETED`;
2. the requester/researcher can be resolved and has a non-blank name;
3. the project has at least one consulted object;
4. every consulted object has a non-blank inventory number and object name.

The API returns typed reasons for ineligible projects. A missing or incomplete
project and an unresolved requester are mapped to `404`; malformed or
incomplete consulted-object facts are mapped to `422`.

### FR-003 — Idempotent creation

There is at most one watch per project. If one already exists, creation returns
it unchanged: the request does not reassess eligibility, replace the snapshot,
change the interval, move the anchor, or change status. The database unique
constraint on `project_id` resolves concurrent create attempts by returning the
winning watch after the conflicting transaction is rolled back.

### FR-004 — Project snapshot

Creation writes one snapshot and links it one-to-one with the watch. The
snapshot contains the project reference, researcher, and consulted objects,
plus:

- a SHA-256 hash of canonical JSON;
- builder version `scientific-return-snapshot-v1`;
- creation time.

The payload is encrypted at rest through the application's field encryptor.
The application repository exposes add and read operations only; it has no
snapshot update operation. Database-level immutability and hash verification
are not currently enforced; see [GAP-006](#gap-006--snapshot-integrity-is-only-partially-enforced).

### FR-005 — Initial due time

`nextRunAt` initially equals `scheduleAnchorAt`.

- With omitted anchor and `startImmediately=true`, the watch is active and due
  immediately.
- A future anchor postpones the first due time even when
  `startImmediately=true`.
- With `startImmediately=false`, the watch is paused. Its due time is still the
  anchor, but the scheduler ignores it until the watch becomes active.

### FR-006 — Read and bulk lookup

The single-project `GET` returns `404` when no watch exists and includes the
consulted objects from the snapshot when it does.

Bulk lookup accepts 1–100 project identifiers, removes duplicates while
preserving first-seen order, and returns one item per distinct identifier. An
item includes the existing watch or, when no watch exists, its eligibility and
typed ineligibility reason. Existing watches are reported as `eligible=true`,
including closed watches; here `eligible` describes the underlying project's
watch eligibility, not whether the existing watch can be modified.

### FR-007 — Partial update

`PATCH` accepts any non-empty combination of:

- `scheduleAnchorAt`;
- `reviewIntervalDays` from 1 through 365;
- `status` (`ACTIVE`, `PAUSED`, or `CLOSED`).

An all-null body returns `422`. When multiple values are supplied, the route
applies anchor first, interval second, and status last in one transaction. An
unknown watch returns `404`; domain-invalid changes return `422`.

### FR-008 — Rescheduling

Changing the anchor or interval re-derives `nextRunAt` from the fixed grid
described in section 5.2. It does not grant a new full interval measured from
the update time. This means shortening an interval may make a watch due
immediately, while lengthening it does not necessarily postpone an already due
never-run watch.

### FR-009 — Manual execution

A review-group member may start a deterministic run for an `ACTIVE` watch with
a snapshot. The route commits the completed run and, when new candidates were
created, attempts to notify the watch creator. Notification failure is logged
and rolled back independently; it does not undo the run.

The manual route does not acquire the scheduler's advisory lock. Concurrent run
protection is therefore incomplete; see [GAP-002](#gap-002--run-concurrency-is-not-fully-controlled).

### FR-010 — Scheduled sweep

The supported entry point is:

```bash
uv run python -m app.jobs.scientific_return run-due --limit 25
```

The job obtains a global, oldest-due-first list of `ACTIVE` watches whose
`nextRunAt <= now`, limited by the command argument. Before processing each
watch, it opens a separate transaction, takes a PostgreSQL transactional
advisory lock keyed by the watch ID, reloads the watch, and confirms it is still
due.

The lock prevents two scheduled sweeps from processing the same watch at once.
It is held across source calls until the deterministic run is committed.

### FR-011 — Completion, failure, and cadence advancement

The deterministic pipeline returns `FAILED` only when all queries fail; partial
query failures may produce a `COMPLETED` run with an error summary. In both
cases the use case records `lastRunAt` and advances `nextRunAt` to the next
future grid point.

The scheduled command counts any returned run as processed, even if the run's
domain status is `FAILED`. Only an exception escaping the use case increments
the command's failed counter. These semantics can delay retry after a total
source failure; see [GAP-003](#gap-003--failed-runs-advance-the-normal-cadence).

### FR-012 — Notification and autonomous follow-up

After a scheduled deterministic run is committed:

1. a project notification is attempted only when the run created new
   candidates;
2. the command then attempts to queue one autonomous investigation per
   consulted object, up to the configured object limit;
3. each autonomous start uses an idempotency key containing the run and object
   IDs;
4. expected conditions such as a disabled feature, open circuit, or an already
   live investigation are logged as normal non-start outcomes;
5. failure for one object does not stop the remaining objects.

The autonomous follow-up is attempted for every returned scheduled run,
including a deterministic run with status `FAILED`.

### FR-013 — Operational metrics

The metrics response covers both the deterministic flow and its nested
`fullAgentic` health data:

| Area | Metrics |
| --- | --- |
| Deterministic | Active watches, runs, failed runs, pending candidates, confirmed candidates, dismissed candidates |
| Autonomous flow | Runs, failed runs, candidate counts, LLM timeouts, rejected source waits, recoveries, exhausted recoveries, live investigations, expired leases, and oldest live age in seconds |

These metrics are global rather than institution-scoped; see GAP-001.

### FR-014 — User-interface surfaces

The application exposes two management experiences:

- the project scientific-return panel creates an active watch immediately with
  the API defaults and supports pause, resume, close, schedule editing, manual
  search, and run history;
- the watchers page lists paginated completed projects, resolves the current
  page's watches in one bulk request, and creates a configured watch in
  `PAUSED` state.

The watchers page offers project search and a client-side watch-state filter.
That state filter applies only to the projects already loaded on the current
page; it is not a server-side, globally paginated filter. Bulk-selection and
configuration-replication logic exists in the component class but its controls
are deliberately hidden by the current template and covered by a test.

## 8. Enforced invariants

| ID | Invariant | Enforcement |
| --- | --- | --- |
| INV-001 | One watch per project | Database unique constraint on `project_id` |
| INV-002 | One snapshot per watch | Unique `project_snapshot_id` foreign key |
| INV-003 | A closed watch cannot return to an active or paused state | Domain transition rules |
| INV-004 | A closed watch cannot be re-anchored or assigned another interval | Domain model |
| INV-005 | `reviewIntervalDays` remains within 1–365 | API validation and domain model |
| INV-006 | A completed run advances to the first future point on the anchor grid | Domain cadence calculation |
| INV-007 | Snapshot payloads and persisted query text are encrypted at rest | Repository field encryption |
| INV-008 | Two scheduled sweep workers do not process the same watch concurrently | PostgreSQL transaction advisory lock |

INV-008 intentionally says **scheduled sweep workers**. The stronger claim that
no two runs of any kind can overlap is not true in the current implementation.

## 9. Acceptance evidence

| ID | Behaviour | Automated evidence |
| --- | --- | --- |
| AC-001 | A watch can be created paused without changing the default active behaviour | `test_scientific_return.py::test_watch_creation_can_be_paused_without_changing_the_default` |
| AC-002 | Creation and lookup return typed ineligibility reasons | `test_scientific_return.py::test_watch_creation_reports_typed_and_human_readable_ineligibility`, `::test_watch_lookup_exposes_each_typed_ineligibility_reason` |
| AC-003 | Bulk lookup preserves order and reports eligibility | `test_scientific_return.py::test_watch_lookup_preserves_order_and_reports_eligibility` |
| AC-004 | A new interval is derived from the anchor, not from update time | `test_scientific_return.py::test_a_new_interval_is_re_derived_from_the_anchor_not_from_now` |
| AC-005 | A late run does not shift the series | `test_scientific_return.py::test_a_late_search_does_not_push_the_series_later` |
| AC-006 | A long outage resumes at the next future grid point | `test_scientific_return.py::test_a_long_outage_resumes_at_the_next_future_slot` |
| AC-007 | A future anchor postpones the first review | `test_scientific_return.py::test_a_future_anchor_postpones_the_first_review` |
| AC-008 | A never-run watch remains due at its anchor after interval change | `test_scientific_return.py::test_a_new_interval_leaves_a_never_run_watch_due` |
| AC-009 | A closed watch cannot be rescheduled | `test_scientific_return.py::test_a_closed_watch_cannot_be_rescheduled` |
| AC-010 | Intervals outside 1–365 are rejected | `test_scientific_return.py::test_an_interval_outside_the_allowed_range_is_refused` |
| AC-011 | Scheduled autonomous work fans out per object and isolates queue failures | `test_sweep_fan_out.py` |
| AC-012 | The watchers page batches lookup and hides unfinished bulk controls | `project-watchers-page.component.spec.ts` |

No focused automated test was found for the scheduled `run-due` selection and
transactional-lock path itself. This is recorded in GAP-010.

## 10. Known implementation gaps

### GAP-001 — Institution isolation is not enforced

**Severity: critical.** Watch repositories resolve by global watch/project IDs,
bulk lookup accepts arbitrary project IDs, scheduled selection and metrics are
global, and the mutation use cases do not compare the watch's institution with
the caller's. `institution_id` is nullable, has no foreign key, and is not
returned by the public watch schema. A staff caller may therefore observe or
mutate scientific-return records outside the intended institution boundary if
it knows or can enumerate identifiers.

**Required change:** make institution ownership non-null and referential,
derive it from the authoritative project boundary, scope every read, lookup,
mutation, history, candidate, metric, and scheduling query, and add negative
cross-institution API tests.

### GAP-002 — Run concurrency is not fully controlled

**Severity: critical.** The transactional advisory lock is used only by
`run-due`. The manual-run route does not take it, and there is no database
constraint preventing more than one live run per watch. Two manual requests, or
a manual request and a sweep, may overlap and contact external sources twice.

**Required change:** place one shared per-watch locking/idempotency mechanism at
the run use-case boundary and cover scheduled/scheduled, manual/manual, and
scheduled/manual races with integration tests.

### GAP-003 — Failed runs advance the normal cadence

**Severity: high.** A run in which every query fails still updates `lastRunAt`
and advances `nextRunAt` by the normal interval. The scheduler also attempts
autonomous follow-up for that failed deterministic run. A temporary source
outage can consequently defer the next deterministic attempt for up to 365
days.

**Required change:** define an explicit retry policy for total failure, preserve
the regular anchor grid separately from retry scheduling, and queue autonomous
follow-up only under a documented run-status policy.

### GAP-004 — External calls run inside the scheduler transaction

**Severity: high.** The scheduled worker holds both a database transaction and
its transaction-scoped advisory lock while performing external bibliographic
requests. Slow sources increase connection occupancy, transaction lifetime, and
lock contention.

**Required change:** claim work in a short transaction using a persisted lease
or unique live-run record, perform network work outside that transaction, and
finalise atomically.

### GAP-005 — Watch updates have no concurrency token

**Severity: medium.** Combined patch fields are applied through separate loads
inside one transaction, but the watch has no version column or row lock.
Concurrent editors can overwrite each other's state, anchor, or interval.

**Required change:** introduce optimistic versioning or a row-level update lock,
return conflicts explicitly, and test concurrent edits.

### GAP-006 — Snapshot integrity is only partially enforced

**Severity: medium.** Application code does not expose an update operation, but
the database does not forbid snapshot changes. The stored SHA-256 hash is not
recomputed and checked when a snapshot is read. Snapshot `project_id` is not a
foreign key, and its equality with the linked watch project is not constrained.

**Required change:** verify the hash on read, constrain project ownership and
link consistency, and add persistence tests for tampering and immutability.

### GAP-007 — Watch representations are inconsistent

**Severity: medium.** The single-project `GET` loads the snapshot and returns
`consultedObjects`. Creation and bulk lookup map watches without loading their
snapshots, so the same response type contains an empty list on those routes.
The project panel uses bulk lookup and can therefore receive incomplete object
coverage data.

**Required change:** either populate consulted objects consistently on every
watch representation or separate summary and detail response schemas so an
empty list cannot be mistaken for an empty snapshot.

### GAP-008 — Schedule timestamps need an explicit timezone contract

**Severity: medium.** The schema accepts a general `datetime`; it does not
explicitly reject timestamps without an offset. The UI sends UTC, but another
client can submit a naive timestamp and create ambiguous persistence or
naive/aware comparison failures.

**Required change:** require offset-aware ISO 8601 input, normalise to UTC, and
add API tests for missing offsets and daylight-saving boundaries.

### GAP-009 — UI behaviour is inconsistent or misleading

**Severity: medium.** The project panel creates an active default watch, while
the watchers page creates a configured paused watch. The watchers page's state
filter covers only the current server page, although it can appear to describe
the complete result set. Dormant bulk logic remains in the component while its
controls are hidden.

**Required change:** establish one creation policy, implement server-side
watch-state filtering with coherent totals, and either finish or remove the
hidden bulk workflow.

### GAP-010 — Scheduler orchestration lacks focused integration coverage

**Severity: medium.** Domain cadence and autonomous fan-out have tests, but no
focused test was found for due selection, lock contention, stale recheck,
failed-run accounting, notification isolation, or the full `run-due` command.

**Required change:** add PostgreSQL-backed orchestration tests for those paths,
especially the races and failure semantics described above.

### GAP-011 — Notifications have no durable delivery retry

**Severity: low.** Notification dispatch is best-effort after the run commit.
Failure is logged and does not roll back the result, which protects search data,
but there is no durable outbox or visible retry state for the missed alert.

**Required change:** route notifications through the application's durable
delivery mechanism or record retryable delivery state.

## 11. Non-functional requirements

- **Confidentiality:** encrypt project snapshots and exact query text at rest.
- **Auditability:** retain creator, snapshot provenance, cadence, run history,
  query outcomes, and candidate counts.
- **Determinism:** calculate cadence from the anchor grid, never from scheduler
  delay.
- **Cost control:** contact sources only for active due watches; search-level
  source and query limits are defined in SPEC-003.
- **Resilience:** isolate notification and per-object autonomous-queue failures
  from an already committed deterministic run.
- **Time:** persist and compare scheduling instants in UTC.

## 12. Traceability

| Concern | Implementation |
| --- | --- |
| Watch lifecycle and cadence | `vitarerum-api/app/scientific_return/domain/models.py` |
| Eligibility, creation, lookup, updates, and runs | `vitarerum-api/app/scientific_return/application/use_cases.py` |
| Persistence and encryption | `vitarerum-api/app/scientific_return/infrastructure/models.py`, `repositories.py` |
| HTTP request/response contract | `vitarerum-api/app/scientific_return/presentation/schemas.py`, `routes.py` |
| Scheduled sweep and autonomous fan-out | `vitarerum-api/app/jobs/scientific_return.py`, `app/scientific_return/presentation/commands.py` |
| Project watch panel | `vitarerum-ui/src/app/features/collections/projects/components/scientific-return-panel/` |
| Watches page | `vitarerum-ui/src/app/features/collections/projects/pages/watchers/` |
| Backend evidence | `vitarerum-api/test/scientific_return/` |
| UI evidence | Component and service `*.spec.ts` files under the UI paths above |

## 13. Open product decisions

1. Should failed deterministic runs use an exponential retry schedule distinct
   from the curatorial review cadence?
2. Should resuming an overdue paused watch trigger an immediate run or offer a
   choice to re-anchor first?
3. Should watches close automatically after a defined period without findings?
4. Should cadence defaults vary by project profile or collection-use purpose?
5. Should all creation surfaces start active, start paused, or ask the user to
   choose explicitly?
