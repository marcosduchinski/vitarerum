# Museum Questions - Internal API Contract

## Purpose

Authenticated staff members review questions submitted through `Pergunte ao Museu`,
send a manual answer when the question is in scope, mark questions out of scope with a
standard e-mail, and close already-finalized questions.

Authentication: bearer token + `X-Permission-Id`.

Authorization: `CURATORIAL` and `COLLECTIONS_MANAGEMENT`.

## Status Transitions

```text
SUBMITTED -> ANSWERED
SUBMITTED -> OUT_OF_SCOPE
SUBMITTED -> IN_PROGRESS (forward/assign responsible staff)
IN_PROGRESS -> IN_PROGRESS (forward/reassign responsible staff)
IN_PROGRESS -> ANSWERED
IN_PROGRESS -> OUT_OF_SCOPE
ANSWERED -> CLOSED
OUT_OF_SCOPE -> CLOSED
```

`SUBMITTED -> CLOSED` is invalid. `close` does not send e-mail.

## Endpoints

### `GET /museum-questions?status=&requesterEmail=&assignedTo=&unassignedOnly=&page=&size=`

Returns a paginated queue ordered by `createdAt ASC`. List items include
`attachmentCount`, not full attachment metadata.

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

Filters:

- `status` is optional: `SUBMITTED`, `IN_PROGRESS`, `ANSWERED`, `OUT_OF_SCOPE`, `CLOSED`
- `requesterEmail` matches the encrypted lookup hash
- `assignedTo` filters questions forwarded to a permission id
- `unassignedOnly=true` filters questions that have not been forwarded

### `GET /museum-questions/{id}`

Returns one `MuseumQuestionDetail`, including `attachments: []` for questions without
images.

### `POST /museum-questions/{id}/answer`

Request:

```json
{ "answerBody": "Manual answer sent to the requester." }
```

Valid from `SUBMITTED` or `IN_PROGRESS`. Sends an e-mail, records `answeredAt`, `answeredBy`,
`answerBody`, `answerSentAt`, and returns status `ANSWERED`.

### `POST /museum-questions/{id}/mark-out-of-scope`

Request:

```json
{ "reason": "Exhibition question" }
```

`reason` may be `null`. Valid from `SUBMITTED` or `IN_PROGRESS`. Sends the standard
out-of-scope e-mail, records `outOfScopeAt`, `outOfScopeBy`, `outOfScopeReason`,
`outOfScopeEmailSentAt`, and returns status `OUT_OF_SCOPE`.

### `POST /museum-questions/{id}/forward`

Request:

```json
{ "targetPermissionId": "perm-curator" }
```

Valid from `SUBMITTED` or `IN_PROGRESS`. The target permission must belong to
`CURATORIAL` or `COLLECTIONS_MANAGEMENT`. Records `assignedTo`, sends an in-app
notification to the target, and moves the question to (or keeps it in) `IN_PROGRESS`.

### `PATCH /museum-questions/{id}/close`

Valid only from `ANSWERED` or `OUT_OF_SCOPE`. Records `closedAt` and `closedBy`.
No e-mail is sent.

### `GET /museum-questions/{questionId}/attachments/{attachmentId}`

Returns the raw image bytes for a question attachment. Staff-only. The endpoint verifies the
attachment belongs to the question, returns the trusted image `Content-Type`, sets
`Content-Disposition: inline`, and includes `X-Content-Type-Options: nosniff`.

### `GET /museum-questions/summary`

Returns staff dashboard counts by status.

Response:

```json
{ "submitted": 9, "answered": 120, "outOfScope": 3, "closed": 45 }
```

## Response deadline

Each question receives a response deadline of 15 calendar days from
`createdAt`. The deadline is persisted as `responseDueAt`.

Questions are overdue when:

- `status` is `SUBMITTED` or `IN_PROGRESS`
- `answeredAt` is `null`
- `responseDueAt` is in the past

A scheduled operational command sends one in-app
`MUSEUM_QUESTION_RESPONSE_OVERDUE` notification to collection managers when a
question first becomes overdue:

```bash
uv run python -m app.museum_questions.presentation.commands notify-overdue --limit 100
```

The command is idempotent per question through `responseOverdueNotifiedAt`.

## `MuseumQuestionListItem`

```json
{
  "id": "q1",
  "requesterName": "Ana Souza",
  "requesterEmail": "ana@example.org",
  "subject": "Visit question",
  "message": "Plain text citizen message",
  "status": "SUBMITTED",
  "createdAt": "2026-07-05T10:00:00Z",
  "responseDueAt": "2026-07-20T10:00:00Z",
  "responseOverdueNotifiedAt": null,
  "responseOverdue": false,
  "answeredAt": null,
  "answeredBy": null,
  "answerBody": null,
  "answerSentAt": null,
  "outOfScopeAt": null,
  "outOfScopeBy": null,
  "outOfScopeReason": null,
  "outOfScopeEmailSentAt": null,
  "closedAt": null,
  "closedBy": null,
  "assignedTo": null,
  "attachmentCount": 1
}
```

## `MuseumQuestionDetail`

```json
{
  "id": "q1",
  "requesterName": "Ana Souza",
  "requesterEmail": "ana@example.org",
  "subject": "Visit question",
  "message": "Plain text citizen message",
  "status": "SUBMITTED",
  "createdAt": "2026-07-05T10:00:00Z",
  "responseDueAt": "2026-07-20T10:00:00Z",
  "responseOverdueNotifiedAt": null,
  "responseOverdue": false,
  "answeredAt": null,
  "answeredBy": null,
  "answerBody": null,
  "answerSentAt": null,
  "outOfScopeAt": null,
  "outOfScopeBy": null,
  "outOfScopeReason": null,
  "outOfScopeEmailSentAt": null,
  "closedAt": null,
  "closedBy": null,
  "assignedTo": null,
  "attachments": [
    {
      "id": "att-1",
      "fileName": "artifact.png",
      "contentType": "image/png",
      "sizeBytes": 1024,
      "createdAt": "2026-07-05T10:00:00Z"
    }
  ]
}
```

## Errors

- `401`: missing/invalid authentication.
- `403`: caller is not staff.
- `404 MUSEUM_QUESTION_NOT_FOUND`: unknown question id.
- `404 MUSEUM_QUESTION_ATTACHMENT_NOT_FOUND`: unknown attachment id for the question.
- `409 INVALID_MUSEUM_QUESTION_TRANSITION`: action is not valid for the current status.
- `422`: invalid request body.

## Rendering Rule

`message`, `answerBody`, and `outOfScopeReason` are untrusted text. Staff UI must render them
as plain text, never as HTML.
