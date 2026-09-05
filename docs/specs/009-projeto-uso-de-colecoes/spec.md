# SPEC-009 — Collection-use project and journals

| Field | Value |
| --- | --- |
| Identifier | SPEC-009 |
| Status | Implemented (with declared isolation, authorization, audit, journal-finalization, and delivery gaps) |
| Bounded context | `app/use_of_collections` — project phase |
| Derived from | Project and journal domain models, application use cases and queries, HTTP routes, Angular project feature, and Use of Collections tests |
| Related specs | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-013](../013-mapeamento-cidoc-crm/spec.md), [SPEC-019](../019-numeros-de-referencia/spec.md), [SPEC-022](../022-cifragem-e-armazenamento/spec.md), [SPEC-023](../023-fronteiras-e-envelope-de-erro/spec.md) |

## 1. Problem

Once access to a museum collection has been approved, the institution must
retain an operational record of what happened to the collection: which objects
were handled, by whom, when and where, which occurrences were observed, and
which publications or other scientific outputs resulted from the work.

Without that record, the approved access has no durable institutional memory
and cannot reliably support reporting, scientific-return review, or semantic
export.

## 2. Goal

Guide a collection-use project from `CREATED` to `COMPLETED` or `CANCELLED`,
while maintaining project-owned object snapshots, lifecycle events, personal
staff tasks, and three independent journals:

- the Object Access Log;
- the Object Occurrence Log;
- the Publication Log.

This spec distinguishes project, journal, and cross-context consistency
boundaries from route-level authorization. Current implementation gaps are
declared in Section 9. The primary security gap is that institution ownership
is not represented or enforced in this context.

## 3. Domain model and ubiquitous language

`CollectionUseProject` is the aggregate root for project metadata, lifecycle,
project-owned object snapshots, and use events. The three journals are separate
aggregate roots associated by `CollectionUseProjectId`; staff TODO items are
separate owner-scoped entities. This separation prevents journal growth from
turning the project into one unbounded transactional aggregate.

The current project, journal, object, and TODO models do not carry an
`institutionId`. Permission references identify actors, but authorization does
not compare the caller's institution with the resource's institution. Tenant
isolation is therefore not an enforced domain invariant (GAP-001).

- **Collection-use project**: approved execution of collection access, in
  `CREATED`, `IN_PROGRESS`, `COMPLETED`, or `CANCELLED` state.
- **Project object**: project-owned snapshot copied from an approved proposal or
  supplied later by staff.
- **Object Access Log**: register of effective object handling and quantities.
- **Object Occurrence Log**: register of noteworthy or anomalous events related
  to project objects.
- **Publication Log**: register of publications or outputs attributed to the
  project.
- **Use event**: `REQUESTED`, `STARTED`, `COMPLETED`, or `CANCELLED` lifecycle
  record.
- **Follow-up project**: independent project derived from a completed project
  and a non-empty subset of its object snapshots.
- **Project TODO item**: personal staff task associated with a project and owned
  by one active permission.

### 3.1 Aggregate and context relationships

| Boundary | Relationship |
| --- | --- |
| `CollectionUseProject` | Owns lifecycle, project metadata, object snapshots, and use events |
| `ObjectAccessLog` | Separate aggregate containing access entries and their attachments |
| `ObjectOccurrenceLog` | Separate aggregate containing occurrence entries and their attachments |
| `PublicationLog` | Separate aggregate containing publication entries and their attachments |
| Staff TODO items | Stored separately and isolated by project plus owner permission |
| `Proposal` | Creates and links the initial project on approval; is not required by a follow-up project |
| Identity | Supplies actors and read-side permission details |
| Reference Numbers | Allocates project and journal references transactionally |
| CIDOC-CRM mapping | Consumes the published project export view through an anti-corruption boundary |
| Scientific Return and Reports | Consume completed-project evidence through published interfaces |

## 4. Actors and authorization

| Actor | Implemented capabilities |
| --- | --- |
| Owning requester (`EXTERNAL`) | List and read owned projects; start, complete, or cancel them; write access and occurrence journals only while `IN_PROGRESS`; write the Publication Log while `IN_PROGRESS`; read available journals and official documents |
| `CURATORIAL` | Read all projects; use every generic staff project operation; write publications after completion; export eligible in-situ visits |
| `COLLECTIONS_MANAGEMENT` | Same generic project and journal capabilities as Curatorial; write publications after completion; export eligible in-situ visits |
| `DIRECTION` | Treated as generic staff for projects: read all projects, mutate lifecycle and metadata, manage objects and TODO items, write journals under staff rules, create follow-ups, and export eligible visits |
| `SYS_ADMIN` | Generic staff project, journal, TODO, follow-up, and export capabilities, but cannot write the Publication Log after completion |

Project detail and subordinate-resource access use one ownership policy: staff
can access every project globally, regardless of institution, while a non-staff
caller can access only a project whose `requestedBy` is their active permission.
A linked proposal with the same requester is also accepted for backward
compatibility. Follow-up projects have no proposal and rely directly on project
ownership.

Lifecycle endpoints do not impose a specific group beyond project access. The
Angular interface exposes the same lifecycle operations to the owning requester
and to staff, subject to state and object-count checks.

---

## 5. Lifecycle

| Command | Required state | Additional condition | Result | Event |
| --- | --- | --- | --- | --- |
| Proposal approval or follow-up creation | — | Initial approval is Curatorial; follow-up creation is staff-only | `CREATED` | `REQUESTED` |
| Start | `CREATED` | Project access | `IN_PROGRESS` | `STARTED` |
| Complete | `IN_PROGRESS` | At least one project object | `COMPLETED`, result `COMPLETED` | `COMPLETED` |
| Cancel directly | `CREATED` or `IN_PROGRESS` | Project access | `CANCELLED`, result `CANCELLED` | `CANCELLED` |
| Cancel through the linked proposal | Any project state | Owning requester cancels the proposal | `CANCELLED`, result `CANCELLED` | `CANCELLED` |

Editing metadata and adding or removing project objects are not lifecycle
transitions and currently create no use event.

## 6. Functional requirements

### FR-001 — Project materialisation and references

An initial project is materialised in the same transaction that approves its
proposal. It starts in `CREATED`, records `REQUESTED`, copies the proposal's
requested-object snapshots, and stores the proposal and requester identifiers.
Approval may therefore create an empty project.

A follow-up is the only project that can be created without a proposal. It
stores `originProjectId`, copies selected object snapshots, preserves the
original requester and intended use, and records its own `REQUESTED` event.

Production routes use the active policies from
[SPEC-019](../019-numeros-de-referencia/spec.md). The seeded institutional masks
are `PR-MUHNAC/COL/YYYY/XXXX` for projects, `OL-MUHNAC/COL/YYYY/XXXX` for access
logs, `OO-MUHNAC/COL/YYYY/XXXX` for occurrence logs, and
`OP-MUHNAC/COL/YYYY/XXXX` for publication logs. Older `CUP`, `OAL`, `OOL`, and
`PUB` values remain recognized as legacy formats rather than production
defaults.

### FR-002 — Lists and project detail

`GET /api/v1/collection-use-projects` is zero-based and accepts `page`, `size`
from 1 to 100, `status`, `type`, `requestedBy`, `originProjectId`, `dateFrom`,
`dateTo`, and `search`. Staff may list all projects and honor any requester
filter. "All" is currently global rather than institution-scoped. A non-staff
caller's `requestedBy` is always overwritten with their own active permission.

`GET /api/v1/collection-use-projects/{projectId}` returns project metadata,
result, origin, linked-proposal summary, requester and authorization views, and
project-owned objects. Requester and authorizer permission details are exposed
only to staff; an external owner receives `null` for those views.

### FR-003 — Starting a project

`POST /api/v1/collection-use-projects/{projectId}/start` requires `CREATED`,
changes the project to `IN_PROGRESS`, and records `STARTED`. Its optional note is
preserved on the event.

When the project has objects and no Object Access Log exists, starting creates
the log and one automatic entry per project object. Every entry has
`numberOfObjects = 1`, links to the project object, and attributes authorship to
the caller. An empty project creates no log; an existing log is left untouched.

After the database commit, the route e-mails the requester.

### FR-004 — Completing a project

`POST /api/v1/collection-use-projects/{projectId}/complete` requires
`IN_PROGRESS` and at least one project object. It sets `status = COMPLETED`,
`result = COMPLETED`, records `COMPLETED`, commits, and then e-mails the
requester. Journal presence or completion is not a prerequisite.

### FR-005 — Cancelling a project

`POST /api/v1/collection-use-projects/{projectId}/cancel` accepts an accessible
project in `CREATED` or `IN_PROGRESS`, sets `status = CANCELLED` and
`result = CANCELLED`, records the supplied reason as the event note, commits,
and then e-mails the requester.

The request schema currently accepts an empty reason. Direct cancellation of a
terminal project returns `409`. Proposal-driven cancellation is the deliberate
exception: cancelling an approved proposal forces its linked project to
`CANCELLED`, even when the project was already `COMPLETED`.

### FR-006 — Editing project metadata

`PATCH /api/v1/collection-use-projects/{projectId}` is staff-only and partially
updates title, purpose, begin date, and end date while the project is `CREATED`
or `IN_PROGRESS`. Omitted fields remain unchanged; explicit `null` is rejected
for these required values. Blank title or purpose and an effective end date
before the begin date return `422`. Terminal projects return `409`.

The edit creates no use event.

### FR-007 — Adding project objects

`POST /api/v1/collection-use-projects/{projectId}/objects` is staff-only and
accepts caller-supplied snapshots while the project is `CREATED` or
`IN_PROGRESS`. Each item requires an inventory number, display title, and object
name at the HTTP/domain boundaries. Neither the object nor its optional
collection association is resolved or checked against the caller's institution.

For a non-empty request, the command creates the Object Access Log if absent
and adds one automatic access entry for every new object. It refuses additions
when the access log is marked concluded. The current schema also permits an
empty `objects` list, which returns `201` without changing the aggregate.

### FR-008 — Removing project objects

`DELETE /api/v1/collection-use-projects/{projectId}/objects/{objectId}` is
staff-only and removes an object in an editable project when it has no dependent
work. A single untouched automatic access entry is removed with the object.

Other access entries, a concluded access log, occurrence entries, publication
entries, or their attachments block removal with
`409 PROJECT_OBJECT_HAS_DEPENDENCIES`; the response includes counts by
dependency type.

`POST .../objects/{objectId}/remove` performs the destructive variant only when
`confirmCascade = true` and a non-blank reason is supplied. It removes related
entries, commits their database deletion, and then deletes their stored files.
The reason is validated but is not persisted as an event or audit record.

### FR-009 — Object Access Log

The access journal has at most one log per project and is created lazily by
project start, object addition, or the first manual entry.

| Endpoint suffix | Behaviour |
| --- | --- |
| `POST /log-entries` | Adds an entry linked to one project object; `numberOfObjects >= 1`; optional observations and handling timestamp |
| `PATCH /log-entries/{entryId}` | Partially updates timestamp, quantity, and observations; explicit `null` clears observations |
| `DELETE /log-entries/{entryId}` | Deletes an entry and, after commit, its attachments |
| `GET /log-entries` | Lists entries with pagination and optional `added_by` filter; returns `accessLog: null` before creation |
| `GET /object-access-log` | Returns log metadata or `404` before creation |

An external owner may add, edit, delete, and attach files only while the project
is `IN_PROGRESS`. Staff may perform those operations in any project state while
the persisted log is not concluded. Reading follows project access regardless
of state.

### FR-010 — Object Occurrence Log

The occurrence journal also has at most one lazily created log. Entries require
a project object, `numberOfObjects >= 1`, occurrence date, non-empty location,
and non-empty detailed description. Testimonial is optional and explicit
`null` clears it during partial editing.

`POST /occurrence-entries`, `PATCH /occurrence-entries/{entryId}`,
`GET /occurrence-entries`, and `GET /object-occurrence-log` follow the same
ownership and phase rules as the access journal. There is currently no endpoint
to delete an entire occurrence entry; only its attachments can be removed.

### FR-011 — Journal attachments

Access, occurrence, and publication entries accept attachments. Every upload is
capped by the global `max_upload_bytes`, requires a non-empty description, and
requires `mediaType` to be one of `DOCUMENT`, `IMAGE`, `VIDEO`, or `OTHER`.
The value classifies the attachment; the server does not currently validate file
magic or require the bytes to match that category.

Upload storage is rolled back if entry persistence fails. Downloads require the
parent project, entry, and file reference to match; unknown resources return
`404`. Removing an attachment commits the metadata change before deleting the
stored file.

Files live under configured `DATA_DIR` and use encryption when configured, as
described by [SPEC-022](../022-cifragem-e-armazenamento/spec.md).

### FR-012 — Publication Log phase and role rule

Each project has at most one Publication Log, created with its first entry. All
entry and attachment writes use the same phase/role rule:

| Project state | Writer |
| --- | --- |
| `IN_PROGRESS` | Only the owning external requester |
| `COMPLETED` | `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, or `DIRECTION` |
| `CREATED` or `CANCELLED` | Nobody |

An entry requires a non-empty note and may reference one object belonging to the
same project. Create, edit, delete, paginated list, log metadata, official RRP
document, and attachment operations are exposed below the project resource.
Reading follows ordinary project access and is not limited by the write rule.

The core entry routes are
`POST /collection-use-projects/{project_id}/publication-entries` and
`PATCH`/`DELETE /collection-use-projects/{project_id}/publication-entries/{entry_id}`;
list, attachment, log-metadata, and document routes share the same prefix.

A publication entry referenced by a confirmed scientific-return decision cannot
be deleted and returns `409 PUBLICATION_ENTRY_IN_USE`. A foreign entry is
reported as `404` so its existence is not disclosed.

### FR-013 — Follow-up projects

`POST /api/v1/collection-use-projects/{projectId}/follow-ups` is staff-only and
requires a `COMPLETED` origin, a valid date interval, unique object IDs, and a
non-empty subset of the origin's objects. Omitted title or purpose inherits the
origin value; a supplied blank value is rejected.

The new project is `CREATED`, has no proposal, owns newly identified copies of
the selected snapshots, inherits requester and intended use, and records a
`REQUESTED` note identifying the origin. No journal or TODO item is copied. Its
requester can access it through direct project ownership. Because institution
ownership is absent, the follow-up also has no tenant boundary to inherit.

### FR-014 — Personal staff TODO items

Staff can list, create, rename, reposition, complete, reopen, and delete their
own TODO items below
`/api/v1/collection-use-projects/{projectId}/todo-items`. Text is trimmed,
non-empty, and at most 160 characters; position is non-negative. Item lookup is
scoped to project and owner, so another permission receives `404` rather than
learning that the item exists.

`GET /api/v1/collection-use-projects/my-todo-items` provides a paginated
owner-scoped dashboard with optional completion and project filters and
`recent` or `project` ordering. External callers are rejected.

### FR-015 — Official journal documents

The API renders institutional DOCX documents from persisted journal data:

| Endpoint | Document |
| --- | --- |
| `GET /object-access-log/document` | RAIS Object Access Log |
| `GET /object-occurrence-log/document` | ROC Object Occurrence Log |
| `GET /publication-log/document` | RRP Publication Register |

Requester contact comes from the project permission and falls back to the
linked proposal contact where supported. A missing log returns `404`, and
project ownership protects every download. The RRP rejects more than 1,000
entries with `422 DOCUMENT_ENTRY_LIMIT_EXCEEDED`; current RAIS and ROC rendering
read only the first 1,000 entries without checking whether more exist.

### FR-016 — Event history

`GET /api/v1/collection-use-projects/{projectId}/events` supports an optional
event-type filter and zero-based pagination with page size from 1 to 100. Events
are sorted by `occurredAt` ascending before pagination and expose actor, instant,
type, and optional note. Equal timestamps have no secondary ordering key.

### FR-017 — CIDOC-CRM export

`POST /api/v1/collection-use-projects/{projectId}/export-in-situ-visit-record`
is implemented by the CIDOC-CRM mapping context and is staff-only. It accepts
only an `IN_SITU_VISIT` project with execution evidence: the project must be
`COMPLETED` and contain a `COMPLETED` event.

The mapping context consumes a read-only published view containing project,
approval, objects, journal entries, attachments, and execution evidence. A
missing project returns `404`; wrong use type or missing evidence returns `409`.
The route uses the same global staff access model as the project context.

### FR-018 — Angular workflow projection

The Angular project feature provides lazy routes for the requester's projects,
staff lists by state, role-specific detail URLs, editing, follow-up creation,
personal TODOs, access and occurrence journals, Publication Log, and related
scientific-return and report entry points.

It uses standalone `OnPush` components, signals/resources, functional guards,
and a typed HTTP service. External journal guards allow access/occurrence pages
only during `IN_PROGRESS` and the Publication Log during `IN_PROGRESS` or
`COMPLETED`. Staff guards allow route entry and rely on API write rules.

The Curatorial, Collections Management, and Direction detail pages are thin
wrappers around the same staff component. Consequently, Direction currently
sees the same project mutation controls as other staff roles.

## 7. Enforced invariants

| ID | Invariant |
| --- | --- |
| INV-001 | Initial projects are created only by proposal approval; follow-ups identify their origin and require no proposal |
| INV-002 | A project completes only from `IN_PROGRESS` and with at least one project object |
| INV-003 | Every lifecycle transition appends a typed use event |
| INV-004 | Direct cancellation cannot change a terminal project |
| INV-005 | Proposal-driven cancellation may cancel a completed linked project |
| INV-006 | Project object snapshots are independent from proposal snapshots after project creation |
| INV-007 | A journal entry can reference only an object owned by the same project |
| INV-008 | A concluded access or occurrence log rejects entry mutation |
| INV-009 | Publication writes obey the project phase and caller group rule; same-institution membership is not enforced |
| INV-010 | A follow-up never inherits journals or TODO items |
| INV-011 | Staff TODO items are private to the permission that owns them, but project access remains global for staff |
| INV-012 | In-situ export requires the intended use plus completed-event evidence |

## 8. Principal failure responses

| Situation | Response |
| --- | --- |
| Missing or invalid authentication | `401` |
| Caller lacks staff or publication-writer group | `403 INSUFFICIENT_GROUP` or `ACCESS_DENIED` |
| Caller cannot access the project | `403 ACCESS_DENIED` |
| Project, log, entry, attachment, or TODO item not found | `404` |
| Invalid lifecycle transition, concluded log, or dependent object removal | `409` |
| Invalid date range, empty required text, invalid attachment category, or unconfirmed cascade | `422` |
| Oversized attachment | `413` |

Handled errors follow the shared envelope in
[SPEC-023](../023-fronteiras-e-envelope-de-erro/spec.md).

## 9. Declared implementation gaps

These are properties of the current repository, not hypothetical future work:

### GAP-001 — Institution isolation is absent (critical)

Projects, project objects, journals, attachments, events, and TODO items have no
institution owner. `assert_project_access` grants every staff permission global
access, list queries are unscoped, and the same policy protects journal
documents and CIDOC-CRM export. Project object collection IDs are accepted
without institutional validation.

**Required change:** add institution ownership to the project aggregate and
propagate it to repository queries and every subordinate-resource boundary;
derive it from the approved proposal or origin project; validate object and
permission references; migrate existing rows; and add cross-institution
negative tests for reads, mutations, files, TODOs, documents, and exports.

### GAP-002 — Access and occurrence logs cannot be finalized (high)

`ObjectAccessLog` and `ObjectOccurrenceLog` persist `dateConclusion` and
`curator`, and mutation code respects those fields, but no application command
or HTTP endpoint concludes or reopens either log. Only imported or directly
persisted data can reach the concluded state.

**Required change:** define authorized conclude/reopen commands, record the
curator and instant, expose them in the API and UI, and decide whether project
completion requires concluded logs.

### GAP-003 — Occurrence entries cannot be deleted (medium)

The Object Occurrence Log supports entry creation and editing but has no endpoint
for deleting a whole occurrence entry. Access and Publication Logs do.

**Required change:** either add a dependency-aware delete operation with file
cleanup or document occurrence records as intentionally immutable.

### GAP-004 — Staff journal writes ignore project lifecycle (high)

External access and occurrence writes are limited to `IN_PROGRESS`, but staff
may mutate entries in `CREATED`, `COMPLETED`, or `CANCELLED` projects whenever
the log is not concluded. Direct route navigation bypasses the UI's normal
visibility choices.

**Required change:** define one phase matrix for each command and enforce it in
the application layer for every adapter.

### GAP-005 — Project role governance is unresolved (high)

Direction is read-only during proposals but generic staff during projects, while
System Administration also receives broad project operations. Lifecycle routes
require only project access, so the owning requester and every staff group can
start, complete, or cancel through the API.

**Required change:** approve and publish a role-command matrix, then enforce it
consistently in use cases, routes, guards, and visible controls.

### GAP-006 — Authorization is split across routes and use cases (high)

Several project and journal use cases assume that the HTTP route already checked
project ownership, staff role, or publication ownership. For example, journal
commands receive a presentation-derived `restrict_to_in_progress` flag, and the
publication policy treats any non-staff actor as eligible during `IN_PROGRESS`
unless a preceding adapter checked ownership.

**Required change:** make application commands accept the actor and enforce
ownership, institution, role, and lifecycle policies themselves; keep only HTTP
error mapping in presentation code.

### GAP-007 — Cancellation and object changes are incompletely audited (high)

`ReasonRequest` accepts an empty direct-cancellation reason. Cascade removal
requires a non-blank reason but discards it; metadata edits and object
additions/removals also create no audit event.

**Required change:** trim and require cancellation reasons, define auditable
changes, and persist actor, reason, timestamp, and before/after data where
required.

### GAP-008 — Project-object snapshots are not authoritative (high)

Staff-supplied snapshots are not reloaded from the Collection Object Index or
validated against institution ownership. An empty `objects` list also returns
`201` without changing the aggregate.

**Required change:** accept authoritative object identifiers, resolve trusted
snapshots server-side, reject foreign-institution objects, and require at least
one item.

### GAP-009 — Attachment classification is not content validation (high)

Attachment `mediaType` is an operator-supplied enum. The server does not inspect
file signatures or verify that content and filename match the selected category.

**Required change:** introduce an explicit allowed-content policy, verify magic
bytes, and store detected media type separately from the business category.

### GAP-010 — Attachment filename handling is unsafe (high)

Attachment downloads interpolate stored upload filenames directly into
`Content-Disposition`, whereas generated documents use the shared safe helper.

**Required change:** use the helper for all attachment responses and test quotes,
CR/LF, Unicode, and traversal-like names.

### GAP-011 — RAIS and ROC can be silently truncated (high)

RAIS and ROC render at most 1,000 entries without comparing the repository
total. RRP correctly rejects overflow instead of producing an incomplete
institutional register.

**Required change:** apply one explicit overflow policy to all official
documents, preferably rejecting incomplete output with the existing typed error.

### GAP-012 — Post-commit side effects are not recoverable (high)

Database deletion commits before stored files are removed, and lifecycle e-mails
are sent after commit. There is no durable outbox, retry queue, or reconciliation
process, so failure can leave orphaned files or undelivered messages.

**Required change:** use durable idempotent jobs/outbox records for delivery and
file reclamation, with observable retry and reconciliation.

### GAP-013 — Project event ordering is unstable (medium)

Events are ordered only by timestamp. Equal timestamps have no sequence or ID
tie-breaker, and Angular also tracks timeline rows by timestamp.

**Required change:** persist a monotonic sequence or apply a stable secondary key
in backend ordering and frontend identity.

### GAP-014 — Authorization metadata is never populated (medium)

`authorisedBy` and `authorisedAt` exist in the project model and response, but
proposal approval does not populate them. Newly approved projects expose both as
`null` unless legacy or external persistence supplied values.

**Required change:** populate them from the approving actor and instant, or
remove the unused contract fields and derive approval evidence from the linked
proposal event.

### GAP-015 — Occurrence-log UI does not reflect conclusion (medium)

Unlike the access-log panel, the Angular occurrence panel does not use
`dateConclusion` to disable controls. A concluded log can present actions that
the API rejects.

**Required change:** project the same conclusion state and read-only behavior in
both panels.

### GAP-016 — Journal query parameter names diverge (medium)

Access and publication list routes accept `added_by`, while Angular query models
emit `addedBy`. The current panels do not use the filter, but a typed future call
would be silently ignored. Occurrence already exposes the camel-case
`reportedBy` alias.

**Required change:** adopt camel-case HTTP aliases consistently and cover request
serialization plus filtering with contract tests.

### GAP-017 — Workflow verification is incomplete (medium)

Backend coverage is extensive for individual operations, but lacks a complete
lifecycle-role matrix, project-event tie test, empty-reason and empty-object-list
tests, and RAIS/ROC overflow tests. Browser E2E does not cover the complete
approval-to-journals-to-completion journey.

**Required change:** add these matrices and a principal browser journey after the
role and journal-finalization policies are decided.

## 10. Acceptance criteria

### AC-001 — Lifecycle guards and events

A project starts only from `CREATED`, completes only from `IN_PROGRESS` with an
object, and direct cancellation rejects terminal states. Each successful command
records its event and result where applicable.

→ `test/use_of_collections/test_domain_models.py::test_submitted_project_records_requested_event`,
`::test_cancel_project_blocks_completed_project`,
`::test_cancel_project_blocks_already_cancelled_project`

→ `test/use_of_collections/test_api.py::test_complete_project_without_objects_returns_409`

### AC-002 — Lifecycle notifications follow commit

Starting, completing, and cancelling a project commit before e-mailing the
external requester.

→ `test/use_of_collections/test_api.py::test_start_project_notifies_external_requester`,
`::test_complete_project_notifies_external_requester`,
`::test_cancel_project_notifies_external_requester`

### AC-003 — Project editing is staff-only and non-lifecycle

Staff can partially edit non-terminal project metadata; external callers,
terminal projects, blank required values, and invalid date ranges are rejected;
editing creates no lifecycle event.

→ `test/use_of_collections/test_api.py::test_staff_can_patch_project_details`,
`::test_patch_project_requires_staff`,
`::test_patch_project_invalid_date_range_returns_422`,
`::test_patch_project_terminal_status_returns_409`

→ `test/use_of_collections/test_domain_models.py::test_edit_project_updates_metadata_without_lifecycle_event`,
`::test_edit_project_blocks_terminal_status`,
`::test_edit_project_rejects_invalid_effective_date_range`

### AC-004 — Object addition synchronizes the access journal

Staff can add objects only to editable projects; a missing access log is
created, an existing log receives automatic entries, and a concluded log blocks
the operation.

→ `test/use_of_collections/test_api.py::test_staff_can_add_project_objects`,
`::test_add_project_objects_requires_staff`,
`::test_add_project_objects_terminal_status_returns_409`,
`::test_add_project_objects_syncs_new_objects_to_existing_access_log`,
`::test_add_project_objects_creates_access_log_when_missing`,
`::test_add_project_objects_blocks_when_access_log_concluded`

### AC-005 — Object removal protects dependent records

Unused objects and untouched automatic entries can be removed directly;
dependent work yields a counted conflict; confirmed cascade removes related
entries and files.

→ `test/use_of_collections/test_api.py::test_staff_can_remove_unused_project_object`,
`::test_remove_project_object_removes_automatic_log_entry`,
`::test_remove_project_object_blocks_with_dependencies`,
`::test_remove_project_object_cascade_requires_confirmation`,
`::test_remove_project_object_cascade_removes_dependencies`

### AC-006 — Access journal preserves project ownership and edit semantics

Access entries are linked to project objects, support multiple handling records,
partial edits and explicit observation clearing, reject foreign or concluded-log
mutations, and expose absence without manufacturing a log.

→ `test/use_of_collections/test_api.py::test_add_log_entry_returns_201_with_access_log_created`,
`::test_log_entry_records_several_accesses_to_the_same_object`,
`::test_edit_log_entry_is_partial_and_clears_observations`,
`::test_delete_log_entry_returns_404_for_another_project`,
`::test_delete_log_entry_on_concluded_access_log_is_blocked`,
`::test_get_object_access_log_returns_404_without_entries`

### AC-007 — Occurrence journal validates required incident data

Occurrence entries require an owned project object, quantity, time, location,
and description; partial edits can clear testimony; a missing journal returns
`404` through its metadata endpoint.

→ `test/use_of_collections/test_api.py::test_add_occurrence_entry_returns_201_with_occurrence_log_created`,
`::test_edit_occurrence_entry_updates_editable_fields`,
`::test_edit_occurrence_entry_is_partial_and_clears_testimonial`,
`::test_get_object_occurrence_log_returns_404_without_entries`

### AC-008 — Attachments are described, bounded, and entry-scoped

Invalid attachment categories and missing descriptions are rejected; storage
uses the configured encrypted adapter; download and deletion remain scoped to
the owning entry and project. This criterion does not establish institution
isolation.

→ `test/use_of_collections/test_api.py::test_log_entry_attachment_invalid_media_type_returns_422`,
`::test_log_entry_attachment_requires_description`,
`::test_log_entry_attachment_uses_configured_encrypted_storage`,
`::test_download_log_entry_attachment_unknown_reference_returns_404`,
`::test_delete_log_entry_attachment_removes_file`,
`::test_occurrence_entry_attachment_requires_description`

### AC-009 — Publication writes obey phase and role

The owning requester writes while `IN_PROGRESS`; Curatorial, Collections
Management, or Direction staff write after `COMPLETED`; other combinations are
rejected; a referenced object must belong to the project.

→ `test/use_of_collections/test_api.py::test_add_publication_entry_in_progress_external_creates_log`,
`::test_add_publication_entry_staff_while_in_progress_rejected`,
`::test_add_publication_entry_staff_once_completed_ok`,
`::test_add_publication_entry_external_once_completed_rejected`,
`::test_add_publication_entry_in_created_status_rejected`,
`::test_add_publication_entry_rejects_foreign_collection_use_object_id`

### AC-010 — Publication evidence cannot be erased

Publication entries support edit, deletion, attachments, pagination, and RRP
rendering, but an entry used by a confirmed scientific-return decision is
protected.

→ `test/use_of_collections/test_api.py::test_edit_publication_entry_updates_note`,
`::test_delete_publication_entry_removes_entry_and_attachments`,
`::test_delete_confirmed_scientific_return_entry_is_blocked`,
`::test_publication_entry_attachment_upload_and_download`,
`::test_download_publication_log_document_fills_the_complete_rrp`

### AC-011 — Follow-ups are independent projects

Only staff can derive a follow-up from a completed project, with a valid date
range and non-empty unique object subset. The project copies snapshots but not
journals, and remains accessible to the original requester.

→ `test/use_of_collections/test_api.py::test_staff_can_create_follow_up_project`,
`::test_follow_up_project_requires_staff`,
`::test_follow_up_project_rejects_non_completed_origin`,
`::test_follow_up_project_rejects_empty_object_ids`,
`::test_follow_up_project_rejects_invalid_date_range`,
`::test_follow_up_project_does_not_copy_journal_logs`,
`::test_follow_up_project_owner_can_access_created_follow_up_project`

### AC-012 — TODO items are permission-private

Staff task lists are isolated by active permission; only the owner can update,
toggle, or delete an item; external users are rejected; the dashboard returns
only the current profile's items. Staff project access itself remains global.

→ `test/use_of_collections/test_project_todos.py::test_todo_items_are_isolated_by_staff_permission`,
`::test_todo_update_toggle_and_delete_require_item_owner`,
`::test_external_callers_cannot_use_project_todos`,
`::test_dashboard_postits_list_only_current_staff_profile_items`,
`::test_todo_text_is_trimmed_and_limited`

### AC-013 — Official documents use persisted journals and ownership

RAIS, ROC, and RRP documents are filled from their corresponding logs; missing
logs return `404`; another requester cannot download the document.

→ `test/use_of_collections/test_api.py::test_download_object_access_log_document_fills_the_rais_form`,
`::test_download_object_access_log_document_is_denied_to_other_researchers`,
`::test_download_object_access_log_document_returns_404_without_log`,
`::test_download_object_occurrence_document_fills_the_roc_form`,
`::test_download_object_occurrence_document_returns_404_without_log`,
`::test_download_publication_log_document_fills_the_complete_rrp`

### AC-014 — Response contracts remain stable

Representative project detail, list, events, journal, error, and access-denied
shapes remain frozen by golden tests.

→ `test/use_of_collections/test_golden_contracts.py::test_golden_project_detail_and_list_shapes`,
`::test_golden_project_events_envelope_shape`,
`::test_golden_log_entries_shapes`,
`::test_golden_occurrence_entries_shapes`,
`::test_golden_publication_entries_shapes`,
`::test_golden_error_bodies`,
`::test_golden_access_denied_body`

### AC-015 — Visit export requires operational evidence

Only an in-situ project completed with a corresponding event can become a
CIDOC-CRM visit record.

→ `test/use_of_collections/test_domain_models.py::test_visit_execution_evidence_rejects_created_project`,
`::test_visit_execution_evidence_rejects_in_progress_project`,
`::test_visit_execution_evidence_accepts_completed_project_with_event`

→ `test/cidoc_crm/test_export_in_situ_visit_use_case.py::test_export_rejects_non_in_situ_visit_use_type`,
`::test_export_rejects_in_situ_visit_without_execution_evidence`

### AC-016 — Angular projects the role- and phase-specific workflow

External and staff routes lead to the appropriate detail pages; lifecycle
controls follow project state and object count; journal guards enforce external
phase access; project objects, follow-ups, TODOs, and journal panels call the
typed project API.

→ frontend: `projects.routes.spec.ts`,
`project-detail-page.component.spec.ts`,
`project-staff-detail-page.component.spec.ts`,
`project-log-pages.spec.ts`,
`project-log-access.guard.spec.ts`,
`project-external-detail.guard.spec.ts`,
`project-api.service.spec.ts`

## 11. Non-functional requirements

- **Transaction boundaries**: each aggregate mutation is persisted in the
  request transaction; cross-aggregate approval and proposal cancellation are
  explicitly orchestrated application operations.
- **External effects**: lifecycle e-mails and storage cleanup happen after the
  relevant commit, subject to the limitations in Section 9.
- **Sensitive data**: collection records, requester details, journal notes, and
  attachments are sensitive application data.
- **Tenant isolation**: the actor carries an institution identifier, but the
  project context does not enforce it; GAP-001 is a release-blocking security
  concern for multi-institution operation.
- **Contract stability**: golden tests freeze representative project and journal
  JSON shapes; OpenAPI remains the per-endpoint schema source.
- **Architecture**: downstream contexts consume the project through
  `app.use_of_collections.public`; the domain remains framework-free.
- **File storage**: relative references remain below configured `DATA_DIR`, with
  encryption at rest when enabled.

## 12. Traceability

| Element | Location |
| --- | --- |
| Project, objects, journals, entries, events, and TODO entities | `vitarerum-api/app/use_of_collections/domain/models.py` |
| Lifecycle, objects, follow-ups, and Proposal-to-Project bridge | `vitarerum-api/app/use_of_collections/application/use_cases/project.py` |
| Access and occurrence journal commands | `vitarerum-api/app/use_of_collections/application/use_cases/journal.py` |
| Publication journal commands and phase/role policy | `vitarerum-api/app/use_of_collections/application/use_cases/publication.py` |
| Personal staff TODO commands | `vitarerum-api/app/use_of_collections/application/use_cases/project_todos.py` |
| Ownership and list/detail queries | `vitarerum-api/app/use_of_collections/application/authorization.py`, `application/queries.py` |
| Actor institution and Identity permission views | `vitarerum-api/app/identity/public.py` |
| Project lifecycle and TODO HTTP routes | `vitarerum-api/app/use_of_collections/presentation/project_routes.py` |
| Journal and generated-document HTTP routes | `vitarerum-api/app/use_of_collections/presentation/journal_routes.py` |
| DOCX builders and renderers | `vitarerum-api/app/use_of_collections/presentation/*_document.py`, `infrastructure/*_docx.py` |
| Persistence and project export reader | `vitarerum-api/app/use_of_collections/infrastructure/repositories.py` |
| Published language | `vitarerum-api/app/use_of_collections/public.py` |
| CIDOC-CRM export | `vitarerum-api/app/cidoc_crm/in_situ_visit_mapping/` |
| Angular routes, pages, components, guards, models, and service | `vitarerum-ui/src/app/features/collections/projects/` |
| Public HTTP contract | OpenAPI at `/openapi.json`; shared rules in `docs/api_contracts/README.md` |

## 13. Open questions

1. What is the authoritative institution owner for an approved project and its
   follow-ups, and how will existing project and journal data be migrated?
2. Which roles should own project start, completion, cancellation, and journal
   editing, particularly for Direction and System Administration?
3. Should access and occurrence logs gain explicit conclude/reopen commands, and
   should project completion require their conclusion?
4. Should the external requester be allowed to add scientific outputs after
   project completion, when publications commonly appear later?
5. Must cascade reasons, metadata changes, and object changes become durable
   audit events?
6. Should project-object snapshots be resolved server-side from the Collection
   Object Index rather than trusted from the caller?
7. Should every generated register reject overflow consistently instead of RAIS
   and ROC silently rendering the first 1,000 entries?
8. Should e-mail and storage cleanup use a durable outbox/reconciliation worker?
