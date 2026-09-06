# SPEC-012 — Document templates by use type

| Field | Value |
| --- | --- |
| Identifier | SPEC-012 |
| Status | Implemented (with declared validation, atomicity, authorization-UX, and versioning gaps) |
| Bounded context | `app/document_templates` |
| Written from | `app/document_templates/`, `test/document_templates/test_api.py`, and the public and administration Angular features |
| Related specs | [SPEC-010](../010-submissao-publica/spec.md), [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-022](../022-cifragem-e-armazenamento/spec.md) |

## 1. Problem

Citizens submitting a collection-use request may need institutional forms but
do not necessarily know which forms apply or where to obtain them. Distributing
files manually by e-mail or from an unmanaged static page allows obsolete
copies to remain in circulation.

## 2. Goal

Maintain a staff-curated catalogue of downloadable document templates by use
type. Expose only active templates through a narrow unauthenticated API and
offer catalogue management to authorized staff.

This spec describes the implemented behavior. Properties that the current
system does not guarantee are listed in Section 8.

## 3. Domain model and boundaries

`DocumentTemplate` is the aggregate root and stores:

- its identifier and `UseType`;
- title, description, mandatory indicator, active state, and display order;
- the current filename and storage reference;
- the permission that originally uploaded it and the original upload time.

The aggregate validates only that its title is not blank. The application layer
coordinates catalogue mutations through a repository and a file-storage port.
The shared storage adapter owns path confinement, atomic byte writes, and
optional encryption. Public Submission and the authenticated proposal form are
downstream consumers of the public read contract; they do not access this
aggregate directly.

## 4. Actors and trust boundaries

| Actor | Capability |
| --- | --- |
| Unauthenticated visitor | List and download active templates for one use type |
| Authenticated external requester | Uses the same public template API from the authenticated proposal form |
| Curatorial, Collections Management, Direction, System Administration | May call every management endpoint |
| System Administrator UI | Receives the Document templates menu entry |

The `/p/admin/document-templates` Angular route is protected only by the parent
authentication guard. Non-system staff can open it by direct URL and are
accepted by the API, but the menu does not advertise it to them. An external
user can also open the page by direct URL, but management requests are rejected
with `403`; the route itself has no staff guard.

Uploaded filenames and bytes are untrusted. Browser `accept=.docx` is guidance
only; the API performs the authoritative byte and path checks.

## 5. Public-channel requirements

### FR-001 — Active templates by use type

`GET /api/v1/public/document-templates?useType={UseType}` requires one valid
`UseType`: `IN_SITU_VISIT`, `EXHIBITION`, or `OTHER`. It returns only active
templates of that type, ordered by `displayOrder` and then `title`. No matches
produce `200` with an empty array; a missing or invalid query value produces
`422`.

The public item contains only:

```json
{
  "id": "template-id",
  "title": "Safety form",
  "description": "Fill and sign",
  "mandatory": true
}
```

It does not expose use type, active state, display order, filename, storage
reference, uploader, or upload time.

### FR-002 — Public download hides inactive records

`GET /api/v1/public/document-templates/{id}/file` downloads the current file
only when the template is active. An unknown identifier, inactive template, or
missing stored file returns the same `404 DOCUMENT_TEMPLATE_NOT_FOUND`, even if
the caller knows the identifier.

The response uses `Content-Disposition: attachment` with a basename-only ASCII
fallback and RFC 5987 UTF-8 filename. Header control characters and path
separators are removed.

The response media type is inferred from the stored filename. Because creation
does not require a `.docx` filename, valid accepted bytes uploaded with another
extension may later be served with that extension's MIME type rather than the
DOCX MIME type.

### FR-003 — Angular consumption

Both `/submit-proposal` and the authenticated proposal-submission page load the
public list whenever a use type is selected. They show title, optional
description, the informational Mandatory badge, and a direct public download
link. The public page localizes this copy in Portuguese and English.

Template-list loading has no dedicated visible error state in these form
sections: an unavailable request resolves to the resource error state while the
template list appears absent.

### FR-004 — Mandatory is informational

`mandatory` labels a template for the requester. Neither the public-submission
API nor the authenticated proposal workflow verifies that a completed instance
of every mandatory template was attached.

## 6. Management requirements

### FR-005 — Authorization and catalogue listing

Every `/api/v1/document-templates` endpoint requires a bearer token,
`X-Permission-Id`, and one of the four staff groups. External permissions receive
`403`.

`GET /api/v1/document-templates` returns active and inactive records. Optional
`useType` filters one type; without it, the flat response is ordered by use type,
display order, and title. It is not paginated. The administration page groups
that flat response by the three known use types in the browser.

Staff items add `useType`, `active`, `displayOrder`, `fileName`, and
`uploadedAt`. The persisted `uploadedBy` and internal storage reference are not
returned.

### FR-006 — Creation

`POST /api/v1/document-templates` accepts `multipart/form-data`:

| Field | Required | Default or behavior |
| --- | --- | --- |
| `file` | yes | byte content must pass the DOCX container check |
| `useType` | yes | one of the three `UseType` values |
| `title` | yes | must not be blank after domain inspection |
| `description` | no | `""` |
| `mandatory` | no | `false` |
| `active` | no | `true` |
| `displayOrder` | no | `0` |

The file is read with the configurable `max_upload_bytes` limit, which defaults
to 25 MiB. Exceeding it returns `413 FILE_TOO_LARGE`.

The current format check opens the file as ZIP and requires
`[Content_Types].xml`. It does not inspect `word/document.xml`, OOXML content
types, relationships, or document readability. Failure returns
`415 INVALID_FILE_FORMAT`.

The untrusted filename is reduced to a safe basename before building
`document_templates/{templateId}/{fileName}`. An empty or unusable name becomes
`template.docx`. The response is `201` with the staff item.

### FR-007 — Full metadata replacement through PATCH

`PATCH /api/v1/document-templates/{id}` applies replacement semantics to all
editable metadata: title, description, mandatory, active, and display order.
The Angular form sends every field.

At the API schema, only `title` is required. Omitting other fields resets them
to `""`, `false`, `true`, and `0`; this is not a partial merge. An unknown
template returns `404`.

### FR-008 — File replacement

`PUT /api/v1/document-templates/{id}/file` validates the new bytes and safe
filename using the creation rules. It saves the new file, changes the aggregate
reference, commits, and then removes the old file when its reference differs.

Replacement does not change `uploadedAt` or `uploadedBy`, so those fields keep
describing the original publication rather than the current file revision.

### FR-009 — Staff download

`GET /api/v1/document-templates/{id}/file` serves the current file whether the
template is active or inactive. Missing metadata or bytes returns the same
`404 DOCUMENT_TEMPLATE_NOT_FOUND` used by the public endpoint. Filename and
media-type behavior matches FR-002.

### FR-010 — Deletion

`DELETE /api/v1/document-templates/{id}` deletes the database row, commits, and
then deletes the stored file. A successful operation returns `204`; an unknown
template returns `404`.

There is no domain reference check, soft deletion, archive, or restore. The
catalogue does not record which template a requester previously downloaded.

### FR-011 — Administration projection

The standalone, OnPush Angular page at `/p/admin/document-templates` provides:

- creation with all catalogue fields and one `.docx` file;
- grouping by use type;
- inline full-metadata editing;
- staff download and file replacement;
- browser-native confirmation before permanent deletion;
- loading and API error feedback.

The page uses signals and `resource()` for local state. It has no dedicated
component test; only the HTTP management service is unit-tested.

## 7. Invariants and error behavior

| ID | Invariant |
| --- | --- |
| INV-001 | Public queries and direct downloads never expose an inactive template |
| INV-002 | The public response never exposes curation or storage metadata |
| INV-003 | Every accepted file is a ZIP containing `[Content_Types].xml` |
| INV-004 | Every stored filename is reduced to a confined basename |
| INV-005 | External permissions cannot use management endpoints |
| INV-006 | Metadata must contain a non-blank title |
| INV-007 | `mandatory` does not currently reject a proposal without that template |

| Condition | Result |
| --- | --- |
| Missing/invalid `useType` or multipart field | `422` |
| Upload exceeds configured limit | `413 FILE_TOO_LARGE` |
| File fails the current container check | `415 INVALID_FILE_FORMAT` |
| Template metadata, inactive public record, or stored bytes not found | `404 DOCUMENT_TEMPLATE_NOT_FOUND` |
| External caller uses a management endpoint | `403` |

## 8. Known gaps and required improvements

| ID | Gap | Required change |
| --- | --- | --- |
| GAP-001 | The DOCX check accepts any ZIP containing `[Content_Types].xml`; it does not prove that the upload is a usable Word document. | Validate required WordprocessingML parts and declared content types, and reject malformed/encrypted containers safely. |
| GAP-002 | Upload filenames are not required to end in `.docx`, while download MIME is inferred from the filename. | Normalize the stored extension to `.docx` and always serve the trusted DOCX MIME with `nosniff`. |
| GAP-003 | API schemas do not bound title, description, filename length, or display order to database-safe/business-safe values. A whitespace title raises an uncaught domain `ValueError`. | Add trimmed Pydantic constraints aligned with database columns and map domain validation failures to a stable `422`/`400` error. |
| GAP-004 | Replacing a file with the same sanitized filename reuses the same storage reference and overwrites the old bytes before database commit. A commit failure cannot restore the old content. | Store every revision under a unique immutable reference; switch the row on commit and delete the previous reference afterward. |
| GAP-005 | After a successful delete commit, file deletion can fail. The row is gone, the API errors, and a retry returns `404` without reclaiming the orphan. | Use a durable cleanup job/outbox or tombstone so post-commit deletion is retryable and observable. |
| GAP-006 | Replacement retains the original `uploadedAt` and `uploadedBy`, and the model has no version or revision history. | Record current-file uploader/time and immutable revisions; expose the intended audit fields to staff. |
| GAP-007 | All four staff groups are authorized by the API, but only System Administration sees the menu; the route itself permits any authenticated profile to render. | Decide the owning roles and align API policy, menu visibility, and a route guard with that decision. |
| GAP-008 | Management and public lists are unpaginated and ordering has no ID tie-breaker. | Add bounded pagination where catalogue growth warrants it and a deterministic secondary `id` order. |
| GAP-009 | Public and authenticated forms do not show a dedicated template-load failure, so required guidance can silently disappear. | Render an accessible error/retry state and prevent misleading “no templates” presentation on request failure. |
| GAP-010 | The administration page has no component tests for creation, grouping, editing, replacement, deletion confirmation, authorization UX, or errors. | Add focused Vitest coverage for the delivered management workflow. |
| GAP-011 | `mandatory` is informational and no attachment is linked to a template/version. | Before enforcement, define template-instance identity, version matching, legacy behavior, and server-side validation. |
| GAP-012 | CORS is application-global rather than a guarantee owned by these public routes. | Keep explicit non-local origins and avoid documenting per-route CORS isolation not enforced by the code. |
| GAP-013 | Templates carry no institution owner. Public queries select only use type and active state, and staff management checks role without institution scope; the catalogue is shared deployment-wide. | Explicitly retain a deployment-wide catalogue or introduce institutional ownership and public institution selection before supporting separate institutional catalogues. Add tests for the chosen visibility and management boundary. |

## 9. Acceptance criteria

### AC-001 — Public active list and narrow projection

Covered by `test/document_templates/test_api.py::test_public_list_returns_only_active_for_use_type` and
the public/authenticated proposal-form component tests that render template
links and Mandatory badges.

### AC-002 — Public visibility and safe download filename

Covered by `test/document_templates/test_api.py::test_public_download_streams_docx`,
`test/document_templates/test_api.py::test_public_download_missing_returns_404`,
`test/document_templates/test_api.py::test_public_download_hides_inactive_template`, and
`test/document_templates/test_api.py::test_public_download_uses_safe_content_disposition`.

### AC-003 — Staff authorization and inactive access

Covered by `test/document_templates/test_api.py::test_staff_list_includes_inactive`,
`test/document_templates/test_api.py::test_staff_download_serves_inactive_template`,
`test/document_templates/test_api.py::test_staff_download_forbidden_for_external`, and
`test/document_templates/test_api.py::test_staff_endpoints_forbidden_for_external`.

### AC-004 — Creation and failed-commit cleanup

Covered by `test/document_templates/test_api.py::test_staff_create_persists_template_and_file`,
`test/document_templates/test_api.py::test_staff_create_sanitizes_traversal_filename`,
`test/document_templates/test_api.py::test_staff_create_rejects_non_docx`, and
`test/document_templates/test_api.py::test_staff_create_cleans_up_file_when_commit_fails`.

### AC-005 — Metadata, replacement, and deletion

Covered by `test/document_templates/test_api.py::test_staff_patch_updates_metadata`,
`test/document_templates/test_api.py::test_staff_patch_missing_returns_404`,
`test/document_templates/test_api.py::test_staff_replace_file_swaps_stored_bytes`, and
`test/document_templates/test_api.py::test_staff_delete_removes_template_and_file`. The same-filename rollback and
post-commit cleanup failure paths in GAP-004/GAP-005 are not covered.

### AC-006 — Angular HTTP contract

The management-service tests cover list filtering, create multipart fields,
full metadata update, replacement, deletion, and blob download. GAP-010 remains
open because the administration component itself has no test.

## 10. Non-functional requirements

- **Confidentiality and integrity**: production requires the shared file
  encryption key. Local/test may intentionally store plaintext files.
- **Path safety**: storage resolves references below `DATA_DIR`, rejects escape,
  and atomically renames temporary writes into place.
- **Least privilege**: the backend, not menu visibility, is the authorization
  boundary.
- **Memory use**: uploads and downloads are currently fully materialized as
  `bytes`/`Response`, bounded on upload by `max_upload_bytes` but not streamed.
- **Accessibility**: management controls use native form elements, but permanent
  deletion relies on the browser's native confirmation dialog.

## 11. Traceability

| Element | Location |
| --- | --- |
| Aggregate root | `vitarerum-api/app/document_templates/domain/models.py` |
| Commands, queries, and ports | `vitarerum-api/app/document_templates/application/` |
| SQLAlchemy repository and record | `vitarerum-api/app/document_templates/infrastructure/` |
| Public/staff routes and schemas | `vitarerum-api/app/document_templates/presentation/` |
| File validation and storage | `vitarerum-api/app/shared/uploads.py`, `app/shared/file_storage.py` |
| Backend acceptance tests | `vitarerum-api/test/document_templates/test_api.py` |
| Administration UI | `vitarerum-ui/src/app/features/admin/document-templates/` |
| Public consumers | `vitarerum-ui/src/app/features/public/submit-proposal/`, `features/collections/proposals/pages/submit/` |
| HTTP client contracts | `vitarerum-ui/src/app/features/admin/services/document-template-management.service.spec.ts` |

## 12. Open decisions

1. Which staff groups own catalogue curation, and should non-system staff see it
   in the menu?
2. Must existing download URLs remain stable after file replacement, or may
   each revision receive a new reference?
3. When `mandatory` becomes enforceable, how will a submitted document prove
   which template and revision it satisfies?
4. Is permanent deletion acceptable, or must historical template revisions be
   retained for institutional audit?
