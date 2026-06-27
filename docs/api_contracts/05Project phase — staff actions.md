# Project phase — staff actions

---

### `GET /collection-use-projects`

**Description** — List all projects across all researchers. Staff see every project regardless of ownership; for staff callers the `requestedBy` detail is populated from `CollectionUseProject.requestedBy` on each item.

**Query parameters**
```
status      : UseStatus    (optional) CREATED | IN_PROGRESS | COMPLETED | CANCELLED
type        : UseType      (optional) EXHIBITION | IN_SITU_VISIT | OTHER — filters intendedUse.useType
requestedBy : PermissionId (optional) scope to projects requested by this permission
dateFrom    : LocalDate    (optional) filter by begin date ≥ dateFrom
dateTo      : LocalDate    (optional) filter by begin date ≤ dateTo
search      : String       (optional) case-insensitive match on title or reference number
page        : Integer       (default 0)
size        : Integer       (default 20)
```

> `requestedBy` is honored only for staff callers — e.g. pass the caller's own `permissionId` for a staff "my projects" view. For non-staff callers it is ignored and the list is always scoped to their own id. The `assignedTo`, `referenceNumber`, and `proposalApproved` filters from the original design are **not implemented**.
`page` is zero-based. `size` must be between 1 and 100.

**Response `200 OK`**
```json
{
  "content": [
    {
      "id": "uuid",
      "referenceNumber": "CUP-1A2B3C4D",
      "title": "string",
      "purpose": "string",
      "note": null,
      "intendedUse": {
        "useType": "IN_SITU_VISIT",
        "description": "string"
      },
      "status": "IN_PROGRESS",
      "result": null,
      "beginDate": "2025-06-01",
      "endDate": "2025-06-30",
      "proposal": {
        "id": "uuid",
        "referenceNumber": "VRP-20250115-0001",
        "title": "string",
        "status": "APPROVED",
        "beginDate": "2025-06-01",
        "endDate": "2025-06-30",
        "submittedAt": "2025-01-15T10:30:00",
        "assignedTo": {
          "permissionId": "uuid",
          "user": {
            "id": "uuid",
            "name": "string",
            "email": "string"
          },
          "group": "CURATORIAL"
        }
      },
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
  ],
  "page": 0,
  "size": 20,
  "totalElements": 87,
  "totalPages": 5
}
```

---

### `GET /collection-use-projects/{project_id}`

**Description** — Get full detail of any project. Staff have access to all projects regardless of ownership; the response populates the `requestedBy` detail from `CollectionUseProject.requestedBy` (it is `null` for non-staff callers).

**Path parameters**
```
project_id : UUID (required)
```

**Response `200 OK`**
```json
{
  "id": "uuid",
  "referenceNumber": "CUP-1A2B3C4D",
  "title": "string",
  "purpose": "string",
  "note": null,
  "intendedUse": {
    "useType": "IN_SITU_VISIT",
    "description": "string"
  },
  "status": "IN_PROGRESS",
  "result": null,
  "beginDate": "2025-06-01",
  "endDate": "2025-06-30",
  "authorisedBy": null,
  "authorisedAt": null,
  "proposal": {
    "id": "uuid",
    "referenceNumber": "VRP-20250115-0001",
    "title": "string",
    "status": "APPROVED",
    "beginDate": "2025-06-01",
    "endDate": "2025-06-30",
    "submittedAt": "2025-01-15T10:30:00",
    "assignedTo": {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "CURATORIAL"
    }
  },
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
```

> `requestedBy` is a required `PermissionId` on `CollectionUseProject`; the API hydrates it as a permission detail for staff callers and returns `null` for non-staff. `authorisedBy` / `authorisedAt` are nullable and are populated only when a stored project has an `authorisedBy` permission that can be hydrated. Staff review context is not embedded here; use the linked proposal endpoints for proposal documents/conversation/requested objects and the paginated project journal endpoints below for logs.

**Response `404 Not Found`**
```json
{
  "error": "PROJECT_NOT_FOUND",
  "message": "No project found with id uuid"
}
```

---

### `POST /collection-use-projects/{project_id}/log-entries` · `.../occurrence-entries`

**Description** — Staff add **object log entries** (to the project's object access log) and **object occurrence entries** (to the project's object occurrence log). Unlike non-staff callers (restricted to `IN_PROGRESS`), staff may add entries at **any** project status — but entries are rejected with `409` once the respective log is concluded. The caller's `permissionId` is recorded as `addedBy` / `reportedBy`. Request/response shapes are defined in the researcher group (file 04).

**Request body** — `log-entries`
```json
{
  "inventoryNumber": "INV-001",
  "numberOfObjects": 2,
  "observations": "string",
  "requestedObjectId": "uuid"
}
```

**Request body** — `occurrence-entries`
```json
{
  "inventoryNumber": "INV-001",
  "numberOfObjects": 1,
  "occurrenceDate": "2025-06-03T11:30:00",
  "location": "Conservation lab, room 2",
  "detailedDescription": "string",
  "testimonial": "string",
  "requestedObjectId": "uuid"
}
```

Both bodies accept an optional `requestedObjectId` linking the entry to a `RequestedObject` of this project's proposal (inventory number must match, else `422`).

**Response `201 Created`** — the `ObjectLogEntry` (`id`, `objectReference`, `numberOfObjects`, `addedAt`, `addedBy`, `observations`, `requestedObjectId`, `attachments`) or the `ObjectOccurrenceEntry` (`id`, `objectReference`, `numberOfObjects`, `occurrenceDate`, `location`, `reportedBy`, `detailedDescription`, `testimonial`, `requestedObjectId`, `attachments`) respectively.

---

### `PATCH /collection-use-projects/{project_id}/log-entries/{entry_id}`

**Description** — Edit an existing object log entry. Only `addedAt`, `numberOfObjects` and `observations` are editable; the entry's object, `addedBy` and `requestedObjectId` are immutable. Partial update — only fields present in the body change (`observations: null` clears it). Staff may edit at any project status, but not once the access log is concluded (`409`). Request/response shapes are defined in the researcher group (file 04).

**Path parameters**
```
project_id : UUID (required)
entry_id   : UUID (required)
```

**Request body** (all fields optional)
```json
{
  "addedAt": "2025-06-03T14:00:00",
  "numberOfObjects": 3,
  "observations": "string"
}
```

**Response `200 OK`** — the updated `ObjectLogEntry` (shape as in file 04).

---

### `PATCH /collection-use-projects/{project_id}/occurrence-entries/{entry_id}`

**Description** — Edit an existing object occurrence entry. Only `numberOfObjects`, `occurrenceDate`, `location`, `detailedDescription` and `testimonial` are editable; the entry's object, `reportedBy` and `requestedObjectId` are immutable. Partial update — only fields present in the body change (`testimonial: null` clears it). Staff may edit at any project status, but not once the occurrence log is concluded (`409`). Request/response shapes are defined in the researcher group (file 04).

**Path parameters**
```
project_id : UUID (required)
entry_id   : UUID (required)
```

**Request body** (all fields optional)
```json
{
  "numberOfObjects": 2,
  "occurrenceDate": "2025-06-03T11:30:00",
  "location": "Conservation lab, room 2",
  "detailedDescription": "string",
  "testimonial": "string"
}
```

**Response `200 OK`** — the updated `ObjectOccurrenceEntry` (shape as in file 04).

---

### `GET /collection-use-projects/{project_id}/log-entries` · `.../occurrence-entries`

**Description** — List a project's object log entries / occurrence entries ordered chronologically, including entries from both the researcher and staff. Both accept `page`/`size` and a permission filter (`added_by` on log entries, `reportedBy` on occurrence entries), and return the paginated envelopes defined in file 04 (with the `accessLog` / `occurrenceLog` header respectively).

**Query parameters**
```
added_by / reportedBy : UUID    (optional) filter by permissionId
page                 : Integer  (default 0)
size                 : Integer  (default 20)
```

`page` is zero-based. `size` must be between 1 and 100.

---

### `GET /collection-use-projects/{project_id}/object-access-log` · `.../object-occurrence-log`

**Description** — Get the project's object access log / object occurrence log header (`referenceNumber`, `dateConclusion`, `curator`), as defined in file 04. `404` while the project has no entries yet.

---

### `POST /collection-use-projects/{project_id}/log-entries/{entry_id}/attachments` · `.../occurrence-entries/{entry_id}/attachments`

**Description** — Staff upload a file to an existing log / occurrence entry at any project status, while the respective log is not concluded (`409` afterwards). `mediaType` is one of `DOCUMENT`, `IMAGE`, `VIDEO`, `OTHER`. `note` is an optional free-text description of the attachment.

**Request body** — `multipart/form-data`
```
file      : File      (required)
mediaType : MediaType (required) DOCUMENT | IMAGE | VIDEO | OTHER
note      : String    (optional)
```

**Response `201 Created`**
```json
{
  "fileReference": "string",
  "fileName": "conservation_note.pdf",
  "mediaType": "DOCUMENT",
  "uploadedAt": "2025-06-04T10:15:00",
  "note": "string"
}
```

**Response `404 Not Found`**
```json
{
  "error": "ENTRY_NOT_FOUND",
  "message": "No entry found with id uuid"
}
```

**Response `422 Unprocessable Entity`**
```json
{
  "error": "VALIDATION_ERROR",
  "message": "'NOT_A_MEDIA_TYPE' is not a valid MediaType"
}
```

---

### `GET /collection-use-projects/{project_id}/log-entries/{entry_id}/attachments/{file_reference}` · `.../occurrence-entries/{entry_id}/attachments/{file_reference}`

**Description** — Download the raw bytes of an attachment on a log / occurrence entry, keyed by the entry's `attachments[].fileReference`. The response is the binary file (not JSON), with `Content-Disposition: attachment` and a `Content-Type` derived from the file name's extension (falling back to `application/octet-stream`). `404` when the entry doesn't belong to this project (`ENTRY_NOT_FOUND`) or no attachment with that `fileReference` exists (`ATTACHMENT_NOT_FOUND`).

---

### `POST /collection-use-projects/{project_id}/publication-entries` · `PATCH …/{entry_id}` · `…/{entry_id}/attachments`

**Description** — Staff add, edit, and attach files to **publication log entries** (a `note` recording a publication/output derived from the project, plus optional attachments). Request/response shapes are defined in the researcher group (file 04). The publication log carries an informational `curator` (the staff member related to the project) and is **not concluded**.

**Phase/role gate differs from the other journals.** A publication entry may be written only by:

- the **external requester** while the project is `IN_PROGRESS`; or
- **`CURATORIAL`, `COLLECTIONS_MANAGEMENT` or `DIRECTION`** staff once the project is `COMPLETED`.

So unlike object access/occurrence logs (where staff may write at any status), staff are **rejected with `403` while the project is still `IN_PROGRESS`**, and the external requester is rejected with `403` once it is `COMPLETED`. Any other project status (`CREATED`, `CANCELLED`) rejects all callers with `409`. `SYS_ADMIN` receives the staff read views but is not among the publication writers.

**Response `403 Forbidden`**
```json
{
  "error": "ACCESS_DENIED",
  "message": "Once the project is COMPLETED only curatorial, collections-management or direction staff can add publication entries"
}
```

---

### `GET /collection-use-projects/{project_id}/publication-entries` · `…/publication-log`

**Description** — List a project's publication entries (paginated, with `added_by` filter and the `publicationLog` header) and get the publication log header (`id`, `referenceNumber`, `projectId`, `curator`), as defined in file 04. `404` (`PUBLICATION_LOG_NOT_FOUND`) while the project has no entries yet. Staff see all projects' publication logs.

---

### `GET /collection-use-projects/{project_id}/events`

**Description** — Get the immutable audit trail of the project lifecycle ordered chronologically. Staff see the complete event history including transitions triggered by the researcher, and can filter by `type`.

**Path parameters**
```
project_id : UUID (required)
```

**Query parameters**
```
type : UseEventType (optional) filter by event type
page : Integer      (default 0)
size : Integer      (default 20)
```

`page` is zero-based. `size` must be between 1 and 100.

`UseEventType` values: `REQUESTED` · `STARTED` · `COMPLETED` · `CANCELLED`

**Response `200 OK`**
```json
{
  "projectId": "uuid",
  "content": [
    {
      "occurredAt": "2025-01-21T15:00:00",
      "type": "REQUESTED",
      "triggeredBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "CURATORIAL"
      },
      "note": null
    },
    {
      "occurredAt": "2025-06-01T09:00:00",
      "type": "STARTED",
      "triggeredBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "EXTERNAL"
      },
      "note": null
    },
    {
      "occurredAt": "2025-06-30T17:00:00",
      "type": "COMPLETED",
      "triggeredBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "EXTERNAL"
      },
      "note": "string"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 3,
  "totalPages": 1
}
```

---

### `POST /collection-use-projects/{project_id}/export-in-situ-visit-record`

**Description** — Staff-only. Generates and persists an `InSituVisitRecord`
(the CIDOC-CRM mapping snapshot) from a project whose `intendedUse.useType` is
`IN_SITU_VISIT`. There is no request body; it reads the project, its proposal's
requested objects, and the three journals, and returns the stored record
(`201 Created`). Errors: `404 PROJECT_NOT_FOUND`, `409 INVALID_USE_TYPE`,
`403` for non-staff callers.

**Path parameters**
```
project_id : UUID (required)
```

The full request/response contract lives in
[`08InSituVisit-CIDOC-CRM.md`](08InSituVisit-CIDOC-CRM.md), which owns the
`InSituVisitRecord` shape; that record can then be projected to CIDOC-CRM JSON-LD
and turned into a narrative (see [`09KG-RAG-Narrative.md`](09KG-RAG-Narrative.md)).
To run the export → narrative chain and persist a durable report in one call, see
[`10Reports-InSituVisit.md`](10Reports-InSituVisit.md).

---

A few conventions worth noting across this group:

**Staff object-journal constraint differs from researcher** — for object access and occurrence logs, the researcher may only add entries while `IN_PROGRESS`; staff may add entries at any project status. Publication entries use the separate phase/role gate documented above.

**No staff-only project commands** — `start`, `complete`, and `cancel` (file 04) are the only state-changing project commands and carry no group restriction; any authorised caller may invoke them. The earlier `suspend`, `resume`, and `close` commands have been removed, along with the `SUSPENDED` and `CLOSED` states.

**Two distinct journal resources** — both are per-project, curator-concluded log aggregates whose entries record exactly one `objectReference`. `log-entries` belong to the **object access log** (`ObjectAccessLog`, `OAL-` reference number) with `numberOfObjects` and optional `observations`; `occurrence-entries` belong to the **object occurrence log** (`ObjectOccurrenceLog`, `OOL-` reference number) with `numberOfObjects`, `occurrenceDate`, `location`, `reportedBy`, `detailedDescription` and optional `testimonial`. Both gain the staff permission filter on their `GET` endpoints (`added_by` / `reportedBy`) and hydrate it as a full `PermissionDetail`. Either entry may carry an optional `requestedObjectId` tying it back to a `RequestedObject` of the proposal, for end-to-end object traceability.

**Shared endpoints are not repeated** — `GET /collection-use-projects/{project_id}` and `GET /collection-use-projects/{project_id}/events` follow the same response structure as the researcher group. The only difference is access scope (staff see all, plus a populated `requestedBy`).
