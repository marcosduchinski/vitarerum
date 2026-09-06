# SPEC-005 — Candidate reader analysis and curatorial feedback

| Field | Value |
| --- | --- |
| Identifier | SPEC-005 |
| Status | Implemented |
| Bounded context | `app/scientific_return` |
| Derived from | Full-agentic reader orchestration, grounding rules, analysis domain model, repositories, routes, prompt migrations, Angular reader modal, and scientific-return tests |
| Related specs | [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-016](../016-prompts-versionados/spec.md), [SPEC-024](../024-investigacao-agentica-autonoma/spec.md), [SPEC-025](../025-base-de-conhecimento-curatorial/spec.md) |

## 1. Problem

Deterministic matching can explain which literal signals it found, but it does
not interpret ambiguous bibliographic context: an author homonym, a catalogue
citation rather than use of a specimen, a similar object from another
collection, or a contradiction elsewhere in the article. Reading that context
costs specialist time.

A language model can assist with this reading, but it cannot acquire curatorial
authority. External publication text is untrusted, model output can be wrong,
and confidence is not evidence. The application therefore needs an auditable,
advisory reader record that remains separate from the candidate decision.

## 2. Goal

Preserve the grounded assessment produced by the full-agentic publication
reader, expose its provenance to authorised reviewers, and collect one staff
utility rating per analysis. None of these operations may confirm, dismiss, or
otherwise change the candidate's curatorial status.

The former standalone shadow-analysis capability was removed by migration
`0075_remove_sr_shadow`. The current analysis is generated only inside the
autonomous investigation described by SPEC-024; this spec covers its retained
reader record and feedback workflow.

## 3. Actors and authorisation

| Actor | Current capability |
| --- | --- |
| `CURATORIAL` | Read reader-analysis history and submit feedback |
| `COLLECTIONS_MANAGEMENT` | Same capability as `CURATORIAL` |
| `DIRECTION` | Same capability as `CURATORIAL` |
| Other staff, including `SYS_ADMIN` | No access through these two endpoints |
| Full-agentic worker | Invoke the reader, ground its claims, and persist completed relevant analyses |
| Language model | Return a constrained semantic assessment; no tools or decision capability |

Both public operations require one of the three review groups. They currently
resolve candidates and analyses by global identifiers without institution
scoping; see GAP-001.

## 4. Domain and architecture

| DDD role | Element | Responsibility |
| --- | --- | --- |
| Entity | `CandidateAgentAnalysis` | Retains reader provenance, grounded result, lifecycle fields, and staff feedback |
| Value object | `CandidateAnalysisResult` | Carries the structured advisory result |
| Domain operation | `record_feedback` | Enforces completed-only, sequential one-time feedback |
| Application service | `ListCandidateAgentAnalyses` | Authorises and filters reader-origin records |
| Application service | `RecordAgentAnalysisFeedback` | Authorises and records a utility rating |
| Domain service | `ground_article_assessment` | Checks reader claims against delivered publication fields |
| Port | `ScientificReturnReasoner` | Abstracts model generation |
| Adapter | `PromptedFullAgenticReasoner` | Builds the isolated reader prompt and validates JSON output |
| Adapter | `OllamaScientificReturnReasoner` | Applies model, timeout, generation, and client-lifecycle settings |
| Repository | `ScientificReturnRepository` | Encrypts and persists analysis input/output and feedback fields |

The reader is a tool-free step inside the full-agentic application workflow.
Publication data reaches that isolated call, while tool execution and final
candidate decisions remain outside its capability boundary.

## 5. Ubiquitous language

- **Reader assessment**: the model's structured relevance interpretation of one
  bibliographic record.
- **Grounding**: deterministic verification that claimed passages and inventory
  forms occur literally in fields delivered to the reader.
- **Reader analysis**: the persisted, post-grounding representation linked to a
  candidate and full-agentic run.
- **Reader-origin record**: an analysis whose prompt-version ID starts with
  `pver-sr-full-reader`.
- **Advisory confidence**: `LOW`, `MEDIUM`, or `HIGH`; a model qualifier, not a
  curatorial decision threshold.
- **Feedback**: staff judgement of utility: `USEFUL`, `PARTIALLY_USEFUL`, or
  `NOT_USEFUL`.
- **Shadow analysis**: the retired standalone analysis flow deleted by migration
  0075; it is not part of the public API.

## 6. Lifecycle

The domain entity supports:

```text
RUNNING ───────> COMPLETED ───────> feedback recorded once
   │
   └───────────> FAILED
```

`complete` and `fail` are valid only from `RUNNING`. Feedback is valid only on
`COMPLETED` and is rejected after one rating has already been recorded.

The production full-agentic path does not currently persist this lifecycle in
stages. It invokes and grounds the reader first, constructs an in-memory
`RUNNING` entity, immediately completes it, and persists it once as
`COMPLETED`. Reader exceptions are written to investigation trajectory/LLM
events instead of creating a `FAILED` analysis row. See GAP-002.

## 7. Public API

| Method and route | Purpose | Access |
| --- | --- | --- |
| `GET /api/v1/scientific-return/candidates/{candidateId}/agent-analyses` | Return newest-first reader analyses for one candidate | Review groups |
| `POST /api/v1/scientific-return/agent-analyses/{analysisId}/feedback` | Record one utility rating and optional comment | Review groups |

There is no endpoint that requests a standalone candidate analysis. Analysis
generation is an internal consequence of the autonomous reader flow.

## 8. Functional requirements

### FR-001 — Reader invocation

During a full-agentic investigation, every previously unseen bibliographic
record that fits the remaining LLM budget may be assessed. The reader is called
with:

| Section | Current content and bound |
| --- | --- |
| Trusted museum context | Investigation observation, query, search intent, search strategy, and curatorial-memory examples |
| Untrusted title | First 1,000 characters |
| Untrusted authors | First 30 authors |
| Untrusted abstract | First 12,000 characters |
| Untrusted indexed text | First 16,000 characters |
| Source identity | Source and source record ID |

The input envelope explicitly separates `trustedMuseumContext` from
`untrustedPublicationData`. The reader has no injected source, publication-log,
candidate-decision, or arbitrary tool capability.

### FR-002 — Published prompt

The adapter resolves the active published prompt by key
`scientific_return_full_agentic_reader` under the scientific-return-analysis
purpose. The returned version ID, version label, content, and default
temperature are used for that call.

The hardened v2 prompt states that publication data is hostile third-party
data, instructs the model to ignore commands within it, forbids institutional
confirmation, treats curatorial memory as hypothesis, and requires literal
short excerpts and observed inventory forms.

The persisted analysis retains prompt version ID and label, but not a copy or
hash of prompt content or temperature; see GAP-005.

### FR-003 — Model-call bounds

The Ollama adapter:

- uses JSON output mode;
- applies the prompt's temperature through model options;
- defaults reasoning mode to disabled;
- limits generation with `SCIENTIFIC_RETURN_LLM_NUM_PREDICT`, default 4,096;
- applies a per-chunk timeout, default 180 seconds;
- applies a total call deadline, default 300 seconds;
- owns and closes one model client per call, including timeout paths;
- maps timeouts and common connection failures to typed reasoner exceptions.

Startup validation requires positive timeouts and generation limit, and ensures
the total deadline is not shorter than the chunk timeout.

### FR-004 — Strict reader response contract

The reader must return one JSON object containing only:

| Field | Validation |
| --- | --- |
| `relevant` | Required boolean |
| `confidence` | Required `LOW`, `MEDIUM`, or `HIGH` |
| `explanation` | Required non-blank string, at most 2,000 characters |
| `passages` | Optional array of strings; at most 20 accepted by the common parser, then first 5 retained and each truncated to 1,200 characters |
| `inventoryForms` | Optional array of strings, at most 20, each at most 1,000 characters |
| `contradictions` | Optional array of strings, at most 20, each at most 1,000 characters |

Markdown JSON fences are stripped. Invalid JSON, a non-object value, unknown
fields, wrong types, invalid enums, oversized content, or missing required
values rejects that assessment. Failure for one article does not abort later
articles in the investigation.

### FR-005 — Deterministic grounding

After a valid response, the application checks every proposed passage and
inventory form against the exact title, abstract, and indexed text delivered in
the bibliographic record.

Grounding normalises Unicode with NFKC, case-folds, and collapses whitespace;
it does not normalise punctuation or inventory separators. A claim is rejected
when it is blank, duplicates an earlier normalised claim of the same kind, or
does not occur as a substring in any delivered field. Rejection details are
written to the investigation trajectory; the persisted analysis input retains
only rejected passage and inventory-form counts.

Accepted inventory forms record `TITLE`, `ABSTRACT`, or `INDEXED_TEXT`, plus the
indexed-text source locator when applicable.

### FR-006 — Inventory-evidence status

| Status | Condition |
| --- | --- |
| `VERIFIED` | At least one claimed inventory form is grounded in a delivered field |
| `NOT_OBSERVED` | No form is grounded and an inspectable full-text body was delivered |
| `UNAVAILABLE` | No form is grounded and no inspectable body was delivered, or source capability is unknown |

A literal form in title or abstract is sufficient for `VERIFIED`. A source that
can sometimes provide full text but did not return it is `UNAVAILABLE`, not
`NOT_OBSERVED`.

These statuses describe the reader's submitted forms, not an exhaustive search
of every possible inventory spelling. `VERIFIED` proves literal occurrence of
a claimed form, not its equivalence to the watched object's registered number.
`NOT_OBSERVED` does not prove that the publication contains no such number.

Grounding does not change the model's `relevant` verdict. A record may therefore
be presented as relevant with no grounded passage or inventory form; see
GAP-003.

### FR-007 — When an analysis is persisted

The application calls candidate presentation only when the grounded assessment
still carries `relevant=true`. It creates or resolves the candidate, links it to
the investigation, and writes a reader analysis. Non-relevant assessments and
reader failures do not create `CandidateAgentAnalysis` rows.

More than one completed reader analysis may exist for the same candidate. There
is no uniqueness constraint on candidate, run, source record, input hash, or
prompt version.

### FR-008 — Persisted input payload

The encrypted `input_payload` contains post-grounding review provenance:

- query and source;
- grounded passages and inventory-form strings;
- curatorial knowledge-item IDs consulted by the investigation;
- discovery basis, search intent, and search strategy;
- inventory-evidence status;
- grounded inventory forms with field and locator;
- rejected passage and inventory-form counts.

It does not contain the complete prompt, trusted observation, publication title,
authors, abstract, indexed text, raw reader response, or detailed grounding
rejections. The API response does not expose `input_payload` itself.

### FR-009 — Persisted result

For the current reader path, the application derives
`CandidateAnalysisResult` as follows:

| Result field | Current value |
| --- | --- |
| `summary` | Grounded assessment explanation |
| `supportingEvidence` | Grounded passages |
| `contradictions` | Reader contradictions |
| `missingEvidence` | Always empty |
| `recommendedAction` | Always `PRESENT_FOR_REVIEW`, assigned by application code |
| `proposedQueries` | Always empty |
| `reasoningSummary` | Grounded assessment explanation |
| `confidence` | Reader confidence |

The result is encrypted at rest. `recommended_action` and `confidence` are also
copied to plaintext enum columns for querying. The recommendation is not chosen
from an action vocabulary by this reader and is never executed by this
functionality.

### FR-010 — Hashes and timing

Each record stores:

- `inputHash`: SHA-256 of `source|sourceRecordId|query`;
- `responseHash`: SHA-256 of the explanation string only;
- start/completion timestamps and non-negative elapsed milliseconds;
- model name, prompt version ID/label, run ID, candidate ID, and creator.

These hashes do not cover the complete persisted payloads or full model
exchange and are not verified during reads; see GAP-004.

### FR-011 — Failed reader calls

A reader exception consumes its reserved LLM-call budget. The investigation
records the typed LLM outcome plus an `ERROR` trajectory event containing
phase, source, record ID, and a truncated exception message, commits that state,
and continues to the next article.

It does not persist a `FAILED` `CandidateAgentAnalysis`. Consequently the
analysis-history endpoint cannot show failed reader attempts, even though the
entity and public schema support `FAILED` and `errorMessage`.

### FR-012 — Analysis history

The history use case first requires review-group access and verifies that the
candidate exists. It loads all candidate analyses newest first and returns only
records whose `promptVersionId` begins with `pver-sr-full-reader`.

The response includes identity, run, status, model, prompt provenance, hashes,
structured result, timing, error message, creator, and all feedback fields. It
does not include the encrypted input payload or grounding-rejection details.

An unknown candidate returns typed `404`. Existing candidates without a reader
record return an empty list.

### FR-013 — Feedback

The feedback request accepts one enum value and an optional comment of at most
2,000 characters. The use case:

1. requires review-group access;
2. loads the analysis by ID;
3. hides missing and non-reader-origin records behind the same typed `404`;
4. requires `COMPLETED`;
5. rejects a sequential second rating with `422`;
6. trims the comment and stores blank as `null`;
7. records feedback value, caller permission, and UTC timestamp;
8. returns the updated analysis.

The one-time rule has no concurrency protection; see GAP-006.

### FR-014 — Absence of candidate effects

Reader assessment, analysis persistence, analysis history, and feedback never:

- change `PENDING`, `CONFIRMED`, or `DISMISSED` status;
- create a `CandidateDecision`;
- create or edit a `PublicationLog` entry;
- execute `recommendedAction` or `proposedQueries`.

Only the separate human-decision command in SPEC-004 can record scientific
return.

### FR-015 — Angular presentation

The project scientific-return panel exposes **Reader analysis** for candidates
created or rediscovered by the autonomous flow. It loads analyses only when the
reviewer opens the dedicated modal.

The standalone `OnPush` modal displays:

- a prominent notice that only the human decision records scientific return;
- status, model, start time, and latency;
- summary, fixed recommended next step, confidence, supporting signals,
  evidence gaps, contradictions, reasoning, and proposed queries when present;
- one of three feedback buttons while no feedback exists;
- the stored feedback value after rating.

The UI does not display prompt version, hashes, creator, completion time,
feedback actor/time/comment, input provenance, or grounding rejection counts.
It also does not offer the optional feedback comment supported by the API; see
GAP-007.

### FR-016 — Shadow-analysis removal

Migration `0075_remove_sr_shadow` deletes analysis rows belonging to the retired
shadow prompt, clears and deletes that prompt template/version, and leaves the
shared analysis table for full-agentic reader provenance.

Downgrade recreates the shadow prompt structure but cannot restore deleted
analysis rows. The OpenAPI contract no longer exposes a shadow-generation
endpoint.

## 9. Enforced invariants

| ID | Invariant | Enforcement |
| --- | --- | --- |
| INV-001 | Reader analysis and feedback cannot directly decide a candidate | Capability boundary and separate decision use case |
| INV-002 | Only review groups can read this history or submit feedback | Application services |
| INV-003 | Only reader-prefix records appear in history or accept feedback | Prompt-version prefix filter |
| INV-004 | A sequential second feedback attempt is rejected | Entity method |
| INV-005 | Feedback requires a completed analysis | Entity method |
| INV-006 | Persisted reader input and structured result are encrypted at rest | Repository mapping |
| INV-007 | Reader claims shown as grounded passages/forms occur in delivered fields under the implemented normalisation | Deterministic grounding service |
| INV-008 | Malformed reader output cannot create a reader analysis | Strict JSON parser and orchestration |

The implementation does not guarantee a durable failed-analysis row, complete
model-call replay, complete-payload hash verification, institution isolation, or
concurrency-safe one-time feedback.

Authenticated encryption does protect the encrypted input/result fields;
GAP-004 concerns the separate audit hashes and their incomplete coverage.

## 10. Acceptance evidence

| ID | Behaviour | Automated evidence |
| --- | --- | --- |
| AC-001 | A relevant full-agentic assessment produces a pending candidate and reader provenance | `test/scientific_return/test_full_agentic_flow.py::test_agent_presents_without_deterministic_gate` |
| AC-002 | Malformed reader output does not abort later articles | `test/scientific_return/test_full_agentic_flow.py::test_malformed_reader_result_does_not_abort_later_articles` |
| AC-003 | The reader returns the published prompt identity | `test/scientific_return/test_full_agentic_reasoner.py::test_reader_returns_the_published_prompt_identity` |
| AC-004 | Literal claims are grounded and invented claims rejected | `test/scientific_return/test_full_agentic_grounding.py` |
| AC-005 | Hostile publication text cannot decide a candidate | `test/scientific_return/test_agent_security.py::test_injected_text_cannot_move_a_candidate` |
| AC-006 | Completed reader feedback is accepted once and a second attempt rejected | `test/scientific_return/test_scientific_return.py::test_curator_can_record_feedback_once_on_completed_analysis` |
| AC-007 | Non-reader records are hidden from history and feedback | `test/scientific_return/test_scientific_return.py::test_analysis_history_and_feedback_exclude_non_reader_records` |
| AC-008 | The real published reader prompt ID fits and the input payload is encrypted | `test/scientific_return/test_full_agentic_repository_postgres.py::test_agent_analysis_accepts_the_real_published_prompt_id` |
| AC-009 | OpenAPI excludes shadow generation and retains reader provenance | `test/scientific_return/test_api_contract.py::test_openapi_removes_shadow_generation_but_keeps_reader_provenance` |
| AC-010 | Shadow downgrade restores schema but not deleted rows | `test/scientific_return/test_shadow_removal_migration.py::test_downgrade_restores_prompt_structure_but_not_deleted_analysis_data` |
| AC-011 | Angular exposes reader analysis separately from investigation history | `scientific-return-panel.component.spec.ts::opens each candidate history in its own dialog` |
| AC-012 | Angular shows where agent-created evidence is retained | `scientific-return-panel.component.spec.ts::says where the evidence of an agent-found candidate is held` |
| AC-013 | Angular service keeps history and feedback endpoints separate | `scientific-return-api.service.spec.ts::keeps the reader analysis and staff feedback on separate endpoints` |

## 11. Known implementation gaps

### GAP-001 — Institution isolation is not enforced

**Severity: critical.** Candidate and analysis lookup use global IDs and the
review-group check does not compare caller institution with watch/project
ownership. A reviewer who knows identifiers may read another institution's
analysis or rate it.

**Required change:** carry authoritative institution ownership through analysis
rows, scope candidate/analysis repositories and endpoints, and add negative
cross-institution tests together with SPEC-002 and SPEC-004 fixes.

### GAP-002 — Failed and running analysis states are not durably represented

**Severity: high.** Production persists only already completed, relevant reader
analyses. Reader timeouts, invalid JSON, unavailable prompts, and other failures
exist only in the investigation trajectory. The analysis endpoint cannot meet
the previous claim that every failed analysis is retained, and the `RUNNING`
and `FAILED` entity/schema paths are effectively dormant for this producer.

**Required change:** decide whether `CandidateAgentAnalysis` is the durable log
of every reader attempt. If so, create it before the call and finalise it after
success/failure; otherwise remove misleading lifecycle fields and link the UI
explicitly to trajectory failures.

### GAP-003 — Relevance can survive with no grounded evidence

**Severity: high.** Grounding removes fabricated passages and inventory forms
but intentionally preserves the model's relevance boolean. A candidate and
completed analysis can therefore be presented when every factual claim was
rejected. The queue labels evidence as `NOT_OBSERVED` or `UNAVAILABLE`, but no
minimum grounded-evidence policy gates presentation.

**Required change:** define the product threshold explicitly. At minimum,
distinguish “model relevance only” from grounded relevance and require prominent
human acknowledgement before confirmation.

### GAP-004 — Integrity hashes do not cover their named payloads

**Severity: high.** `inputHash` covers only source, source-record ID, and query,
not `input_payload` or the full model input. `responseHash` covers only the
explanation, not the reader JSON or persisted result. Neither is verified on
read. Different assessments can therefore share both hashes while passages,
inventory forms, contradictions, confidence, or context differ.

**Required change:** hash canonical complete persisted input/result envelopes,
store a separate transport-exchange hash if needed, version the hash contract,
and verify it during rehydration or audit export.

### GAP-005 — Model-call provenance is incomplete

**Severity: high.** The row stores model name and prompt identifiers but not
prompt content hash, prompt temperature, reasoning setting, generation limit,
provider/base endpoint identity, trusted observation, bounded publication input,
or raw validated response. It cannot reproduce or independently verify the
model call.

**Required change:** persist a secret-free, versioned execution manifest and
content hashes for the exact prompt and bounded inputs. Define retention for raw
responses separately from the grounded review result.

### GAP-006 — One-time feedback is race-prone

**Severity: medium.** Two concurrent feedback requests can load an unrated row,
both pass the entity check, and overwrite value, comment, actor, and time. No
version or conditional update prevents last-write-wins behaviour.

**Required change:** use optimistic versioning or an atomic update conditioned
on `staff_feedback IS NULL`, return `409` for the loser, and add a PostgreSQL
concurrency test.

### GAP-007 — UI exposes only a partial audit and no comment

**Severity: medium.** The modal omits prompt provenance, hashes, creator,
completion time, full feedback provenance, and the grounded input summary. The
optional feedback comment is supported by the backend but impossible to submit
or read in the UI.

**Required change:** provide progressive disclosure for technical provenance,
show grounding status and rejected-claim counts, and either implement feedback
comments end to end or remove the unused field from the public contract.

### GAP-008 — Reader lineage is identified by string prefix

**Severity: medium.** History and feedback trust any `prompt_version_id`
beginning with `pver-sr-full-reader`; there is no foreign key or persisted prompt
purpose/key on the analysis row. A malformed or manually inserted identifier
can be classified as reader provenance.

**Required change:** add a referential prompt-version link and query lineage by
the authoritative template key/purpose, or persist a validated analysis kind
enum at creation.

### GAP-009 — Feedback has no aggregate utility reporting

**Severity: low.** Feedback is stored per analysis but no published metric
groups usefulness by model, prompt version, evidence status, or time period.
The data cannot yet support the evaluation loop implied by the feature.

**Required change:** define denominators and privacy thresholds, then expose an
institution-scoped evaluation report rather than raw global counts.

### GAP-010 — Plaintext fields need classification and retention

**Severity: low.** Input and result payloads are encrypted, but model/prompt
identifiers, hashes, status, confidence, recommended action, error message,
creator, feedback value/comment/actor, and timing remain plaintext. Comments
and errors may contain sensitive free text.

**Required change:** classify each field, sanitise errors, encrypt sensitive
comments where required, and establish retention/erasure rules.

## 12. Non-functional requirements

- **Human authority:** reader output must never confirm, dismiss, or create a
  publication entry.
- **Prompt-injection resistance:** publication content remains isolated as
  untrusted data in a tool-free reader call, followed by deterministic
  grounding.
- **Confidentiality:** persisted reader input and result payloads remain
  encrypted at rest; credentials never enter the prompt or response contract.
- **Bounded execution:** model input, output, generation, and total call time
  have enforced limits.
- **Auditability:** retain model, prompt identity, timestamps, grounded result,
  hashes, and feedback, subject to the limitations above.
- **Accessibility:** the UI must state that the recommendation is advisory and
  expose feedback controls with text labels.

## 13. Traceability

| Concern | Implementation |
| --- | --- |
| Analysis entity, result, lifecycle, and feedback | `vitarerum-api/app/scientific_return/domain/models.py` |
| Reader response and published-prompt adapter | `vitarerum-api/app/scientific_return/infrastructure/full_agentic_reasoner.py` |
| Deterministic grounding | `vitarerum-api/app/scientific_return/application/full_agentic_grounding.py` |
| Analysis production in the autonomous workflow | `vitarerum-api/app/scientific_return/application/full_agentic.py` |
| History and feedback application services | `vitarerum-api/app/scientific_return/application/agent_analysis.py` |
| Persistence and encryption | `vitarerum-api/app/scientific_return/infrastructure/{models,repositories}.py` |
| Prompt published-language adapter | `vitarerum-api/app/scientific_return/infrastructure/prompt_acl.py` |
| Ollama adapter | `vitarerum-api/app/scientific_return/infrastructure/reasoner_ollama.py` |
| API contract | `vitarerum-api/app/scientific_return/presentation/{schemas,routes}.py` |
| Reader prompt versions | `vitarerum-api/alembic/versions/00000068_0068_full_agentic_prompts.py`, `00000070_0070_harden_full_agentic_prompts.py` |
| Shadow removal | `vitarerum-api/alembic/versions/00000075_0075_remove_scientific_return_shadow_analysis.py` |
| Angular reader modal | `vitarerum-ui/src/app/features/collections/projects/components/candidate-analyses-modal/` |
| Angular orchestration | `vitarerum-ui/src/app/features/collections/projects/components/scientific-return-panel/` |
| Automated evidence | `vitarerum-api/test/scientific_return/` and related Angular `*.spec.ts` files |

## 14. Open product decisions

1. Should every reader attempt have its own durable analysis row, including
   non-relevant, failed, and malformed responses?
2. Is a model-only relevance verdict sufficient to create a review candidate
   when no passage or inventory form survives grounding?
3. Should staff feedback assess semantic relevance, grounding quality, time
   saved, or the usefulness of the fixed `PRESENT_FOR_REVIEW` action?
4. Should reviewers be able to revise feedback, with append-only history,
   instead of a permanent one-shot rating?
5. Which reader provenance belongs in the normal UI and which belongs only in a
   technical audit export?
