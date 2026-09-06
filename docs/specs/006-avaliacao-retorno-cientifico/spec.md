# SPEC-006 — Empirical evaluation of scientific-return discovery

| Field | Value |
| --- | --- |
| Identifier | SPEC-006 |
| Status | Implemented |
| Bounded context | `app/scientific_return` |
| Delivery surface | Operator CLI and JSON reports; no HTTP endpoint or Angular UI |
| Derived from | Evaluation fixture, deterministic evaluator, agentic evaluator, CLI composition, published baselines, and automated tests |
| Related specs | [SPEC-003](../003-pipeline-deterministico-bibliografico/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-024](../024-investigacao-agentica-autonoma/spec.md) |

## 1. Problem

Scientific-return discovery cannot safely gain autonomy on anecdotal evidence.
The team needs to distinguish whether a source returned a known publication,
whether deterministic evidence made it reviewable, and whether the constrained
agentic increment can close a measured baseline gap.

The instrument can itself mislead. Live indexes change, fixture declarations
become stale, a retrieved record is not necessarily actionable, and a
known-DOI proxy is not human-reviewed precision. Evaluation therefore needs
explicit inputs, strict fixture validation, per-case evidence, and honest
limitations.

## 2. Goal

Run two empirical evaluations over a versioned MUHNAC fixture:

- a deterministic baseline reusing production query planning, evidence,
  actionability, deduplication, and live bibliographic adapters; and
- a bounded agentic harness measuring planning, policy evaluation, one
  inventory-variant search action, and reflection without creating production
  watches, candidates, decisions, or publication records.

The output is an operator-generated JSON report. This is a repeatable
procedure, not a perfectly reproducible experiment: external indexes, model
output, time, prompts, and server configuration may change between runs.

## 3. Actors and delivery boundary

| Actor | Capability |
| --- | --- |
| Operator or developer | Run either evaluator and choose CLI sources/output |
| Fixture maintainer | Curate known cases, declarations, cited forms, and unmapped papers |
| Staff reviewer | Edit a deterministic review queue and finalise its metrics |
| Bibliographic source | Return current external search results |
| Investigation reasoner | Produce a plan and reflection for the agentic harness |

There is no authentication check because evaluation has no HTTP endpoint.
Access follows the operator's shell, database, network, model, and filesystem
permissions. No Angular component presents the reports; review is an offline
JSON-editing process.

## 4. Architecture and domain position

Evaluation is application-layer instrumentation, not a production aggregate.
Its immutable data classes describe cases and report projections; they have no
repository and are not persisted through the scientific-return domain model.

| Role | Element | Responsibility |
| --- | --- | --- |
| Fixture value | `EvaluationFixture` | Version, cases, and unmapped publications |
| Case value | `EvaluationCase` | Known publication and one-object snapshot |
| Application service | `evaluate_cases` | Execute and aggregate the deterministic baseline |
| Application service | `evaluate_agentic_cases` | Exercise the bounded agentic harness |
| Parser | `parse_human_reviews` | Validate completed offline reviews |
| Projector | `finalize_human_review_report` | Add review metrics without new searches |
| Production policy | `AgentActionPolicy` | Authorise or reject a proposed action |
| Production tool | `InventoryVariantSearchTool` | Search, deduplicate, build evidence, and classify actionability |
| Composition root | `presentation.commands` | Select live dependencies, configuration, and output |

The deterministic evaluator directly reuses production analysis functions. The
agentic evaluator reuses the policy and inventory-variant tool, but not the
complete assisted orchestrator described by SPEC-001 or the autonomous
orchestrator described by SPEC-024.

## 5. Ubiquitous language

- **Case**: one museum object and one expected publication identified by DOI.
- **Fixture**: versioned cases plus publications not yet expressible as cases.
- **Retrieved**: the expected DOI appeared in a source result.
- **Actionable**: deterministic evidence passes the production review gate.
- **Baseline status**: `RESOLVED`, `GAP`, or `UNVERIFIED`.
- **Resolved**: the expected DOI became actionable, not merely retrieved.
- **Expected gap**: `NONE`, `UNKNOWN`, `INVENTORY_FORMAT`,
  `INSTITUTIONAL_ACRONYM`, `NO_INVENTORY_IN_TEXT`, or `NOT_INDEXED`.
- **Agentic objective**: `DISCOVER_CANDIDATE`, `ENRICH_CANDIDATE`, or `NONE`,
  derived by deterministic measurement.
- **Known-case precision proxy**: expected-DOI actionable matches divided by
  all actionable candidates; it is not adjudicated precision.
- **Review queue**: actionable candidates exported for offline classification.
- **Gap closed**: a declared `GAP` whose expected DOI becomes actionable in the
  agentic harness.
- **Indexability ceiling**: fixture-derived reachability, separate from what
  one run actually retrieved.

## 6. Versioned fixture

The shipped `scientific-return-eval-fixture-v3` currently contains 12 cases and
6 unmapped publications. Five original resolved cases are protected by tests.

### FR-001 — Required case data

Every case requires its ID, author, museum inventory number, object name,
expected title and DOI, notes, baseline status, and expected gap. It may also
carry a measured inventory-evidence boolean and literal cited inventory forms.

The case builds an in-memory `ProjectSnapshotPayload` containing one consulted
object, a synthetic project ID/reference, and the author as researcher.

### FR-002 — Fixture validation

Loading rejects a non-object root, missing or empty case list, duplicate case
IDs, missing required strings, unsupported enums, non-boolean inventory
evidence, an `UNVERIFIED` case claiming measured inventory evidence, a fully
resolved case with inventory evidence that also declares a gap, and a `GAP`
whose expected gap is `NONE`.

A resolved case without inventory evidence may declare an enrichment gap.
Inventory-format and institutional-acronym cases are tested to ensure a cited
form can be generated and attempted within the configured query budget.

The loader silently skips non-object items within `cases` and `unmappedPapers`
instead of rejecting them; see GAP-006.

### FR-003 — Unmapped publications

`unmappedPapers` retains a reference, expected DOI, cited forms, and reason when
the museum-side number or another required fact is unavailable. These entries
are visible in the fixture but excluded from both evaluators and report metrics.

## 7. Deterministic baseline

### FR-004 — Command

```bash
uv run python -m app.jobs.scientific_return evaluate-phase0 \
  --sources crossref,europe_pmc \
  --result-limit 20 \
  --output scientific-return-baseline.json
```

`--sources` accepts comma-separated `crossref`, `openalex`, and `europe_pmc`, or
`all`. Empty selection and `all` expand to all three. Explicit OpenAlex without
`OPENALEX_API_KEY` fails; `all` warns and skips it. Unknown names fail.

The result limit is coerced to at least one. Without `--output`, formatted JSON
goes to standard output. CLI help still incorrectly calls this a “five-case”
baseline; see GAP-007.

### FR-005 — Source execution

For each case and source, the evaluator builds normal deterministic queries,
calls the live adapter, records result count and expected-DOI rank, builds
production evidence, retains actionable candidates, adds adaptive queries when
the initial set produced none, and deduplicates by the production key.

Source exceptions are truncated to 500 characters, counted, and do not stop
later work. Adapters use the operational PostgreSQL-backed rate limiter and
total source timeout. Thus evaluation does not write production aggregates but
can write rate-limit coordination state; “no database writes” is not literal.

### FR-006 — Retrieval and resolution

| Measure | Condition |
| --- | --- |
| `retrieved` / top-level `recall` | Expected DOI appeared in results |
| `observedBaselineStatus=RESOLVED` | Expected DOI became actionable |

Only the second means the publication reaches a human. A retrieved but
non-actionable DOI remains a `GAP`. The top-level `recall` preserves the older
retrieval metric and must not be read as reviewable-candidate recall.

DOI matching case-folds and removes only an exact `https://doi.org/` prefix; it
does not otherwise canonicalise DOI syntax.

### FR-007 — Derived objective and declaration drift

| Observation | Derived objective |
| --- | --- |
| Expected DOI is not actionable | `DISCOVER_CANDIDATE` |
| Expected DOI is actionable without primary inventory evidence | `ENRICH_CANDIDATE` |
| Expected DOI is actionable with primary inventory evidence | `NONE` |

Observed status and inventory evidence are compared with fixture declarations.
`UNVERIFIED` declarations are listed separately and do not count as mismatches.
Metrics publish declared/observed counts, mismatch and unverified IDs,
discovery/enrichment targets, and reachable inventory-format gap IDs.

### FR-008 — Deterministic report

The report includes generation time, fixture version, global and per-source
retrieval/actionability metrics, declaration metrics, review metrics, a
deduplicated actionable review queue, and per-case trajectories, source
results, candidates, evidence, observed status, objective, and drift result.

It does not capture every effective setting or an immutable external-response
snapshot; see GAP-002.

### FR-009 — Known-case proxy

`knownCasePrecisionProxy` divides expected-DOI actionable matches by all
actionable candidates. Other genuine returns not represented by the fixture are
counted as non-matches. This is a noise proxy, not precision or a sufficient
promotion gate.

## 8. Offline human review

### FR-010 — Review entry

Each candidate has `review_id = case ID | deduplication key`. Staff may add
`CONFIRMED`, `DISMISSED`, or `UNCERTAIN`, plus justification, reviewer, and an
ISO 8601 timestamp with timezone. Blank decisions remain pending. Completed
reviews require all fields, and duplicate completed IDs are rejected.

The queue exposes `known_case_match`, so reviewers can see the expected-answer
signal before classifying; see GAP-004.

### FR-011 — Finalisation without searches

```bash
uv run python -m app.jobs.scientific_return evaluate-phase0 \
  --reviews scientific-return-baseline.json \
  --output scientific-return-reviewed.json
```

This reads the existing JSON, validates completed reviews, preserves the report,
replaces `humanReviewMetrics`, and adds `reviewFinalizedAt`. It makes no source
calls. `human_precision` is `confirmed / (confirmed + dismissed)`, excluding
uncertain decisions. It is a confirmation share, not independently verified
statistical precision.

Finalisation does not prove that reviewed IDs belong to the original queue;
see GAP-005.

## 9. Agentic harness

### FR-012 — Command and modes

```bash
uv run python -m app.jobs.scientific_return evaluate-agentic \
  --mode SUPERVISED --sources europe_pmc \
  --output scientific-return-agentic.json
```

| Documented mode | Plan | Policy | Search tool |
| --- | --- | --- | --- |
| `SHADOW` | Yes | No | No |
| `POLICY_ONLY` | Yes | Yes, rejecting execution because of mode | No |
| `SUPERVISED` | Yes | Yes | Only when authorised |

Parsing also accepts enum values `DISABLED` and `SCHEDULED`, contrary to help.
The adapters from `--sources` are separate from the server-side source allowlist
used by policy; the report's `allowedSources` names only the latter.

### FR-013 — Observation

Each case becomes a `DISCOVER_CANDIDATE` observation with its synthetic
one-object snapshot, deterministic queries marked as already tried,
server-configured budget, and three advertised actions. Policy narrows execution
to `SEARCH_INVENTORY_VARIANTS`.

Although baseline evaluation derives enrichment targets, the harness always
uses discovery and does not measure `ENRICH_CANDIDATE`; see GAP-009.

### FR-014 — Plan, policy, and execution

The reasoner produces a plan. Policy-capable modes apply the production action
policy. Tool-capable modes run the production inventory-variant tool against
selected live sources, deduplicate results, and apply production evidence and
actionability.

Plan failures are captured per case. Tool attempts retain query, source, result
count, error, duplicates, actionable non-target counts, and planned action.

### FR-015 — Reflection

Reflection is requested whenever a plan exists, including non-executing modes.
Invalid or unavailable reflection is counted, not raised. The context always
contains an empty evidence delta and no executed queries or sources, even after
execution. Thus validity measures response shape/service availability, not
reflection over search results; see GAP-010.

### FR-016 — Gap closure and reachability

A declared `GAP` closes only when the expected DOI becomes actionable.
Retrieval alone does not close it. The report separately exposes discovery
recall, inventory-evidence recall, reviewable-candidate recall, indexability
ceiling, and per-source `NOT_REACHED`, `DISCOVERED`, or `EVIDENCE_REACHED`.

The ceiling comes from fixture declarations, never from one run's failure.

### FR-017 — Agentic report provenance

The report records generation time, fixture and agent-contract versions, mode,
server-side allowed sources, part of the budget, validity rates, policy
results, gaps, recalls, duplicates/noise, external attempts, reachability, and
per-case results.

It omits model/prompt identity, actual selected adapters, timeouts,
`maxIterations`, and `maxActions`; see GAP-002.

## 10. Side-effect boundary

Neither evaluator creates production watches, runs, candidates, evidence rows,
decisions, publication logs, agentic investigations, or trajectories.

The deterministic command still makes network calls and writes rate-limit
coordination. Agentic evaluation additionally reads published prompts from
PostgreSQL and calls the configured model. Output-file replacement is an
explicit CLI side effect.

## 11. Enforced invariants

| ID | Invariant | Enforcement |
| --- | --- | --- |
| INV-001 | No production scientific-return aggregate is persisted | In-memory evaluators |
| INV-002 | Deterministic evidence/actionability uses production functions | Direct reuse |
| INV-003 | Agentic search uses production policy and inventory tool | Harness composition |
| INV-004 | `UNVERIFIED` cannot claim inventory measurement | Fixture parser |
| INV-005 | A declared `GAP` requires a non-`NONE` cause | Fixture parser |
| INV-006 | Gap closure requires expected-DOI actionability | Agentic projection |
| INV-007 | Declaration drift is reported per case | Baseline metrics |
| INV-008 | Completed review requires identity, rationale, and zoned time | Review parser |

These do not guarantee stable live results, blinded review, complete
provenance, full production parity, or valid review membership.

## 12. Acceptance evidence

| ID | Behaviour | Automated evidence |
| --- | --- | --- |
| AC-001 | Fixture loads and preserves original cases | `test/scientific_return/test_evaluation_fixture.py::test_the_shipped_fixture_loads`, `test/scientific_return/test_evaluation_fixture.py::test_the_original_cases_survive_the_extraction` |
| AC-002 | Fixture has discovery and enrichment targets | `test/scientific_return/test_evaluation_fixture.py::test_the_fixture_separates_discovery_targets_from_enrichment_targets`, `test/scientific_return/test_evaluation_fixture.py::test_the_fixture_adds_cases_the_baseline_has_not_resolved` |
| AC-003 | Declared gaps are generator- and budget-reachable | `test/scientific_return/test_evaluation_fixture.py::test_declared_inventory_gaps_are_reachable_by_the_variant_generator`, `test/scientific_return/test_evaluation_fixture.py::test_declared_gaps_are_reachable_within_the_configured_query_budget` |
| AC-004 | Cited form alone does not close a gap | `test/scientific_return/test_evaluation_fixture.py::test_the_recorded_form_alone_does_not_close_a_declared_gap` |
| AC-005 | Unmapped publications remain documented | `test/scientific_return/test_evaluation_fixture.py::test_unmapped_papers_are_documented` |
| AC-006 | Invalid fixture declarations and duplicate IDs fail | `test/scientific_return/test_evaluation_fixture.py::test_a_fully_resolved_case_may_not_declare_a_gap`, `test/scientific_return/test_evaluation_fixture.py::test_a_gap_case_must_state_its_cause`, `test/scientific_return/test_evaluation_fixture.py::test_an_unverified_case_may_not_claim_a_measurement`, `test/scientific_return/test_evaluation_fixture.py::test_duplicated_case_ids_are_rejected` |
| AC-007 | Baseline exposes source metrics and review queue | `test/scientific_return/test_scientific_return.py::test_evaluation_reports_per_source_metrics_and_review_queue` |
| AC-008 | Review timestamps require a timezone | `test/scientific_return/test_scientific_return.py::test_phase_zero_review_requires_a_timezone` |
| AC-009 | Three documented modes have distinct effects | `test/scientific_return/test_agentic_evaluation.py::test_shadow_mode_asks_the_model_and_executes_nothing`, `test/scientific_return/test_agentic_evaluation.py::test_policy_only_decides_but_still_executes_nothing`, `test/scientific_return/test_agentic_evaluation.py::test_supervised_mode_executes_the_authorised_action` |
| AC-010 | Retrieval without actionability does not close a gap | `test/scientific_return/test_agentic_evaluation.py::test_a_gap_counts_as_closed_only_when_the_case_becomes_actionable`, `test/scientific_return/test_agentic_evaluation.py::test_a_retrieved_but_unmatched_record_does_not_close_the_gap` |
| AC-011 | Report retains provenance subset, plan, duplicates, and noise | `test/scientific_return/test_agentic_evaluation.py::test_the_report_records_what_it_was_run_with`, `test/scientific_return/test_agentic_evaluation.py::test_the_plan_action_is_reported_for_auditing`, `test/scientific_return/test_agentic_evaluation.py::test_report_aggregates_measured_duplicates_and_false_positives` |
| AC-012 | Invalid plans and reflections are non-fatal | `test/scientific_return/test_agentic_evaluation.py::test_an_invalid_plan_is_counted_not_fatal`, `test/scientific_return/test_agentic_evaluation.py::test_an_unavailable_reflection_is_counted_not_fatal` |
| AC-013 | Agentic queries do not repeat baseline queries | `test/scientific_return/test_agentic_evaluation.py::test_the_cycle_starts_from_what_the_pipeline_already_tried` |
| AC-014 | Ceiling does not hide agent recall failure | `test/scientific_return/test_agentic_evaluation.py::test_the_ceiling_does_not_absorb_the_agents_own_recall_failure` |

## 13. Known implementation gaps

### GAP-001 — Live evaluation is not strictly reproducible

**Severity: high.** Indexes, full text, rankings, model output, prompts, time,
and configuration change. The same fixture and command may produce a different
report.

**Required change:** distinguish repeatability from reproducibility and provide
a sanitised source-response snapshot plus deterministic replay mode if strict
reproduction is required.

### GAP-002 — Execution provenance is incomplete

**Severity: high.** Baseline omits explicit selected sources, result limit,
planner/version identity, adapter versions, and response hashes. Agentic output
also omits model/prompt identity, actual adapters, timeouts, and two budget
dimensions.

**Required change:** add a shared, versioned, secret-free execution manifest
with code, fixture, prompt, input, and response hashes.

### GAP-003 — Baseline `recall` means retrieval, not reviewability

**Severity: high.** A record rejected by actionability increments headline
recall although it remains a baseline gap.

**Required change:** rename it `retrievalRecall`, add
`reviewableCandidateRecall`, and version consumers and published reports.

### GAP-004 — Human review is not blinded

**Severity: high.** `known_case_match` reveals ground truth before review,
potentially biasing the resulting metric.

**Required change:** export a blinded package and join decisions to ground truth
only during controlled finalisation.

### GAP-005 — Review membership is not validated

**Severity: high.** Injected IDs can make reviewed counts exceed queue length,
make pending counts negative, and distort metrics.

**Required change:** validate exact membership and duplicate queue IDs, and bind
reviews to a hash of the original report.

### GAP-006 — Malformed fixture array items are silently skipped

**Severity: medium.** Non-object cases and unmapped papers are filtered out.

**Required change:** reject each malformed item with its array index and add
negative tests.

### GAP-007 — CLI contract is stale and weakly constrained

**Severity: medium.** Phase-zero help says five cases; agentic help lists three
modes while parsing also accepts `DISABLED` and `SCHEDULED`.

**Required change:** use fixture-neutral help, argparse choices, and CLI tests.

### GAP-008 — Review has no managed UI or audit store

**Severity: medium.** JSON editing uses free-text identity with no assignment,
authentication, immutable audit history, concurrency control, or accessible UI.

**Required change:** either retain this as a developer instrument or create a
permissioned, blinded Angular evaluation workflow separate from production
candidate decisions.

### GAP-009 — Agentic evaluation ignores enrichment objectives

**Severity: high.** Every case runs as discovery, including derived enrichment
targets.

**Required change:** run measured objectives with an existing candidate for
enrichment and report the cohorts separately.

### GAP-010 — Reflection is disconnected from tool results

**Severity: high.** It always receives empty evidence, query, and source data.

**Required change:** build the production-equivalent post-execution reflection
context or rename the validity metric to reflect its narrower meaning.

### GAP-011 — The harness is not the full production cycle

**Severity: medium.** It omits production iteration state, persistence,
presentation, reader grounding, stop semantics, idempotency, circuit breaker,
and recovery paths.

**Required change:** label it as component evaluation and add an isolated
end-to-end evaluation around the production orchestrator.

### GAP-012 — Metrics omit latency and cost

**Severity: medium.** Reports do not measure source/model latency, token usage,
monetary cost, or curator time per confirmed candidate.

**Required change:** capture per-stage duration and usage/cost with explicit
denominators and confidence intervals.

## 14. Non-functional requirements

- **Human authority:** evaluation cannot create a production decision.
- **Methodological honesty:** retrieval, actionability, proxy precision, and
  confirmation share remain separately named.
- **Bounded execution:** calls obey configured rate limits, timeouts, result
  limits, and agent budgets.
- **Failure isolation:** one query, plan, tool, or reflection failure does not
  invalidate unrelated cases.
- **Confidentiality:** reports may contain researcher and reviewer identities,
  metadata, and free-text rationale and require appropriate storage.
- **No automatic scheduling:** evaluation is an explicit operator action.

## 15. Traceability

| Concern | Implementation |
| --- | --- |
| Fixture, baseline, report, and review finalisation | `vitarerum-api/app/scientific_return/application/evaluation.py` |
| Shipped fixture | `vitarerum-api/app/scientific_return/application/fixtures/evaluation_cases.json` |
| Agentic harness and report | `vitarerum-api/app/scientific_return/application/agentic_evaluation.py` |
| Shared evidence/query rules | `vitarerum-api/app/scientific_return/application/analysis.py` |
| Shared policy and tool | `vitarerum-api/app/scientific_return/domain/agent_policies.py`, `application/agent_tools.py` |
| CLI composition | `vitarerum-api/app/scientific_return/presentation/commands.py` |
| Job entry point | `vitarerum-api/app/jobs/scientific_return.py` |
| Automated evidence | `vitarerum-api/test/scientific_return/test_evaluation_fixture.py`, `test/scientific_return/test_agentic_evaluation.py`, `test/scientific_return/test_scientific_return.py` |
| Current baseline | [`docs/evaluation/scientific-return-fixture-v3-baseline.md`](../../evaluation/scientific-return-fixture-v3-baseline.md) and companion JSON |
| Superseded baseline | [`docs/evaluation/scientific-return-phase0-crossref-baseline.md`](../../evaluation/scientific-return-phase0-crossref-baseline.md) |

## 16. Open product decisions

1. Is evaluation developer-only, or does staff need a permissioned and blinded
   workflow?
2. Which metric and confidence threshold permit a mode promotion, and who owns
   that decision?
3. Are dated live reruns sufficient, or must published baselines be replayable
   from captured responses?
4. How should negative cases be sampled so precision is not inferred only from
   one expected DOI per positive case?
5. Should discovery, enrichment, and full-agentic reader evaluation remain
   separate cohorts and gates?
6. What latency, token, monetary, and curator-time budgets define acceptable
   cost per confirmed scientific return?
