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
- `PATCH /watches/{watchId}` with `{ "status": "ACTIVE|PAUSED|CLOSED" }`

A closed watch cannot be reopened.

## Execute and inspect searches

- `POST /watches/{watchId}/runs`
- `GET /watches/{watchId}/runs?page=0&size=10`

A run records every planned query, source, result count, error and timestamp.
`candidateCount` includes known candidates and `newCandidateCount` identifies
discoveries from that run. Crossref is always enabled; OpenAlex is added when
`OPENALEX_API_KEY` is configured. The planner sends only combinations of author,
inventory number and object name from the immutable project snapshot.
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
uv run python -m app.scientific_return.presentation.commands run-due --limit 25
uv run python -m app.scientific_return.presentation.commands evaluate-phase0
```

`run-due` uses a PostgreSQL transaction advisory lock per watch and emits one
project notification only when the run creates new candidates. The evaluation
command runs the five versioned known-publication cases and prints JSON.

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

## Error codes

- `SCIENTIFIC_RETURN_WATCH_NOT_FOUND`: watch does not exist.
- `SCIENTIFIC_RETURN_CANDIDATE_NOT_FOUND`: candidate does not exist.
- `COMPLETED_PROJECT_NOT_FOUND`: project does not exist or is not completed.
- `SCIENTIFIC_RETURN_INVALID`: domain validation failed.
