# API Endpoint Specification: KG-RAG Museum Narrative

## 1. Overview

This endpoint orchestrates a **Knowledge Graph-Augmented Generation (KG-RAG)** pipeline. It takes a raw database record of an *in situ* museum visit, maps it to semantic **CIDOC-CRM v7.1.3 JSON-LD**, expands and validates the graph with a pure-Python RDF stack (`rdflib` + `owlrl` for RDFS/OWL-RL closure, `pyshacl` for domain/range consistency), and feeds the validated graph into a local **Llama 3.1 (8B)** LLM.

The final text is adapted to a specific **Narrative Type**, allowing the museum to repurpose the exact same historical data for multiple communication channels (e.g., formal compliance, public engagement, or education).

> **Implementation status.** Implemented as the bounded context `app/ai/museum_narrative`, which reads the CIDOC-CRM mapping through the published `app.cidoc_crm.public` Open Host Service. The formal API contract is `docs/api_contracts/09KG-RAG-Narrative.md`. The notes below mark where the delivered behaviour refines this original spec.

---

## 2. Endpoint Definition

* **HTTP Method:** `POST`
* **Path:** `/api/v1/cedoc-mapping/in-situ-visit/{record_id}/narrative`
* **Content-Type:** `application/json`

### Path Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `record_id` | String | The unique identifier of the raw source record within the institution's database. |

### Request Body (Configuration Options)

```json
{
  "target_language": "pt",
  "narrative_type": "social_media",
  "creativity_temperature": 0.3
}

```

### Supported Narrative Types (`narrative_type`)

| Value | Target Audience | Tone & Style Constraints |
| --- | --- | --- |
| `institutional` | Curators, Board, Open Data Portals | Formal, bureaucratic, focused on institutional impact, preservation, and administrative completeness. |
| `scientific` | Academic Community, Researchers | Rigorous, objective, emphasizing research methodologies, metadata accuracy, and scientific output (e.g., publications). |
| `audioguide_adult` | General Museum Visitors | Engaging, clear, informative, contextualizing the historical and cultural significance without heavy technical jargon. |
| `audioguide_child` | Young Learners, Schools | Storytelling approach, highly pedagogical, enthusiastic tone, focusing on interactive elements and curiosity triggers. |
| `social_media` | Digital Community (Instagram/TikTok) | Concise, dynamic, hook-driven, enthusiastic, optimizing engagement with a call-to-action and native use of emojis. |

*Note: `target_language` defaults to `"pt"` and `creativity_temperature` to `0.3`.*

> **Implemented behaviour (refines the original fallback).** `narrative_type` is a **rendering style** (the LLM persona), not a fact about the visit — the same graph is retold in different tones. The visit data does not encode a communication style, so the original "Abordagem 2 (Data-Driven via `crm:E55_Type`)" fallback cannot meaningfully discriminate. When `narrative_type` is omitted the backend therefore defaults to **`institutional`** and reports `resolution_source: "default"`.

---

## 3. Internal Pipeline Execution Steps

```
[Phase 1: Extract & Map] ──> [Phase 2: Semantic Reasoning] ──> [Phase 3: Prompt Selection] ──> [Phase 4: Local LLM Run]

```

### Phase 1: Extraction & Semantic Mapping

1. Fetch the raw record matching `{record_id}` (`InSituVisitRecord`).
2. Apply the schema mapper to output the baseline **JSON-LD** referencing the official CIDOC-CRM context.

### Phase 2: Inference Engine & Consistency

1. Parse the JSON-LD into an `rdflib` graph.
2. Apply RDFS/OWL-RL closure with `owlrl` over the bundled CIDOC-CRM class hierarchy (subclass inheritance + transitive properties such as `P89 falls within`).
3. Validate domain/range with `pyshacl` against the bundled CIDOC-CRM shapes. On non-conformance, abort and return HTTP `422` (`SEMANTIC_VALIDATION_FAILED`).

> **Implemented notes.** (a) `owlready2`/HermiT (OWL-DL, JVM) was intentionally **not** used — the pure-Python `rdflib` + `owlrl` + `pyshacl` stack covers expansion and the domain/range consistency we care about. (b) "Dynamic Type Resolution" is **dropped**: `narrative_type` is resolved from the request body, else the `institutional` default (see §2) — it is not derived from the graph.

### Phase 3: Prompt Engineering (Persona Alignment)

Select the pre-configured system instruction template based on the resolved `narrative_type`.

```text
[SYSTEM PROMPT]
You are an expert museum communicator specializing in {narrative_type} storytelling. 
Translate the provided structured graph data into a fluid narrative.

CRITICAL CONSTRAINTS:
1. You must ONLY use facts declared in the provided JSON-LD context. Do not hallucinate outside events.
2. Adopt the absolute tone, style, and structure of the requested narrative type: {narrative_type}.

[CONTEXT DATA (CIDOC-CRM Validated Graph)]
{Expanded_JSON_LD_Payload}

[USER PROMPT]
Generate the final text tailored to the specified narrative type constraints.

```

### Phase 4: Local LLM Interfacing

1. Send the persona prompt + validated graph to **Llama 3.1:8b** via Ollama (`langchain-ollama`), reusing the ProposalChat adapter pattern.
2. Keep `temperature=0.3` (or the user-defined override) to ensure strict factual grounding.

> **Implemented notes.** The response is a **single JSON body** (non-streaming) matching §4. Connection failures map to `503 MODEL_UNAVAILABLE`, timeouts to `504 MODEL_TIMEOUT`. Configured via `OLLAMA_BASE_URL`, `NARRATIVE_MODEL` (default `llama3.1:8b`), `NARRATIVE_TIMEOUT_SECONDS`.
>
> **Persistence.** Each generation is stored as a row in `generated_narratives` and the `POST` returns its `narrative_id` + `generated_at`. Stored narratives are read back via `GET /{record_id}/narratives` (paginated, newest first) and `GET /{record_id}/narratives/{narrative_id}` (`404 NARRATIVE_NOT_FOUND`), and the text can be corrected via `PATCH /{record_id}/narratives/{narrative_id}`. See `09KG-RAG-Narrative.md`.

---

## 4. Response Examples

### Example A: Success Response for `social_media` (`200 OK`)

```json
{
  "record_id": "9481a-2026",
  "status": "success",
  "meta": {
    "resolved_narrative_type": "social_media",
    "resolution_source": "request_body",
    "llm_model": "llama3.1:8b"
  },
  "data": {
    "narrative": "🐋 Ciência em ação no Museu! Ontem, recebemos o investigador João para estudar de perto o nosso incrível acervo biológico, com foco especial na carcaça de baleia-comum. 📝 Após um dia intenso de medições e análises no laboratório, esta imersão científica já deu frutos: um novo artigo científico foi submetido! O património do museu continua a impulsionar o conhecimento global. Ficou curioso? Venha visitar a nossa galeria! #MuseuLisboa #Ciencia #Biodiversidade"
  }
}

```

### Example B: Success Response for `institutional` (`200 OK`)

```json
{
  "record_id": "9481a-2026",
  "status": "success",
  "meta": {
    "resolved_narrative_type": "institutional",
    "resolution_source": "default",
    "llm_model": "llama3.1:8b"
  },
  "data": {
    "narrative": "Registou-se a conclusão da atividade de investigação in situ referente ao processo 9481a-2026, conduzida pelo Investigador João nas instalações do Museu Nacional de História Natural e da Ciência de Lisboa. A atividade envolveu o acesso direto e a aplicação de procedimentos de análise técnica ao espécime de baleia-comum catalogado na coleção de biologia. O escopo da visita foi plenamente cumprido, resultando na geração de logs de ocorrência patrimonial e na formalização de um produto de retorno científico, em total conformidade com as diretrizes de desenvolvimento de coleções desta instituição."
  }
}

```

### Error Responses

#### `422 Unprocessable Entity` (Semantic Validation Failed)

```json
{
  "error": "SEMANTIC_VALIDATION_FAILED",
  "message": "The reasoner rejected the generated graph due to ontology constraints."
}

```

#### `400 Bad Request` (Invalid Narrative Type requested)

```json
{
  "error": "INVALID_NARRATIVE_TYPE",
  "message": "The requested narrative_type 'marketing_sales' is not supported. Choose from: institutional, scientific, audioguide_adult, audioguide_child, social_media."
}

```

#### `404 Not Found` (Unknown record)

```json
{
  "error": "IN_SITU_VISIT_NOT_FOUND",
  "message": "No in-situ visit record found with id 9481a-2026"
}

```

#### `403 Forbidden` (Non-staff caller)

This is a staff action (`CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`, `SYS_ADMIN`); `EXTERNAL` callers get `403`.

#### `503 Service Unavailable` / `504 Gateway Timeout` (Local LLM)

Returned with `MODEL_UNAVAILABLE` when the Ollama model cannot be reached, or `MODEL_TIMEOUT` when it does not respond within `NARRATIVE_TIMEOUT_SECONDS`.

```json
{
  "error": "MODEL_UNAVAILABLE",
  "message": "The language model is currently unavailable"
}

```