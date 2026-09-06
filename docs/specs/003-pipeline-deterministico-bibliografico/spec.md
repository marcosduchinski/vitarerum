# SPEC-003 — Deterministic bibliographic-discovery pipeline

| Field | Value |
| --- | --- |
| Identifier | SPEC-003 |
| Status | Implemented |
| Bounded context | `app/scientific_return` |
| Derived from | `application/{analysis,use_cases}.py`, bibliographic-source ports and adapters, persistence mappings, configuration, routes, and scientific-return tests |
| Related specs | [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-006](../006-avaliacao-retorno-cientifico/spec.md), [SPEC-024](../024-investigacao-agentica-autonoma/spec.md) |

## 1. Problem

Discovering publications derived from a collection-use project requires more
than sending one broad web search. The system must formulate traceable queries,
search heterogeneous bibliographic indexes responsibly, recognise evidence,
avoid presenting the same publication repeatedly, and retain enough provenance
for later curatorial review.

## 2. Goal

Run a deterministic and auditable **first-pass discovery pipeline** from the
watch's project snapshot. Given the same snapshot and the same bibliographic
records, planning, normalisation, evidence classification, and deduplication
follow the same rules. External indexes are mutable, so this is not a guarantee
that two runs at different times return identical records.

The pipeline creates or rediscovers **publication candidates**. It never
confirms, corrects, or dismisses them; those decisions belong to SPEC-004.

## 3. Domain and architecture

Scientific return is the bounded context. Deterministic discovery is an
application workflow inside it, not a separate aggregate.

| DDD role | Element | Responsibility |
| --- | --- | --- |
| Aggregate root | `ScientificReturnWatch` | Defines whether a search may run and records its cadence |
| Entity | `ScientificReturnSearchRun` | Records one pipeline execution and its outcome |
| Entity | `ScientificReturnQuery` | Records one logical source query and its result |
| Aggregate root | `CandidatePublication` | Preserves the first accepted bibliographic identity, status, and evidence |
| Entity | `CandidateEvidence` | Explains why one candidate relates to a project or object |
| Value-like immutable input | `ProjectSnapshotPayload` | Supplies the researcher and consulted objects used for planning and matching |
| Port | `BibliographicSource` | Abstracts an external bibliographic index |
| Adapters | Crossref, OpenAlex, Europe PMC | Translate logical queries and external records |
| Repository port | `ScientificReturnRepository` | Persists runs, queries, candidates, evidence, watches, and snapshots |

Dependencies point inward: source adapters and SQLAlchemy repositories
implement application ports; planning and evidence rules do not import HTTP or
database frameworks.

## 4. Ubiquitous language

- **Run**: one complete deterministic pass over the configured sources.
- **Planned query**: an immutable logical query containing type, audited text,
  and, when applicable, a structured author hint.
- **Exact trajectory**: one of the four initial query strategies for a
  consulted object.
- **Adaptive trajectory**: a later query using the first term of a multi-token
  object name.
- **Bibliographic record**: a source-neutral record returned by an adapter.
- **Evidence**: a typed, ranked explanation linking a record to the researcher
  or a consulted object.
- **Actionable record**: a record with at least one evidence type accepted by
  the candidate gate.
- **Deduplication key**: watch-local identity derived from DOI or selected
  metadata.
- **New candidate**: an actionable record whose deduplication key is not yet
  present in the watch.
- **Touched candidate**: an existing or newly created candidate returned during
  the run.

## 5. Scope

**In scope:** deterministic query planning, adaptive planning, source
selection, source throttling and retry, record mapping, evidence construction,
actionability, watch-local deduplication, candidate creation, and run/query
audit data.

**Out of scope:** watch lifecycle and cadence (SPEC-002), human decisions
(SPEC-004), assisted agentic investigation (SPEC-001), autonomous agentic
investigation (SPEC-024), and offline quality evaluation (SPEC-006).

## 6. Public operations

| Method and route | Behaviour | Access |
| --- | --- | --- |
| `POST /api/v1/scientific-return/watches/{watchId}/runs` | Execute the deterministic pipeline and return the run with its queries | `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION` |
| `GET /api/v1/scientific-return/watches/{watchId}/runs?page=0&size=10` | Return newest-first run history and query details | Authenticated staff |

The list endpoint accepts `page >= 0` and `1 <= size <= 100`. A run may start
only for an existing `ACTIVE` watch with a linked snapshot. Institution scoping
and run-concurrency limitations are documented in SPEC-002.

## 7. Pipeline sequence

For each run, the application service performs these steps in order:

1. load and validate the active watch and snapshot;
2. create a `RUNNING`, `DETERMINISTIC` run;
3. build the exact query plan once from the snapshot;
4. visit sources in configured order while a shared query budget remains;
5. execute and persist every attempted logical query;
6. after a source's exact trajectories, append adaptive trajectories only when
   that source did not add a previously untouched candidate to the run set;
7. normalise each returned record, derive its watch-local deduplication key,
   and look for an existing candidate;
8. for a new key, construct evidence and create a candidate only if actionable;
9. finalise counts and status, then advance the watch cadence as specified by
   SPEC-002.

Sources and queries run sequentially. The pipeline does not run source calls in
parallel.

## 8. Functional requirements

### FR-001 — Exact query plan

For each consulted object, the planner produces four trajectories in this
order:

| Type | Logical audited text | Structured author hint |
| --- | --- | --- |
| `INVENTORY` | `"inventory number"` | none |
| `AUTHOR_INVENTORY` | `"researcher" "inventory number"` | researcher |
| `INVENTORY_OBJECT` | `"inventory number" "object name"` | none |
| `AUTHOR_OBJECT` | `"researcher" "object name"` | researcher |

Every snapshot value is trimmed and enclosed in double quotes. Equal
`PlannedQuery` values across objects are removed while preserving first-seen
order. Planning uses only the snapshot researcher, inventory number, and object
name.

The planner does not escape an embedded double quote in a snapshot value; see
GAP-008.

### FR-002 — Adaptive plan

After all exact trajectories for one source have been attempted, the pipeline
may append two queries per consulted object:

| Type | Replacement |
| --- | --- |
| `INVENTORY_OBJECT` | Replace the complete object name with its first whitespace-separated term |
| `AUTHOR_OBJECT` | Apply the same replacement and retain the author hint |

No adaptive query is produced when the object name consists of one term.
Duplicates are removed while preserving order, and the remaining global query
budget truncates the adaptive plan.

The implementation treats every multi-token object name as eligible for this
broadening. It does not validate that the value is a taxonomic binomial; see
GAP-003.

### FR-003 — Adaptive trigger semantics

Adaptive trajectories are appended only at the end of a source's initial
query list when the size of the run's touched-candidate set has not increased
since that source began.

Consequences:

- records without actionable evidence do not suppress adaptation;
- a newly created candidate suppresses adaptation for that source;
- the first rediscovery of a known candidate can also suppress adaptation;
- a candidate already touched by an earlier source does not increase the set
  again and therefore does not suppress adaptation in a later source.

This is touched-candidate behaviour, not strictly “no new candidate created”.

### FR-004 — Enabled sources and order

| Order | Source | Enablement | Query result limit |
| --- | --- | --- | --- |
| 1 | Crossref | Always enabled | `SCIENTIFIC_RETURN_RESULT_LIMIT`, default 20 |
| 2 | OpenAlex | Enabled when `OPENALEX_API_KEY` is non-empty | Same per-query limit |
| 3 | Europe PMC | Enabled when `EUROPE_PMC_ENABLED=true` | Same per-query limit |

The source order matters because all sources share one query ceiling. An early
source can consume the complete budget and prevent later sources from running.

### FR-005 — Crossref adapter

Crossref receives the complete logical query in its `query` parameter and the
configured result limit in `rows`. When configured, `CROSSREF_MAILTO` is sent
both as a request parameter and in the user agent.

The adapter maps title, authors, publication date, abstract, URL, DOI, source
record identity, and a SHA-256 hash of the raw JSON record. Markup is removed
from title and abstract before persistence.

### FR-006 — OpenAlex adapter

OpenAlex's general `search` field does not index authorship in the required way.
For a query with an author hint, the adapter:

1. removes the author phrase from the free-text `search` value;
2. sends the researcher through `filter=raw_author_name.search:{author}`;
3. omits `search` entirely when no terms remain.

The adapter maps DOI, authorships, publication date, landing URL, and rebuilds
the abstract from OpenAlex's inverted index. The API key is sent as a request
parameter, and a logging filter redacts its literal value from `httpx` log
messages.

The persisted `queryText` remains the logical planned string, not a complete
record of these actual transport parameters; see GAP-002.

### FR-007 — Europe PMC adapter and transient full text

Europe PMC receives the complete logical string in `query`, uses
`resultType=core`, and optionally sends `EUROPE_PMC_EMAIL`. For results carrying
a PMCID, the adapter attempts open-access XML enrichment for the first
`EUROPE_PMC_FULL_TEXT_RESULT_LIMIT` result positions, default 10.

Full-text processing follows these rules:

- a document larger than 15 MiB is not parsed;
- XML parse failure produces metadata-only output;
- HTTP or source-budget failure during enrichment produces metadata-only output
  without losing the search result;
- results are cached by PMCID for the lifetime of the adapter instance;
- extracted text exists only on the in-memory `BibliographicRecord` and is not
  stored on the deterministic candidate.

The pipeline may persist derived evidence whose `sourceField` is `full_text`,
but not the full-text body or a supporting excerpt.

### FR-008 — Retry and wait policy

All three adapters classify `429`, `500`, `502`, `503`, and `504` as transient.
They retry up to the source-specific configured maximum, using `Retry-After`
when parseable or exponential backoff otherwise. Other HTTP errors are raised
without retry.

The common source budget:

- accepts both delay-seconds and HTTP-date forms of `Retry-After`;
- refuses a requested delay above
  `SCIENTIFIC_RETURN_SOURCE_MAX_RETRY_AFTER_SECONDS`, default 60 seconds;
- refuses to begin an operation that cannot fit within the remaining source
  budget;
- wraps throttle wait plus adapter execution in a hard
  `SCIENTIFIC_RETURN_SOURCE_TOTAL_TIMEOUT_SECONDS` ceiling, default 120 seconds.

Europe PMC full-text enrichment handles budget exhaustion as a degradation to
metadata. Exhaustion of the main search is a failed query.

### FR-009 — Deployment-wide source throttling

Every enabled source is wrapped by a PostgreSQL-backed rate limiter. It
atomically reserves the next source-specific time slot in
`sr_source_throttles`, commits, closes that short database session, and only
then sleeps until the reserved time. It therefore coordinates API replicas and
workers without holding its own database connection while waiting.

The configured intervals are:

- Crossref: `CROSSREF_MIN_INTERVAL_SECONDS`, default 0.25 seconds;
- OpenAlex: 0.1 seconds;
- Europe PMC: 0.1 seconds.

If the reserved wait would exceed
`SCIENTIFIC_RETURN_SOURCE_RATE_LIMIT_MAX_WAIT_SECONDS`, the reservation is
rolled back and the query fails instead of extending the backlog.

### FR-010 — Shared query and result limits

`SCIENTIFIC_RETURN_MAX_QUERIES_PER_RUN`, default 40, caps attempted external
queries across all sources and both exact and adaptive trajectories. Every
attempt consumes one unit, whether it succeeds or fails.

`SCIENTIFIC_RETURN_RESULT_LIMIT`, default 20, is passed to each query. It is not
a whole-run result ceiling. Configuration currently lacks positive-value
validation for both settings; see GAP-007.

### FR-011 — Record normalisation for matching

General text matching applies Unicode NFKD decomposition, removes combining
marks, case-folds, replaces non-word runs with spaces, and collapses whitespace.

Inventory matching additionally:

- removes all characters except ASCII letters and digits;
- uppercases the value;
- rewrites known `MUNHAC` occurrences to `MUHNAC`;
- collapses an immediately repeated `MB` collection-code segment;
- tries both the full compact value and, when present, the substring beginning
  at the first `MBdd` collection code.

Matching uses substring containment rather than token or identifier boundaries.
The metadata text also includes authors even though a hit is labelled
`title_or_abstract`; see GAP-004.

### FR-012 — Author matching

The researcher's normalised token set must be a subset of at least one
bibliographic author's token set. Token order is irrelevant. An author match by
itself creates supporting evidence but is not actionable.

### FR-013 — Evidence construction

| Evidence type | Strength | Current condition |
| --- | --- | --- |
| `AUTHOR` | `SUPPORTING` | Researcher tokens match one author |
| `INVENTORY_NUMBER` | `PRIMARY` | An inventory variant occurs in combined metadata or indexed text |
| `OBJECT_NAME` | `SUPPORTING` | The complete normalised object name occurs |
| `OBJECT_NAME` | `WEAK` | Only the first term of a multi-token object name occurs |
| `AUTHOR_INVENTORY` | `PRIMARY` | Author and inventory match the same record |
| `INVENTORY_OBJECT` | `PRIMARY` | Inventory and complete/first-term object match the same record |
| `AUTHOR_OBJECT` | `SUPPORTING` | Author and complete/first-term object match the same record |

Object-specific evidence stores `objectId`. Every evidence row stores a value,
source-field label, human-readable explanation, and creation time. Deterministic
evidence does not carry autonomous-investigation provenance fields.

### FR-014 — Actionability gate

A new record becomes a candidate when its evidence includes at least one of:

- `INVENTORY_NUMBER`;
- `AUTHOR_INVENTORY`;
- `INVENTORY_OBJECT`;
- `AUTHOR_OBJECT`.

An isolated author or isolated object-name match is not actionable. Because
`AUTHOR_OBJECT` is accepted, author plus a first-term object match is sufficient
even though both constituent signals are supporting or weak.

### FR-015 — Deduplication key

Deduplication is local to one watch.

- When a DOI exists, the key is the case-folded DOI after removing one exact
  leading `https://doi.org/`.
- Otherwise, the key is a SHA-256 hash of normalised title, publication-date
  string, and normalised first author.

The database enforces uniqueness on `(watch_id, deduplication_key)`. DOI
canonicalisation is deliberately described narrowly because the implementation
does not currently handle every DOI representation; see GAP-005.

### FR-016 — Existing candidates

When a key already exists, the pipeline counts the candidate as touched and
skips evidence construction and persistence. It does not:

- create another candidate;
- change `PENDING`, `CONFIRMED`, or `DISMISSED` status;
- update title, DOI, URL, authors, abstract, source, or raw metadata hash;
- merge evidence from the new source or query;
- record a deterministic rediscovery relation to the current run.

There is no `SNOOZED` candidate state in the current domain.

### FR-017 — Query audit record

Every attempted logical query is persisted with:

- run ID, source, query type, and planned `queryText`;
- send timestamp and returned record count;
- `COMPLETED` or `FAILED` status;
- a truncated error message when failed.

`queryText` is encrypted at rest and decrypted for authorised API responses.
Error messages remain plaintext in the current database mapping. The record
does not retain request parameters, response identifiers, response hashes, or
the relationship between a query and the candidates it touched.

### FR-018 — Run outcome and counters

At completion, the run records:

| Field | Meaning |
| --- | --- |
| `sourceCount` | Distinct sources for which at least one query was attempted |
| `candidateCount` | Distinct existing or new candidates touched in the run |
| `newCandidateCount` | Distinct candidates created in the run |

The run is `FAILED` only when every attempted query raised an exception. It is
`COMPLETED` when at least one query completed, even if all completed queries
returned no results and other queries failed. Partial errors are concatenated
and truncated to 2,000 characters.

Each query error stores `ExceptionType: message`, truncated to 500 characters.
The pipeline catches all `Exception` subclasses at query scope and continues.
There is no focused automated coverage of these aggregate status semantics;
see GAP-006.

## 9. Enforced invariants

| ID | Invariant | Enforcement |
| --- | --- | --- |
| INV-001 | Planning uses only researcher, inventory number, and object name from the snapshot | Pure planning functions |
| INV-002 | One query attempt consumes one unit of the shared run ceiling | Application-service counter |
| INV-003 | A new candidate is not created without actionable evidence | `is_actionable` gate |
| INV-004 | The deterministic pipeline never confirms or dismisses a candidate | Application workflow boundary |
| INV-005 | Candidate identity is unique per watch and deduplication key | Database unique constraint |
| INV-006 | Persisted logical query text is encrypted at rest | Repository field encryption |
| INV-007 | Europe PMC full-text bodies are not persisted on deterministic candidates | Adapter record and candidate mapping |
| INV-008 | Source throttle reservations are global across application processes using the same database | PostgreSQL throttle table |

The implementation does **not** guarantee identical external results between
runs, complete transport-level request replay, candidate metadata refresh on
rediscovery, or one open transaction never spanning a source call.

## 10. Acceptance evidence

| ID | Behaviour | Automated evidence |
| --- | --- | --- |
| AC-001 | Exact planning uses researcher, inventory, and object | `test/scientific_return/test_scientific_return.py::test_planner_uses_only_author_inventory_and_object` |
| AC-002 | Adaptive planning replaces a multi-token object with its first term | `test/scientific_return/test_scientific_return.py::test_adaptive_planner_broadens_only_binomial_object_to_genus` |
| AC-003 | Adaptive trajectories follow an exact pass with no touched candidate | `test/scientific_return/test_scientific_return.py::test_pipeline_uses_adaptive_query_after_exact_queries_fail` |
| AC-004 | Museum-prefix and repeated collection segments are normalised | `test/scientific_return/test_scientific_return.py::test_evidence_normalizes_museum_prefix_and_repeated_inventory_segments` |
| AC-005 | A record returned by multiple trajectories creates one candidate | `test/scientific_return/test_scientific_return.py::test_pipeline_deduplicates_same_record_across_query_trajectories` |
| AC-006 | Query limit is enforced and shared across sources | `test/scientific_return/test_scientific_return.py::test_pipeline_caps_external_queries_per_run`, `test/scientific_return/test_scientific_return.py::test_pipeline_query_cap_is_shared_across_sources` |
| AC-007 | A dismissed candidate remains dismissed when rediscovered | `test/scientific_return/test_scientific_return.py::test_dismissed_candidate_is_remembered_on_later_run` |
| AC-008 | Crossref retries `429` and does not retry a permanent client error | `test/scientific_return/test_crossref.py` |
| AC-009 | OpenAlex maps records, routes structured authors, requires a key, and redacts it from logs | `test/scientific_return/test_openalex.py` |
| AC-010 | Europe PMC enriches from and caches open-access full text | `test/scientific_return/test_europe_pmc.py` |
| AC-011 | Excessive retry waits and total call duration are bounded | `test/scientific_return/test_source_wait_budget.py` |
| AC-012 | PostgreSQL coordinates source throttle reservations | `test/scientific_return/test_source_rate_limiter.py` |
| AC-013 | Logical query text round-trips through the encrypted repository mapping | `test/scientific_return/test_investigation_repository.py::test_queries_are_listed_across_every_run_of_a_watch` |

## 11. Known implementation gaps

### GAP-001 — Pipeline transactions span external calls

**Severity: high.** The run and query repository operations flush through the
request or scheduled-job session, and the caller commits only after the whole
deterministic use case returns. The database transaction therefore remains open
while bibliographic sources answer. This contradicts the previous version of
this spec and increases connection use, lock duration, rollback scope, and the
cost of slow sources.

**Required change:** persist a claimed run in a short transaction, execute each
external call outside an open unit of work, and commit query/candidate progress
through explicit idempotent steps. Coordinate this with the shared run lock
proposed by SPEC-002.

### GAP-002 — Audit records do not reproduce transport requests

**Severity: high.** `queryText` records the logical planned string. OpenAlex
removes the author from `search` and sends it separately in `filter`, but those
actual parameters are not stored. No adapter persists endpoint, effective
parameters, response IDs, or a response hash. The current audit can explain the
strategy but cannot faithfully replay or prove the wire request.

**Required change:** persist a sanitised canonical request envelope and response
manifest per query, excluding secrets, alongside the logical strategy text.

### GAP-003 — Adaptive “genus” expansion is not taxonomically validated

**Severity: high.** The planner and evidence builder use the first token of any
multi-token object name. A common name such as “Blue whale” is treated as if
“Blue” were a genus, which can broaden search and create weak evidence with
high false-positive potential.

**Required change:** model scientific name and taxonomic rank explicitly, or
apply a validated binomial parser. Rename the behaviour and evidence messages
until genus status can be proven.

### GAP-004 — Matching boundaries and source labels are imprecise

**Severity: high.** Object and inventory checks use substring containment
without token or identifier boundaries. The value `MB11` can match a longer
identifier, and a genus token can match inside another word after
normalisation. `_metadata_text` includes author names, yet matching evidence is
labelled `title_or_abstract`, so source provenance may be inaccurate.

**Required change:** separate searchable fields, use boundary-aware matching,
record the exact matched field, and add adversarial false-positive tests.

### GAP-005 — DOI and metadata deduplication are brittle

**Severity: high.** DOI normalisation removes only one exact HTTPS resolver
prefix. `doi:`, HTTP resolver URLs, whitespace, escaping, trailing punctuation,
and equivalent Unicode forms may produce different keys. Records without DOI
depend on source-specific date strings, so `2025`, `2025-01`, and `2025-01-01`
do not deduplicate. Concurrent read-then-insert races can still hit the unique
constraint and abort a run.

**Required change:** introduce a canonical DOI value object, normalise partial
dates, define conservative metadata matching, and handle uniqueness conflicts
as rediscovery rather than run failure.

### GAP-006 — Failure semantics lack focused tests and safe error shaping

**Severity: medium.** No focused deterministic-pipeline test was found for
all-query failure, partial failure, a zero-query run, or error truncation. Broad
exception capture stores exception text and returns it to staff, which may leak
adapter or infrastructure details.

**Required change:** test each status boundary and map internal failures to
typed, sanitised operational errors while retaining protected diagnostic detail
outside the public response.

### GAP-007 — Numeric pipeline settings accept invalid values

**Severity: medium.** Configuration validates source wait budgets but not
positive `SCIENTIFIC_RETURN_RESULT_LIMIT` or
`SCIENTIFIC_RETURN_MAX_QUERIES_PER_RUN`. A zero or negative query ceiling can
produce a `COMPLETED` run with no attempt; an invalid result limit is delegated
to an external source.

**Required change:** validate both as positive bounded integers at startup and
test configuration failure.

### GAP-008 — Query terms are quoted but not escaped

**Severity: medium.** Snapshot values are wrapped in double quotes without
escaping embedded quotes or source query syntax. Although snapshot fields are
non-blank, they are not constrained against these characters.

**Required change:** introduce a source-neutral query-term value object and let
each adapter encode it for its own query language.

### GAP-009 — Rediscovery preserves stale metadata and evidence

**Severity: medium.** An existing key short-circuits before evidence building.
Later, richer records cannot correct missing metadata, add a full-text inventory
match, or identify another consulted object. The run also lacks an explicit
deterministic candidate-link table, so `candidateCount` is retained only as an
aggregate number.

**Required change:** define merge rules for immutable identity versus mutable
bibliographic metadata, append evidence idempotently with provenance, and store
run-to-candidate rediscovery links.

### GAP-010 — Privacy and retention are not explicit

**Severity: medium.** Query text and the project snapshot are encrypted, but
candidate title, authors, abstract, URL, evidence values/explanations, and
source error messages are stored in plaintext. No retention period is defined
for failed queries, rejected records, or candidate metadata.

**Required change:** complete a field-level data classification, encrypt or
redact sensitive derived fields where justified, and define retention and
erasure rules.

### GAP-011 — Source ordering can starve later indexes

**Severity: low.** Exact and adaptive queries consume one global ceiling in a
fixed Crossref → OpenAlex → Europe PMC order. Larger snapshots can exhaust the
budget before the only configured full-text adapter is contacted.

**Required change:** define a deliberate allocation policy, such as per-source
minimums plus a shared reserve, and verify coverage under large snapshots.

## 12. Non-functional requirements

- **Determinism:** pure planning and matching rules must remain deterministic
  for fixed snapshot and record inputs.
- **Explainability:** every accepted candidate must expose typed evidence with a
  source-field label and readable explanation.
- **Confidentiality:** logical queries containing researcher and inventory data
  must remain encrypted at rest and secrets must not enter logs or audit fields.
- **External-service civility:** honour configured minimum intervals and bounded
  `Retry-After` values across all application replicas.
- **Bounded work:** enforce both query-count and per-call duration ceilings.
- **Human authority:** discovery may propose candidates but never make the
  publication decision.

## 13. Traceability

| Concern | Implementation |
| --- | --- |
| Query planning, matching, evidence, actionability, and deduplication | `vitarerum-api/app/scientific_return/application/analysis.py` |
| Run orchestration and counters | `vitarerum-api/app/scientific_return/application/use_cases.py` |
| Bibliographic source contract | `vitarerum-api/app/scientific_return/application/ports.py` |
| Crossref translation | `vitarerum-api/app/scientific_return/infrastructure/crossref.py` |
| OpenAlex translation and key redaction | `vitarerum-api/app/scientific_return/infrastructure/openalex.py` |
| Europe PMC and transient full text | `vitarerum-api/app/scientific_return/infrastructure/europe_pmc.py` |
| Shared wait and retry budget | `vitarerum-api/app/scientific_return/infrastructure/source_wait.py` |
| Deployment-wide throttle | `vitarerum-api/app/scientific_return/infrastructure/source_rate_limiter.py` |
| SQL persistence and field encryption | `vitarerum-api/app/scientific_return/infrastructure/{models,repositories}.py` |
| Source wiring and order | `vitarerum-api/app/scientific_return/presentation/dependencies.py` |
| HTTP contract | `vitarerum-api/app/scientific_return/presentation/{routes,schemas}.py` |
| Configuration defaults and validation | `vitarerum-api/app/config.py` |
| Automated evidence | `vitarerum-api/test/scientific_return/` |

## 14. Open product decisions

1. Should publication date be part of the evidence model, for example to reject
   records published before the collection-use project?
2. Which bibliographic fields may be refreshed on rediscovery, and which must
   remain exactly as first observed?
3. Should a source-specific allocation reserve guarantee that at least one
   full-text query is attempted for every consulted object?
4. Is storing a short, licensed evidence excerpt preferable to retaining only
   a `full_text` source label that cannot later be independently inspected?
5. How long should failed-query diagnostics and unconfirmed candidates be
   retained?
