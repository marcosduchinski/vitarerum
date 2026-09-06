# SPEC-017 — AI-Assisted Museum Narrative

| Field | Value |
| --- | --- |
| Identifier | SPEC-017 |
| Status | Implemented (with declared authorisation, publication-safety, provenance, validation, and concurrency gaps) |
| Bounded context | `app/ai/museum_narrative` |
| Derived from | Backend, frontend, migrations, architecture contracts, consumers, diagrams, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-013](../013-mapeamento-cidoc-crm/spec.md), [SPEC-015](../015-relatorio-visita-in-situ/spec.md), [SPEC-016](../016-prompts-versionados/spec.md) |

## 1. Problem

An in-situ visit record is structured evidence, not an accessible account for
curators, researchers, visitors, or children. Writing a separate account for
every audience and visit does not scale. Generating one with a language model,
however, introduces the risk of plausible but unsupported people, dates,
objects, places, and outcomes.

The system must therefore preserve the evidence used for generation, constrain
the model to a compact factual representation, and retain deterministic review
signals and human editorial history.

## 2. Goal and scope

This context generates a narrative from a persisted in-situ visit record. It:

- rebuilds and validates the record's CIDOC-CRM projection as a semantic gate;
- translates the record view into canonical visit facts;
- resolves a versioned system prompt for the selected narrative style;
- calls the configured Ollama-compatible model;
- checks the generated text with deterministic heuristics;
- persists generation provenance and a frozen fact snapshot; and
- supports exact reads, history, preview, and append-only editorial revisions.

The context does not create the source visit record, publish reports to external
audiences, decide whether a flagged narrative is fit for publication, or manage
prompt versions.

The code and some historical documentation use the term **KG-RAG**. The
implemented pipeline does not retrieve passages from a graph, run semantic
search, use embeddings, or query a vector store. CIDOC-CRM is a validation gate;
the model receives serialized canonical facts. KG-RAG must therefore be treated
as a historical architectural label, not a claim that graph retrieval-augmented
generation is implemented.

## 3. Strategic context

`ai.museum_narrative` is a supporting AI context. Its principal relationships
are:

| Relationship | Integration style | Responsibility |
| --- | --- | --- |
| CIDOC-CRM Mapping → Museum Narrative | Published Language plus anti-corruption adapter | Build and validate the graph, then expose a record view translated into canonical facts. |
| AI Prompts → Museum Narrative | Published Language plus anti-corruption adapter | Resolve the published prompt or an exact version for preview. |
| Museum Narrative → In-Situ Visit Reports | Open Host Service / Published Language | Generate, read, revise, and delete narrative artefacts linked by a report. |
| Museum Narrative → Ollama-compatible service | Driven port and infrastructure adapter | Generate text from the system prompt and canonical facts. |

Cross-context source dependencies are constrained by import-linter. The report
context nevertheless imports narrative presentation DTOs in addition to the
published-language module; that registered exception creates schema coupling.

## 4. Ubiquitous language and domain model

### 4.1 Canonical visit facts

`CanonicalVisitFacts` is an immutable, model-facing representation of the visit.
It includes the project reference, title and purpose, planned interval,
requester, approval and execution evidence, requested objects, access logs,
occurrences, publications, attachment references, evidence gaps, and source
snapshot identity/version.

Missing approval or execution evidence is represented explicitly with
`MissingFact`; other gaps are rendered as `EvidenceGap` values. The model does
not receive CIDOC IRIs or expanded JSON-LD.

### 4.2 Semantic gate

The CIDOC adapter first builds the current JSON-LD projection and validates it.
A non-conforming graph stops the operation. Only then does the adapter read the
record view and construct canonical facts. The validated document and validation
report are returned with the facts for snapshotting.

This is a gate over a newly built projection, not retrieval from a knowledge
graph and not proof that the generated prose is factually correct.

### 4.3 Fact snapshot

`NarrativeFactSnapshot` freezes:

- the canonical facts as sorted JSON and their SHA-256 hash;
- the facts-builder version;
- the prompt version label;
- the CIDOC JSON-LD document;
- the SHACL validation report and conformance result; and
- the source record identifier and creation time.

The snapshot is persisted immediately before the model call in the same database
transaction. A handled failure prevents the route-level commit, so normal
request rollback removes the uncommitted snapshot.

### 4.4 Generated narrative aggregate

`GeneratedNarrative` is the aggregate root for one model execution. It retains
the current narrative text, resolved style and source, language, temperature,
model name, generation time, fact-snapshot identifier, prompt-version identifier
and label, SHA-256 hash of the original model response, and deterministic
validation result.

The same source record may have multiple independent generations. The report
context links one generated narrative to each report.

### 4.5 Editorial revision

`GeneratedNarrativeRevision` records the previous text, revised text, editor's
permission identifier, and timestamp. Editing changes the aggregate's current
text while leaving original generation metadata and findings unchanged.

The revision history makes the original model response recoverable after the
first edit. Before any edit, the aggregate's current text is the original
response.

### 4.6 Narrative types

| Value | Intended audience and tone |
| --- | --- |
| `institutional` | Formal institutional, curatorial, compliance, and open-data communication. |
| `scientific` | Rigorous and methodological research communication. |
| `audioguide_adult` | Clear, engaging interpretation for adult visitors with limited jargon. |
| `audioguide_child` | Playful, pedagogical storytelling for younger audiences. |
| `social_media` | Concise, hook-driven copy with a call to action. |

The style is a rendering choice, not a fact about the visit. An omitted type
resolves to `institutional` with source `default`; an explicit value has source
`request_body`.

## 5. Authorisation and data exposure

All narrative endpoints call `require_staff`. `EXTERNAL` callers receive `403`,
but every staff group has the same capability to generate, preview, list, read,
and edit narratives for any known record identifier. There is no project,
collection, role, or creator ownership check.

Stored responses expose canonical fact JSON, CIDOC JSON-LD, SHACL reports,
people, evidence, model metadata, and revision actors to staff callers. Source
facts, including names and attachment-reference metadata, are also sent to the
configured model endpoint. Ollama defaults to localhost but may be configured
for a hosted endpoint with a bearer token; deployment policy must therefore
determine whether this is local or external processing.

## 6. Functional requirements

### FR-001 — Generate and persist a narrative

`POST /api/v1/cidoc-mapping/in-situ-visit/{recordId}/narrative` accepts:

| Field | Default | Validation |
| --- | --- | --- |
| `target_language` | `pt` | Currently an unrestricted string. |
| `narrative_type` | omitted → `institutional` | Must be one of the five narrative types. |
| `creativity_temperature` | `0.3` | Inclusive range `0.0..1.0`. |

The use case resolves the published prompt, validates and translates the visit
record, creates a fact snapshot, calls the model, validates the response, and
persists a generation. An empty model response is rejected and no narrative is
committed.

The report UI is the main user-facing generation path. It offers Portuguese and
English, all five styles, and a temperature slider in `0.1` increments. Report
creation first exports a fresh visit record, then generates a fresh narrative,
then links both in one transaction.

### FR-002 — Enforce the semantic gate

Generation and preview proceed only when the rebuilt CIDOC-CRM projection
conforms. A missing record returns `404 IN_SITU_VISIT_NOT_FOUND`; failed semantic
validation returns `422 SEMANTIC_VALIDATION_FAILED`.

Prompt resolution currently happens before record preparation. Consequently, a
missing published prompt can yield `503` before an invalid record identifier is
checked.

### FR-003 — Use canonical facts as the model input

The model receives the selected versioned prompt as its system message and
canonical facts serialized as JSON, the requested language code, and a task
instruction as its user message. It receives neither the validated JSON-LD
document nor CIDOC-CRM IRIs. The graph and validation report remain stored audit
artefacts.

### FR-004 — Resolve versioned prompts

Persisted generation resolves the published `in_situ_narrative` prompt keyed by
narrative type. A missing published prompt returns
`503 NARRATIVE_PROMPT_UNAVAILABLE`. There is no embedded fallback prompt in the
generation flow.

Each stored narrative keeps both the prompt-version identifier and label.
Publishing a newer prompt does not rewrite historical narrative metadata.

`build_system_prompt()` and static persona descriptions remain in the
application module but are not called by the production generation path. They
must not be interpreted as an operational fallback.

### FR-005 — Freeze generation provenance

Every successful generation stores:

- narrative type and resolution source;
- target language and temperature;
- configured model name and generation timestamp;
- fact-snapshot identifier, payload and hash;
- prompt-version identifier and label;
- original model-response hash; and
- validation conformance and findings.

The stored provenance does not include the exact prompt content, model digest,
provider/base URL, full sampling configuration, request actor, request ID, or
execution latency.

### FR-006 — Perform deterministic post-generation checks

The current heuristic validator emits advisory findings for:

| Code | Detection mechanism |
| --- | --- |
| `invented_date` | ISO `YYYY-MM-DD` and numeric `D/M/YYYY` mentions absent from allowed factual dates. |
| `planned_date_as_executed` | Planned boundary dates treated as execution evidence according to nearby Portuguese/English execution words and execution availability. |
| `invented_person` | Title-led Portuguese/English person-name patterns absent from canonical people. |
| `invented_object` | Identifier-like `INV`, `RO`, `OBJ`, or `XL` tokens absent from canonical objects. |
| `invented_place` | Limited Portuguese/English room, gallery, laboratory, or reserve patterns absent from occurrence locations. |

The validator is regex-based and intentionally incomplete. Findings set
`validation_conforms` to false but do not change or reject the generated text.
A date strictly inside the planned interval is allowed; planned interval
boundaries receive additional execution-evidence checks.

### FR-007 — Preserve declared absence

The canonical payload explicitly includes missing approval, missing execution
evidence, and calculated evidence gaps instead of silently dropping them. The
prompt instructs the model not to fill those gaps with invented detail.

### FR-008 — List and read generation history

| Endpoint | Behaviour |
| --- | --- |
| `GET /{recordId}/narratives?page=0&size=20` | Paginated generations, newest first; size `1..100`. |
| `GET /{recordId}/narratives/{narrativeId}` | Exact stored generation with current text and frozen snapshot. |

Exact reads enforce that the narrative belongs to the record in the path and
otherwise return `404 NARRATIVE_NOT_FOUND`. Listing does not verify that the
record exists: an unknown identifier returns an empty page.

The Angular report screens show the narrative linked to a report, not the full
generation history for a source record.

### FR-009 — Preview without persistence

`POST /{recordId}/narrative/preview` requires exactly one prompt source:

- `prompt_version_id`, which may resolve a draft, published, or archived exact
  version belonging to the selected narrative type; or
- ad hoc `content`, which also requires an explicit narrative type.

Preview uses the same semantic gate, canonical facts, model, and deterministic
validator as generation. It returns prompt source/status and generation
metadata but persists neither a fact snapshot nor a narrative. Invalid source
combinations return structured `422` validation errors.

The prompt-management UI exposes this operation only for in-situ narrative
templates. Its project selector resolves a previously generated report to a
record identifier, so a completed project without a report cannot be previewed
through that UI even though the API accepts a record directly.

### FR-010 — Edit narrative text and append a revision

`PATCH /{recordId}/narratives/{narrativeId}` replaces only the current narrative
text. Blank text returns `422`. A successful edit appends a revision containing
the previous text, revised text, editor permission ID, and time.

Original generation metadata, response hash, fact snapshot, and deterministic
findings remain unchanged. The report detail UI provides this edit operation and
warns before discarding unsaved changes.

### FR-011 — List editorial revisions

`GET /{recordId}/narratives/{narrativeId}/revisions?page=0&size=20` returns
revisions oldest first with size `1..100`. The narrative must belong to the
record in the path.

Revisions are append-only through exposed use cases. There is no edit reason,
review decision, electronic signature, or distinction between correction,
redaction, and stylistic change.

### FR-012 — Present an audit trail

The report audit endpoint and Angular audit page aggregate:

1. source execution and approval evidence;
2. persisted CIDOC-CRM/SHACL artefacts;
3. frozen canonical facts;
4. model, prompt, temperature, time, and response hash;
5. deterministic findings over the original generated text; and
6. chronological editorial revisions and current text.

The UI escapes narrative and finding text before applying trusted highlight
markup. It links a recorded prompt-version identifier to its exact management
view.

### FR-013 — Delete through report lifecycle

There is no public narrative-delete HTTP endpoint. The narrative Published
Language exposes a hard-delete operation used when an in-situ report is deleted.
It removes the generated narrative, all revisions, and its fact snapshot while
preserving the exported visit record.

Therefore, generated narrative history is not retained indefinitely. External
report publications are revoked by the report workflow before deletion.

### FR-014 — Map operational failures

| Situation | HTTP result |
| --- | --- |
| Unsupported narrative type | `400 INVALID_NARRATIVE_TYPE` |
| Missing visit record | `404 IN_SITU_VISIT_NOT_FOUND` |
| Missing narrative or record/narrative mismatch | `404 NARRATIVE_NOT_FOUND` |
| Missing exact prompt version in preview | `404 PROMPT_VERSION_NOT_FOUND` |
| Prompt version belongs to another style | `422 PROMPT_VERSION_NARRATIVE_TYPE_MISMATCH` |
| CIDOC/SHACL gate failure | `422 SEMANTIC_VALIDATION_FAILED` |
| Invalid preview combination or request validation | `422` validation envelope |
| Model or published prompt unavailable, including blank output | `503` |
| Model timeout | `504 MODEL_TIMEOUT` |
| External caller | `403` |

## 7. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | No model call occurs unless the rebuilt CIDOC-CRM projection passes the semantic gate. |
| INV-002 | The model receives canonical facts, not CIDOC IRIs or the JSON-LD graph. |
| INV-003 | Every newly persisted narrative records the selected prompt-version ID/label and configured model name. |
| INV-004 | A successful generation links to the frozen canonical facts and gate artefacts used for that execution. |
| INV-005 | Publishing a new prompt does not mutate already generated narrative metadata. |
| INV-006 | Editorial correction changes only current text and appends a revision. |
| INV-007 | Original generation metadata, hash, findings, and fact snapshot survive editorial correction unchanged. |
| INV-008 | Deterministic findings are advisory and never rewrite generated text. |
| INV-009 | Exact reads, edits, and revision lists enforce record/narrative ownership. |
| INV-010 | Preview persists neither a narrative nor a fact snapshot. |
| INV-011 | Report deletion may hard-delete the linked narrative, revisions, and fact snapshot. |

The database uses plain identifier columns rather than foreign keys between
narrative, fact snapshot, prompt version, visit record, revision, and report
records. Several invariants are application-enforced rather than
database-enforced.

## 8. Acceptance and test traceability

| Behaviour | Representative automated evidence |
| --- | --- |
| Default/explicit type and invalid type | `test/ai/museum_narrative/test_api.py::test_default_type_returns_institutional`, `test/ai/museum_narrative/test_use_case.py::test_explicit_type_is_used_with_request_body_source`, `test/ai/museum_narrative/test_api.py::test_invalid_type_is_400` |
| Semantic gate and frozen output | `test/ai/museum_narrative/test_api.py::test_semantic_failure_is_422`, `test/ai/museum_narrative/test_use_case.py::test_facts_adapter_validates_cidoc_before_facts`, `test/ai/museum_narrative/test_use_case.py::test_fact_snapshot_freezes_cidoc_gate_output_used_for_generation` |
| Prompt resolution and historical identity | `test/ai/museum_narrative/test_use_case.py::test_generation_uses_published_prompt_registry_output`, `test/ai/museum_narrative/test_use_case.py::test_existing_narrative_keeps_prompt_version_after_new_publish`, `test/ai/museum_narrative/test_prompt_acl.py::test_prompt_acl_rejects_version_from_another_narrative_type` |
| Canonical input and declared absence | `test/ai/museum_narrative/test_use_case.py::test_fact_snapshot_freezes_payload_used_for_generation`, `test/ai/museum_narrative/test_use_case.py::test_user_prompt_receives_canonical_facts_and_declared_absence` |
| Deterministic findings | `test/ai/museum_narrative/test_use_case.py::test_narrative_with_invented_date_is_marked_for_review`, `test/ai/museum_narrative/test_use_case.py::test_planned_date_as_execution_is_marked_for_review`, `test/ai/museum_narrative/test_use_case.py::test_invented_person_object_and_place_are_marked_for_review` |
| Preview rules and no persistence | `test/ai/museum_narrative/test_api.py::test_preview_returns_draft_metadata_without_persisting`, `test/ai/museum_narrative/test_api.py::test_preview_accepts_ad_hoc_content_with_null_prompt_version_id`, `test/ai/museum_narrative/test_use_case.py::test_preview_rejects_invalid_prompt_source_combinations` |
| History, exact reads, and isolation | `test/ai/museum_narrative/test_api.py::test_listed_newest_first_after_two_generations`, `test/ai/museum_narrative/test_api.py::test_get_under_wrong_record_is_404`, `test/ai/museum_narrative/test_use_case.py::test_list_revisions_under_wrong_record_raises` |
| Editorial correction and revisions | `test/ai/museum_narrative/test_api.py::test_patch_updates_narrative_text`, `test/ai/museum_narrative/test_api.py::test_list_revisions_returns_original_text_first_and_editor`, `test/ai/museum_narrative/test_repository.py::test_repository_lists_revisions_oldest_first_with_editor` |
| Model and authorisation failures | `test/ai/museum_narrative/test_api.py::test_model_unavailable_is_503`, `test/ai/museum_narrative/test_api.py::test_model_timeout_is_504`, `test/ai/museum_narrative/test_api.py::test_blank_model_output_is_503`, `test/ai/museum_narrative/test_api.py::test_external_caller_is_403` |
| Angular report and audit UI | `create-in-situ-visit-report-modal.component.spec.ts`, `in-situ-visit-report-narrative.component.spec.ts`, `edit-in-situ-visit-narrative-dialog.component.spec.ts`, `in-situ-visit-audit-trail-page.component.spec.ts` |

## 9. Non-functional requirements

- **Advisory posture:** model output and heuristic validation are review aids,
  not factual certification or publication approval.
- **Transactional generation:** direct generation and report orchestration commit
  only after successful persistence of their complete operation.
- **Architecture:** domain and application remain framework-free; cross-context
  reads use published languages and adapters.
- **Auditability:** hashes detect differences only when the retained input or
  original text is available; they do not authenticate authorship themselves.
- **Provider configuration:** generation uses a configurable Ollama-compatible
  endpoint. The default is `llama3.1:8b` on localhost, not a deployment guarantee.
- **Performance:** generation makes a synchronous model call in the HTTP request;
  there is no background job, progress endpoint, cancellation, or idempotency key.

## 10. Known gaps and recommended changes

| ID | Priority | Finding | Recommended change |
| --- | --- | --- | --- |
| GAP-001 | High | Any staff member can read sensitive facts and revisions, generate variants, and edit any narrative when identifiers are known. | Define reader, generator, editor, reviewer, and publisher permissions and enforce project/collection scope in the backend. |
| GAP-002 | High | A narrative with deterministic findings can still be linked to and externally published as a report. | Introduce an explicit human review decision and block external publication until the decided policy is satisfied. |
| GAP-003 | High | Model processing may be local or hosted, while prompts include personal and operational source data. | Document the deployment processing boundary, minimise/redact model input, and require an approved provider/privacy configuration outside local environments. |
| GAP-004 | High | Prompt labels allow 96 characters in `ai.prompts`, but both narrative prompt-label columns are `VARCHAR(64)`. | Align column and API limits through a migration and test the maximum valid prompt label. |
| GAP-005 | High | Exact prompt content and reproducible model identity are not frozen; prompt history may be removed by migrations. | Snapshot prompt content/hash and record provider, immutable model digest/version, and effective generation parameters. |
| GAP-006 | Medium | Regex checks cover narrow patterns and can produce false negatives or positives. | Treat `validation_conforms` as heuristic review status, expand multilingual fixtures, measure precision/recall, and avoid presenting it as factual conformance. |
| GAP-007 | Medium | Concurrent editorial updates have no expected version, row lock, or ETag and can overwrite each other. | Add optimistic concurrency with a version token and return `409` for stale edits. |
| GAP-008 | Medium | `target_language` is unrestricted and unbounded although persistence allows 16 characters. | Use a documented language enum or validated BCP 47 tag with matching database length and reject invalid input before generation. |
| GAP-009 | Medium | Generated-by identity, review decision, edit reason, request correlation, and latency are absent from provenance. | Persist the actor, review workflow, revision reason, request ID, and execution timing. |
| GAP-010 | Medium | Plain IDs without foreign keys permit orphaned cross-artefact references if workflows diverge. | Add safe constraints where lifecycle permits, or scheduled integrity checks where cross-context FKs are intentionally avoided. |
| GAP-011 | Medium | Direct generation is synchronous, not idempotent, and has no cancellation or progress state. | Add an idempotency key and consider an asynchronous job if production latency warrants it. |
| GAP-012 | Medium | Full generation history exists only in the API; the report UI shows one linked generation and its edits. | Add a staff history/comparison view if repeated generation is an intended workflow. |
| GAP-013 | Low | Listing narratives for a nonexistent record returns an empty `200` page. | Decide whether collection reads should verify record existence and consistently return `404`. |
| GAP-014 | Low | Historical `KG-RAG` naming overstates the validation-gated fact pipeline. | Rename user-facing/code documentation, or implement and evidence graph retrieval before retaining the term as a capability claim. |
| GAP-015 | Low | Static persona-building code is unused after prompts became managed content. | Remove or isolate the dead helper after verifying no external imports. |

## 11. Traceability

| Element | Location |
| --- | --- |
| Aggregate, snapshots, revisions, and types | `vitarerum-api/app/ai/museum_narrative/domain/` |
| Canonical facts and deterministic validation | `vitarerum-api/app/ai/museum_narrative/domain/facts.py` and `validation.py` |
| Generation, preview, read, list, and edit use cases | `vitarerum-api/app/ai/museum_narrative/application/use_cases.py` |
| Canonical user-prompt serialization | `vitarerum-api/app/ai/museum_narrative/application/prompts.py` |
| CIDOC-CRM and prompt adapters | `vitarerum-api/app/ai/museum_narrative/infrastructure/cidoc_acl.py` and `prompt_acl.py` |
| Model adapter and persistence | `vitarerum-api/app/ai/museum_narrative/infrastructure/` |
| Narrative HTTP API | `vitarerum-api/app/ai/museum_narrative/presentation/` |
| Published language consumed by reports | `vitarerum-api/app/ai/museum_narrative/public.py` |
| Report generation, detail, editor, and audit UI | `vitarerum-ui/src/app/features/collections/reports/` |
| Backend automated tests | `vitarerum-api/test/ai/museum_narrative/` |
| Context and generation-flow diagrams | `docs/diagrams/in-situ-visit-context-map.puml` and `in-situ-visit-cidoc-narrative-flow.puml` |

## 12. Open product decisions

1. Which staff roles and project/collection scopes may generate, read, edit,
   review, and externally publish a narrative?
2. Which findings or evidence gaps must block publication, and who can override
   that decision with a recorded justification?
3. Is hosted model processing permitted for the personal and collection data in
   canonical facts, and under which retention and contractual controls?
4. Which languages are officially supported and evaluated for generation and
   deterministic checks?
5. Must deleted reports retain narrative snapshots and revisions for an
   institutional audit-retention period?
6. What quality dataset and measurable thresholds are required for each
   narrative type before prompt or model changes reach production?
