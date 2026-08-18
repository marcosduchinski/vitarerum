# Scientific Return - Staff API

Base path: `/api/v1/scientific-return`.

All endpoints require a valid bearer token and `X-Permission-Id`. Read endpoints
accept staff groups. Mutations are restricted to `CURATORIAL`,
`COLLECTIONS_MANAGEMENT`, and `DIRECTION`; `SYS_ADMIN` has diagnostic read
access but cannot make curatorial decisions.

The feature is advisory and human-in-the-loop. Bibliographic results are
candidates until a staff member confirms them. Only confirmation creates a
project publication-log entry.

The immutable project snapshot and the exact external query text are encrypted
at rest with the application's configured database field-encryption key. This
protects the internal association between researcher, project and consulted
objects while retaining hashes and public bibliographic metadata for audit and
deduplication.

## LLM shadow analysis

Phase 3B adds an optional advisory analysis after the deterministic pipeline has
created a candidate and its evidence. It is disabled by default and requires:

```dotenv
SCIENTIFIC_RETURN_LLM_ENABLED=true
SCIENTIFIC_RETURN_LLM_MODEL=llama3.1:8b
SCIENTIFIC_RETURN_LLM_TIMEOUT_SECONDS=60
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_API_KEY=<secret>
```

`OLLAMA_API_KEY` is only required by providers that authenticate requests. The
model receives the minimum project snapshot, normalized candidate metadata,
verified evidence and the recorded query trajectory. Publication text is
explicitly treated as untrusted data.

- `POST /candidates/{candidateId}/agent-analyses` generates and persists one
  shadow analysis.
- `GET /candidates/{candidateId}/agent-analyses` returns its audit history.
- `POST /agent-analyses/{analysisId}/feedback` records `USEFUL`,
  `PARTIALLY_USEFUL`, or `NOT_USEFUL` once per completed analysis.

The structured result separates supporting evidence, contradictions, missing
evidence, one typed recommended action, proposed queries, a short reasoning
summary and advisory confidence. The record retains model and published-prompt
versions, encrypted input and output, hashes, latency, errors and staff
feedback. Invalid output, timeout or provider failure produces a `FAILED`
analysis and does not interrupt the deterministic candidate pipeline.

Shadow analysis never invokes a bibliographic source, changes candidate state,
creates a decision or writes to `PublicationLog`. A proposed action is displayed
for review only; execution belongs to Phase 3C and requires a separate,
deterministic authorization policy.

## Activate a watch

`POST /projects/{projectId}/watch`

```json
{
  "reviewIntervalDays": 90
}
```

Returns `201` with the watch. The project must be `COMPLETED`, have a resolved
requester name, and every consulted object must have an inventory number and
object name. Calling this endpoint again returns the existing watch.

## Read and control a watch

- `GET /projects/{projectId}/watch`
- `PATCH /watches/{watchId}` with `status`, `reviewIntervalDays`, or both

Both body fields are optional and a body with neither is `422`. Examples:

```json
{ "status": "PAUSED" }
{ "reviewIntervalDays": 30 }
```

A closed watch cannot be reopened, nor re-cadenced. `reviewIntervalDays` stays
within 1..365 and moves `nextRunAt` with it: the new date is measured from the
last search (`lastRunAt + interval`), never from now, so shortening the cadence
can make a watch due immediately and lengthening it cannot grant a fresh full
period. A watch that has never run stays due at its activation date, because
re-cadencing is not a way to postpone a review that is already owed.

## Execute and inspect searches

- `POST /watches/{watchId}/runs`
- `GET /watches/{watchId}/runs?page=0&size=10`

A run records every planned query, source, result count, error and timestamp.
`candidateCount` includes known candidates and `newCandidateCount` identifies
discoveries from that run. Crossref is always enabled; OpenAlex is added when
`OPENALEX_API_KEY` is configured. Europe PMC is added to recurring searches
only when `EUROPE_PMC_ENABLED=true`; its open-access full text is inspected
transiently for evidence and is not persisted. The planner sends only
combinations of author, inventory number and object name from the immutable
project snapshot.
Executions are capped by `SCIENTIFIC_RETURN_MAX_QUERIES_PER_RUN` (40 by
default). `CROSSREF_MAILTO` should identify the deployment to Crossref's polite
pool. Calls are serialized with a configurable minimum interval. Responses
`429`, `500`, `502`, `503`, and `504` are retried with exponential backoff or
the server-provided `Retry-After`, up to `CROSSREF_MAX_RETRIES`.

When exact strategies yield no actionable candidate for a source, at most two
additional strategies may replace a binomial object name with its genus. This
adaptive step is recorded like every other query.

## Operational metrics

`GET /metrics`

Returns active watches, total and failed runs, and pending, confirmed and
dismissed candidate counts.

## Scheduled execution and evaluation

```bash
uv run python -m app.jobs.scientific_return run-due --limit 25
uv run python -m app.jobs.scientific_return evaluate-phase0
```

`app.jobs.scientific_return` is a composition-root wrapper: it registers every
ORM mapper and delegates to the commands themselves. Invoking
`app.scientific_return.presentation.commands` directly fails as soon as it
touches the database, because the candidate table's foreign key into
`use_of_collections` cannot resolve — the context is forbidden from importing
that context, so registration is the entry point's job. The API never hits this
because `app.main` imports every router.

`run-due` uses a PostgreSQL transaction advisory lock per watch and emits one
project notification only when the run creates new candidates. The evaluation
command runs the five versioned known-publication cases and prints JSON.
`--sources` selects `crossref`, `openalex` and/or `europe_pmc`; `all` is the
default and skips OpenAlex with a warning when its key is absent. `--output`
writes the reproducible report to a file. The report contains a review queue;
after staff completes its human-decision fields, `--reviews` imports it and
calculates review coverage and human precision without repeating external
searches.

In production the sweep runs as a Cloud Run job triggered by Cloud Scheduler.
`cloudbuild.yaml` refreshes the job image on every deploy; the job itself and
its trigger are created once:

```bash
# One-time: the job. --command overrides the image ENTRYPOINT so a scheduled
# sweep does not re-run alembic; migrations stay the migrate job's business.
gcloud run jobs create vitarerum-scientific-return \
  --image us-east1-docker.pkg.dev/PROJECT_ID/vitarerum/vitarerum:latest \
  --region us-east1 \
  --command python \
  --args -m,app.jobs.scientific_return,run-due,--limit,25 \
  --set-secrets DATABASE_URL=vitarerum-database-url:latest \
  --max-retries 1 \
  --task-timeout 30m

# One-time: the cadence. Daily at 03:00 UTC; watches only run when their own
# nextRunAt is due, so the schedule is a floor, not the review interval.
gcloud scheduler jobs create http vitarerum-scientific-return-daily \
  --location us-east1 \
  --schedule '0 3 * * *' \
  --uri 'https://us-east1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/vitarerum-scientific-return:run' \
  --http-method POST \
  --oauth-service-account-email SCHEDULER_SA@PROJECT_ID.iam.gserviceaccount.com
```

The scheduler's service account needs `roles/run.invoker` on the job. Set the
job's secrets and environment to match the API service — it opens its own
database session and reads the same settings.

Two cadences are in play and they are not the same thing. The Cloud Scheduler
cron decides how often the sweep *looks*; each watch's `reviewIntervalDays`
decides whether it is due when the sweep arrives. A daily sweep with 90-day
watches contacts no source on 89 of every 90 days.

## Review candidates

`GET /projects/{projectId}/candidates?status=PENDING&page=0&size=20`

Each candidate contains normalized bibliographic metadata and an ordered list
of evidence. `objectId` links object-specific evidence to the consulted object
snapshot. Evidence strength is `PRIMARY`, `SUPPORTING`, or `WEAK`; it is not
an automated confidence decision.

The global staff queue is available from:

`GET /candidates?status=PENDING&source=CROSSREF&evidenceStrength=PRIMARY&page=0&size=20`

Queue items add `projectId` so the interface can open the project that owns the
watch. Filters are optional; status defaults to `PENDING`.

## Decide a candidate

`POST /candidates/{candidateId}/decision`

Confirm:

```json
{
  "decision": "CONFIRM"
}
```

Correct and confirm:

```json
{
  "decision": "CORRECT_AND_CONFIRM",
  "justification": "Corrected from the publisher record.",
  "correction": {
    "title": "Corrected title",
    "doi": "10.1000/example",
    "url": "https://doi.org/10.1000/example",
    "authors": ["First Author", "Second Author"]
  }
}
```

Dismissal requires a justification. Snoozing requires a future
`snoozedUntil`. Confirmation and correction-confirmation create the
`PublicationLogEntry` in the same database transaction and return its ID in
`confirmedPublicationEntryId`.

Decision history is available from:

`GET /candidates/{candidateId}/decisions`

The history includes the evidence snapshot seen at decision time.

## Assisted investigation

An investigation is a bounded agentic cycle over one watch and, optionally, one
candidate. It runs synchronously: the response carries the whole trajectory,
already terminal.

The model never executes anything. It proposes one typed action and, at most,
which consulted object it concerns; a deterministic policy authorises the action
and derives the queries, the sources and the result limit. Evidence is always
recomputed by the same deterministic rules the scheduled pipeline uses, and the
candidate still requires a human decision.

The cycle is disabled by default. `SCIENTIFIC_RETURN_AGENT_MODE` must be
`SUPERVISED` for a tool to run; `SHADOW` and `POLICY_ONLY` stop before execution
and `DISABLED` refuses the request.

### Start a discovery investigation

```http
POST /api/v1/scientific-return/watches/{watch_id}/investigations
Idempotency-Key: <uuid>
```

Looks for a publication the deterministic pipeline did not turn into an
actionable candidate. Ending without a candidate is a valid result, not a
failure.

### Start an enrichment investigation

```http
POST /api/v1/scientific-return/candidates/{candidate_id}/investigations
Idempotency-Key: <uuid>
```

Looks for additional verified evidence for a `PENDING` candidate. It never
changes the candidate's title, authors, DOI, URL or status: correcting those
remains a human act.

`Idempotency-Key` is optional but recommended. Repeating a request with the same
key returns the investigation that key already produced, without contacting any
source again. Omitting it means the caller did not ask for idempotency, and each
request starts a new investigation.

Both return `201 Created`:

```json
{
  "id": "b7f1...",
  "watchId": "6f2c...",
  "candidateId": null,
  "objective": "DISCOVER_CANDIDATE",
  "status": "AWAITING_HUMAN_REVIEW",
  "mode": "SUPERVISED",
  "stopReason": "EVIDENCE_SUFFICIENT",
  "currentIteration": 1,
  "budget": {
    "maxIterations": 1,
    "maxQueries": 4,
    "maxNewCandidates": 5,
    "usedIterations": 1,
    "usedQueries": 4,
    "createdCandidates": 1
  },
  "startedAt": "2026-08-17T21:04:11Z",
  "completedAt": "2026-08-17T21:05:52Z",
  "createdBy": "perm-1",
  "previousInvestigationId": null,
  "iterations": [
    {
      "id": "b7f1...:1",
      "number": 1,
      "status": "COMPLETED",
      "startedAt": "2026-08-17T21:04:12Z",
      "completedAt": "2026-08-17T21:05:52Z",
      "observation": {
        "researcher": "Rita P. Eusebio",
        "projectReference": "PRJ-0001",
        "objects": [
          {
            "id": "object-1",
            "inventoryNumber": "MUHNAC/MB11-001283",
            "objectName": "Trichoniscoides machadoi"
          }
        ],
        "triedQueries": ["\"MUHNAC/MB11-001283\""],
        "allowedActions": ["SEARCH_INVENTORY_VARIANTS", "PRESENT_FOR_REVIEW"]
      },
      "plan": {
        "objective": "Locate missing inventory evidence.",
        "actionType": "SEARCH_INVENTORY_VARIANTS",
        "objectId": "object-1",
        "reasoningSummary": "The candidate has taxon support but no inventory evidence.",
        "expectedEvidence": ["INVENTORY_NUMBER"]
      },
      "policy": {
        "authorized": true,
        "justification": "3 untried inventory variant(s) over 1 source(s).",
        "rejectionReason": null
      },
      "tool": {
        "executedQueries": ["\"MB11-001283\"", "\"MNHNC:MB11:001283\""],
        "sources": ["EUROPE_PMC"],
        "totalResults": 4,
        "createdCandidateIds": ["c91a..."],
        "addedEvidenceIds": []
      },
      "evidenceDelta": {
        "added": ["INVENTORY_NUMBER"],
        "preserved": [],
        "removed": []
      },
      "reflection": {
        "progress": "EVIDENCE_ADDED",
        "evidenceDeltaSummary": "A primary inventory-number evidence was added.",
        "remainingGaps": [],
        "recommendedStop": true,
        "reasoningSummary": "The objective of the iteration was achieved."
      },
      "telemetry": {
        "model": "llama3.1:8b",
        "promptVersion": "scientific-return-agent-plan-v1",
        "planLatencyMs": 40413,
        "reflectionLatencyMs": 59116,
        "totalLatencyMs": 99529
      },
      "evidenceBeforeHash": "e3b0...",
      "evidenceAfterHash": "9f86...",
      "errorMessage": null
    }
  ]
}
```

`stopReason` is always present on a terminal investigation. `EVIDENCE_SUFFICIENT`
is the only happy-path reason; the others record why the cycle ended without
adding anything, and none of them blocks the human review queue.

`telemetry` is null for an investigation recorded before telemetry existed, and
whenever the model was never reached.

### Read investigations

```http
GET /api/v1/scientific-return/watches/{watch_id}/investigations
GET /api/v1/scientific-return/candidates/{candidate_id}/investigations
GET /api/v1/scientific-return/investigations/{investigation_id}
```

Read-only. These never continue, retry or re-run a cycle.

## Error codes

- `SCIENTIFIC_RETURN_WATCH_NOT_FOUND`: watch does not exist.
- `SCIENTIFIC_RETURN_CANDIDATE_NOT_FOUND`: candidate does not exist.
- `COMPLETED_PROJECT_NOT_FOUND`: project does not exist or is not completed.
- `SCIENTIFIC_RETURN_INVALID`: domain validation failed.
- `SCIENTIFIC_RETURN_LLM_DISABLED`: shadow analysis is disabled by feature flag.
- `SCIENTIFIC_RETURN_LLM_UNAVAILABLE`: no published prompt or reasoner is
  available.
- `SCIENTIFIC_RETURN_AGENT_ANALYSIS_NOT_FOUND`: analysis does not exist.
- `SCIENTIFIC_RETURN_AGENT_DISABLED`: the operating mode does not run
  investigations (`503`).
- `SCIENTIFIC_RETURN_INVESTIGATION_RUNNING`: a non-terminal investigation
  already covers this watch, objective and candidate (`409`).
- `SCIENTIFIC_RETURN_INVESTIGATION_NOT_FOUND`: investigation does not exist.
