# Proposal phase — researcher actions

---

### `POST /proposals`

**Description** — Researcher submits a first contact request. Atomically creates a `Proposal` in `SUBMITTED` status and a `Conversation` seeded with the initial email message (Business Rule 01 — every proposal opens with an email). Records a `SUBMITTED` `ProposalEvent`. The caller's `PermissionId` is recorded as `requestedBy`. In the normal researcher flow the caller is an `EXTERNAL` group member. **No `CollectionUseProject` is created at this point** — the project is materialised only when a curator approves the proposal (`POST /proposals/{proposal_id}/approve`).

**All proposal-defining fields are optional.** A proposal may be submitted as a stub — with none of `title`, `intendedUse`, `purpose`, `beginDate`, or `endDate` — and completed in a later step. Every field below may be omitted or sent as `null`; an empty `{}` body is accepted.

**Request body**
```json
{
  "title": "string | null",
  "intendedUse": {
    "useType": "EXHIBITION | IN_SITU_VISIT | OTHER",
    "description": "string"
  },
  "purpose": "string | null",
  "beginDate": "2025-06-01 | null",
  "endDate": "2025-06-30 | null",
  "initialMessageRecipient": "collections@museum.pt",
  "initialMessageSubject": "string",
  "initialMessageBody": "string"
}
```

`title`, `intendedUse`, `purpose`, `beginDate`, and `endDate` are all optional and default to `null` when omitted. `intendedUse`, when present, describes how the collection will be used: a categorised `useType` (`EXHIBITION` · `IN_SITU_VISIT` · `OTHER`) and a free-text `description` (optional, defaults to an empty string); when omitted the whole `intendedUse` is `null`. `initialMessageRecipient` defaults to `collections@museum.pt` when omitted or blank. `initialMessageSubject` falls back to `title` (and `title`, when omitted, falls back to `initialMessageSubject`); `initialMessageBody` falls back to `purpose`; both default to an empty string when neither is given. The sender of the seeded message is resolved from the authenticated caller. The `endDate`-after-`beginDate` rule is only enforced when both dates are present.

**A proposal is always created object-free.** The collection objects a researcher wants are described in prose in the initial message; they are attached as structured `RequestedObject` entries only later, once the researcher has searched the catalog and selected the matches, via `POST /proposals/{proposal_id}/requested-objects`. This endpoint accepts no `requestedObjects` field — any such field in the body is ignored.

**Response `201 Created`**
```json
{
  "proposal": {
    "id": "uuid",
    "referenceNumber": "VRP-20250115-0001",
    "title": "string | null",
    "status": "SUBMITTED",
    "intendedUse": {
      "useType": "IN_SITU_VISIT",
      "description": "string"
    },
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
    "assignedTo": null,
    "submittedAt": "2025-01-15T10:30:00"
  },
  "conversationId": "uuid"
}
```

The submit response carries only the `proposal` summary and the `conversationId`; there is no project yet. `title`, `intendedUse`, `beginDate`, and `endDate` are echoed back as stored and are `null` when they were not supplied. `beginDate` and `endDate`, when present, are the requested use period. The proposal reference follows `VRP-YYYYMMDD-XXXX`, where `XXXX` is sequential per submission date. The project (with its `CUP-XXXXXXXX` reference number) appears once the proposal is approved.

**Response `422 Unprocessable Entity`**
```json
{
  "error": "INVALID_DATE_RANGE",
  "message": "endDate must be after beginDate"
}
```

---

### `GET /proposals`

**Description** — List proposals visible to the caller. Researchers only receive proposals
where `requestedBy` matches their active permission id; staff callers can see all proposals
and may use the filters below.

**Query parameters**
```
status       : ProposalStatus (optional, repeatable) e.g. status=REJECTED&status=CANCELLED
type         : UseType        (optional) EXHIBITION | IN_SITU_VISIT | OTHER
assigned_to  : UUID           (optional)
requested_by : UUID           (optional, honoured for staff only)
date_from    : Date           (optional)
date_to      : Date           (optional)
search       : String         (optional)
page         : Integer        (default 0)
size         : Integer        (default 20)
```

For non-staff callers, `requested_by` is ignored and replaced with the caller's active
permission id. `page` is zero-based. `size` must be between 1 and 100.

**Response `200 OK`**
```json
{
  "content": [
    {
      "id": "uuid",
      "referenceNumber": "VRP-20250115-0001",
      "title": "string | null",
      "status": "SUBMITTED",
      "intendedUse": {
        "useType": "IN_SITU_VISIT",
        "description": "string"
      },
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
      "assignedTo": null,
      "submittedAt": "2025-01-15T10:30:00"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

---

### `POST /proposals/{proposal_id}/requested-objects`

**Description** — Append collection objects the researcher wishes to use to an existing proposal. This is the **only** way objects are attached to a proposal. The objects come from an external catalog: the researcher searches it, selects the matching items from the result list, and the client submits the **`ObjectReference` snapshot it already holds from that search result**. The server does not resolve anything — it stores the snapshot as given. Allowed while the proposal is not in a terminal status (`APPROVED`/`REJECTED`/`CANCELLED`). Returns the full updated proposal detail (same shape as `GET /proposals/{proposal_id}`).

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "objects": [
    {
      "inventoryNumber": "INV-002",
      "displayTitle": "Book of Hours",
      "objectName": "Illuminated manuscript",
      "briefDescriptionSnapshot": "string | null",
      "category": "string",
      "description": "string"
    }
  ]
}
```

`inventoryNumber`, `displayTitle`, and `objectName` are **required** for each item (a missing one yields `422`); `briefDescriptionSnapshot` is optional and defaults to `null`; `category` and `description` are optional and default to an empty string. The three required fields are the snapshot captured from the catalog search result at selection time.

**Response `201 Created`** — the updated `ProposalDetail` (see `GET /proposals/{proposal_id}`), with the new entries present in `requestedObjects`.

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Cannot add requested objects to a decided proposal"
}
```

---

### `GET /proposals/{proposal_id}`

**Description** — Get full detail of a proposal. Researchers only see proposals where
`requestedBy` matches their active permission id. Staff callers (`CURATORIAL`,
`COLLECTIONS_MANAGEMENT`, `DIRECTION`, `SYS_ADMIN`) may read any proposal. Other callers
get `403`.

**Path parameters**
```
proposal_id : UUID (required)
```

**Response `200 OK`**
```json
{
  "id": "uuid",
  "referenceNumber": "VRP-20250115-0001",
  "title": "string | null",
  "status": "PENDING",
  "intendedUse": {
    "useType": "IN_SITU_VISIT",
    "description": "string"
  },
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
  "assignedTo": {
    "permissionId": "uuid",
    "user": {
      "id": "uuid",
      "name": "string",
      "email": "string"
    },
    "group": "CURATORIAL"
  },
  "collectionUseProject": {
    "id": "uuid",
    "referenceNumber": "",
    "title": "",
    "status": "CREATED",
    "requestedBy": null
  },
  "conversationId": "uuid",
  "documents": [
    {
      "id": "uuid",
      "type": "RESEARCH_FORM",
      "fileName": "research_form.docx",
      "fileReference": "string",
      "submittedAt": "2025-01-16T09:00:00",
      "submittedBy": {
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
  "requestedDocuments": [
    {
      "id": "uuid",
      "type": "RESEARCH_FORM",
      "description": "string",
      "requestedAt": "2025-01-16T09:00:00",
      "requestedBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "COLLECTIONS_MANAGEMENT"
      }
    }
  ],
  "requestedObjects": [
    {
      "id": "uuid",
      "objectReference": {
        "inventoryNumber": "INV-001",
        "displayTitle": "Book of Hours",
        "objectName": "Illuminated manuscript",
        "briefDescriptionSnapshot": "string | null"
      },
      "category": "manuscript",
      "description": "string",
      "requestedAt": "2025-01-15T10:30:00",
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
  "submittedAt": "2025-01-15T10:30:00"
}
```

`status` is a `ProposalStatus` — one of `SUBMITTED`, `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`. The top-level `referenceNumber` is the proposal reference (`VRP-YYYYMMDD-XXXX`), the top-level `title` is the title submitted with the proposal, and `beginDate` / `endDate` are the requested use period. `title`, `intendedUse`, `beginDate`, and `endDate` are nullable: a stub proposal submitted without them carries `null` until they are filled in (e.g. at approval). The `intendedUse` object is either fully present or `null` as a whole. `collectionUseProject` is always present in the shape, but until the proposal is approved no project exists yet: its `id`, `referenceNumber`, and `title` are empty strings, `status` is the placeholder `CREATED`, and `requestedBy` is `null`. After approval these reflect the real project (`CUP-XXXXXXXX`) and its `requestedBy` permission. `conversationId` may be `null` only if the persisted proposal has no conversation row. `requestedDocuments` lists the document types a staff attendant has formally requested (via `POST /proposals/{proposal_id}/request-documents`); `documents` lists the files actually uploaded; `requestedObjects` lists the collection objects the researcher asked to use (attached via `POST /proposals/{proposal_id}/requested-objects`). `submittedBy`, `requestedBy` are full permission objects, not bare ids. Each `objectReference` carries the snapshot the client supplied from the catalog search result — `inventoryNumber` is always present; `displayTitle`, `objectName`, and `briefDescriptionSnapshot` may be `null` in stored data, although the requested-object creation endpoint requires `displayTitle` and `objectName`.

**Response `404 Not Found`**
```json
{
  "error": "PROPOSAL_NOT_FOUND",
  "message": "No proposal found with id uuid"
}
```

**Response `403 Forbidden`**
```json
{
  "error": "ACCESS_DENIED",
  "message": "You do not have access to this proposal"
}
```

---

### `POST /proposals/{proposal_id}/cancel`

**Description** — Cancels a proposal. Only the requester recorded in `requestedBy` can cancel it, and cancellation is allowed from `SUBMITTED`, `PENDING`, or `APPROVED`. `REJECTED` proposals are terminal and cannot be cancelled. Records a `CANCELLED` `ProposalEvent`. If the proposal already has an associated `CollectionUseProject`, the project is also transitioned to `CANCELLED`, its `result` is set to `CANCELLED`, and a `CANCELLED` `UseEvent` is recorded, regardless of the project's previous status.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "reason": "Research trip cancelled"
}
```

**Response `200 OK`**
```json
{
  "proposal": {
    "id": "uuid",
    "referenceNumber": "VRP-20250115-0001",
    "title": "Research on 19th century photographs",
    "status": "CANCELLED",
    "beginDate": "2025-02-01",
    "endDate": "2025-02-10",
    "assignedTo": null,
    "lastEvent": {
      "occurredAt": "2025-01-17T10:00:00",
      "type": "CANCELLED",
      "triggeredBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "EXTERNAL"
      },
      "note": "Research trip cancelled"
    }
  },
  "collectionUseProject": null
}
```

When a linked project exists, `collectionUseProject` contains its cancelled summary:

```json
{
  "collectionUseProject": {
    "id": "uuid",
    "referenceNumber": "CUP-1A2B3C4D",
    "title": "Research on 19th century photographs",
    "status": "CANCELLED",
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

**Response `403 Forbidden`**
```json
{
  "error": "ACCESS_DENIED",
  "message": "Only the requester can cancel this proposal"
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Cannot cancel a rejected proposal"
}
```

---

### `POST /proposals/{proposal_id}/documents`

**Description** — Uploads a `.docx` file to the proposal's document store, in response to a staff document request. Records a `DOCUMENTS_SUBMITTED` `ProposalEvent`. The proposal must be in `PENDING` status; otherwise `409`. The `documentType` string identifies the category.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body** — `multipart/form-data`
```
file         : File    (required) .docx file
documentType : String  (required) e.g. "RESEARCH_FORM", "IDENTIFICATION", "INSTITUTION_LETTER"
```

**Response `201 Created`**
```json
{
  "id": "uuid",
  "type": "RESEARCH_FORM",
  "fileName": "research_form.docx",
  "fileReference": "string",
  "submittedAt": "2025-01-16T09:00:00",
  "submittedBy": {
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

**Response `415 Unsupported Media Type`** — returned when the filename is not `.docx`.
```json
{
  "error": "INVALID_FILE_FORMAT",
  "message": "Only .docx files are accepted"
}
```

If the filename ends in `.docx` but the bytes are not a real DOCX (a ZIP carrying the OOXML
`[Content_Types].xml` part), the same `error` is returned with message
`Only valid .docx files are accepted`. The content is validated, not just the extension.

**Response `413 Payload Too Large`** — the upload exceeds the configured limit
(`MAX_UPLOAD_BYTES`, default 25 MiB).
```json
{
  "error": "FILE_TOO_LARGE",
  "message": "File exceeds the 26214400-byte limit"
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "Proposal is not in PENDING status"
}
```

---

### `GET /proposals/{proposal_id}/documents`

**Description** — List all documents submitted for a proposal. Access follows the same
rules as proposal detail: the requester and staff may list documents.

**Path parameters**
```
proposal_id : UUID (required)
```

**Response `200 OK`**
```json
{
  "proposalId": "uuid",
  "documents": [
    {
      "id": "uuid",
      "type": "RESEARCH_FORM",
      "fileName": "research_form.docx",
      "fileReference": "string",
      "submittedAt": "2025-01-16T09:00:00",
      "submittedBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "EXTERNAL"
      }
    }
  ]
}
```

---

### `GET /proposals/{proposal_id}/documents/{document_id}`

**Description** — Download the binary content of a single document (e.g. a conversation message attachment). Streams the stored file resolved from its `fileReference`, with a `Content-Disposition: attachment` header so browsers save it under its original `fileName`. Access follows the same rules as the parent proposal: the requester and staff (`CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`, `SYS_ADMIN`) may download; other callers get `403`.

**Path parameters**
```
proposal_id : UUID (required)
document_id : UUID (required)
```

**Response `200 OK`** — binary file stream (not JSON)
```
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="research_form.docx"

<binary file content>
```

The `Content-Type` reflects the stored file's media type (`.docx` today). Clients authenticate with the usual `Authorization` / `X-Permission-Id` headers — there is no public/presigned URL, so the file must be fetched through this endpoint rather than linked directly.

**Response `404 Not Found`**
```json
{
  "error": "NOT_FOUND",
  "message": "Document not found for this proposal"
}
```

**Response `403 Forbidden`**
```json
{
  "error": "ACCESS_DENIED",
  "message": "You do not have access to this proposal"
}
```

---

### `GET /proposals/{proposal_id}/events`

**Description** — Get the immutable audit trail of a proposal, paginated in insertion order. Reflects every `ProposalEvent` recorded on the aggregate. Access follows the same rules as proposal detail: the requester and staff may list events.

**Path parameters**
```
proposal_id : UUID (required)
```

**Query parameters**
```
page : Integer (default 0)
size : Integer (default 20)
```

`page` is zero-based. `size` must be between 1 and 100.

`ProposalEventType` values: `SUBMITTED` · `ASSIGNED` · `FORWARDED` · `DOCUMENTS_REQUESTED` · `DOCUMENTS_SUBMITTED` · `REVIEW_STARTED` · `REFERRED_TO_DIRECTION` · `DIRECTION_CLARIFIED` · `APPROVED` · `REJECTED` · `CANCELLED`

**Response `200 OK`**
```json
{
  "proposalId": "uuid",
  "content": [
    {
      "occurredAt": "2025-01-15T10:30:00",
      "type": "SUBMITTED",
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
      "occurredAt": "2025-01-16T08:45:00",
      "type": "ASSIGNED",
      "triggeredBy": {
        "permissionId": "uuid",
        "user": {
          "id": "uuid",
          "name": "string",
          "email": "string"
        },
        "group": "CURATORIAL"
      },
      "note": "Assuming this request"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2,
  "totalPages": 1
}
```

---

### `GET /proposals/{proposal_id}/conversation`

**Description** — Get the conversation for a proposal with its messages, paginated in insertion order. Access follows the same rules as proposal detail: the requester and staff may read the conversation.

**Path parameters**
```
proposal_id : UUID (required)
```

**Query parameters**
```
page : Integer (default 0)
size : Integer (default 20)
```

`page` is zero-based. `size` must be between 1 and 100.

**Response `200 OK`**
```json
{
  "conversationId": "uuid",
  "proposalId": "uuid",
  "messages": [
    {
      "id": "uuid",
      "sentAt": "2025-01-15T10:30:00",
      "sender": "researcher@university.pt",
      "recipient": "collections@museum.pt",
      "subject": "Research visit request",
      "body": "string",
      "attachments": [
        {
          "documentId": "uuid",
          "fileName": "research_form.docx"
        }
      ]
    },
    {
      "id": "uuid",
      "sentAt": "2025-01-16T08:45:00",
      "sender": "collections@museum.pt",
      "recipient": "researcher@university.pt",
      "subject": "RE: Research visit request",
      "body": "string",
      "attachments": []
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2,
  "totalPages": 1
}
```

---

### `POST /proposals/{proposal_id}/conversation/messages`

**Description** — Send a message in the conversation. The message is immutable once submitted, reflecting the email semantics of the `Message` value object. No messages can be added once the proposal reaches a terminal status (`APPROVED`, `REJECTED`, `CANCELLED`). Access follows the same rules as proposal detail: the requester and staff may send messages while the proposal is open.

**Path parameters**
```
proposal_id : UUID (required)
```

**Request body**
```json
{
  "recipient": "collections@museum.pt",
  "subject": "string",
  "body": "string",
  "documentIds": ["uuid"]
}
```

`documentIds` is optional. Each id must reference a document already uploaded to this proposal (`POST /proposals/{proposal_id}/documents`); the server resolves the file name and returns the references in `attachments`.

**Response `201 Created`**
```json
{
  "id": "uuid",
  "sentAt": "2025-01-17T11:00:00",
  "sender": "researcher@university.pt",
  "recipient": "collections@museum.pt",
  "subject": "string",
  "body": "string",
  "attachments": [
    {
      "documentId": "uuid",
      "fileName": "research_form.docx"
    }
  ]
}
```

**Response `409 Conflict`**
```json
{
  "error": "INVALID_TRANSITION",
  "message": "No messages can be added to a closed or decided proposal"
}
```

---

A few conventions worth noting across this group:

**`sender` is derived from the authenticated user** — the sender email is never submitted in the request body, it is resolved from the session. Only `recipient` needs to be provided.

**`POST /proposals` creates two aggregates, not three** — it creates a `Proposal` (`SUBMITTED`) and a `Conversation` (with its opening message) atomically. The `CollectionUseProject` is **not** created here; it is created on approval. This is the key difference from earlier revisions of the API.

**Document upload uses `multipart/form-data`** — files are never base64 encoded in JSON bodies. Only `.docx` is accepted, and the proposal must be in `PENDING` status. The `fileReference` in the response is the internal storage path resolved by the file service.

**Events are always read-only** — `GET /proposals/{proposal_id}/events` exposes the immutable audit trail. There is no POST to this endpoint; events are only produced as side effects of commands.

**Message attachments reference proposal documents** — attachments are never uploaded in the message body. The caller first uploads a file via `POST /proposals/{proposal_id}/documents`, then references the returned document `id` in `documentIds`. The server resolves each to a `{ documentId, fileName }` attachment on the message, so the same file can be attached to multiple messages without duplication.
