# Document Templates — API Contract

Staff-curated `.docx` templates offered per `UseType` on the public submission screen. A citizen
downloads the templates for their chosen use type, fills them in and attaches the completed files
to the request. Staff manage the catalog (upload, edit, activate, reorder, delete).

Two audiences share one context:

- **Public** endpoints under `/public/document-templates` — **no auth** (same trust model as the
  public proposal submission): they only expose active templates and stream the blank `.docx`.
- **Staff** endpoints under `/document-templates` — require a session (`Authorization: Bearer …` +
  `X-Permission-Id`) and membership in a staff group (`CURATORIAL`, `COLLECTIONS_MANAGEMENT`,
  `DIRECTION`, `SYS_ADMIN`). Non-staff callers get `403`.

## Base URL

| Environment | URL |
|---|---|
| Local dev | `http://127.0.0.1:8000/api/v1` |
| Production | `https://api.vitarerum.example/api/v1` |

## Resource shapes

Public list item:

```json
{ "id": "uuid", "title": "In-situ visit safety form", "description": "Fill and sign.", "mandatory": true }
```

Staff item (adds curation fields):

```json
{
  "id": "uuid",
  "useType": "IN_SITU_VISIT",
  "title": "In-situ visit safety form",
  "description": "Fill and sign.",
  "mandatory": true,
  "active": true,
  "displayOrder": 0,
  "fileName": "safety-form.docx",
  "uploadedAt": "2026-07-02T12:00:00Z"
}
```

`useType` is one of `EXHIBITION`, `IN_SITU_VISIT`, `OTHER`. `mandatory` is informational for now
(shown to the citizen); attachment of mandatory templates is **not** yet enforced at submission.

---

## Public endpoints (no auth)

### `GET /public/document-templates?useType={UseType}`

Lists the **active** templates for the given use type, ordered by `displayOrder` then `title`.
`useType` is required.

**Response `200`** — array of public list items (see above). Empty array when none are configured.

### `GET /public/document-templates/{id}/file`

Streams the template's `.docx`. Serves **active templates only** — a deactivated template is `404`
even to a caller who knows its id (deactivation removes it from public reach, not just from the
list).

**Response `200`** — body is the file; `Content-Type` is the DOCX MIME type and
`Content-Disposition: attachment; filename="…"` carries a sanitised file name (basename only; no
path separators; header-injection safe).

**Response `404`** — `{ "error": "DOCUMENT_TEMPLATE_NOT_FOUND", "message": "No document template with id …" }`
(unknown id, inactive template, or missing stored file).

---

## Staff endpoints (auth + staff group)

### `GET /document-templates?useType={UseType}`

Lists **all** templates (active and inactive). `useType` is optional; omit it to list every use
type, grouped by `useType` then `displayOrder`.

**Response `200`** — array of staff items.

### `GET /document-templates/{id}/file`

Streams the template's `.docx`. Unlike the public download, this serves templates in **any state**
(including inactive), so staff can review a deactivated template before re-activating or replacing
it. Same safe `Content-Disposition` handling as the public download.

**Response `200`** — the file. **`404`** — unknown id / missing stored file. **`403`** — non-staff.

### `POST /document-templates`

Creates a template. Content type: `multipart/form-data`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | ✅ | real `.docx` (magic-byte validated, not just extension); the stored name is sanitised to a basename |
| `useType` | string (enum) | ✅ | `EXHIBITION` \| `IN_SITU_VISIT` \| `OTHER` |
| `title` | string | ✅ | non-empty |
| `description` | string | — | defaults to `""` |
| `mandatory` | boolean | — | defaults to `false` |
| `active` | boolean | — | defaults to `true` |
| `displayOrder` | integer | — | defaults to `0` |

**Response `201`** — the created staff item.
**Errors** — `415 INVALID_FILE_FORMAT` (not a real DOCX); `413 FILE_TOO_LARGE`; `403` (non-staff).

### `PATCH /document-templates/{id}`

Replaces the editable metadata (full replace — the management form submits all fields). JSON body:

```json
{ "title": "…", "description": "…", "mandatory": false, "active": true, "displayOrder": 1 }
```

**Response `200`** — the updated staff item. **`404`** — unknown id.

### `PUT /document-templates/{id}/file`

Replaces the stored `.docx`. Content type: `multipart/form-data` with a single `file` part.

**Response `200`** — the updated staff item (new `fileName`). **`404`** — unknown id.
**`415 INVALID_FILE_FORMAT`** — not a real DOCX.

### `DELETE /document-templates/{id}`

Removes the template and its stored file.

**Response `204`** — no body. **`404`** — unknown id.
