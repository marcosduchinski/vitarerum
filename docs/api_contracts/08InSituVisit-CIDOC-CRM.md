# In Situ Visit — CIDOC-CRM mapping

The In Situ Visit CEDOC mapping is a separate bounded context
(`app/cidoc_crm/in_situ_visit_mapping`) that stores **generated mapping records** of
in-situ visits, ready to be projected onto CIDOC-CRM. The aggregate root is
`InSituVisitRecord`; it owns four child collections — `requestedObjects`,
`inSituOccurrences`, `inSituLogs`, `inSituPublications` — and the occurrence, log,
and publication records each own a list of `attachments`. The whole graph is one
consistency boundary: it is created in a single POST and read back whole. See
`docs/cidoc-crm.puml` for the domain model.

A record is a **snapshot**: its `id` and `generatedAt` are assigned by the server at
creation time and are never supplied by the client. Child and attachment ids are
likewise server-assigned.

All endpoints use the same authentication as the rest of the API (`Authorization`
bearer token + `X-Permission-Id` header) and the same error shape
(`{ "error": "CODE", "message": "string" }`). These are **staff actions**: only
`CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`, and `SYS_ADMIN` may call them;
`EXTERNAL` callers (researchers) get `403`.

---

## POST /api/v1/cedoc-mapping/in-situ-visit

**Description** — Persists a new in-situ visit mapping record with its full child
graph. The server assigns the aggregate `id`, every child/attachment `id`, and the
`generatedAt` timestamp, then returns the stored record. Responds `201 Created`.

**Request body**

```json
{
  "code": "ISV-2026-001",
  "visitBeginDate": "2026-01-15",
  "visitEndDate": "2026-01-17",
  "visitorName": "Dr. Ana Ribeiro",
  "placeName": "Reserve room B",
  "requestedObjects": [
    {
      "sourceId": "RO-001",
      "description": "Ceramic amphora, inv. 1872",
      "position": 0
    }
  ],
  "inSituOccurrences": [
    {
      "sourceId": "OCC-001",
      "description": "Surface crack observed on the base",
      "position": 0,
      "attachments": [
        {
          "sourceId": "OCC-001-A1",
          "description": "Detail photo of the crack",
          "reference": "https://files.example/occ-001-a1.jpg",
          "position": 0
        }
      ]
    }
  ],
  "inSituLogs": [
    {
      "sourceId": "LOG-001",
      "description": "Object handled with gloves under supervision",
      "position": 0,
      "attachments": []
    }
  ],
  "inSituPublications": [
    {
      "sourceId": "PUB-001",
      "description": "Field report excerpt",
      "position": 0,
      "attachments": []
    }
  ]
}
```

**Field notes**

```
code            : string (required)          — external code of the visit
visitBeginDate  : date (required, YYYY-MM-DD)
visitEndDate    : date (required, YYYY-MM-DD)
visitorName     : string (required)
placeName       : string (required)
requestedObjects   : array (optional, default [])
inSituOccurrences  : array (optional, default [])
inSituLogs         : array (optional, default [])
inSituPublications : array (optional, default [])
```

Each child item carries `sourceId` (required), `description` (optional, default
`""`), and `position` (required integer, used for ordering). Occurrences, logs, and
publications also carry `attachments` (optional, default `[]`); each attachment
carries `sourceId`, `description` (optional, default `""`), `reference` (required
URL/locator), and `position`. `requestedObjects` have no attachments.

**Response 201 Created**

```json
{
  "id": "uuid",
  "code": "ISV-2026-001",
  "visitBeginDate": "2026-01-15",
  "visitEndDate": "2026-01-17",
  "visitorName": "Dr. Ana Ribeiro",
  "placeName": "Reserve room B",
  "generatedAt": "2026-06-19T10:30:00Z",
  "requestedObjects": [
    {
      "id": "uuid",
      "sourceId": "RO-001",
      "description": "Ceramic amphora, inv. 1872",
      "position": 0
    }
  ],
  "inSituOccurrences": [
    {
      "id": "uuid",
      "sourceId": "OCC-001",
      "description": "Surface crack observed on the base",
      "position": 0,
      "attachments": [
        {
          "id": "uuid",
          "sourceId": "OCC-001-A1",
          "description": "Detail photo of the crack",
          "reference": "https://files.example/occ-001-a1.jpg",
          "position": 0
        }
      ]
    }
  ],
  "inSituLogs": [
    {
      "id": "uuid",
      "sourceId": "LOG-001",
      "description": "Object handled with gloves under supervision",
      "position": 0,
      "attachments": []
    }
  ],
  "inSituPublications": [
    {
      "id": "uuid",
      "sourceId": "PUB-001",
      "description": "Field report excerpt",
      "position": 0,
      "attachments": []
    }
  ]
}
```

**Response 403 Forbidden**

```json
{
  "error": "INSUFFICIENT_GROUP",
  "message": "Only CURATORIAL or COLLECTIONS_MANAGEMENT or DIRECTION or SYS_ADMIN members can perform this action"
}
```

**Response 422 Unprocessable Content** — returned for malformed bodies (missing
required field, invalid date). Follows the shared validation shape:

```json
{
  "message": "Validation failed",
  "errors": [
    { "field": "visitBeginDate", "message": "Input should be a valid date" }
  ]
}
```

---

## GET /api/v1/cedoc-mapping/in-situ-visit

**Description** — Lists stored in-situ visit mapping records, most recently
generated first, with their full child graphs. Paginated.

**Query parameters**

```
page : integer (optional, default 0,  min 0)        — zero-based page index
size : integer (optional, default 20, 1..100)       — page size
```

**Response 200 OK**

```json
{
  "content": [
    {
      "id": "uuid",
      "code": "ISV-2026-001",
      "visitBeginDate": "2026-01-15",
      "visitEndDate": "2026-01-17",
      "visitorName": "Dr. Ana Ribeiro",
      "placeName": "Reserve room B",
      "generatedAt": "2026-06-19T10:30:00Z",
      "requestedObjects": [],
      "inSituOccurrences": [],
      "inSituLogs": [],
      "inSituPublications": []
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

Each item in `content` has the same shape as the POST `201` response. `totalElements`
is the total count across all pages; `totalPages` is `ceil(totalElements / size)`.

**Response 403 Forbidden** — same shape as the POST endpoint (non-staff callers).

---

## GET /api/v1/cedoc-mapping/in-situ-visit/{record_id}/cidoc-crm

**Description** — Returns a **CIDOC-CRM 7.1.3 JSON-LD** representation of a stored
record, mapping the aggregate onto CRM entities and properties. The visit becomes an
`E7_Activity`; the visitor an `E21_Person` (`P14_carried_out_by`); the place an
`E53_Place` (`P7_took_place_at`); the dates an `E52_Time-Span` (`P4_has_time-span`)
whose interval is declared with `P170i_time_is_defined_by` → an `E61` Time Primitive
literal. Each `requestedObject` becomes an `E20_Biological_Object`
(`P16_used_specific_object`); each occurrence an `E7_Activity` sub-event
(`P9_consists_of`, note via `P3_has_note`); each publication an `E65_Creation`
(`P9_consists_of`) that `P94_has_created` an `E73_Information_Object`; each log an
`E31_Document` (`P70_documents`); each attachment an `E31_Document` with
`schema:contentUrl` taken from its `reference`. Read-only; persists nothing.

> Targets the stable CIDOC-CRM **7.1.3** release. `P82a`/`P82b` are not used — 7.1.3
> defines the declared interval through `P170 defines time`.

**Path parameters**

```
record_id : UUID (required) — the InSituVisitRecord id returned by POST
```

**Response 200 OK** — a raw JSON-LD document (`application/json`; no Pydantic
response model). The `@context` is the official CIDOC-CRM 7.1.3 term map
(defining the `crm` prefix and every E/P term) **inlined** so the document is
self-contained, merged with the project-local prefixes (`ex`, `dcterms`,
`schema`, `xsd`, `rdfs`):

```json
{
  "@context": {
    "crm": "http://www.cidoc-crm.org/cidoc-crm/",
    "E7_Activity": { "@id": "crm:E7_Activity" },
    "P170i_time_is_defined_by": { "@id": "crm:P170i_time_is_defined_by" },
    "…": "… (full 7.1.3 term map) …",
    "ex": "http://example.org/museum/",
    "dcterms": "http://purl.org/dc/terms/",
    "schema": "https://schema.org/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
  },
  "@graph": [
    {
      "@id": "ex:visit/3f1c…",
      "@type": "crm:E7_Activity",
      "rdfs:label": "In situ visit VS-0001",
      "crm:P14_carried_out_by": { "@id": "ex:actor/dr-ana-ribeiro" },
      "crm:P7_took_place_at": { "@id": "ex:place/reserve-room-b" },
      "crm:P4_has_time-span": { "@id": "ex:timespan/visit-3f1c…" },
      "crm:P2_has_type": { "@id": "ex:type/in-situ-visit" },
      "crm:P16_used_specific_object": { "@id": "ex:object/visit-3f1c…/ro-001" },
      "crm:P9_consists_of": [
        { "@id": "ex:occurrence/visit-3f1c…/occ-001" },
        { "@id": "ex:creation/visit-3f1c…/pub-001" }
      ]
    },
    {
      "@id": "ex:timespan/visit-3f1c…",
      "@type": "crm:E52_Time-Span",
      "rdfs:label": "2026-01-15 - 2026-01-17",
      "crm:P170i_time_is_defined_by": "2026-01-15/2026-01-17"
    }
  ]
}
```

The full `@graph` additionally contains the actor, place, `E55_Type` vocabulary
terms, the per-child nodes described above, and a provenance node
(`ex:graph/visit-{id}`) carrying `dcterms:created` (the record's `generatedAt`),
`ex:mapping_version`, and `ex:crm_version`.

**Response 404 Not Found**

```json
{
  "error": "IN_SITU_VISIT_NOT_FOUND",
  "message": "No in-situ visit record found with id 3f1c…"
}
```

**Response 403 Forbidden** — same shape as the other endpoints (non-staff callers).

---

## POST /api/v1/collection-use-projects/{project_id}/export-in-situ-visit-record

**Description** — Generates an `InSituVisitRecord` **from an existing
collection-use project** and persists it, then returns the stored record (same
`201 Created` body shape as `POST /api/v1/cedoc-mapping/in-situ-visit`). This is a
cross-context export: the mapping context reads the project and its journals
through the Use of Collections published language (OHS), maps them, and saves a
fresh snapshot. Each call creates a **new** record (no de-duplication); `id`,
child/attachment ids and `generatedAt` are server-assigned.

Staff-only, same auth and error shape as the rest of the context.

**Pre-condition** — the project's `intendedUse.useType` must be `IN_SITU_VISIT`.

**Field mapping (project → record)**

```
code               <- project.referenceNumber
visitBeginDate     <- project.beginDate
visitEndDate       <- project.endDate
visitorName        <- requester's display name (falls back to the permission id)
placeName          <- configured INSTITUTION_NAME
requestedObjects   <- proposal.requestedObjects  (sourceId = inventory number)
inSituOccurrences  <- ObjectOccurrenceLog entries (sourceId = entry id, attachments sourceId/reference = fileReference)
inSituLogs         <- ObjectAccessLog entries     (sourceId = entry id, attachments sourceId/reference = fileReference)
inSituPublications <- PublicationLog entries      (sourceId = entry id, attachments sourceId/reference = fileReference)
```

There is no request body; `place_name` comes from the `INSTITUTION_NAME` setting.

**Response 201 Created** — identical shape to the
`POST /api/v1/cedoc-mapping/in-situ-visit` response above.

**Response 403 Forbidden** — non-staff callers (`EXTERNAL`).

**Response 404 Not Found**

```json
{
  "error": "PROJECT_NOT_FOUND",
  "message": "No collection-use project found with id {project_id}"
}
```

**Response 409 Conflict** — the project is not an in-situ visit:

```json
{
  "error": "INVALID_USE_TYPE",
  "message": "Project intended use must be IN_SITU_VISIT to export an in-situ visit record"
}
```

---

### See also

[`10Reports-InSituVisit.md`](10Reports-InSituVisit.md) — runs this export
together with narrative generation and persists the linkage as an
`InSituVisitReport` in a single call.
