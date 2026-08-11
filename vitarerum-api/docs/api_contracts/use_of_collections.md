# Use of Collections API Contract

Base path: `/api/v1`

All authenticated endpoints require `Authorization: Bearer <token>` and
`X-Permission-Id`. Authorization failures return `403`; authentication failures
return `401`.

## Proposal Approval Creates A Project

`POST /proposals/{proposalId}/approve`

Approving a proposal creates the corresponding collection-use project. The
project receives its initial `objects` collection by copying the proposal's
requested objects into project-owned object snapshots.

When the proposal has no requested objects yet, approval is still allowed and
the project is created with `objects: []` on its detail response. Staff can add
project-owned object snapshots later while the project is editable.

The successful response remains a dual aggregate response:

```json
{
  "proposal": {
    "id": "proposal-id",
    "referenceNumber": "VRP-20260715-0001",
    "title": "Collection study",
    "status": "APPROVED",
    "beginDate": "2026-07-20",
    "endDate": "2026-07-25",
    "assignedTo": null,
    "lastEvent": null
  },
  "collectionUseProject": {
    "id": "project-id",
    "referenceNumber": "CUP-20260715-0001",
    "title": "Collection study",
    "status": "CREATED",
    "requestedBy": null
  }
}
```

## Project Objects

Project object snapshots are returned on project detail responses:

```json
{
  "id": "project-object-id",
  "inventoryNumber": "INV-001",
  "displayTitle": "Book of Hours",
  "objectName": "Illuminated manuscript",
  "briefDescriptionSnapshot": null,
  "category": "manuscript",
  "description": ""
}
```

Log and occurrence entries reference project-owned object snapshots through
`collectionUseObjectId`.

## Add Project Objects

`POST /collection-use-projects/{projectId}/objects`

Staff-only. Accepted while the project is editable (`CREATED` or `IN_PROGRESS`).

Request:

```json
{
  "objects": [
    {
      "inventoryNumber": "INV-002",
      "displayTitle": "Field notebook",
      "objectName": "Notebook",
      "briefDescriptionSnapshot": null,
      "category": "archive",
      "description": "Added after approval"
    }
  ]
}
```

Response: `201 ProjectDetailResponse`.

Side effects:

- ensures the project has an `ObjectAccessLog`;
- creates one automatic `ObjectLogEntry` for each added object;
- the automatic entry has `numberOfObjects: 1`, no observations, no attachments,
  and `collectionUseObjectId` pointing to the added project object.

## Remove Project Object Without Cascade

`DELETE /collection-use-projects/{projectId}/objects/{objectId}`

Staff-only. Accepted while the project is editable (`CREATED` or `IN_PROGRESS`).

Successful response: `204 No Content`.

This endpoint is intentionally conservative. It removes the project object only
when there are no related records that need explicit user confirmation.

Allowed case:

- the object has no related records; or
- the only related record is the automatic access-log entry created when the
  object was added. In that case the automatic entry is physically deleted with
  the object.

Blocked case:

If the object has occurrence entries, publication entries, attachments, or
non-automatic access-log entries, the endpoint returns `409`:

```json
{
  "error": "PROJECT_OBJECT_HAS_DEPENDENCIES",
  "message": "Project object has related records and requires cascade confirmation",
  "dependencies": {
    "accessLogEntries": 1,
    "occurrenceEntries": 2,
    "publicationEntries": 1,
    "attachments": 3
  }
}
```

Clients should surface this as a destructive confirmation step before calling
the cascade endpoint.

## Remove Project Object With Cascade

`POST /collection-use-projects/{projectId}/objects/{objectId}/remove`

Staff-only. Accepted while the project is editable (`CREATED` or `IN_PROGRESS`).

Request:

```json
{
  "confirmCascade": true,
  "reason": "Object was added to the wrong project."
}
```

Successful response: `204 No Content`.

Validation:

- `confirmCascade` must be `true`;
- `reason` must be non-empty.

Side effects:

- physically deletes the project object;
- physically deletes related object access-log entries;
- physically deletes related object occurrence entries;
- physically deletes related publication entries that reference the object;
- deletes stored files attached to those related entries.

Clients must not use this endpoint as the default removal path. First call the
non-cascade `DELETE`; call this endpoint only after showing the dependency
summary and collecting an explicit reason.

## Object Access Log Document

`GET /collection-use-projects/{projectId}/object-access-log/document`

Returns the project's object access log rendered onto MUHNAC's RAIS register
(`RAIS_formColecoesAcessoInSituRegisto`). Readable by anyone who may read the
log itself, staff and the project's own researcher alike.

Successful response: `200 OK` with

- `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `Content-Disposition: attachment; filename="{accessLogReferenceNumber}-RAIS.docx"`

The rendered form carries the log's reference number, the download date, the
researcher's name and e-mail, the collections reached, the curator, the
conclusion date (blank while the log is open), and one object line per entry —
inventory number, designation, type (the project object's `category`), number of
objects, access date and observations. Dates print day-first (`DD-MM-YYYY`).
Fewer than fifteen entries are padded with blank lines so the document keeps the
printed form's shape; more than fifteen extend the table.

Only persisted entries appear: unsaved edits in a client must be saved before
downloading.

Returns `404 OBJECT_ACCESS_LOG_NOT_FOUND` when the project has no access log yet
(no object has been logged).
