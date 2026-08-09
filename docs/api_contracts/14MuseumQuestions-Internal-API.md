# Museum Questions - Internal API Contract

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

### `GET /museum-questions/summary`

Returns staff dashboard counts by status.

Response:

```json
{ "submitted": 9, "answered": 120, "outOfScope": 3, "closed": 45 }
```

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

## Errors

- `401`: missing/invalid authentication.
- `403`: caller is not staff.
- `404 MUSEUM_QUESTION_NOT_FOUND`: unknown question id.
- `409 INVALID_MUSEUM_QUESTION_TRANSITION`: action is not valid for the current status.
- `422`: invalid request body.

## Rendering Rule

`message`, `answerBody`, and `outOfScopeReason` are untrusted text. Staff UI must render them
as plain text, never as HTML.
