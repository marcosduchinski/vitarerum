# Collection Data Sources — Admin API Contract

Staff-only management of the scientific-collection catalogue: staff-uploaded `.xlsx` files feed
a searchable object index (one indexed row per spreadsheet row). Since 2026-07-06 the catalogue
has two levels — `CollectionArea` (an administrative/scientific classification, e.g. "Natural
History") groups one or more `Collection`s (e.g. Zoology, Botany) — but permissions and ingestion
stay unchanged at the `Collection` level: uploads, curators and documents never belong to an area
directly.

All endpoints require a session (`Authorization: Bearer …` + `X-Permission-Id`). Three scopes,
enforced **on the server** — the frontend menu/route is not a security boundary:

- **SYS_ADMIN** — sole administrator of the collection catalogue: create/rename/remove a
  collection or an area, move a collection between areas, assign/remove curators.
- **SYS_ADMIN and COLLECTIONS_MANAGEMENT** — manage source documents (upload/delete/reindex) of
  **any** collection.
- **CURATORIAL** — manages source documents only for collections it's assigned to as curator.

Any other staff group (e.g. `DIRECTION`) can still list the catalogue (read-only, nothing
`manageable`). Non-staff callers get `403`.

## Base URL

| Environment | URL |
|---|---|
| Local dev | `http://127.0.0.1:8000/api/v1` |
| Production | `https://api.vitarerum.example/api/v1` |

## Resource shapes

Collection area:

```json
{ "id": "uuid", "name": "Natural History", "collectionCount": 6 }
```

Collection (list/get/create/update/move-area all return this shape):

```json
{
  "id": "uuid",
  "areaId": "uuid",
  "areaName": "Natural History",
  "name": "Zoology",
  "curators": [
    {
      "permissionId": "uuid",
      "name": "Grace Curator",
      "email": "grace@museum.test",
      "assignedAt": "2026-06-01T09:00:00Z"
    }
  ],
  "documentCount": 3,
  "manageable": true
}
```

`manageable` is server-decided (see scopes above) — `true` for SYS_ADMIN/COLLECTIONS_MANAGEMENT
always, and for CURATORIAL only on collections it curates. A curator whose permission no longer
resolves in Identity still lists by `permissionId`, with `name`/`email` as `null`.

Curator candidate (a permission eligible to be assigned as curator):

```json
{ "permissionId": "uuid", "name": "Grace Curator", "email": "grace@museum.test" }
```

Source document:

```json
{
  "id": "uuid",
  "collectionId": "uuid",
  "fileName": "zoology-inventory.xlsx",
  "sourceKind": "UPLOAD",
  "status": "INDEXED",
  "errorMessage": null,
  "rowCount": 412,
  "uploadedAt": "2026-06-20T10:00:00Z",
  "indexedAt": "2026-06-20T10:00:03Z"
}
```

`status` is one of `UPLOADED` | `INDEXED` | `ERROR`. A parse failure (e.g. spreadsheet exceeds
the row cap) keeps the uploaded file but sets `status=ERROR` with `errorMessage`, so the admin
screen can surface it without losing the upload.

---

## Collection areas

### `GET /admin/collection-data-sources/areas`

SYS_ADMIN only. Lists every collection area with its live collection count.

**Response `200`** — array of collection area shapes, ordered by name.
**`403`** — non-SYS_ADMIN (`INSUFFICIENT_GROUP`).

### `POST /admin/collection-data-sources/areas`

Creates a collection area. Body:

```json
{ "name": "Documentation & Media" }
```

`name` is trimmed and required non-empty.

**Response `201`** — the created area (`collectionCount: 0`).
**`422 INVALID_COLLECTION_AREA_NAME`** — blank name.
**`409 COLLECTION_AREA_NAME_ALREADY_EXISTS`** — duplicate name (case-sensitive, after trim).
**`403`** — non-SYS_ADMIN.

### `PATCH /admin/collection-data-sources/areas/{areaId}`

Renames a collection area. Body: `{ "name": "…" }`.

**Response `200`** — the updated area.
**`404 COLLECTION_AREA_NOT_FOUND`** — unknown id.
**`422 INVALID_COLLECTION_AREA_NAME`** / **`409 COLLECTION_AREA_NAME_ALREADY_EXISTS`** — as above.

### `DELETE /admin/collection-data-sources/areas/{areaId}`

Removes a collection area. **Blocked while any collection is still assigned to it** — unlike
collection removal (which cascades permanently), removing an area would otherwise take out every
collection under it, so the caller must move or remove those collections first.

**Response `204`** — no body.
**`404 COLLECTION_AREA_NOT_FOUND`** — unknown id.
**`409 COLLECTION_AREA_IN_USE`** — one or more collections still reference this area.
**`403`** — non-SYS_ADMIN.

---

## Collections

### `GET /admin/collection-data-sources/collections`

Lists the full catalogue, each flagged with `manageable` for the caller. Available to any staff
member (see scopes above).

**Response `200`** — array of collection shapes.

### `POST /admin/collection-data-sources/collections`

SYS_ADMIN only. Body:

```json
{ "name": "Mineralogy", "areaId": "uuid" }
```

`areaId` is now required — every collection belongs to exactly one area from creation.

**Response `201`** — the created collection (`curators: []`, `documentCount: 0`).
**`404 COLLECTION_AREA_NOT_FOUND`** — `areaId` does not resolve.
**`422 INVALID_COLLECTION_NAME`** — blank name.
**`409 COLLECTION_NAME_ALREADY_EXISTS`** — duplicate name (after trim).
**`403`** — non-SYS_ADMIN.

### `GET /admin/collection-data-sources/collections/{collectionId}`

**Response `200`** — the collection, enriched like the list. **`404 COLLECTION_NOT_FOUND`**.

### `PATCH /admin/collection-data-sources/collections/{collectionId}`

SYS_ADMIN only. Renames the collection — **does not** change its area (see move-area below).
Body: `{ "name": "…" }`.

**Response `200`** — the updated collection.
**`404 COLLECTION_NOT_FOUND`** / **`422 INVALID_COLLECTION_NAME`** / **`409 COLLECTION_NAME_ALREADY_EXISTS`**.
**`403`** — non-SYS_ADMIN.

### `POST /admin/collection-data-sources/collections/{collectionId}/move-area`

SYS_ADMIN only. Moves the collection to a different area — a dedicated action (mirrors curator
assign/remove), not a side effect of the rename above. Body:

```json
{ "areaId": "uuid" }
```

**Response `200`** — the updated collection (new `areaId`/`areaName`).
**`404 COLLECTION_NOT_FOUND`** — unknown collection.
**`404 COLLECTION_AREA_NOT_FOUND`** — unknown target area.
**`403`** — non-SYS_ADMIN.

### `DELETE /admin/collection-data-sources/collections/{collectionId}`

SYS_ADMIN only. **Permanently** removes the collection and everything under it — curator
assignments, source documents (live or already soft-deleted), indexed rows, and their files.
Irreversible; there is no "inactive" state to fall back to.

**Response `204`** — no body. **`404 COLLECTION_NOT_FOUND`**. **`403`** — non-SYS_ADMIN.

---

## Curators

### `GET /admin/collection-data-sources/curator-candidates`

SYS_ADMIN only. Lists permissions in the `CURATORIAL` group — decouples the curator picker from
the generic identity `/users?group_id=` API.

**Response `200`** — array of curator candidates. **`403`** — non-SYS_ADMIN.

### `POST /admin/collection-data-sources/collections/{collectionId}/curators`

SYS_ADMIN only. Body: `{ "permissionId": "uuid" }`. Idempotent — assigning an already-assigned
permission returns the existing assignment.

**Response `201`** — the curator assignment.
**`404 COLLECTION_NOT_FOUND`** — unknown collection.
**`404 PERMISSION_NOT_FOUND`** — `permissionId` does not resolve in Identity.
**`422 PERMISSION_NOT_CURATORIAL`** — the target permission is not in the `CURATORIAL` group.
**`403`** — non-SYS_ADMIN.

### `DELETE /admin/collection-data-sources/collections/{collectionId}/curators/{permissionId}`

SYS_ADMIN only.

**Response `204`** — no body. **`404 COLLECTION_NOT_FOUND`**. **`403`** — non-SYS_ADMIN.

---

## Source documents

Source document responses include the optional semantic mapping used by
`/objects/search` to build proposal-ready object snapshots:

```json
{
  "id": "doc-1",
  "collectionId": "col-zoo",
  "fileName": "zoology.xlsx",
  "sourceKind": "UPLOAD",
  "status": "INDEXED",
  "errorMessage": null,
  "rowCount": 42,
  "uploadedAt": "2026-07-01T10:00:00Z",
  "indexedAt": "2026-07-01T10:00:02Z",
  "contentMatchesSearchableColumns": true,
  "objectMapping": {
    "inventoryNumberColumn": "Inventory No",
    "displayTitleColumn": "Name",
    "displayTitleColumns": ["Name"],
    "objectNameColumn": null,
    "descriptionColumns": ["Description", "Notes"],
    "searchableColumns": ["Inventory No", "Name", "Description"]
  }
}
```

New uploads must provide `objectMapping` before indexing. Existing documents may
still have `objectMapping: null` until they are corrected. The mapping is stored
on the source document. `searchableColumns` controls which cell values are
concatenated into `collection_index_object.content`, so changing it rebuilds
the document's indexed rows. `contentMatchesSearchableColumns=false` marks a
legacy document whose persisted `content` has not yet been rebuilt under the
named-column rule.

### `GET /admin/collection-data-sources/collections/{collectionId}/documents`

Lists the collection's **live** (non-deleted) source documents. Requires management scope for
this collection (see scopes above).

**Response `200`** — array of source documents. **`404 COLLECTION_NOT_FOUND`**. **`403`** —
caller lacks scope for this collection (`ACCESS_DENIED`).

### `POST /admin/collection-data-sources/collections/{collectionId}/documents`

Uploads and synchronously indexes a spreadsheet. Content type: `multipart/form-data`, single
`file` field (real `.xlsx`, magic-byte validated), plus the required semantic object mapping:

- `inventoryNumberColumn`
- `displayTitleColumns` (one or more columns; `displayTitleColumn` remains accepted for older clients)
- `objectNameColumn` (empty string means fallback to display title)
- `descriptionColumns` (JSON string list, e.g. `["Description", "Notes"]`)
- `searchableColumns` (JSON string list; must contain at least one known column)

The UI should call the columns-preview endpoint first, let the user choose the
mapping, then call this upload endpoint. The backend validates the mapping
against the parsed spreadsheet before indexing.

Idempotency by content hash:
- identical live file already on this collection → dedupe, no-op, returns the existing document.
- same file name, different content → new version: the previous source is soft-deleted and its
  index rows removed before the new one is indexed.
- parse failure (or exceeding the row cap) → persisted as `status=ERROR` with the file kept, so
  the failure is visible in the admin screen.

**Response `201`** — the source document. **`404 COLLECTION_NOT_FOUND`**. **`415`** — not a real
`.xlsx`. **`422 SOURCE_DOCUMENT_MAPPING_INVALID`** — missing/unknown mapping columns.
**`422 SOURCE_DOCUMENT_SEARCHABLE_COLUMNS_EMPTY`** — no searchable columns supplied.
**`403`** — caller lacks scope for this collection.

### `POST /admin/collection-data-sources/collections/{collectionId}/documents/columns-preview`

Parses an uploaded spreadsheet and returns the sorted union of column names,
without saving the file and without indexing rows. This is the pre-upload step
used to choose the required object snapshot columns.

Content type: `multipart/form-data`, single `file` field.

**Response `200`**

```json
{ "columns": ["Description", "Inventory No", "Name"] }
```

**`404 COLLECTION_NOT_FOUND`**. **`415`** — not a real `.xlsx`. **`403`** — out of scope.

### `DELETE /admin/collection-data-sources/documents/{documentId}`

Soft-deletes the document record and removes its rows from the object index; the stored file is
reclaimed only after the delete commits.

**Response `204`** — no body. **`404 SOURCE_DOCUMENT_NOT_FOUND`**. **`403`** — out of scope.

### `POST /admin/collection-data-sources/documents/{documentId}/reindex`

Re-reads the stored file and rebuilds its indexed rows using `searchableColumns`
(e.g. after fixing an `ERROR` status or after a legacy backfill).

**Response `200`** — the updated source document. **`404 SOURCE_DOCUMENT_NOT_FOUND`** — unknown
document or its stored file is missing. **`403`** — out of scope.

### `GET /admin/collection-data-sources/documents/{documentId}/columns`

Returns the sorted union of column names found in the indexed `cells` for the source document.
Used by the admin UI to configure object mapping without reparsing the file.

**Response `200`**

```json
{ "columns": ["Description", "Inventory No", "Name"] }
```

**`404 SOURCE_DOCUMENT_NOT_FOUND`**. **`403`** — out of scope.

### `PUT /admin/collection-data-sources/documents/{documentId}/object-mapping`

Stores the semantic column mapping used to build `objectSnapshot` on search hits.

**Request**

```json
{
  "inventoryNumberColumn": "Inventory No",
  "displayTitleColumn": "Name",
  "displayTitleColumns": ["Name", "Scientific name"],
  "objectNameColumn": null,
  "descriptionColumns": ["Description", "Notes"],
  "searchableColumns": ["Inventory No", "Name", "Scientific name"]
}
```

`inventoryNumberColumn` and at least one display title column are required.
`displayTitleColumn` is kept as the first-column compatibility field;
new clients should send `displayTitleColumns`. `objectNameColumn` is optional
and falls back to the composed display title at search time. `searchableColumns`
must contain at least one column. All supplied columns must exist in the parsed
column list for the document. Saving this mapping re-reads the stored file and
rebuilds the document's indexed rows atomically with the mapping change.

**Response `200`** — the updated source document. **`422 SOURCE_DOCUMENT_MAPPING_INVALID`** —
unknown or invalid columns. **`422 SOURCE_DOCUMENT_SEARCHABLE_COLUMNS_EMPTY`** — no searchable
columns supplied. **`404 SOURCE_DOCUMENT_NOT_FOUND`**. **`403`** — out of scope.

---

## Notes

- Object search (`/objects/search`, `/objects/search/collections`) is a separate, broadly
  staff-accessible read side — see `plano-objects-search.md`. It is unaffected by
  `CollectionArea`: search stays scoped to `Collection`, with no area-level facet.
- `CollectionArea` grants no authorization by itself — a curator's scope is still determined
  solely by which `Collection`s they're assigned to, never by area membership. This may become a
  future decision (a curator managing every collection of an area) but is out of scope today.
