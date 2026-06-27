# KG-RAG Museum Narrative

A Knowledge-Graph-Augmented-Generation endpoint that turns a stored in-situ visit
into a human narrative. It reuses the CIDOC-CRM 7.1.3 mapping (see
`08InSituVisit-CIDOC-CRM.md`), expands + validates the graph (`rdflib` + `owlrl` +
`pyshacl`), selects a persona prompt by `narrative_type`, and runs a local
**Llama 3.1:8b** model via Ollama. Lives in its own context
(`app/ai/museum_narrative`) and reads the mapping through `app.cidoc_crm.public`.

`narrative_type` is a **rendering style** (the LLM persona), not a property of the
visit: the same facts are retold in different tones. The graph is the model's only
permitted source of facts. Same auth as the rest of the API (`Authorization` +
`X-Permission-Id`); **staff-only**. Errors use `{ "error": CODE, "message": str }`.

Every generation is **persisted** as a stored history row: the same record can be
retold many times in different styles/languages/temperatures, and each run is
kept. A manual `PATCH` may later correct only the narrative text; the generation
metadata stays unchanged. The `POST` returns the new `narrative_id`; the two
`GET` endpoints below read the stored history back.

---

## POST /api/v1/cedoc-mapping/in-situ-visit/{record_id}/narrative

**Path parameters**

```
record_id : UUID (required) — the stored InSituVisitRecord id
```

**Request body** (all optional)

```json
{
  "target_language": "pt",
  "narrative_type": "social_media",
  "creativity_temperature": 0.3
}
```

```
target_language        : string  (default "pt")   — output language code
narrative_type         : enum    (optional)       — see table; omitted → "institutional"
creativity_temperature : number  (default 0.3, 0.0–1.0) — LLM temperature
```

### Narrative types

| Value | Audience | Tone |
| --- | --- | --- |
| `institutional` | Curators, board, open-data portals | Formal, bureaucratic, compliance-focused. |
| `scientific` | Researchers | Rigorous, objective, methodology & outputs. |
| `audioguide_adult` | General visitors | Engaging, clear, low jargon. |
| `audioguide_child` | Young learners | Storytelling, pedagogical, enthusiastic. |
| `social_media` | Digital community | Concise, hook-driven, emojis, CTA. |

If `narrative_type` is omitted, the backend defaults to **`institutional`**
(`resolution_source: "default"`); when supplied it is echoed with
`resolution_source: "request_body"`.

**Response 200 OK** — also persists the narrative and returns its `narrative_id`
and `generated_at`.

```json
{
  "narrative_id": "f1e2d3c4-...",
  "record_id": "9481a-2026",
  "status": "success",
  "generated_at": "2026-06-21T10:30:00Z",
  "meta": {
    "resolved_narrative_type": "social_media",
    "resolution_source": "request_body",
    "target_language": "pt",
    "creativity_temperature": 0.3,
    "llm_model": "llama3.1:8b"
  },
  "data": {
    "narrative": "🐋 Ciência em ação no Museu! …"
  }
}
```

### Errors

**400 `INVALID_NARRATIVE_TYPE`** — unknown `narrative_type`.

```json
{
  "error": "INVALID_NARRATIVE_TYPE",
  "message": "The requested narrative_type 'marketing_sales' is not supported. Choose from: institutional, scientific, audioguide_adult, audioguide_child, social_media."
}
```

**404 `IN_SITU_VISIT_NOT_FOUND`** — no record with `record_id`.

**422 `SEMANTIC_VALIDATION_FAILED`** — the reasoner/SHACL rejected the graph.

```json
{
  "error": "SEMANTIC_VALIDATION_FAILED",
  "message": "The reasoner rejected the generated graph due to ontology constraints."
}
```

**403 `INSUFFICIENT_GROUP`** — non-staff caller. **503 `MODEL_UNAVAILABLE`** — the
local LLM could not be reached or returned an empty narrative. **504
`MODEL_TIMEOUT`** — the LLM did not respond in time.

---

## GET /api/v1/cedoc-mapping/in-situ-visit/{record_id}/narratives

Lists the stored narratives for an in-situ visit record, **newest first**,
paginated. Staff-only.

**Query parameters**

```
page : integer (optional, default 0,  min 0)
size : integer (optional, default 20, 1..100)
```

**Response 200 OK**

```json
{
  "content": [
    {
      "narrative_id": "f1e2d3c4-...",
      "record_id": "9481a-2026",
      "generated_at": "2026-06-21T10:30:00Z",
      "meta": {
        "resolved_narrative_type": "social_media",
        "resolution_source": "request_body",
        "target_language": "pt",
        "creativity_temperature": 0.3,
        "llm_model": "llama3.1:8b"
      },
      "data": { "narrative": "🐋 …" }
    }
  ],
  "page": 0,
  "size": 20,
  "total_elements": 1,
  "total_pages": 1
}
```

An unknown `record_id` simply returns an empty page (`total_elements: 0`).

---

## GET /api/v1/cedoc-mapping/in-situ-visit/{record_id}/narratives/{narrative_id}

Returns one stored narrative. Staff-only. The body is a single
`StoredNarrative` object (same shape as a `content[]` item above).

**404 `NARRATIVE_NOT_FOUND`** — no stored narrative with `narrative_id` under this
`record_id` (the narrative must belong to the visit record in the path).

```json
{
  "error": "NARRATIVE_NOT_FOUND",
  "message": "No narrative found with id f1e2d3c4-..."
}
```

**403 `INSUFFICIENT_GROUP`** — non-staff caller.

---

## PATCH /api/v1/cedoc-mapping/in-situ-visit/{record_id}/narratives/{narrative_id}

Edits the **text** of a stored narrative (a manual editorial correction). Only
the `narrative` property is mutable; the metadata (type, source, language,
temperature, model, `generated_at`) is preserved. Staff-only.

**Request body**

```json
{ "narrative": "Corrected narrative text." }
```

```
narrative : string (required, non-empty) — the replacement text (trimmed)
```

**Response 200 OK** — the updated `StoredNarrative` (same shape as the GET above).

**404 `NARRATIVE_NOT_FOUND`** — no stored narrative with `narrative_id` under this
`record_id` (the narrative must belong to the visit record in the path).

**422** — empty/blank `narrative` (validation). **403 `INSUFFICIENT_GROUP`** —
non-staff caller.

---

### Runtime note

Requires Ollama running with `llama3.1:8b` pulled (`ollama pull llama3.1:8b`),
configurable via `OLLAMA_BASE_URL`, `NARRATIVE_MODEL`, `NARRATIVE_TIMEOUT_SECONDS`.

---

### See also

[`10Reports-InSituVisit.md`](10Reports-InSituVisit.md) — composes the project
export with this narrative generation and persists both ids as an
`InSituVisitReport` in a single staff-only call.
