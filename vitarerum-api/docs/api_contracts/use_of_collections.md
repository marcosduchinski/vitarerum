# Use of Collections API Contract

Base path: `/api/v1`

All authenticated endpoints require `Authorization: Bearer <token>` and
`X-Permission-Id`. Authorization failures return `403`; authentication failures
return `401`.

## Direction Review Workflow

`POST /proposals/{proposalId}/refer-to-direction`

Available only to the proposal's assigned Curatorial or Collections Management
member. The target permission must be active and belong to `DIRECTION`.

```json
{
  "targetPermissionId": "direction-permission-id",
  "reason": "Strategic decision required"
}
```

`reason` is mandatory. The proposal remains `PENDING`, is assigned to the
selected Direction permission, emits `REFERRED_TO_DIRECTION`, and notifies the
recipient. The event exposes its structured `targetPermission` as well as the
actor, timestamp, and reason.

`POST /proposals/{proposalId}/return-to-staff`

Available only to the assigned Direction member. The target permission must be
active and belong to `CURATORIAL` or `COLLECTIONS_MANAGEMENT`.

```json
{
  "targetPermissionId": "staff-permission-id",
  "reason": "Please revise the insurance conditions"
}
```

The Direction response in `reason` is mandatory. The proposal remains
`PENDING`, is reassigned to staff, emits `DIRECTION_CLARIFIED`, and notifies the
recipient. Direction members may only access proposals assigned to their active
permission. Their access is read-only apart from this return command;
generic assign/forward commands cannot be used to enter or leave the Direction
lane.

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
- `Content-Disposition: attachment; filename="{accessLogReferenceNumber}-RAIS.docx"`,
  with the reference's slashes folded to hyphens
  (`OL-MUHNAC/COL/2026/0001` → `OL-MUHNAC-COL-2026-0001-RAIS.docx`)

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

## Publication Log Document

`GET /collection-use-projects/{projectId}/publication-log/document`

Returns the project's complete publication/output log rendered onto the RRP
register. The download is independent of the paginated listing used by the UI:
all persisted entries are included, oldest first, up to the document safety cap
of 1,000 entries.

Successful response: `200 OK` with

- `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `Content-Disposition: attachment; filename="{publicationLogReferenceNumber}-RRP.docx"`,
  with the reference's slashes folded to hyphens

The register identifies the project, requester and curator, reports the total
number of entries, and prints one row per result: sequence, date, author, note,
optional linked object, and supporting file names/descriptions. Supporting
files remain separate downloads; the register lists them but does not embed
their binary content.

Only persisted entries appear. Returns `404 PUBLICATION_LOG_NOT_FOUND` when no
publication log has been issued and `422 DOCUMENT_ENTRY_LIMIT_EXCEEDED` above
the safety cap.

## Object Occurrence Report Document

`GET /collection-use-projects/{projectId}/object-occurrence-log/document`

Returns the project's whole occurrence log rendered onto MUHNAC's ROC report
(`ROC_formOcorrenciaColecoes`). The form describes a single incident, so its
information table repeats once per occurrence — each block naming its own
collection and object, which is what lets one document carry the entire log.
Blocks run oldest first, across objects. Readable by anyone who may read the log
itself.

Successful response: `200 OK` with

- `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `Content-Disposition: attachment; filename="{occurrenceLogReferenceNumber}-ROC.docx"`,
  with the reference's slashes folded to hyphens

Each block carries the entry's collection, designation, inventory number, date,
place, detailed description, testimonials and images. The blank form's
instruction text is replaced, so an unfilled field comes out empty rather than
showing its instructions.

Three fields are adapted to the form's shape:

- the form has no quantity field, so a block covering more than one object
  prints its inventory number as `INV-001 (3 objetos)`;
- `Imagens` lists the entry's attachments by name and description, one per line.
  The files themselves stay attached to the entry and are downloaded separately;
- the form signs off once, so "Reportado por" names every distinct reporter in
  the log, joined with `; `.

Entries whose project object has since been removed are omitted.

Returns `404 OBJECT_OCCURRENCE_LOG_NOT_FOUND` when the project has no occurrence
log yet (no occurrence has been reported).
