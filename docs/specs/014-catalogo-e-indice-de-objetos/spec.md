# SPEC-014 — Collection Catalogue and Searchable Object Index

| Field | Value |
| --- | --- |
| Identifier | SPEC-014 |
| Status | Implemented (with declared security, resilience, ingestion, and search-accuracy gaps) |
| Bounded context | `app/collection_object_index` |
| Derived from | Backend, frontend, migrations, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-007](../007-identidade-e-acesso/spec.md), [SPEC-008](../008-proposta-uso-de-colecoes/spec.md) |

## 1. Problem

The museum's scientific collection data is maintained in spreadsheets. Staff
need to find collection objects without losing the source of each result, while
the institution needs explicit control over who may curate the catalogue and
replace the files that feed the index.

## 2. Goal and scope

This context:

- organises scientific collections into collection areas;
- assigns curators to individual collections;
- ingests `.xlsx` source documents and indexes their rows synchronously;
- lets staff search indexed objects, optionally within one collection;
- preserves the collection, source document, sheet, and row coordinates of
  every result; and
- builds an object snapshot that downstream collection-use workflows can
  attach to a proposal.

It is not the authoritative collection-management system. The spreadsheet is
the imported source, and this context owns a searchable projection of it.
Semantic/vector search, background ingestion, source-file download, and
row-level read restrictions are outside the current implementation.

## 3. Ubiquitous language

| Term | Meaning |
| --- | --- |
| **Collection area** | Administrative or scientific classification that groups collections. It does not grant access. |
| **Collection** | Unit of catalogue organisation, curator assignment, and document-management scope. |
| **Curator assignment** | Link between one `CURATORIAL` permission and one collection. |
| **Source document** | Uploaded `.xlsx` file in `UPLOADED`, `INDEXED`, or `ERROR` state. |
| **Object mapping** | Declares the inventory-number, display-title, object-name, description, and searchable columns. |
| **Indexed row** | One non-empty spreadsheet row, including its cells and source coordinates. |
| **Object snapshot** | Stable search-result projection used by downstream proposal workflows. |
| **Match reason** | Compact explanation of why an indexed row matched a query. |

## 4. Domain model and boundaries

### 4.1 Aggregate responsibilities

- `CollectionArea` owns its identifier and trimmed, non-empty name.
- `Collection` owns its area reference and trimmed, non-empty name.
- `CuratorAssignment` records the collection, permission, assigning actor, and
  assignment timestamp.
- `SourceDocument` owns file provenance, content hash, lifecycle state,
  mapping, row count, timestamps, and soft-deletion state.
- `ObjectSnapshotMapping` requires an inventory-number column and at least one
  display-title column. User commands additionally require at least one
  searchable column.
- Indexed rows are a replaceable read projection, not independent domain
  aggregates.

### 4.2 Context dependencies

- Identity publishes the caller permission and curator-candidate details.
- File storage owns the encrypted or local stored bytes behind an opaque file
  reference.
- PostgreSQL provides full-text and trigram search.
- Collection-use workflows consume the object snapshot; they do not query the
  source spreadsheet directly.

No domain event or audit trail is currently emitted for catalogue, assignment,
upload, mapping, reindex, or deletion actions.

## 5. Authorisation

Authorisation is enforced by backend use cases. Frontend menus and hidden
buttons are usability features, not security boundaries.

| Capability | `SYS_ADMIN` | `COLLECTIONS_MANAGEMENT` | assigned `CURATORIAL` | unassigned `CURATORIAL` | `DIRECTION` | non-staff |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Search every indexed collection | Yes | Yes | Yes | Yes | Yes | No (`403`) |
| List the collection catalogue | Yes | Yes | Yes | Yes | Yes | No (`403`) |
| Manage areas, collections, and curator assignments | Yes | No | No | No | No | No |
| Manage source documents in any collection | Yes | Yes | No | No | No | No |
| Manage source documents in an assigned collection | Yes | Yes | Yes | No | No | No |
| List curator candidates | Yes | No | No | No | No | No |

A collection area never expands a curator's scope. A curator gains management
rights only through an explicit assignment to a collection. Every staff group
has read access to the complete searchable index; document-management scope
does not restrict search results.

## 6. Functional requirements

### FR-001 — Collection areas

Only `SYS_ADMIN` may list, create, rename, or remove collection areas. Names
are trimmed and must be non-empty. The list includes the number of collections
in each area. A duplicate name returns `409
COLLECTION_AREA_NAME_ALREADY_EXISTS`; an unknown area returns `404
COLLECTION_AREA_NOT_FOUND`; an area containing a collection cannot be removed
and returns `409 COLLECTION_AREA_IN_USE`.

### FR-002 — Collections

Only `SYS_ADMIN` may create, rename, move, or permanently remove a collection.
A collection must reference an existing area. Names are trimmed, non-empty,
limited to 255 characters by the API, and unique according to the database
comparison rules. Moving uses `POST
/admin/collection-data-sources/collections/{collectionId}/move-area` with
`areaId` in the body.

Permanent removal deletes indexed rows, all live and soft-deleted source
document records, curator assignments, and the collection record. Stored files
are reclaimed only after the database commit.

### FR-003 — Server-computed management scope

Each collection response includes `manageable`, computed from the caller and
curator assignments. A curator whose permission no longer resolves in Identity
remains listed by `permissionId`, with a null name and email.

### FR-004 — Curator assignments

Only `SYS_ADMIN` may assign or remove curators. The target permission must
exist in Identity and belong to `CURATORIAL`; otherwise the API returns `404
PERMISSION_NOT_FOUND` or `422 PERMISSION_NOT_CURATORIAL`. Assignment is
idempotent at the collection/permission pair and records `assignedAt` and the
assigning permission internally.

`GET /admin/collection-data-sources/curator-candidates` returns only
`CURATORIAL` permissions with `permissionId`, name, and email. Eligibility does
not itself grant collection scope.

### FR-005 — Column preview

`POST .../collections/{collectionId}/documents/columns-preview` validates and
parses an uploaded workbook, then returns the case-insensitively sorted union
of columns found in its data rows. It neither stores the file nor updates the
index. The caller must be allowed to manage the target collection.

The preview is the first step in the Angular upload flow: the user chooses the
mapping before confirming the upload.

### FR-006 — Valid source workbook and upload limits

The upload must be a ZIP-based OOXML workbook containing both
`[Content_Types].xml` and `xl/workbook.xml`; the system does not trust the
filename extension alone. The parser then opens it with `openpyxl` in
read-only, data-only mode.

The configured request limit is currently 25 MiB (`max_upload_bytes`), and the
hard application limit is 20,000 indexed data rows per workbook. Oversized
requests return `413 FILE_TOO_LARGE`. A workbook that cannot be parsed, or that
exceeds the row limit after parsing, is reported as an invalid spreadsheet.

The row limit is currently a code constant, not a configurable setting.

### FR-007 — Required object mapping

An upload requires:

- one inventory-number column;
- one or more display-title columns, whose non-empty values are joined in
  order;
- an optional object-name column, falling back to the display title;
- zero or more description columns; and
- one or more searchable columns.

Every selected column must exist in the parsed workbook. An empty searchable
selection returns `422 SOURCE_DOCUMENT_SEARCHABLE_COLUMNS_EMPTY`; an unknown
column or otherwise invalid mapping returns `422
SOURCE_DOCUMENT_MAPPING_INVALID`.

### FR-008 — Spreadsheet parsing

For each worksheet, the first non-empty row is its header and every following
non-empty row becomes an indexed row. Completely empty rows are skipped. Cells
are normalised to trimmed text: booleans are lowercase, dates use ISO format,
and integral floats omit `.0`. Empty headers become `Column N`; exact duplicate
headers receive stable numeric suffixes such as `(2)`.

Only non-empty cells are retained. Formulas are read through their cached
calculated values because the parser uses `data_only=True`; the application
does not calculate formulas.

### FR-009 — Synchronous ingestion and document lifecycle

Upload, parsing, mapping validation, index replacement, and document-state
updates run synchronously in the request transaction.

| Situation | Result |
| --- | --- |
| New content | Store a new file and document, then index it. |
| Identical live content in the same collection | Reuse the existing document, apply the submitted mapping, and rebuild its index from the submitted bytes. No new file is stored. |
| Same sanitised filename with different content | Create a new document version, soft-delete the previous document, remove its rows, commit, then reclaim the previous file. |
| Parser failure or more than 20,000 rows while creating a new document | Keep the new file and persist the document as `ERROR` with the message. |
| Mapping validation failure | Reject the request and remove the newly stored file; no `ERROR` document is retained. |

Content identity is the SHA-256 hash within a collection. Deduplication is by
content even when the submitted filename differs. Filenames are reduced to a
safe basename before storage, but the helper does not explicitly truncate them
to the database's 255-character limit.

### FR-010 — Indexed content and retained cells

Only values from the mapping's searchable columns are concatenated into the
`content` used by full-text, substring, and approximate matching. Updating the
mapping rebuilds that content.

The index nevertheless retains the complete map of all non-empty cells in each
row, and the search API returns that complete map. Searchable-column selection
therefore controls matching, not field-level disclosure.

`contentMatchesSearchableColumns = false` identifies a migrated legacy
document whose persisted content has not yet been rebuilt under the named
column rule. For such documents, empty searchable-column metadata falls back
to all retained cell keys until the document is reindexed.

### FR-011 — Mapping update and reindex

`PUT .../documents/{documentId}/object-mapping` reads the stored file,
validates the complete mapping, replaces all indexed rows, and saves the new
mapping in one transaction. A validation or parsing failure rolls back the
mapping and index changes.

`POST .../documents/{documentId}/reindex` rebuilds the index from the stored
file and current mapping. A parser failure marks the document `ERROR` and
preserves a false legacy-content indicator. A missing stored file returns
`404 SOURCE_DOCUMENT_NOT_FOUND`.

The Angular UI warns before rebuilding legacy searchable content.

### FR-012 — Source-document deletion

Deleting a source document removes its indexed rows and soft-deletes its
record. The stored file is deleted only after the database transaction commits.
Soft-deleted documents are excluded from document lists and search results.

There is no restore, source-file download, or retry-cleanup endpoint.

### FR-013 — Object search

`GET /objects/search` requires a non-empty `q`, accepts an optional
`collectionId`, uses zero-based `page`, and accepts a `size` from 1 to 100
(default 20). It returns the total and the requested page of live indexed rows.

Matching combines PostgreSQL `plainto_tsquery('simple', ...)`, case-insensitive
substring matching, and `pg_trgm.word_similarity` above the fixed `0.4`
threshold. Results are ordered by the provisional sum of full-text rank and
word similarity, then by source-document identifier and row number.

The backend validates only that `q` has at least one character; direct API
clients can currently submit whitespace-only input. The Angular UI trims the
query and never sends an empty value.

### FR-014 — Provenance, highlight, and match reason

Every hit returns collection, source-document identifier, filename, sheet,
one-based spreadsheet row number, all retained cells, and a PostgreSQL-generated
highlight. The Angular client escapes the highlight and re-enables only the
backend's `<b>` markers as `<mark>`.

At most one match reason is returned, with this priority:

`exact > substring > text > approximate`

`columns` may be empty when the matching method is known but its source column
cannot be attributed reliably. A semantic reason is not returned because
semantic search is not implemented.

### FR-015 — Object snapshot

A hit has an object snapshot only when its mapped cells produce a non-empty
inventory number, display title, and object name. The snapshot contains:

- `inventoryNumber`;
- `displayTitle`;
- `objectName`;
- optional joined description;
- `category`, currently the collection name.

When mandatory mapped values are empty, `objectSnapshot` is null and the UI
shows that the result cannot provide the mapped proposal snapshot.

### FR-016 — Search collection facet

`GET /objects/search/collections` returns the complete collection catalogue to
staff, including collections with no indexed rows. Each entry contains up to
12 alphabetically ordered distinct searchable-column labels and their total
count. The Angular search page displays at most four labels in its scope
summary and allows the user to search all collections or one selected
collection.

## 7. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | Document-management scope is decided by the backend for each collection. |
| INV-002 | A collection area never grants curator access. |
| INV-003 | User-initiated indexing requires a mapping with at least one searchable column. |
| INV-004 | Indexed search content is derived only from searchable columns, except for the declared legacy fallback. |
| INV-005 | Every indexed row retains its collection, document, sheet, and row provenance. |
| INV-006 | A failed mapping update does not replace the previously committed mapping. |
| INV-007 | A deleted source document cannot contribute live search results. |
| INV-008 | Database deletion is committed before the corresponding stored file is reclaimed. |
| INV-009 | Search is staff-wide and is independent of document-management scope. |

## 8. Error contract

| Condition | Response or state |
| --- | --- |
| Non-staff access | `403` |
| Missing collection, area, permission, document, or stored document file | `404` with the resource-specific error code |
| Duplicate collection or area name | `409` |
| Removing an area in use | `409 COLLECTION_AREA_IN_USE` |
| Unsupported workbook container | `415 INVALID_FILE_FORMAT` |
| Upload above configured byte limit | `413 FILE_TOO_LARGE` |
| Invalid mapping | `422 SOURCE_DOCUMENT_MAPPING_INVALID` |
| No searchable columns | `422 SOURCE_DOCUMENT_SEARCHABLE_COLUMNS_EMPTY` |
| New-document parse/row-limit failure | Committed source document in `ERROR` |
| Preview, mapping-update, or deduplicated-upload parse failure | `422 INVALID_SPREADSHEET`; no new `ERROR` document |

## 9. Acceptance and test traceability

| Capability | Automated evidence |
| --- | --- |
| Workbook parsing and normalisation | `test_parser.py` |
| Catalogue, areas, curators, upload API, mapping, and deletion | `test_api.py` |
| Domain scope, deduplication, versioning, reindex, and rollback behaviour | `test_use_cases.py` |
| Search endpoint contract and staff restriction | `test_search_api.py` |
| PostgreSQL full-text/trigram search, reasons, facets, and stable pagination | `test_search_postgres.py` |
| Angular catalogue administration and upload/mapping flow | `collection-data-sources-page.component.spec.ts` |
| Angular search, filters, empty states, snapshots, and safe highlighting | `object-search-page.component.spec.ts` |

### Acceptance scenarios

1. Given a manageable collection and a valid `.xlsx`, when staff previews the
   file, selects a valid mapping, and uploads it, then the source document is
   `INDEXED` and its non-empty data rows become searchable.
2. Given identical content already live in a collection, when it is uploaded
   again with a valid mapping, then the existing document is reused and its
   index is rebuilt without storing a second file.
3. Given a live document with the same filename but different content, when a
   replacement is uploaded, then only the new version contributes results and
   the previous stored file is reclaimed after commit.
4. Given a curator not assigned to a collection, when they attempt to preview,
   upload, map, reindex, or delete one of its documents, then the request is
   forbidden.
5. Given any staff permission, when it searches without a collection filter,
   then results may come from every indexed collection and include complete
   source provenance.
6. Given a soft-deleted source document, when staff searches for content that
   existed only in that source, then no result is returned.
7. Given a mapping update that references an unknown column, when it is
   submitted, then the prior mapping and index remain committed.
8. Given a search highlight containing untrusted markup, when Angular renders
   it, then arbitrary markup is escaped and only supported highlight markers
   are rendered.

## 10. Non-functional requirements and current constraints

- Production search requires PostgreSQL and the `pg_trgm` extension; the
  generated `tsv` column uses the `simple` text-search configuration.
- Upload bytes are read in 1 MiB chunks but accumulated in memory before
  parsing. `openpyxl` reads workbook rows in streaming mode.
- Ingestion and reindexing are synchronous and share the request/database
  transaction. The 20,000-row limit bounds rows but not sheet count, column
  count, decompressed OOXML size, or parser execution time.
- Search ranking and the `0.4` similarity threshold are explicitly
  provisional and require calibration with representative museum data.
- Stored files live outside a public web root. The production storage adapter
  is governed by the storage/encryption specification; this context keeps only
  opaque references.
- The search response can be large because each hit includes all non-empty
  cells, in addition to a highlight and snapshot.

## 11. Known gaps and required improvements

| Priority | Gap | Required change |
| --- | --- | --- |
| High | The Angular search explanation says accent differences are ignored, but the PostgreSQL query does not use `unaccent` or another accent-folding strategy. | Either implement and test accent-insensitive indexing/querying, including a migration for the generated search vector, or remove that UI claim. |
| High | Selecting searchable columns does not prevent other row cells from being returned to every staff user. | Confirm the data-disclosure policy. If searchable columns are also intended as a visibility boundary, filter `cells` in the API/index and add authorisation/privacy tests. |
| High | Search is intentionally global for every staff group, including `DIRECTION` and curators outside their assigned collections. | Obtain an explicit institutional decision and add collection-level read scope if collection data is sensitive. |
| High | Stored-file deletion occurs after commit and has no durable retry/outbox. A storage failure can return an error after the database change is already committed and leave an orphaned file. | Add idempotent asynchronous cleanup with retry and observability for document deletion, collection deletion, and same-name replacement. |
| Medium | Failed source files are retained but cannot be downloaded for diagnosis or replaced by document identifier. | Add a protected download/diagnostic flow or revise the retention rationale and UI guidance. |
| Medium | The fixed row limit does not bound workbook complexity or ZIP expansion, and ingestion is synchronous. | Add OOXML decompression/complexity safeguards, time/resource limits, metrics, and consider queued ingestion for operational scale. |
| Medium | Whitespace-only API queries pass request validation. | Trim and reject blank queries in the backend domain/application boundary. |
| Medium | Filename sanitisation does not enforce the 255-character persistence limit. | Normalise and cap filenames before persistence, preserving an extension and collision-safe storage key. |
| Medium | Catalogue mutation and ingestion have no audit events or optimistic concurrency protection. | Record actor/action/outcome events and define conflict handling for concurrent uploads, replacements, mapping updates, and deletions. |
| Medium | Formula values depend on workbook caches and can silently be empty when caches are absent. | Document the requirement to save/recalculate workbooks before upload or detect formula cells without cached values and warn the user. |
| Low | Collection and area uniqueness follows database comparison rules and is not explicitly case-insensitive. | Decide whether names that differ only by case are valid; enforce the decision consistently. |
| Low | Search results cannot be sorted or inspected beyond relevance pagination, and there is no direct source-document download. | Validate the MVP need for sort, export, source inspection, or deep links before expanding the UI. |

## 12. Traceability

| Element | Location |
| --- | --- |
| Domain model | `vitarerum-api/app/collection_object_index/domain/` |
| Use cases and authorisation | `vitarerum-api/app/collection_object_index/application/` |
| Spreadsheet parser, persistence, and PostgreSQL search | `vitarerum-api/app/collection_object_index/infrastructure/` |
| HTTP contract | `vitarerum-api/app/collection_object_index/presentation/` and `/openapi.json` |
| Catalogue and source-management UI | `vitarerum-ui/src/app/features/admin/collection-data-sources/` |
| Staff object-search UI | `vitarerum-ui/src/app/features/objects/` |
| Backend tests | `vitarerum-api/test/collection_object_index/` |

## 13. Open product decisions

1. Is staff-wide read access to every collection a deliberate data policy?
2. Do searchable columns control matching only, or must they also control which
   cells are disclosed in results?
3. Should a curator assignment ever inherit from a collection area?
4. What retention and recovery policy applies to failed and soft-deleted source
   documents?
5. Should accent-insensitive matching be guaranteed for Portuguese catalogue
   data?
6. At what volume should synchronous ingestion move to a queued job with
   progress and retry?
7. Should semantic search become a fourth search mechanism or a separately
   governed search path?
