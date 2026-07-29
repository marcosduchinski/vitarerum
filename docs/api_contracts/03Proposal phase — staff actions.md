# Proposal phase — staff actions

---

### `GET /proposals`

**Description** — List proposals. Staff (any of `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`, `SYS_ADMIN`) see all proposals; non-staff callers are automatically scoped to the proposals they requested. Same endpoint as the researcher list — visibility is decided from the caller's group.

**Query parameters**
```
status      : ProposalStatus[] (optional, repeatable) SUBMITTED | PENDING | APPROVED | REJECTED | CANCELLED
type        : UseType          (optional) EXHIBITION | IN_SITU_VISIT | OTHER — filters intendedUse
requested_by: UUID             (optional) filter by researcher (honoured for staff only)
assigned_to : UUID             (optional) filter by attendant permissionId
date_from   : LocalDate        (optional) filter by requested begin date range
date_to     : LocalDate        (optional)
search      : String           (optional) search by title or reference number
page        : Integer          (default 0)
size        : Integer          (default 20)
```

Repeat `status` to match any of several statuses (OR semantics), for example
`?status=REJECTED&status=CANCELLED`. A single `status` value remains supported.
`page` is zero-based. `size` must be between 1 and 100.

**Response `200 OK`**
```json
{
  "content": [
    {
      "id": "uuid",
      "referenceNumber": "VRP-20250115-0001",
      "title": "string | null",
      "status": "PENDING",
      "intendedUse": "IN_SITU_VISIT",
      "beginDate": "2025-06-01 | null",
      "endDate": "2025-06-30 | null",
      "requestedBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "EXTERNAL"
      },
      "requesterContact": null,
      "assignedTo": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "CURATORIAL"
      },
      "submittedAt": "2025-01-15T10:30:00",
      "submissionChannel": "AUTHENTICATED"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 38,
  "totalPages": 2
}
```

List items carry the proposal summary only, including the proposal `referenceNumber` (`VRP-YYYYMMDD-XXXX`), `title`, and persisted `submissionChannel` (`PUBLIC` or `AUTHENTICATED`) — there is no embedded `collectionUseProject` (use `GET /proposals/{proposal_id}` for the linked project reference). `title`, `intendedUse`, `beginDate`, and `endDate` are nullable: a proposal submitted as a stub carries `null` for any of these until it is filled in. Public submissions that are not yet approved may have `requestedBy: null` and `requesterContact: { "name", "email" }`, because the Identity user/permission is provisioned only during approval.

> **Note — nullable proposal fields in command responses.** Every staff command below returns a proposal summary whose `title`, `beginDate`, and `endDate` (and, where shown, `intendedUse`) echo the stored proposal. For a stub proposal that has not yet been completed these are `null`. They are shown below with concrete example values for brevity.

---

### `PATCH /proposals/{proposal_id}`

**Description** — Staff correct a proposal's defining metadata: `title`, `intendedUse`, `beginDate`, and `endDate`. Partial update — an omitted key leaves the field unchanged, while an explicit `null` clears it (`title`, `beginDate`, `endDate` are nullable). `intendedUse` is replaced when supplied. Records **no** `ProposalEvent` and does **not** change the proposal status. Allowed only while the proposal is in a non-terminal status (`SUBMITTED` or `PENDING`); editing a decided or cancelled proposal returns `409`. The caller must belong to a staff group.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "title": "string | null",
  "intendedUse": "IN_SITU_VISIT",
  "beginDate": "2025-06-01 | null",
  "endDate": "2025-06-30 | null"
}
```

All fields are optional. Omit a field to leave it untouched; send `null` to clear `title`, `beginDate`, or `endDate`.

**Response `200 OK`**
```json
{
  "id": "uuid",
  "referenceNumber": "VRP-20250115-0001",
  "title": "string | null",
  "status": "PENDING",
  "beginDate": "2025-06-01 | null",
  "endDate": "2025-06-30 | null",
  "lastEvent": {
    "occurredAt": "2025-01-16T08:45:00",
    "type": "ASSIGNED",
    "triggeredBy": {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "COLLECTIONS_MANAGEMENT"
    },
    "note": "string"
  }
}
```

`lastEvent` echoes the proposal's most recent event (unchanged — this command records none) and is `null` when the proposal has no events.

**Response `403 Forbidden`**
```json
{
  "error": "INSUFFICIENT_GROUP",
  "message": "Only CURATORIAL or COLLECTIONS_MANAGEMENT or DIRECTION or SYS_ADMIN members can perform this action"
}
```

If the caller is neither staff nor the requester, the proposal access check may instead
return `ACCESS_DENIED` with message `You do not have access to this proposal`.

**Response `404 Not Found`**
```json
{
  "error": "PROPOSAL_NOT_FOUND",
  "message": "No proposal found with id uuid"
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Cannot edit a proposal that is already decided or cancelled"
}
```

**Response `422 Unprocessable Entity`** — when the effective `endDate` (incoming where supplied, otherwise stored) precedes the effective `beginDate`.
```json
{
  "error": "INVALID_DATE_RANGE",
  "message": "endDate must be after beginDate"
}
```

---

### `POST /proposals/{proposal_id}/assign`

**Description** — A staff member assumes responsibility for the request, becoming its attendant and moving it into review. If no `targetPermissionId` is provided the caller assigns themselves. Updates `assignedTo`, transitions the proposal from `SUBMITTED` to `PENDING`, and records an `ASSIGNED` `ProposalEvent`. Allowed from any non-terminal status. The caller must belong to a staff group, and any explicit `targetPermissionId` must also belong to a staff group.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "targetPermissionId": "uuid",
  "note": "string"
}
```

Both fields are optional. When `targetPermissionId` is omitted the caller is assigned.

**Response `200 OK`**
```json
{
  "id": "uuid",
  "referenceNumber": "VRP-20250115-0001",
  "title": "string",
  "status": "PENDING",
  "beginDate": "2025-06-01",
  "endDate": "2025-06-30",
  "assignedTo": {
    "permissionId": "uuid",
    "user": {
      "id": "uuid",
      "name": "string",
      "email": "string"
    },
    "group": "COLLECTIONS_MANAGEMENT"
  },
  "lastEvent": {
    "occurredAt": "2025-01-16T08:45:00",
    "type": "ASSIGNED",
    "triggeredBy": {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "COLLECTIONS_MANAGEMENT"
    },
    "note": "string"
  }
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Cannot assign a proposal that is already decided or cancelled"
}
```

**Response `404 Not Found`** — when an explicit `targetPermissionId` does not exist.
```json
{
  "error": "PERMISSION_NOT_FOUND",
  "message": "No permission found with id uuid"
}
```

**Response `422 Unprocessable Entity`** — when an explicit `targetPermissionId` belongs
to a non-staff group.
```json
{
  "error": "INVALID_PERMISSION_TARGET",
  "message": "Target permission must belong to a staff group"
}
```

---

### `POST /proposals/{proposal_id}/request-documents`

**Description** — Staff formally request supplementary documents from the researcher. Records a `DOCUMENTS_REQUESTED` `ProposalEvent` and appends the requested document types. The proposal must be in `PENDING` status; the status is unchanged. Each requested document carries a `type` and a `description`. `type` is **free-form text**, not a fixed catalogue: staff name the document in their own words. The server trims surrounding whitespace and requires a non-empty value of at most **128 characters** (else `422 VALIDATION_ERROR`).

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "requiredDocuments": [
    {
      "type": "Research form",
      "description": "string"
    }
  ],
  "note": "string"
}
```

**Response `200 OK`**
```json
{
  "id": "uuid",
  "referenceNumber": "VRP-20250115-0001",
  "title": "string",
  "status": "PENDING",
  "beginDate": "2025-06-01",
  "endDate": "2025-06-30",
  "lastEvent": {
    "occurredAt": "2025-01-16T09:00:00",
    "type": "DOCUMENTS_REQUESTED",
    "triggeredBy": {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "COLLECTIONS_MANAGEMENT"
    },
    "note": "string"
  }
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Documents can only be requested when proposal is in PENDING status"
}
```

**Response `403 Forbidden`**
```json
{
  "error": "INSUFFICIENT_GROUP",
  "message": "Only CURATORIAL or COLLECTIONS_MANAGEMENT or DIRECTION or SYS_ADMIN members can perform this action"
}
```

---

### `POST /proposals/{proposal_id}/request-document-corrections`

**Description** — Staff flag already-submitted documents for correction/replacement and/or request missing ones. Appends the items as `DocumentCorrectionItem`s (status `REQUESTED`), records a `DOCUMENT_CORRECTIONS_REQUESTED` `ProposalEvent`, and e-mails the requester a scoped, single-use amendment link (the public flow in file 11). This is **instructory**: the proposal stays in `PENDING` (unlike `reject`). The proposal must be in `PENDING` status.

Each item carries a **free-form** `documentType` (not a fixed catalogue): the server trims surrounding whitespace and requires a non-empty value of at most **128 characters**. When `documentId` is present it flags that existing document for replacement (the id must belong to the proposal); when `documentId` is omitted/`null` a *missing* document is requested and `documentType` is the only scope. The public amendment upload must re-send this `documentType` **exactly as received**.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "items": [
    {
      "documentType": "Insurance certificate",
      "reason": "The scan is illegible; please re-upload a clear copy.",
      "documentId": "uuid"
    },
    {
      "documentType": "Authorization letter",
      "reason": "Please attach the signed authorization letter.",
      "documentId": null
    }
  ],
  "note": "string (optional)"
}
```

**Response `200 OK`** — the updated `Proposal` command view (same shape as the other staff commands: `id`, `referenceNumber`, `title`, `status` `= PENDING`, `beginDate`, `endDate`, `lastEvent` `= DOCUMENT_CORRECTIONS_REQUESTED`).

**Response `422 Unprocessable Content`**
```json
{
  "error": "NO_CORRECTION_ITEMS",
  "message": "At least one correction item is required."
}
```
`VALIDATION_ERROR` is returned instead when a `documentType` is blank or exceeds 128 characters, or when a `documentId` does not belong to the proposal.

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Document corrections can only be requested when proposal is in PENDING status"
}
```
`MISSING_REQUESTER_CONTACT` (also `409`) is returned when the proposal has no requester to e-mail the amendment link to.

**Response `403 Forbidden`**
```json
{
  "error": "INSUFFICIENT_GROUP",
  "message": "Only CURATORIAL or COLLECTIONS_MANAGEMENT or DIRECTION or SYS_ADMIN members can perform this action"
}
```

---

### `POST /proposals/{proposal_id}/forward`

**Description** — Staff forward the request to another staff member with a question or solicitation. Updates `assignedTo` and records a `FORWARDED` `ProposalEvent`. Does not change the proposal status. The proposal must be in `PENDING` status. The caller and target permission must both belong to staff groups.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "targetPermissionId": "uuid",
  "note": "string"
}
```

`targetPermissionId` is required; `note` is optional.

**Response `200 OK`**
```json
{
  "id": "uuid",
  "referenceNumber": "VRP-20250115-0001",
  "title": "string",
  "status": "PENDING",
  "beginDate": "2025-06-01",
  "endDate": "2025-06-30",
  "assignedTo": {
    "permissionId": "uuid",
    "user": {
      "id": "uuid",
      "name": "string",
      "email": "string"
    },
    "group": "CURATORIAL"
  },
  "lastEvent": {
    "occurredAt": "2025-01-17T14:00:00",
    "type": "FORWARDED",
    "triggeredBy": {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "COLLECTIONS_MANAGEMENT"
    },
    "note": "string"
  }
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Proposal must be PENDING to be forwarded to another staff member"
}
```

**Response `404 Not Found`** — when `targetPermissionId` does not exist.
```json
{
  "error": "PERMISSION_NOT_FOUND",
  "message": "No permission found with id uuid"
}
```

**Response `422 Unprocessable Entity`** — when `targetPermissionId` belongs to a non-staff
group.
```json
{
  "error": "INVALID_PERMISSION_TARGET",
  "message": "Target permission must belong to a staff group"
}
```

---

### `POST /proposals/{proposal_id}/approve`

**Description** — Curator approves the proposal and materialises the project. Transitions the proposal from `PENDING` to `APPROVED` and **creates** the linked `CollectionUseProject` in `CREATED` status. Records an `APPROVED` `ProposalEvent` and a `REQUESTED` `UseEvent` on the new project. The project's `title`, `purpose`, `beginDate`, and `endDate` are taken from this request body (the curator confirms/adjusts the project parameters at approval time), and `requestedBy` is copied from the approved proposal. Existing requested objects are copied as project-owned snapshots; if the proposal has no requested objects yet, approval still succeeds and the project detail later returns `objects: []`. For an authenticated proposal `requestedBy` already exists on the proposal; for a **public** proposal (`requestedBy: null` + `requesterContact` set), this call is the moment Identity provisions — or reuses — a user/permission for the contact's e-mail, and that resolved `requestedBy` is what gets copied onto the project. A proposal rejected or cancelled before approval never reaches this provisioning step, and never creates a user, permission, or credentials e-mail. Only available to `CURATORIAL` group members.

**Public-proposal credentials** — There is no password-reset/self-service flow yet, so this is the only way a newly provisioned requester gets access:
- If the requester's e-mail is **new** to Identity, a user is created with a generated temporary password, and — once this request's changes are durably committed — an e-mail is sent to that address with a login link and the temporary password.
- If the e-mail already belongs to an existing user, that user (and any existing `EXTERNAL` permission) is reused as-is: its password is **not** reset, and no credentials e-mail is sent.
- Accepted risk (provisional, until a real password-reset flow exists): the temporary password does not expire and there is no forced change on first login; it is delivered once, by e-mail, and that is the requester's only record of it.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "title": "string",
  "purpose": "string",
  "beginDate": "2025-06-01",
  "endDate": "2025-06-30",
  "note": "string"
}
```

`title`, `purpose`, `beginDate`, `endDate` are required; `note` is optional. These fields
define the created `CollectionUseProject`; the proposal summary in the response echoes the
proposal's already stored `title`, `beginDate`, and `endDate`.

**Response `200 OK`**
```json
{
  "proposal": {
    "id": "uuid",
    "referenceNumber": "VRP-20250115-0001",
    "title": "string",
    "status": "APPROVED",
    "beginDate": "2025-06-01",
    "endDate": "2025-06-30",
    "assignedTo": null,
    "lastEvent": {
      "occurredAt": "2025-01-21T15:00:00",
      "type": "APPROVED",
      "triggeredBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "CURATORIAL"
      },
      "note": "string"
    }
  },
  "collectionUseProject": {
    "id": "uuid",
    "referenceNumber": "CUP-1A2B3C4D",
    "title": "string",
    "status": "CREATED",
    "requestedBy": {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "EXTERNAL"
    }
  }
}
```

The proposal `referenceNumber` follows `VRP-YYYYMMDD-XXXX`. The project `collectionUseProject.referenceNumber` follows the `CUP-XXXXXXXX` pattern (8 hex chars), and `collectionUseProject.requestedBy` is copied from the approved proposal (provisioned from `requesterContact` during this call for a public proposal that didn't already have one).

**Response `403 Forbidden`**
```json
{
  "error": "INSUFFICIENT_GROUP",
  "message": "Only CURATORIAL members can perform this action"
}
```

**Response `422 Unprocessable Entity`** — when `endDate` precedes `beginDate`.
```json
{
  "error": "INVALID_DATE_RANGE",
  "message": "endDate must be after beginDate"
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Proposal must be PENDING to be approved"
}
```

---

### `POST /proposals/{proposal_id}/reject`

**Description** — Curator rejects the proposal. Transitions the proposal from `PENDING` to `REJECTED`, records a `REJECTED` `ProposalEvent`, and appends a conversation message from the caller's permission user to the requester using `reason` as the message body. No project is created or affected (the project only exists after approval). A `reason` is mandatory. Only available to `CURATORIAL` group members.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "reason": "string"
}
```

**Response `200 OK`**
```json
{
  "id": "uuid",
  "referenceNumber": "VRP-20250115-0001",
  "title": "string",
  "status": "REJECTED",
  "beginDate": "2025-06-01",
  "endDate": "2025-06-30",
  "assignedTo": null,
  "lastEvent": {
    "occurredAt": "2025-01-21T15:00:00",
    "type": "REJECTED",
    "triggeredBy": {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "CURATORIAL"
    },
    "note": "string"
  }
}
```

**Response `422 Unprocessable Entity`** — when `reason` is missing from the body (schema-enforced).

**Response `403 Forbidden`**
```json
{
  "error": "INSUFFICIENT_GROUP",
  "message": "Only CURATORIAL members can perform this action"
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Proposal must be PENDING to be rejected"
}
```

---

A few conventions worth noting across this group:

**Group-restricted commands** — `assign`, `forward`, and `request-documents` require a staff permission (`CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`, or `SYS_ADMIN`). `approve` and `reject` require `CURATORIAL`. Invalid group membership returns `403 Forbidden` (`INSUFFICIENT_GROUP`). Explicit assignment/forwarding targets must be staff permissions, otherwise the API returns `422 INVALID_PERMISSION_TARGET`.

**Single review state** — the implemented flow is `SUBMITTED` → `assign` (`→ PENDING`, event `ASSIGNED`) → all review activity happens in `PENDING` (`request-documents`, document uploads, `forward`, messages — none change the status) → `approve` (`→ APPROVED`, creates the project), `reject` (`→ REJECTED`), or requester cancellation (`→ CANCELLED`). There is no separate `PENDING_DOCUMENTS`/`UNDER_REVIEW`/`PENDING_DIRECTION` state, and there is no `start-review` endpoint.

**Dual-aggregate responses** — `approve` returns the updated `Proposal` and the newly-created `CollectionUseProject` together, reflecting that it atomically decides the proposal and materialises the project. Requester cancellation (`POST /proposals/{proposal_id}/cancel`, defined in file 02) returns the cancelled proposal and the linked project summary when a project already exists. `reject` returns the proposal alone.

**`reason` is schema-mandatory on rejection** — a missing `reason` is rejected by request validation with `422 Unprocessable Entity`.

**Conversation and document endpoints are shared** — staff use the same `GET/POST /proposals/{proposal_id}/conversation`, `POST /proposals/{proposal_id}/conversation/messages`, `POST/GET /proposals/{proposal_id}/documents`, and `GET /proposals/{proposal_id}/documents/{document_id}` (download) contracts defined in the researcher group. The sender is always resolved from the authenticated user's session.
