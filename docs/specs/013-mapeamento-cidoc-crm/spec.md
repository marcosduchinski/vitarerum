# SPEC-013 — CIDOC-CRM mapping for in-situ visits

| Field | Value |
| --- | --- |
| Identifier | SPEC-013 |
| Status | Implemented (with declared semantic-identity, reproducibility, validation, and API-validation gaps) |
| Bounded context | `app/cidoc_crm/in_situ_visit_mapping` |
| Written from | Domain, mapping definition and engine, SHACL validation, persistence, APIs, cross-context adapters, Angular CIDOC viewer, and `test/cidoc_crm/` |
| Related specs | [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-015](../015-relatorio-visita-in-situ/spec.md), [SPEC-017](../017-narrativa-museologica/spec.md) |

## 1. Problem

An internal record of an in-situ visit is useful to the museum but is not an
interoperable heritage-data representation. Reuse by reports, knowledge graphs,
or external systems requires an explicit semantic mapping.

The principal risk is overstatement: planned dates are not evidence of an
event, a free-text visitor is not necessarily one person, and an unknown
collection object must not be classified more narrowly than the source permits.

## 2. Goal

Persist immutable-style in-situ visit snapshots and project them as
self-contained JSON-LD targeting CIDOC-CRM 7.1.3. Preserve source evidence and
omit unsupported event-time assertions.

This spec documents implemented behavior. It does not claim full CIDOC-CRM
conformance; the narrower guarantees and current gaps are stated below.

## 3. Strategic and tactical model

The mapping context is a supporting subdomain. Use of Collections is its
upstream supplier, accessed through that context's published language and a
local anti-corruption adapter. In-situ Visit Reports and Museum Narrative are
downstream consumers through `app.cidoc_crm.public`.

`InSituVisitRecord` is the aggregate root. Its consistency boundary contains:

- requested-object records;
- occurrence, access-log, and publication records;
- attachments owned by occurrences, logs, and publications.

The root and every child/attachment are entities with server-generated UUIDs.
`ChildData` and `AttachmentData` are immutable creation values. The repository
writes the complete graph and eagerly reconstructs it. There are no update or
delete operations for the snapshot in this context.

The root captures record-schema, mapping, and CRM version labels. The JSON-LD
projection itself is generated on read from the mapping definition currently
bundled with the running application.

## 4. Actors and interfaces

| Actor or consumer | Capability |
| --- | --- |
| Curatorial, Collections Management, Direction, System Administration | Create, list, export, and read CIDOC projections |
| External permission | No access; receives `403` |
| Use of Collections | Supplies project evidence through a published read contract |
| In-situ Visit Reports | Exports a fresh record when generating a report and reads stored record views |
| Museum Narrative | Consumes the published CIDOC document and semantic validation services |
| Angular report user | Opens validated JSON-LD, retries loading, and copies it to the clipboard |

All HTTP endpoints require a bearer token and matching `X-Permission-Id` for a
staff group. There is no public CIDOC endpoint in this context.

Staff access is deployment-wide. `institutionName` is descriptive provenance,
not an institution identifier or authorization boundary; see GAP-014.

## 5. Snapshot requirements

### FR-001 — Direct record creation

`POST /api/v1/cidoc-mapping/in-situ-visit` creates and commits a complete
aggregate, returning `201`. Required root fields are `code`, `visitBeginDate`,
`visitEndDate`, `visitorName`, and `placeName`. The four child collections are
optional and default to empty arrays.

Direct creation accepts only the base child contract: `sourceId`, description,
position, and attachments where applicable. It does not accept institution,
project provenance, execution evidence, approval, enriched object/occurrence
fields, attachment media type, or client-supplied identities.

This endpoint can therefore create a snapshot without execution evidence. Such
a record receives no visit time-span in JSON-LD. Its mandatory begin/end fields
remain record data but are not asserted as event time.

### FR-002 — Server-owned identity and generation time

The root, every child, and every attachment receive UUIDs in the domain factory.
The factory also stamps `generatedAt` in UTC and defaults
`recordSchemaVersion` to `2`. Creation use cases read `mappingVersion` and
`crmVersion` from the bundled mapping metadata (`0.7.0` and `7.1.3` currently).

The clock and UUID generator are direct domain functions rather than injected
ports.

### FR-003 — Explicit source order

Every child and attachment carries a source identifier and integer position.
ORM relationships order nested collections by position when records are loaded.
The API and domain do not require non-negative or unique positions/source IDs.

### FR-004 — Paginated record list

`GET /api/v1/cidoc-mapping/in-situ-visit?page=&size=` returns complete nested
records newest first by `generatedAt`. Page defaults to `0`, size defaults to
`20`, and size is constrained to 1–100. Equal generation times have no explicit
ID tie-breaker.

There is no standalone raw-record detail endpoint; the list and the published
language provide record views.

## 6. Project-export requirements

### FR-005 — Export from a collection-use project

`POST /api/v1/collection-use-projects/{id}/export-in-situ-visit-record`
translates the upstream project view, persists a new snapshot, commits, and
returns `201`.

| Condition | Result |
| --- | --- |
| Project not found | `404 PROJECT_NOT_FOUND` |
| Intended use is not `IN_SITU_VISIT` | `409 INVALID_USE_TYPE` |
| Execution evidence is insufficient | `409 VISIT_NOT_EVIDENCED` |
| Caller is external | `403` |

Repeated exports are not deduplicated: each accepted call creates another
snapshot for the same source project.

### FR-006 — Minimum execution evidence

The upstream published reader marks a visit as occurred only when the project
is `COMPLETED` and contains a `COMPLETED` domain event. The event time and actor
become `executionOccurredAt` and `executionRecordedBy`. Missing conditions are
captured as evidence gaps and reject export.

This is operational evidence of project completion, not independent proof of
the physical visit.

### FR-007 — Exported provenance and enrichment

The project reference becomes the record code. Export captures project ID,
title, purpose, planned dates, execution evidence, latest approval evidence,
requested-object snapshots, occurrences, access logs, publications, attachment
references, and related-object source IDs.

The configured `institutionName` is captured both as `institutionName` and
`placeName`. This preserves deployment attribution but currently conflates an
institutional actor/name with the physical visit place.

### FR-008 — Anti-corruption boundary

Only `infrastructure/context_acl.py` knows the Use of Collections published
types. It translates them into `ProjectExportData`, `ExportObject`, and
`ExportEntry`, keeping upstream aggregates and vocabulary out of the mapping
domain and application layers.

## 7. JSON-LD projection requirements

### FR-009 — Config-driven mapping

`GET /api/v1/cidoc-mapping/in-situ-visit/{recordId}/cidoc-crm` loads the stored
aggregate and applies `in_situ_visit_to_cidoc.json`. Unknown records return
`404 IN_SITU_VISIT_NOT_FOUND`.

The document contains an inlined CIDOC-CRM 7.1.3 term context plus local `ex`,
`dcterms`, `schema`, `xsd`, and `rdfs` prefixes. It therefore requires no remote
context resolution when parsed.

### FR-010 — Conservative event time

The visit receives an `E52_Time-Span` only when `executionOccurredAt` exists.
Its time primitive comes from that completion evidence. Planned project dates
and the direct-record begin/end fields are not asserted as visit event time.

Occurrence/access-log child times are projected only when their respective
source fields exist.

### FR-011 — Object and relationship mapping

Requested objects are typed as `crm:E19_Physical_Object`, never automatically
as `E20_Biological_Object`. Related source IDs link occurrences, logs,
publications, and their attachments to the corresponding generated object URI.

Attachments are `E31_Document` nodes, carry their reference as
`schema:contentUrl`, and use their description as a note. Log authorship/time is
modelled through activity-context nodes rather than loose properties.

### FR-012 — Graph provenance

The provenance node is an `E73_Information_Object`. It records graph creation
time and the mapping/CRM versions from the currently loaded mapping definition.
`dcterms:creator` comes from the snapshot's institution name and is omitted when
that value is empty.

The stored `mappingVersion` and `crmVersion` are returned in record DTOs but are
not used to select mapping rules or populate graph provenance during later
reads.

### FR-013 — Default semantic validation

The CIDOC endpoint validates by default. It parses JSON-LD into RDF and invokes
pySHACL with bundled shapes and a bundled partial class hierarchy using RDFS
inference. Failure returns `422 SEMANTIC_VALIDATION_FAILED` with the textual
validation report. `?validate=false` explicitly skips this gate.

The validation shapes check domain/range for the subset of CIDOC properties
listed in `in_situ_visit_shapes.ttl`; they are not a complete validation of all
CIDOC-CRM 7.1.3 constraints or every predicate emitted by the mapper.

`validate_cidoc` reports conformance without returning an expanded graph.
`expand_and_validate_cidoc`, exposed to downstream contexts, separately
materializes RDFS closure and returns expanded JSON-LD.

### FR-014 — Angular projection

The report detail opens a standalone, OnPush native-dialog component. It calls
the CIDOC endpoint with default validation, pretty-prints the JSON-LD as escaped
text, exposes retry/close behavior, and can copy the document to the clipboard.
It does not download a `.jsonld` file or visualize the graph.

## 8. Semantic invariants

| ID | Invariant |
| --- | --- |
| INV-001 | Root and nested identities and `generatedAt` are server-owned |
| INV-002 | The aggregate is persisted and reconstructed with all nested children |
| INV-003 | Planned dates are never asserted as the visit event time |
| INV-004 | Requested objects are not classified more narrowly than `E19` |
| INV-005 | The JSON-LD context is bundled and inlined |
| INV-006 | Graph creator comes from the snapshot or is omitted |
| INV-007 | Project export requires completed-project event evidence |
| INV-008 | Use of Collections is accessed through its published language and the local ACL |
| INV-009 | External permissions cannot use the mapping APIs |

## 9. Known gaps and required improvements

| ID | Gap | Required change |
| --- | --- | --- |
| GAP-001 | All generated resource URIs expand under `http://example.org/museum/`. They are placeholders, not institution-owned persistent identifiers. | Configure a validated institutional base URI, persist its version/provenance, and define URI permanence and redirect policy. |
| GAP-002 | Export assigns configured `institutionName` to `placeName`, treating an institution name as `E53_Place`. | Capture a distinct authoritative place identifier/name and model institution and place as separate resources. |
| GAP-003 | Free-text `visitorName` is always asserted as one `E21_Person`; it may represent an organization, team, or ambiguous name. | Capture typed actors with stable identifiers or use a less specific class until actor type is evidenced. |
| GAP-004 | Stored mapping/CRM versions do not control regeneration; every read uses current rules and provenance metadata. Old snapshots can silently produce a different graph. | Version mapping assets immutably and select the stored version, or persist the generated graph/hash with the snapshot. |
| GAP-005 | Normalizing source IDs into slugs can collapse distinct values to the same URI, while source IDs and positions are not unique within collections. | Detect collisions and derive identifiers from stable escaped IDs or hashes with aggregate-level uniqueness validation. |
| GAP-006 | Direct creation accepts blank strings, reversed dates, negative/duplicate positions, arbitrary references, and unbounded collection/text sizes subject mainly to database columns. | Add domain invariants and bounded Pydantic schemas, including date order, identifiers, counts, positions, and reference formats. |
| GAP-007 | SHACL shapes cover only selected domain/range rules, but earlier documentation described general CIDOC conformance. | Publish the exact conformance profile, expand shape coverage, and version shapes with the mapping. |
| GAP-008 | `schema:contentUrl` may expose internal storage references rather than durable authorized content URLs. | Define reference semantics and emit resolvable access-controlled or public persistent URLs only when disclosure is authorized. |
| GAP-009 | Repeated project export creates indistinguishable additional snapshots without an export reason or source revision marker. | Define idempotency or record source revision/hash, trigger, actor, and reason so multiple snapshots are interpretable. |
| GAP-010 | Domain time and UUID generation are hard-coded, reducing deterministic testing and explicit provenance control. | Inject clock and identifier-generator ports at the application boundary. |
| GAP-011 | List order lacks an ID tie-breaker and returns complete aggregates, which can become expensive. | Add deterministic ordering and consider summary rows plus a raw-record detail endpoint. |
| GAP-012 | Direct create/list API behavior has little focused endpoint coverage compared with export and CIDOC generation. | Add tests for creation, list pagination/order, complete nested mapping, validation boundaries, and staff authorization. |
| GAP-013 | The Angular viewer offers raw copy only, with no download, graph summary, provenance warning, or validation-profile explanation. | Add an accessible `.jsonld` download and human-readable provenance/validation summary where users need to assess or exchange the graph. |
| GAP-014 | Records have no institution ownership ID, and create/list/export/CIDOC routes enforce only staff membership. Any staff permission can read nested visit data and project exports across a shared deployment. | Derive institutional ownership from the source boundary, scope reads and exports, and test cross-institution denials before multi-institution use. Do not infer ownership from the free-text `institutionName`. |

## 10. Acceptance criteria

### AC-001 — Project export and rejection paths

Covered by `test/cidoc_crm/test_export_in_situ_visit_api.py` and
`test/cidoc_crm/test_export_in_situ_visit_use_case.py`, including missing project, wrong use
type, insufficient evidence, external authorization, persistence, and related
object propagation.

### AC-002 — Conservative time and object semantics

Covered by `test/cidoc_crm/test_cidoc_mapping.py` tests for planned dates, execution evidence,
generic physical-object typing, visit actor/place/type links, and enriched
occurrence context.

### AC-003 — Self-contained version-targeted JSON-LD

Covered by `test/cidoc_crm/test_cidoc_mapping.py::test_targets_cidoc_713`,
`test/cidoc_crm/test_cidoc_mapping.py::test_context_is_inlined_official_713_plus_local_prefixes`, and graph-creator
tests. GAP-001 and GAP-004 remain outside those assertions.

### AC-004 — Children, attachments, and related-object links

Covered by the full-expansion, content URL, note, activity-context, publication,
attachment, and ACL tests in `test/cidoc_crm/test_cidoc_mapping.py` and `test/cidoc_crm/test_context_acl.py`.

### AC-005 — Validation behavior

Covered by `test/cidoc_crm/test_cidoc_api.py` and `test/cidoc_crm/test_jsonld_validation.py`: validation is on
by default, may be skipped explicitly, detects the tested domain/range
violation, and the non-expanding entry point does not call graph expansion.

### AC-006 — Aggregate persistence

Covered by `test/cidoc_crm/test_in_situ_visit_repository.py`, which round-trips enriched root,
child, attachment, provenance, and version fields. Direct HTTP creation/listing
coverage remains GAP-012.

### AC-007 — Angular JSON-LD viewer

The co-located Vitest suite verifies lazy loading on open, formatted output,
retry, clipboard copy, and controlled close behavior.

## 11. Non-functional requirements

- **Network independence**: parsing the returned JSON-LD does not require
  fetching a remote context.
- **Semantic caution**: absent execution time is omitted instead of inferred
  from planned dates.
- **Consistency**: root and children are added in one transaction; report
  generation composes export and narrative creation under its caller's single
  commit.
- **Performance**: semantic validation parses the document and performs RDFS
  inference on each validated read; there is no projection cache.
- **Architecture**: ORM classes use `...Orm` because domain entity names already
  use `...Record`. Cross-context access uses published-language modules.

## 12. Traceability

| Element | Location |
| --- | --- |
| Aggregate, entities, and creation values | `vitarerum-api/app/cidoc_crm/in_situ_visit_mapping/domain/models.py` |
| Use cases and ports | `vitarerum-api/app/cidoc_crm/in_situ_visit_mapping/application/` |
| Mapping definition, context, engine, and shapes | `vitarerum-api/app/cidoc_crm/in_situ_visit_mapping/application/cidoc/` |
| Use of Collections ACL | `vitarerum-api/app/cidoc_crm/in_situ_visit_mapping/infrastructure/context_acl.py` |
| ORM mapping and repository | `vitarerum-api/app/cidoc_crm/in_situ_visit_mapping/infrastructure/` |
| HTTP routes and DTOs | `vitarerum-api/app/cidoc_crm/in_situ_visit_mapping/presentation/` |
| Downstream published language | `vitarerum-api/app/cidoc_crm/public.py` |
| Backend verification | `vitarerum-api/test/cidoc_crm/` |
| Angular viewer | `vitarerum-ui/src/app/features/collections/reports/components/in-situ-visit-cidoc-dialog/` |
| Visual model | `docs/diagrams/cidoc-crm-in-situ-visit-record-model.svg` |

## 13. Open decisions

1. What institution-owned base URI and permanence policy should identify graph
   resources?
2. Which evidence distinguishes a person, organization, group, physical place,
   and institution before a narrower CIDOC class is asserted?
3. Must a stored snapshot reproduce byte-equivalent JSON-LD indefinitely, or is
   remapping under newer declared rules acceptable?
4. What exact SHACL profile constitutes acceptance for external publication?
5. Should project export be idempotent per source revision, or intentionally
   append-only with explicit export provenance?
