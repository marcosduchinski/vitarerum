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

### `GET /museum-questions/{id}/triage`

Returns the latest stored `MuseumQuestionTriage`.

If the binary triage has never been run, returns `404 TRIAGE_NOT_FOUND`.

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
