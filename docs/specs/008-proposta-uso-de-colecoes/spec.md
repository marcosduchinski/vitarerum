# SPEC-008 — Collection-use proposal

| Field | Value |
| --- | --- |
| Identifier | SPEC-008 |
| Status | Implemented (with declared isolation, authorization, audit, contract, and delivery gaps) |
| Bounded context | `app/use_of_collections` — proposal phase |
| Derived from | Proposal domain model, application use cases and queries, HTTP routes, Angular proposal feature, and Use of Collections tests |
| Related specs | [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-010](../010-submissao-publica/spec.md), [SPEC-007](../007-identidade-e-acesso/spec.md), [SPEC-019](../019-numeros-de-referencia/spec.md), [SPEC-023](../023-fronteiras-e-envelope-de-erro/spec.md) |
| Architecture decision | [ADR-0001](../../architecture/adr/0001-submission-channel.md) |

## 1. Problem

A request to access museum collections starts as a conversation: a researcher
describes what they need before every object, date, and document is necessarily
known. The institution must turn that request into a traceable decision while
preserving requester ownership, staff responsibility, supporting evidence, and
the relationship to any project created by approval.

## 2. Goal

Guide a request from its opening message through assignment, clarification,
document review, and a final decision. Approval creates the Collection Use
Project; rejection and cancellation do not create one. Public intake remains a
separate upstream context and enters this workflow only after e-mail
confirmation.

This spec distinguishes aggregate invariants from route-level authorization and
documents current implementation gaps in Section 9. The most significant gap is
that the proposal aggregate and its persistence model do not carry institution
ownership, even though the authenticated actor does.

## 3. Domain model and ubiquitous language

`Proposal` is the aggregate root for the proposal phase. It owns requested
objects, requested-document records, submitted-document metadata,
document-correction items, and proposal events. `Conversation` is a separate
aggregate created in the same transaction and addressed by `ProposalId`.
`CollectionUseProject` is another aggregate and is materialised only by
approval.

The current `Proposal` and `CollectionUseProject` records do not contain an
`institutionId`. Their permission references are plain identifiers and access
decisions do not compare the caller's institution. Institution isolation is
therefore not an enforced domain invariant (GAP-001).

- **Proposal**: formal request in `SUBMITTED`, `PENDING`, `APPROVED`,
  `REJECTED`, or `CANCELLED` state.
- **Submission channel**: explicit `AUTHENTICATED` or `PUBLIC` origin.
- **Requester**: an Identity permission in `requestedBy`. A public proposal may
  temporarily carry only `requesterContact` until approval provisions Identity.
- **Requested object**: proposal-owned snapshot of an object selected from the
  collection catalogue.
- **Requested document**: free-text document type that staff asks the requester
  to provide.
- **Document correction item**: request to replace a submitted document or
  supply a missing one; its state is `REQUESTED` or `RESOLVED`.
- **Proposal event**: typed record of a workflow or lifecycle action.
- **Direction lane**: temporary reassignment of a `PENDING` proposal to a
  Direction permission, entered by `REFERRED_TO_DIRECTION` and left by
  `DIRECTION_CLARIFIED`.

### 3.1 Aggregate relationships

| Aggregate | Relationship |
| --- | --- |
| `Proposal` | Owns proposal-phase state and references the resulting project ID after approval |
| `Conversation` | Has the same proposal ID and always starts with one message |
| `CollectionUseProject` | Receives independent copies of approved metadata and requested-object snapshots |
| Identity | Supplies actors and permission views; provisions a public requester at approval |
| Public Submission | Supplies confirmed public proposals and the scoped amendment adapter |
| Reference Numbers | Allocates proposal and project references transactionally |

## 4. Actors and authorization

| Actor | Implemented capabilities |
| --- | --- |
| Requester (`EXTERNAL`) | Submit through the authenticated UI, read owned proposals, add/remove requested objects, upload documents, use the conversation, and cancel an owned proposal |
| `CURATORIAL` | Staff capabilities plus approval and rejection |
| `COLLECTIONS_MANAGEMENT` | Read all proposals, edit, assign/take over, forward, request documents/corrections, and manage proposal content |
| `SYS_ADMIN` | Same generic staff capabilities exposed by the routes, but not approval or rejection |
| `DIRECTION` | Read an individually assigned proposal and return it to Curatorial or Collections Management with a reason |

The backend submission endpoint accepts any authenticated permission; the
Angular authenticated submission route is guarded for `EXTERNAL`. Section 9
records this difference, the Direction list-scope gap, and the absence of
institution isolation for staff access and recipient resolution.

---

## 5. Lifecycle

| Command | Required state | Resulting state | Event |
| --- | --- | --- | --- |
| Authenticated or confirmed public submission | — | `SUBMITTED` | `SUBMITTED` |
| Assign / take over | any non-terminal state | `PENDING` | `ASSIGNED` |
| Forward | `PENDING` | `PENDING` | `FORWARDED` |
| Request documents | `PENDING` | `PENDING` | `DOCUMENTS_REQUESTED` |
| Submit a document | `PENDING` | `PENDING` | `DOCUMENTS_SUBMITTED` |
| Request corrections | `PENDING` | `PENDING` | `DOCUMENT_CORRECTIONS_REQUESTED` |
| Submit satisfied corrections | `PENDING` | `PENDING` | `DOCUMENT_CORRECTIONS_SUBMITTED` |
| Refer to Direction | `PENDING`, current assignee | `PENDING` | `REFERRED_TO_DIRECTION` |
| Return to staff | `PENDING`, current Direction assignee | `PENDING` | `DIRECTION_CLARIFIED` |
| Approve | `PENDING` | `APPROVED` | `APPROVED` |
| Reject | `PENDING` | `REJECTED` | `REJECTED` |
| Cancel by requester | anything except `REJECTED` or `CANCELLED` | `CANCELLED` | `CANCELLED` |

Metadata edits and requested-object additions/removals are not lifecycle
transitions and currently create no proposal event.

---

## 6. Functional requirements

### RF-001 — Authenticated submission

`POST /api/v1/proposals` accepts `multipart/form-data`, creates the proposal in
`SUBMITTED`, creates its conversation with one opening message, and records the
`SUBMITTED` event in the same transaction. The caller's active `PermissionId`
becomes `requestedBy`, and `submissionChannel` is `AUTHENTICATED`.

At the API boundary, `title`, `intendedUse`, `purpose`, `beginDate`, `endDate`,
and all three `initialMessage*` fields are optional. If both dates are present,
the end date cannot precede the start date. `intendedUse`, when present, is
`EXHIBITION`, `IN_SITU_VISIT`, or `OTHER`.

The API accepts zero to five initial files. Each file is capped at 10 MiB and
must contain PDF, JPEG, PNG, or DOCX data. Initial files are stored as
`REQUESTER_ATTACHMENT`, independent of their filename or media type.

### RF-002 — Authenticated Angular form

The Angular route `/p/collections/proposals/submit` is guarded for `EXTERNAL`
and presents a narrower workflow than the API:

- only `IN_SITU_VISIT` can be submitted; `EXHIBITION` and `OTHER` are shown but
  blocked with an availability notice;
- intended use, both dates, a valid date interval, opening-message subject and
  body, and one to five supporting files are required;
- active document templates are shown for the selected intended use;
- after success, the requester is taken to the generic proposal detail.

### RF-003 — No requested objects or project at submission

Submission does not accept structured requested objects. The requester first
describes the need in prose and may later add catalogue snapshots through
`POST /api/v1/proposals/{proposalId}/requested-objects`. A proposal may be
approved with no requested objects, producing an empty project.

No project aggregate is persisted at submission. Rejected or pre-approval
cancelled proposals never materialise a project.

### RF-004 — Reference numbers

The proposal receives `VRP-YYYYMMDD-XXXX` on submission. Approval allocates a
`CUP-XXXXXXXX` reference for the project. Both use the shared transactional
allocator and uniqueness-retry boundary described by
[SPEC-019](../019-numeros-de-referencia/spec.md).

### RF-005 — Lists, filters, and detail access

`GET /api/v1/proposals` is paginated with zero-based `page`, `size` from 1 to
100, repeated `status` filters with OR semantics, and optional `type`,
`assigned_to`, `requested_by`, `date_from`, `date_to`, and `search` filters.

For non-staff callers, the application query overwrites `requested_by` with the
caller's active permission. Operational staff can list all proposals and apply
any supported filter. "All" is currently global rather than institution-scoped.
Individual proposal detail, events, documents, and conversation use the shared
ownership policy: staff can read all regardless of institution, external
callers can read only their own, and Direction can read only a proposal assigned
to their active permission. Direction is nevertheless treated as generic staff
by the list query (GAP-001 and GAP-002).

### RF-006 — Atomic submission and staff broadcast

If initial upload or persistence fails, every file already written for that
submission is reclaimed. The proposal, conversation, opening event, in-app
notifications, and database metadata commit together.

On successful submission, staff permissions in Curatorial, Collections
Management, Direction, and System Administration are notified, excluding the
submitting permission. In-app recipients are distinct permissions; post-commit
e-mails are deduplicated by user. Recipient lookup is global by group and does
not restrict the broadcast to the submitter's institution (GAP-001).

### RF-007 — Requested objects

`POST /api/v1/proposals/{proposalId}/requested-objects` appends one or more
caller-supplied object snapshots. The API requires `inventoryNumber`,
`displayTitle`, and `objectName`; collection identifiers/names and a brief
description are optional. `DELETE` on the requested-object subresource removes
one snapshot.

Owners and operational staff may perform these operations while the proposal is
`SUBMITTED` or `PENDING`; Direction is blocked. Terminal proposals reject
changes. Approval copies the snapshots into independent project-owned
`CollectionUseObject` entities.

### RF-008 — Assignment and forwarding

`POST /api/v1/proposals/{proposalId}/assign` assigns a specified operational
staff permission or defaults to the caller, moves a non-terminal proposal to
`PENDING`, and records `ASSIGNED`. It supports taking over another staff
member's assignment.

`POST /api/v1/proposals/{proposalId}/forward` requires `PENDING`, assigns a
specified operational staff permission, and records `FORWARDED`. Direction is
not a valid target for either generic command; the dedicated Direction command
must be used.

An unknown target returns `404`; an external or otherwise invalid target returns
`422 INVALID_PERMISSION_TARGET`. Assigning or forwarding to oneself sends no
notification or e-mail. Taking over notifies the previous assignee. Assignment
and forwarding notify the new assignee in-app before commit and by e-mail after
commit. Target validation checks activity and operational role, but not whether
the target belongs to the same institution as the proposal or caller (GAP-001).

### RF-009 — Requested documents

`POST /api/v1/proposals/{proposalId}/request-documents` requires operational
staff and a `PENDING` proposal. It appends requested-document records, leaves
the proposal `PENDING`, and records `DOCUMENTS_REQUESTED`.

Document type is a free-text value object: whitespace is trimmed, the value must
be non-empty, and its maximum length is 128 characters. The current request
schema permits an empty `requiredDocuments` list and this command does not send
an e-mail or notification to the requester.

### RF-010 — Authenticated document submission

`POST /api/v1/proposals/{proposalId}/documents` is available to an authorized
requester or operational staff while the proposal is `PENDING`. Unlike initial
submission, this endpoint accepts **only a valid DOCX file**. The upload uses the
global `max_upload_bytes` limit rather than the initial-submission 10 MiB limit.

`documentType` follows the same trimmed, non-empty, 128-character free-text
rule. The document and `DOCUMENTS_SUBMITTED` event are persisted together. If
the aggregate or repository operation fails after storage, the new file is
reclaimed. An assigned staff permission is notified unless it is the uploader;
the e-mail is sent after commit.

Authorized users may list, download, and attach proposal documents to
conversation messages. Download authorization is checked against the parent
proposal.

### RF-011 — Document-correction request

`POST /api/v1/proposals/{proposalId}/request-document-corrections` requires
operational staff, at least one item, and a `PENDING` proposal. It records
`DOCUMENT_CORRECTIONS_REQUESTED` without changing state.

Each item has a free-text `documentType`, a reason, and an optional
`documentId`. With an ID, the document must belong to the proposal and is marked
for replacement; without one, the type scopes a missing-document request. A
proposal with neither a resolvable authenticated requester nor
`requesterContact` returns `409 MISSING_REQUESTER_CONTACT`.

After the correction items commit, the Public Submission adapter creates and
sends the scoped amendment invitation described by
[SPEC-010](../010-submissao-publica/spec.md).

### RF-012 — Correction satisfaction

The amendment channel accepts only document types and document IDs within the
token's still-open scope. A replacement upload atomically detaches the flagged
document and reclaims its stored file.

Completion resolves only the named open items and succeeds only if each has a
current document of the requested type. For a replacement, the satisfying
document must have an ID different from the flagged document. Unsatisfied work
returns `422 UNSATISFIED_CORRECTION`; a successful submission records
`DOCUMENT_CORRECTIONS_SUBMITTED` and leaves the proposal `PENDING`.

### RF-013 — Staff metadata editing

`PATCH /api/v1/proposals/{proposalId}` lets operational staff change `title`,
`intendedUse`, `beginDate`, and `endDate` on `SUBMITTED` or `PENDING` proposals.
Omitted fields remain unchanged; explicit `null` clears a field. The effective
date interval is validated against both supplied and stored values.

Terminal proposals return `409 INVALID_TRANSITION`; an invalid interval returns
`422 INVALID_DATE_RANGE`. Metadata editing creates no proposal event.

### RF-014 — Direction lane

`POST /api/v1/proposals/{proposalId}/refer-to-direction` requires a caller in
Curatorial or Collections Management who is the current assignee of a
`PENDING` proposal. The target must be an active Direction permission and the
reason must be non-blank. The command preserves `PENDING`, changes
`assignedTo`, records `REFERRED_TO_DIRECTION` with actor, target, and trimmed
reason, and notifies the target in-app.

`POST /api/v1/proposals/{proposalId}/return-to-staff` is the exit. It requires
the current Direction assignee, an active Curatorial or Collections Management
target, and a non-blank response. It preserves `PENDING`, reassigns the proposal,
records `DIRECTION_CLARIFIED`, and notifies the target in-app.

The Angular router gives Direction a dedicated read-only detail page without a
Messages tab and redirects Direction away from the standard assignment detail.
Other mutating routes block Direction, although their machine-readable error
codes are not yet uniform (Section 9).

### RF-015 — Rejection

`POST /api/v1/proposals/{proposalId}/reject` is restricted to `CURATORIAL` and
requires `PENDING`. It changes the state to `REJECTED`, records the event, and
adds a conversation message addressed to the requester in the same transaction.
After commit, it sends the rejection e-mail.

### RF-016 — Approval and project materialisation

`POST /api/v1/proposals/{proposalId}/approve` is restricted to `CURATORIAL` and
requires `PENDING` plus a valid date interval. In one transaction it:

1. changes the proposal to `APPROVED` and records `APPROVED`;
2. creates `CollectionUseProject` in `CREATED` and records `REQUESTED`;
3. copies the approved `title`, `purpose`, `beginDate`, and `endDate` from the
   command body rather than from nullable proposal fields;
4. uses the proposal's intended use, defaulting to `OTHER` when absent;
5. clones every requested-object snapshot into the project;
6. links both aggregates by their identifiers.

Approval with no requested objects creates an empty project.

### RF-017 — Public-requester provisioning at approval

For a public proposal with `requestedBy = null`, approval first verifies that
the proposal is approvable, then asks Identity to provision or reuse the
requester's e-mail and permission. The resulting permission becomes both the
proposal requester and project requester.

For a new account, the route sends the temporary-access e-mail only after
commit and does not also send the ordinary approval e-mail. For an existing
account, it does not reset credentials and sends the approval e-mail after
commit. A public proposal rejected or cancelled before approval never reaches
provisioning.

### RF-018 — Requester cancellation

`POST /api/v1/proposals/{proposalId}/cancel` requires the caller's active
permission to equal `requestedBy`. It rejects an already `CANCELLED` or
`REJECTED` proposal, but allows cancellation from `SUBMITTED`, `PENDING`, and
`APPROVED`.

If a project is linked, cancellation forces that project to `CANCELLED`, sets
its result to `CANCELLED`, and records its event regardless of the previous
project state, including `COMPLETED`. This proposal-driven exception is the only
path that cancels a completed project.

### RF-019 — Conversation

`GET /api/v1/proposals/{proposalId}/conversation` returns a paginated message
thread. `POST .../conversation/messages` adds a message while the proposal is
not terminal and may reference documents belonging to that proposal. The
conversation aggregate rejects new messages after approval, rejection, or
cancellation.

Public proposals without a provisioned requester still have their opening
message, but the staff Angular page hides its reply composer until an active
requester identity exists. The Direction-specific page does not expose the
conversation.

### RF-020 — Event history

`GET /api/v1/proposals/{proposalId}/events` sorts events by timestamp descending
before applying zero-based pagination with page size from 1 to 100. Each event
may expose its actor, target permission, note, and timestamp. A public
`SUBMITTED` event may have no actor until Identity is provisioned; Angular
renders a generic external principal in that case. Equal timestamps have no
secondary ordering key (Section 9).

### RF-021 — Angular workflow projection

The Angular feature provides separate lazy routes for submission, the
requester's proposals, unassigned proposals, own assignments, other staff
assignments, approved proposals, rejected/cancelled proposals, editing, and the
Direction lane. It uses standalone components, signals/resources, route guards,
and a typed HTTP service.

Public pre-approval proposals arrive with `requestedBy = null`; the client
synthesizes a display-only external principal from `requesterContact`. This is a
presentation fallback and does not create an Identity permission.

## 7. Enforced invariants

| ID | Invariant |
| --- | --- |
| INV-001 | An authenticated proposal has `requestedBy`; a public proposal has `requesterContact` until Identity resolves it |
| INV-002 | Proposal submission creates exactly one opening conversation message and a `SUBMITTED` event |
| INV-003 | No persisted project exists before approval |
| INV-004 | Only a Curatorial permission can approve or reject a proposal; same-institution membership is not currently enforced |
| INV-005 | Approval requires `PENDING` and creates the linked project in the same transaction |
| INV-006 | A correction item is resolved only when a matching current document satisfies it |
| INV-007 | An amendment cannot modify documents outside its token scope |
| INV-008 | An external permission reads only proposals it owns; staff access is not institution-scoped |
| INV-009 | A rejected proposal cannot be cancelled |
| INV-010 | Entering and leaving the Direction lane preserves `PENDING` and records actor, target, and reason |
| INV-011 | Only the current assignee can refer to Direction or return to operational staff |
| INV-012 | Proposal-driven cancellation also cancels any linked project |

## 8. Principal failure responses

| Situation | Response |
| --- | --- |
| Missing or invalid authentication | `401` |
| Caller lacks the required group | `403 INSUFFICIENT_GROUP` or command-specific Direction code |
| Caller cannot access the proposal | `403 ACCESS_DENIED` |
| Proposal, document, conversation, or target permission not found | `404` |
| Invalid lifecycle transition or missing requester contact | `409` |
| Invalid date range, document type, correction list, or permission target | `422` |
| Oversized file | `413` |
| Unsupported initial content or non-DOCX later upload | `415` |

Handled failures follow the shared envelope in
[SPEC-023](../023-fronteiras-e-envelope-de-erro/spec.md).

## 9. Declared implementation gaps

These are properties of the current repository, not hypothetical future work:

### GAP-001 — Institution isolation is absent (critical)

Proposal and project records do not store an institution identifier, and their
permission identifiers are not institution-scoped foreign keys. Staff detail
access and list queries are global, assignment targets are validated by role and
activity but not by institution, requested collection snapshots are not checked
against institutional ownership, and the submission broadcast resolves every
permission in each staff group across all institutions.

**Required change:** add explicit institution ownership to proposal and project
aggregates and persistence; derive it at intake; enforce it in repositories,
authorization, assignment, object validation, recipient resolution, and
follow-up project creation; migrate existing rows; and add cross-institution
negative tests for every read, mutation, download, notification, and e-mail
path.

### GAP-002 — Direction list access is broader than detail access (high)

Direction detail access is restricted to the active assignment, but
`GET /api/v1/proposals` treats Direction as generic staff. A direct API caller
can list summaries for proposals not assigned to that Direction permission; the
Angular UI normally supplies its own `assigned_to` filter.

**Required change:** enforce Direction assignment scope in the application query
and repository criteria; do not rely on a client-supplied filter.

### GAP-003 — Pre-approval project wire representation is misleading (high)

Before approval, no project is persisted, but `ProposalDetailResponse` emits a
placeholder `collectionUseProject` with empty IDs, reference, and title plus
`CREATED` status. The TypeScript model treats the field as optional, so wire and
domain semantics do not align.

**Required change:** return `null` or omit the project before approval and freeze
that contract in backend and frontend tests.

### GAP-004 — API and Angular submission contracts diverge (high)

The authenticated API accepts any authenticated group, optional opening fields,
zero documents, and every use type. The Angular route is external-only and
requires a complete in-situ request with at least one file.

**Required change:** choose one authoritative submission policy, enforce its
security and domain rules in the application/API, and let the UI mirror them.

### GAP-005 — Decision input validation is incomplete (high)

`ReasonRequest` accepts an empty rejection or cancellation reason, and the
approval API accepts empty `title` and `purpose`. Angular form rules do not
protect direct API callers.

**Required change:** trim and validate these fields at the request boundary and
preserve the rules in domain value objects or commands.

### GAP-006 — Direction error semantics are inconsistent (medium)

Direction mutations are blocked outside `return-to-staff`, but some routes
return `DIRECTION_READ_ONLY` while edit, assign, request-documents, and forward
return `INSUFFICIENT_GROUP`.

**Required change:** centralize the policy and return one documented error code.

### GAP-007 — Proposal history is not a complete audit trail (high)

Metadata edits and requested-object additions/removals create no proposal
events. The event history is therefore a lifecycle log, not a complete record of
proposal changes.

**Required change:** define auditable fields and emit before/after events with
actor and timestamp for each required change.

### GAP-008 — Requested-object snapshots are not authoritative (high)

Snapshots are supplied by the caller and are not reloaded or verified against
the Collection Object Index. A direct API caller controls their descriptive
text and optional collection association.

**Required change:** resolve object IDs server-side, verify institution and
catalogue ownership, and create snapshots from trusted data.

### GAP-009 — Document requests can be ineffective (medium)

A requested-document command can contain an empty list and does not notify the
requester. Only the correction flow sends a scoped invitation.

**Required change:** require at least one item and define a durable requester
notification path for both authenticated and public proposals.

### GAP-010 — Post-commit delivery is not durable (high)

E-mails are direct post-commit calls without an outbox or retry queue. Correction
items commit before the separate amendment-token operation, so a failure can
leave durable open corrections without a delivered link.

**Required change:** use a transactional outbox with idempotent delivery and
make correction creation plus invitation issuance one recoverable workflow.

### GAP-011 — Proposal download header is unsafe (high)

Proposal document download interpolates the stored upload filename directly
into `Content-Disposition`, instead of using the existing safe attachment-header
helper.

**Required change:** use the shared helper and add tests for quotes, CR/LF,
non-ASCII names, and traversal-like filenames.

### GAP-012 — Authorization is split across routes and use cases (medium)

Several commands rely on the HTTP route to apply actor, Direction, ownership,
or target-role checks before invoking application services. Calling those
services from another adapter can therefore apply a different policy.

**Required change:** move reusable authorization and target validation into the
application boundary while keeping HTTP mapping in presentation code.

### GAP-013 — Event ordering is unstable on equal timestamps (medium)

Event ordering uses only `occurredAt`. Two events with the same timestamp have
no sequence or ID tie-breaker, so newest-first order is not guaranteed.

**Required change:** persist a stable sequence or sort by timestamp plus a
monotonic tie-breaker consistently in backend and mock implementations.

### GAP-014 — Workflow verification is incomplete (medium)

Backend tests cover the main lifecycle, but request-document and
request-correction HTTP matrices are less complete and browser E2E does not
exercise the authenticated submission-to-decision journey. The Angular proposal
suite currently has two failures: the generic detail test expects a Forward
button absent from the template, and the mock cancellation test can order
`APPROVED` before `CANCELLED` when timestamps match.

**Required change:** reconcile the intended Forward UI, make mock ordering
deterministic, cover the missing matrices, and add the principal browser
journey.

## 10. Acceptance criteria

### CA-001 — Submission is atomic and bounded

Given a valid authenticated request, submission returns `201`, creates a
`SUBMITTED` proposal and conversation, preserves intended use and dates, accepts
supported initial files, and reclaims files on failure.

→ `test/use_of_collections/test_api.py::test_submit_proposal_returns_201`,
`::test_submit_proposal_carries_intended_use_through_to_detail`,
`::test_submit_proposal_accepts_supporting_document_types`,
`::test_submit_proposal_rolls_back_saved_documents_when_upload_fails`

### CA-002 — Staff broadcast distinguishes permissions from users

Submission notifies every eligible staff permission except the actor, while
e-mail is sent once per distinct user. These tests describe the current global
broadcast and do not establish institution isolation.

→ `test/use_of_collections/test_api.py::test_submit_proposal_notifies_all_staff_except_actor`,
`::test_submit_proposal_dedupes_broadcast_email_by_user_not_notifications`

### CA-003 — Lists enforce requester ownership

Repeated statuses and pagination reach the repository correctly. Staff may
scope by requester; non-staff cannot widen or spoof their requester filter.

→ `test/use_of_collections/test_api.py::test_list_proposals_paginates_results`,
`::test_list_proposals_filters_by_multiple_statuses`,
`::test_staff_can_scope_list_with_requested_by`,
`::test_non_staff_requested_by_is_ignored_and_forced_to_own_id`

### CA-004 — Requested objects remain proposal snapshots

Adding searched object snapshots exposes them on detail; removal updates the
proposal; approval with none creates an empty project.

→ `test/use_of_collections/test_api.py::test_relate_searched_objects_surfaces_them_on_detail`,
`::test_remove_requested_object_updates_proposal_detail`,
`::test_approve_proposal_without_objects_creates_empty_project`

### CA-005 — Assignment and forwarding validate targets and notifications

Staff can assign or forward to valid operational staff, cannot target external
or Direction permissions through generic commands, and self-assignment sends no
effect. Taking over notifies the previous assignee.

→ `test/use_of_collections/test_api.py::test_staff_can_assign_proposal_to_staff_target`,
`::test_staff_can_forward_proposal_to_staff_target`,
`::test_assign_proposal_rejects_external_target_permission`,
`::test_forward_proposal_rejects_external_target_permission`,
`::test_assign_proposal_to_self_sends_no_notification_or_email`,
`::test_take_over_assignment_notifies_previous_assignee`

### CA-006 — Staff editing uses effective values

Omitted fields remain unchanged, explicit null clears nullable proposal fields,
terminal states reject edits, and the effective date range is validated.

→ `test/use_of_collections/test_api.py::test_staff_can_patch_proposal_title`,
`::test_patch_proposal_null_title_clears_it`,
`::test_patch_proposal_omitted_fields_left_unchanged`,
`::test_patch_proposal_terminal_status_returns_409`,
`::test_patch_proposal_invalid_date_range_returns_422`

### CA-007 — Authenticated document delivery is DOCX-only

Blank document types and non-DOCX content are rejected; valid DOCX is stored and
the assigned staff member is notified unless they are the uploader.

→ `test/use_of_collections/test_api.py::test_submit_document_empty_document_type_returns_422`,
`::test_submit_document_rejects_non_docx_content`,
`::test_submit_document_accepts_valid_docx`,
`::test_submit_document_notifies_assigned_staff_target`,
`::test_submit_document_to_self_sends_no_notification_or_email`

### CA-008 — Correction scope and satisfaction hold

Correction items require `PENDING`, reference only proposal documents, and
resolve only when a new matching document satisfies each targeted item. Public
amendment operations remain within that scope and reclaim replaced files.

→ `test/use_of_collections/test_domain_models.py::test_request_document_corrections_requires_pending`,
`::test_request_document_corrections_unknown_document_id_raises`,
`::test_submit_document_corrections_rejects_unsatisfied_item`,
`::test_submit_document_corrections_replacement_needs_fresh_document`

→ `test/use_of_collections/test_correction_flow.py::test_amendment_add_then_submit_resolves`,
`::test_amendment_upload_out_of_scope_is_rejected`,
`::test_amendment_upload_replaces_flagged_document`,
`::test_amendment_remove_reclaims_file`

### CA-009 — Direction lane preserves ownership and history

Only the current operational assignee can refer a pending proposal to an active
Direction target with a reason. Only the current Direction assignee can return
it to active operational staff with a response. Both commands preserve state
and record target and reason.

→ `test/use_of_collections/test_domain_models.py::test_refer_to_direction_changes_assignee_and_records_reason_and_target`,
`::test_return_to_staff_requires_reason_and_current_direction_assignee`,
`::test_return_to_staff_records_direction_clarification`

→ `test/use_of_collections/test_api.py::test_curator_can_refer_assigned_proposal_to_direction`,
`::test_direction_can_return_proposal_to_staff_with_required_reason`,
`::test_direction_cannot_read_a_proposal_assigned_to_another_member`

### CA-010 — Rejection closes the proposal with a message

A Curatorial rejection of a pending proposal records `REJECTED` and appends the
requester-facing reason to the conversation.

→ `test/use_of_collections/test_api.py::test_reject_proposal_creates_message_to_requester`

### CA-011 — Approval materialises the project and resolves public identity

Approval rejects an invalid interval, creates an empty project when no objects
were requested, provisions a new public account before commit, and chooses the
correct post-commit e-mail for new versus existing accounts.

→ `test/use_of_collections/test_api.py::test_approve_proposal_invalid_date_range_returns_422`,
`::test_approve_proposal_without_objects_creates_empty_project`,
`::test_approve_public_proposal_sends_access_email_after_commit`,
`::test_approve_public_proposal_new_account_skips_approval_email`,
`::test_approve_public_proposal_existing_account_sends_approval_email`

### CA-012 — Requester cancellation cascades

Only `requestedBy` can cancel; rejected proposals cannot be cancelled; a linked
project is cancelled from any state, including completed.

→ `test/use_of_collections/test_api.py::test_cancel_proposal_by_requester_without_project_returns_cancelled`,
`::test_cancel_proposal_cascades_to_existing_project_any_status`,
`::test_cancel_proposal_rejects_non_requester`,
`::test_cancel_proposal_rejects_rejected_status`

→ `test/use_of_collections/test_domain_models.py::test_proposal_driven_project_cancellation_allows_completed_project`

### CA-013 — External ownership protects resource reads

An external permission cannot read another requester's proposal events,
documents, or resulting project events. Document downloads also enforce parent
proposal ownership.

→ `test/use_of_collections/test_api.py::test_external_user_cannot_read_other_proposal_events`,
`::test_external_user_cannot_read_other_proposal_documents`,
`::test_external_user_cannot_read_other_project_events`,
`::test_download_document_rejects_non_owner`

### CA-014 — Event sorting precedes pagination

Events with distinct timestamps are sorted newest-first before pagination.

→ `test/use_of_collections/test_api.py::test_proposal_event_log_is_sorted_newest_first_before_pagination`

### CA-015 — Angular exposes role-specific workflows

The external form enforces the narrower in-situ submission flow; staff pages
support assume, take-over, routing, edit, document correction, approval, and
rejection; Direction uses a dedicated return-only page; terminal details render
read-only history.

→ frontend: `proposal-submit-page.component.spec.ts`,
`proposals-new-page.component.spec.ts`, `proposal-my-detail-page.component.spec.ts`,
`proposal-direction-detail-page.component.spec.ts`,
`proposal-direction.guard.spec.ts`, and `proposal-api.service.spec.ts`

## 11. Non-functional requirements

- **Transaction boundary**: proposal, conversation, event, project creation,
  requester provisioning, and in-app notifications participate in the request
  transaction where their command requires them.
- **External effects**: e-mails are attempted only after the relevant commit;
  the limitations of that strategy are declared in Section 9.
- **Sensitive data**: requester contact fields and stored files use the shared
  encryption rules in [SPEC-022](../022-cifragem-e-armazenamento/spec.md).
- **Tenant isolation**: the actor carries an institution identifier, but this
  context does not yet enforce it on proposal or project data; GAP-001 is a
  release-blocking security concern for multi-institution operation.
- **Contract stability**: golden tests freeze representative proposal detail,
  command, error, and pagination shapes.
- **Architecture**: application code consumes Identity, Notifications, and
  Reference Numbers through their published interfaces. The scoped amendment
  implementation is supplied at the composition root.

## 12. Traceability

| Element | Location |
| --- | --- |
| `Proposal`, `Conversation`, entities, value objects, and transitions | `vitarerum-api/app/use_of_collections/domain/models.py` |
| Proposal commands | `vitarerum-api/app/use_of_collections/application/use_cases/proposal.py` |
| Approval, cancellation, and Proposal-to-Project bridge | `vitarerum-api/app/use_of_collections/application/use_cases/project.py` |
| Ownership and list/detail queries | `vitarerum-api/app/use_of_collections/application/authorization.py`, `application/queries.py` |
| Actor institution and global group lookup | `vitarerum-api/app/identity/public.py`, `app/identity/infrastructure/repositories.py` |
| Proposal HTTP routes and schemas | `vitarerum-api/app/use_of_collections/presentation/proposal_routes.py`, `presentation/schemas.py` |
| Repositories, external requester, and notification e-mails | `vitarerum-api/app/use_of_collections/infrastructure/` |
| Scoped amendment integration | `vitarerum-api/app/use_of_collections/application/ports.py`, `app/public_submission/infrastructure/amendment.py` |
| Angular routes, pages, components, guards, and service | `vitarerum-ui/src/app/features/collections/proposals/` |
| Submission-channel decision | `docs/architecture/adr/0001-submission-channel.md` |

## 13. Open questions

1. What is the authoritative institution owner for authenticated and confirmed
   public proposals, and how will existing records be migrated safely?
2. Should the backend adopt the Angular authenticated-submission contract, or
   should the UI expose the full optional API contract?
3. Should Direction list scoping be enforced in the application query rather
   than left to an `assigned_to` filter supplied by the client?
4. Should proposal detail return `collectionUseProject: null` before approval?
5. Which metadata and requested-object changes must become auditable proposal
   events?
6. Should requested-object snapshots be verified against the Collection Object
   Index before they enter the aggregate?
7. Should requester notifications, validation of decision reasons, and durable
   e-mail delivery be standardized across all proposal commands?
