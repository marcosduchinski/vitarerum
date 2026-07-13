# Museum Questions — Internal API Contract

## Purpose

Authenticated staff members review questions submitted through `Pergunte ao Museu`,
send a manual answer when the question is in scope, mark questions out of scope with a
standard e-mail, and close already-finalized questions.

Authentication: bearer token + `X-Permission-Id`.

Authorization: any staff group (`CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`,
`SYS_ADMIN`) via `require_staff`.

## Status Transitions

```text
SUBMITTED -> ANSWERED
SUBMITTED -> OUT_OF_SCOPE
ANSWERED -> CLOSED
OUT_OF_SCOPE -> CLOSED
```

`SUBMITTED -> CLOSED` is invalid. `close` does not send e-mail.

## Endpoints

### `GET /museum-questions?status=&page=&size=`

Returns a paginated queue ordered by `createdAt ASC`.

Response:

```json
{
  "content": [],
  "page": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0
}
```

`status` is optional: `SUBMITTED`, `ANSWERED`, `OUT_OF_SCOPE`, `CLOSED`.

### `GET /museum-questions/{id}`

Returns one `MuseumQuestion`.

### `POST /museum-questions/{id}/triage`

Runs AI triage for one question and returns a `MuseumQuestionTriage`.

When `use_category_classification_enabled` is enabled, the response still waits only for
the binary triage. The experimental use-category classification is created as
`PENDING` in the same transaction and processed asynchronously after commit.
When `use_category_embedding_shadow_enabled` is also enabled, a second shadow
classification with `classifierKind=EMBEDDING` is created and processed
asynchronously for calibration; operational responses continue to surface only the
current `LLM` use-category classification.
When `use_category_cascade_enabled` is also enabled, a `classifierKind=CASCADE`
classification is created and processed asynchronously. The cascade runs
embeddings first and escalates to the LLM on low confidence, narrow margin,
long messages, or uncertain categories. If Tier 2 fails after Tier 1 succeeded,
the row is completed with `quality=DEGRADED` and fallback metadata; the
operational `GET /triage` response still surfaces only the current `LLM` line
until the UI/operations phase promotes `CASCADE`.

### `GET /museum-questions/{id}/triage`

Returns the latest stored `MuseumQuestionTriage`.

If the binary triage has never been run, returns `404 TRIAGE_NOT_FOUND`.

### `GET /museum-questions/{id}/triage/classifications`

Returns the current use-category classifier executions attached to the latest
stored triage. This endpoint is for internal evaluation/calibration: it can show
the operational `LLM` line, the shadow `EMBEDDING` line, and the experimental
`CASCADE` line side by side, including execution metadata. It does not change
the operational triage response.

If the binary triage has never been run, returns `404 TRIAGE_NOT_FOUND`.

### `PUT /museum-questions/{id}/triage/use-categories`

Request:

```json
{ "categories": ["ANSWERING_ENQUIRIES", "RESEARCH_PROJECTS"] }
```

Persists the staff-reviewed final category set for the latest triage. This creates
a new current `classifierKind=CASCADE` classification with
`classifierVersion=staff-reviewed-v1`, `confidence=1.0` scores, and metadata
including `staff_reviewed`, `reviewed_by`, and `reviewed_at`. If a current
`CASCADE` line exists, it is superseded and the new line receives
`runNumber + 1`.

An empty `categories` list is valid and records `outcome=UNCLEAR`. This action
does not change `verdict`, `effectiveVerdict`, or `staffOverrideVerdict`.

Response: `UseCategoryClassificationAuditList` for the latest triage.

### `GET /museum-questions/triage/classifications/calibration.csv?limit=100`

Exports a calibration CSV for human labelling and threshold/prototype tuning.
The file intentionally omits citizen message text, requester name, and requester
e-mail. It includes `message_hash_sha256`, computed from normalized message text,
so exported rows can be checked against the live application without storing
personal data in git or a shared spreadsheet.

Columns:

```csv
triage_id,question_id,internal_link,question_status,triage_created_at,binary_effective_verdict,message_hash_sha256,llm_status,llm_outcome,llm_assigned_categories,llm_category_scores,embedding_status,embedding_outcome,embedding_assigned_categories,embedding_category_scores,embedding_metadata,human_categories
```

`human_categories` is blank by design; the curatorial reviewer fills it outside
the system after consulting the original question in the application.

### `PATCH /museum-questions/{id}/triage/verdict`

Request:

```json
{ "verdict": "OUT_OF_SCOPE" }
```

Records a staff correction of the binary AI verdict and returns the updated
`MuseumQuestionTriage`.

### `PUT /museum-questions/{id}/triage/search-terms`

Request:

```json
{
  "terms": [{ "english": "Allende meteorite", "portuguese": "Meteorito Allende" }]
}
```

Reconciles staff-edited search terms for an in-scope triage and returns the updated
`MuseumQuestionTriage`.

### `POST /museum-questions/{id}/answer`

Request:

```json
{ "answerBody": "Manual answer sent to the requester." }
```

Valid only from `SUBMITTED`. Sends an e-mail, records `answeredAt`, `answeredBy`,
`answerBody`, `answerSentAt`, and returns status `ANSWERED`.

### `POST /museum-questions/{id}/mark-out-of-scope`

Request:

```json
{ "reason": "Exhibition question" }
```

`reason` may be `null`. Valid only from `SUBMITTED`. Sends the standard
out-of-scope e-mail, records `outOfScopeAt`, `outOfScopeBy`, `outOfScopeReason`,
`outOfScopeEmailSentAt`, and returns status `OUT_OF_SCOPE`.

### `PATCH /museum-questions/{id}/close`

Valid only from `ANSWERED` or `OUT_OF_SCOPE`. Records `closedAt` and `closedBy`.
No e-mail is sent.

## `MuseumQuestion`

```json
{
  "id": "q1",
  "requesterName": "Ana Souza",
  "requesterEmail": "ana@example.org",
  "subject": "Visit question",
  "message": "Plain text citizen message",
  "status": "SUBMITTED",
  "createdAt": "2026-07-05T10:00:00Z",
  "answeredAt": null,
  "answeredBy": null,
  "answerBody": null,
  "answerSentAt": null,
  "outOfScopeAt": null,
  "outOfScopeBy": null,
  "outOfScopeReason": null,
  "outOfScopeEmailSentAt": null,
  "closedAt": null,
  "closedBy": null
}
```

## `MuseumQuestionTriage`

```json
{
  "id": "triage-1",
  "questionId": "q1",
  "verdict": "IN_SCOPE",
  "effectiveVerdict": "IN_SCOPE",
  "staffOverrideVerdict": null,
  "isVisitRelated": true,
  "mentionedObjects": [
    { "english": "Allende meteorite", "portuguese": "Meteorito Allende", "origin": "AI" }
  ],
  "objectMatches": [],
  "suggestedReply": null,
  "searchStrategy": "Correspondência aproximada por similaridade textual...",
  "modelName": "llama3.1:8b",
  "createdAt": "2026-07-10T12:00:00Z",
  "useCategoryClassification": {
    "status": "COMPLETED",
    "outcome": "CATEGORIZED",
    "quality": "FULL",
    "classifierKind": "LLM",
    "classifierModel": "llama3.1:8b",
    "classifierVersion": "llm-use-category-v1",
    "assignedCategories": [
      { "category": "RESEARCH_PROJECTS", "confidence": 0.91, "source": "LLM" }
    ],
    "categoryScores": [
      { "category": "RESEARCH_PROJECTS", "confidence": 0.91, "source": "LLM" }
    ],
    "classifiedAt": "2026-07-10T12:00:05Z",
    "error": null
  }
}
```

`useCategoryClassification.status` values:

- `NOT_REQUESTED`: synthesized by the API when no current child row exists; never
  persisted.
- `PENDING`: the child row exists and asynchronous classification has not finished.
- `COMPLETED`: classification finished successfully; `outcome`, `quality`, and
  `classifiedAt` are non-null.
- `FAILED`: classification was attempted and failed; `error` and `classifiedAt` are
  non-null.

When no current child row exists, `useCategoryClassification` is returned as:

```json
{
  "status": "NOT_REQUESTED",
  "outcome": null,
  "quality": null,
  "classifierKind": null,
  "classifierModel": null,
  "classifierVersion": null,
  "assignedCategories": [],
  "categoryScores": [],
  "classifiedAt": null,
  "error": null
}
```

## `UseCategoryClassificationAuditList`

```json
{
  "triageId": "triage-1",
  "classifications": [
    {
      "id": "classification-1",
      "triageId": "triage-1",
      "status": "COMPLETED",
      "outcome": "CATEGORIZED",
      "quality": "FULL",
      "classifierKind": "EMBEDDING",
      "classifierModel": "nomic-embed-text",
      "classifierVersion": "embedding-prototypes-v1",
      "runNumber": 1,
      "supersededAt": null,
      "assignedCategories": [
        { "category": "RESEARCH_PROJECTS", "confidence": 0.86, "source": "EMBEDDING" }
      ],
      "categoryScores": [],
      "classifiedAt": "2026-07-10T12:01:00Z",
      "error": null,
      "metadata": {
        "threshold_profile": "embedding-prototypes-v1",
        "would_escalate_due_to_length": false
      },
      "createdAt": "2026-07-10T11:59:00Z"
    }
  ]
}
```

## Errors

- `401`: missing/invalid authentication.
- `403`: caller is not staff.
- `404 MUSEUM_QUESTION_NOT_FOUND`: unknown question id.
- `404 TRIAGE_NOT_FOUND`: no AI triage has been run for the question.
- `409 TRIAGE_NOT_IN_SCOPE`: search terms were submitted for an out-of-scope triage.
- `409 INVALID_MUSEUM_QUESTION_TRANSITION`: action is not valid for the current status.
- `422`: invalid request body.

## Rendering Rule

`message`, `answerBody`, and `outOfScopeReason` are untrusted text. Staff UI must render them
as plain text, never as HTML.
