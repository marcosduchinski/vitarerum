# Reports — In-Situ Visit Report

A composing endpoint that produces a durable **report** for an in-situ visit
project in a single call. It chains two existing operations — the CIDOC-CRM
**export** (`08InSituVisit-CIDOC-CRM.md`) and the KG-RAG **narrative**
generation (`09KG-RAG-Narrative.md`) — and persists the linkage between the
project, the exported `InSituVisitRecord`, and the generated narrative as an
`InSituVisitReport`.

Lives in its own context (`app/reports/in_situ_visit`). It is a **cross-context
orchestrator**: it owns only the
`InSituVisitReport` aggregate and composes the export and narrative use cases
through their published interfaces — it never touches another context's
aggregates directly. The whole chain runs in **one database transaction**, so a
failure in narrative generation leaves no orphaned record.

Same auth as the rest of the API (`Authorization` + `X-Permission-Id`);
**staff-only**. Errors use the shared `{ "error": CODE, "message": str }` shape.

Each call is **append-only**: a fresh `InSituVisitRecord`, a fresh narrative, and
a fresh `InSituVisitReport` are created every time. There is no deduplication on
`project_id` — calling twice yields two independent reports. The `GET` endpoints
below read that history back (list across all projects or per project, fetch one
by id, and fetch one with its narrative and record embedded).

---

## POST /api/v1/reports/collection-use/{project_id}/in_situ_visit

Exports the project, generates a narrative from the resulting record, and
persists an `InSituVisitReport` tying them together. Staff-only.

The `project_id` must reference a project whose `intendedUse.useType` is
`IN_SITU_VISIT` (same precondition as the underlying export).

**Path parameters**

```
project_id : UUID (required) — the CollectionUseProject to report on
```

**Request body** (all optional — forwarded to narrative generation)

```json
{
  "target_language": "pt",
  "narrative_type": "institutional",
  "creativity_temperature": 0.3
}
```

```
target_language        : string  (default "pt")   — output language code
narrative_type         : enum    (optional)       — omitted → "institutional";
                                                     see 09KG-RAG-Narrative.md
creativity_temperature : number  (default 0.3, 0.0–1.0) — LLM temperature
```

### Execution order

1. **Export** the project → a new `InSituVisitRecord` (`inSituVisitRecordId`).
2. **Generate** a narrative for that record with the body params → a new
   narrative (`narrativeId`).
3. **Build & persist** the `InSituVisitReport`, stamping `createdBy` from the
   caller's permission and `createdAt` with the server time.
4. Commit once; return `201`.

**Response `201 Created`** — ids only. Fetch the record and narrative through
their own `GET` endpoints (docs 08 / 09) when the full content is needed.

```json
{
  "id": "a1b2c3d4-...",
  "createdAt": "2026-06-22T10:30:00Z",
  "createdBy": "permission-uuid",
  "projectId": "project-uuid",
  "narrativeId": "narrative-uuid",
  "inSituVisitRecordId": "record-uuid"
}
```

```
id                  : UUID — the InSituVisitReport id
createdAt           : ISO-8601 timestamp (UTC) — when the report was generated
createdBy           : UUID — the staff caller's PermissionId (X-Permission-Id)
projectId           : UUID — the source CollectionUseProject
narrativeId         : UUID — the generated narrative (see 09)
inSituVisitRecordId : UUID — the exported CIDOC-CRM record (see 08)
```

### Errors

Because the endpoint composes the export and narrative steps, it surfaces the
union of their failures. All share the `{ "error": CODE, "message": str }` shape.

| Status | Code                         | When                                            |
| ------ | ---------------------------- | ----------------------------------------------- |
| `401`  | —                            | Missing/invalid credentials.                    |
| `403`  | `INSUFFICIENT_GROUP`         | Non-staff caller.                               |
| `404`  | `PROJECT_NOT_FOUND`          | No project with `project_id`.                   |
| `409`  | `INVALID_USE_TYPE`           | The project's `useType` is not `IN_SITU_VISIT`. |
| `400`  | `INVALID_NARRATIVE_TYPE`     | Unknown `narrative_type`.                       |
| `422`  | `SEMANTIC_VALIDATION_FAILED` | The reasoner/SHACL rejected the graph.          |
| `503`  | `MODEL_UNAVAILABLE`          | The local LLM could not be reached or returned an empty narrative. |
| `504`  | `MODEL_TIMEOUT`              | The LLM did not respond in time.                |

The export step (`404` / `409`) runs first; if it fails, no narrative or report
is created.

---

## GET /api/v1/reports/collection-use/in_situ_visit

Lists **every** report across **all** projects, **newest first** (`createdAt`
descending), paginated. Staff-only — a cross-project overview of all in-situ
visit reports generated. Each item carries its `projectId`; use the per-project
list below to scope to one project.

**Query parameters**

```
page : integer (optional, default 0,  min 0)
size : integer (optional, default 20, 1..100)
```

**Response `200 OK`** — a paginated envelope (`content[]` + `page` / `size` /
`totalElements` / `totalPages`). Unlike the other report endpoints (which return
ids only), each row here is **enriched for list rendering**: alongside the
linkage ids it carries the visit's display fields — `code`, `visitorName`,
`placeName`, `visitBeginDate`, `visitEndDate` — read at request time from the
report's record through the CIDOC-CRM published language (no data is denormalised
onto the report). Those record fields are `null` if the record can't be read.

```json
{
  "content": [
    {
      "id": "a1b2c3d4-...",
      "createdAt": "2026-06-22T10:30:00Z",
      "createdBy": "permission-uuid",
      "projectId": "project-uuid",
      "narrativeId": "narrative-uuid",
      "inSituVisitRecordId": "record-uuid",
      "code": "CUP-ABCD1234",
      "visitorName": "Maria do Rosário",
      "placeName": "Museum",
      "visitBeginDate": "2026-06-01",
      "visitEndDate": "2026-06-03"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

An empty store returns `totalElements: 0`. `403 INSUFFICIENT_GROUP` for non-staff callers.

---

## GET /api/v1/reports/collection-use/{project_id}/in_situ_visit

Lists the reports generated for a project, **newest first** (`createdAt`
descending), paginated. Staff-only.

**Path parameters**

```
project_id : UUID (required) — the CollectionUseProject whose reports to list
```

**Query parameters**

```
page : integer (optional, default 0,  min 0)
size : integer (optional, default 20, 1..100)
```

**Response `200 OK`**

```json
{
  "content": [
    {
      "id": "a1b2c3d4-...",
      "createdAt": "2026-06-22T10:30:00Z",
      "createdBy": "permission-uuid",
      "projectId": "project-uuid",
      "narrativeId": "narrative-uuid",
      "inSituVisitRecordId": "record-uuid"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

An unknown `project_id` simply returns an empty page (`totalElements: 0`).
`403 INSUFFICIENT_GROUP` for non-staff callers.

---

## GET /api/v1/reports/collection-use/{project_id}/in_situ_visit/{report_id}

Returns one report by id. Staff-only. The report must belong to the project in
the path — fetching another project's report under this `project_id` is a `404`.

**Path parameters**

```
project_id : UUID (required) — the owning CollectionUseProject
report_id  : UUID (required) — the InSituVisitReport id
```

**Response `200 OK`** — a single `InSituVisitReport` object (same shape as a
`content[]` item above).

**Response `404 REPORT_NOT_FOUND`** — no report with `report_id` under this
`project_id`.

```json
{
  "error": "REPORT_NOT_FOUND",
  "message": "No report found with id a1b2c3d4-... for project project-uuid"
}
```

`403 INSUFFICIENT_GROUP` for non-staff callers.

---

## GET /api/v1/reports/collection-use/{project_id}/in_situ_visit/{report_id}/detail

Returns one report **with its narrative and in-situ visit record embedded** — the
single call that backs the report detail page. Staff-only; same project-ownership
rule and `404 REPORT_NOT_FOUND` as the plain get-by-id above.

The server reads the linked narrative and record back through each context's
published language (`app.ai.museum_narrative.public` /
`app.cidoc_crm.public`), so `narrative` and `record` are the same DTOs those
contexts' own endpoints return (`09KG-RAG-Narrative.md` /
`08InSituVisit-CIDOC-CRM.md`). The `record` carries the nested
`requestedObjects` / `inSituOccurrences` / `inSituLogs` / `inSituPublications`,
each with their `attachments`. An attachment's `reference` is a URL/path; the
client decides whether to render it inline (image) or as a link.

**Path parameters**

```
project_id : UUID (required) — the owning CollectionUseProject
report_id  : UUID (required) — the InSituVisitReport id
```

**Response `200 OK`**

```json
{
  "id": "a1b2c3d4-...",
  "createdAt": "2026-06-22T10:30:00Z",
  "createdBy": "permission-uuid",
  "projectId": "project-uuid",
  "narrativeId": "narrative-uuid",
  "inSituVisitRecordId": "record-uuid",
  "narrative": {
    "narrative_id": "narrative-uuid",
    "record_id": "record-uuid",
    "generated_at": "2026-06-22T10:30:00Z",
    "meta": {
      "resolved_narrative_type": "institutional",
      "resolution_source": "default",
      "target_language": "pt",
      "creativity_temperature": 0.3,
      "llm_model": "llama3.1:8b"
    },
    "data": { "narrative": "…" }
  },
  "record": {
    "id": "record-uuid",
    "code": "CUP-ABCD1234",
    "visitBeginDate": "2026-06-01",
    "visitEndDate": "2026-06-03",
    "visitorName": "Maria do Rosário",
    "placeName": "Museum",
    "generatedAt": "2026-06-22T10:30:00Z",
    "requestedObjects": [{ "id": "...", "sourceId": "INV-1", "description": "…", "position": 0 }],
    "inSituOccurrences": [
      {
        "id": "...",
        "sourceId": "OCC-1",
        "description": "…",
        "position": 0,
        "attachments": [
          {
            "id": "...",
            "sourceId": "ATT-1",
            "description": "photo",
            "reference": "https://files/img.jpg",
            "position": 0
          }
        ]
      }
    ],
    "inSituLogs": [],
    "inSituPublications": []
  }
}
```

`narrative` / `record` are normally always present (artifacts are append-only and
never deleted); they are nullable only to guard against a broken link.

**Response `404 REPORT_NOT_FOUND`** — no report with `report_id` under this
`project_id`. `403 INSUFFICIENT_GROUP` for non-staff callers.

---

A few conventions worth noting:

**One transaction, atomic.** The export, narrative, and report are written under
a single commit. If narrative generation fails (`422` / `503` / `504`), the
exported record is rolled back too — no partial artifacts are persisted.

**Synchronous and slow.** Step 2 runs a local LLM (Ollama, `llama3.1:8b`)
synchronously, so this endpoint inherits its latency and the `503` / `504`
failure modes. Clients should set a generous timeout. Runtime requirements match
`09KG-RAG-Narrative.md` (`OLLAMA_BASE_URL`, `NARRATIVE_MODEL`,
`NARRATIVE_TIMEOUT_SECONDS`).

**Append-only, no dedup.** This endpoint creates fresh artifacts on every call. Re-running it
for the same project is intentional — e.g. to produce a narrative in a different
style or language — and yields a distinct `InSituVisitReport`.
