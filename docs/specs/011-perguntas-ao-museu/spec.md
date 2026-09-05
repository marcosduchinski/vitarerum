# SPEC-011 — Ask the Museum

| Field | Value |
| --- | --- |
| Identifier | SPEC-011 |
| Status | Implemented (with declared delivery, audit, privacy, and operational gaps) |
| Bounded context | `app/museum_questions` |
| Written from | `app/museum_questions/`, `test/museum_questions/`, and the public and staff Angular features |
| Related specs | [SPEC-010](../010-submissao-publica/spec.md), [SPEC-018](../018-notificacoes/spec.md), [SPEC-022](../022-cifragem-e-armazenamento/spec.md) |

## 1. Problem

Not every contact with the museum is a formal collection-use request. Forcing
simple questions through the complete proposal workflow creates unnecessary
friction for citizens and unnecessary work for staff.

The open channel must nevertheless resist abuse, protect personal data, keep
uploaded images private, and give the institution a manageable response queue.

## 2. Goal

Provide a lightweight public channel for a question and one final staff reply,
without a public account, public status lookup, or conversation thread. Give
Curatorial and Collections Management staff an internal queue, assignment,
response, closure, and overdue-warning workflow.

This spec describes the implemented behavior. Properties that the current
system does not guarantee are listed in Section 9.

## 3. Scope and ubiquitous language

The public form explains that the operational scope is collection use,
especially on-site research visits. Other questions are not rejected during
submission. The backend can classify them as out of scope and send a standard
notice, although that action is currently hidden in the Angular staff page.

- **Museum question**: the aggregate root containing the request, response
  state, latest assignment, lifecycle audit fields, and image attachments.
- **Assignment**: the latest staff permission responsible for the question.
  Assigning a question moves it to `IN_PROGRESS`.
- **Response deadline**: 15 calendar days after submission, stored as
  `responseDueAt`.
- **Overdue question**: a `SUBMITTED` or `IN_PROGRESS` question without an
  answer whose response deadline has passed.
- **Final response**: either a manual answer or the standard out-of-scope
  notice. The requester cannot reply through this context.

The aggregate owns its attachment metadata. Files are held by the shared file
storage adapter; identity supplies staff and permission details; notifications
and e-mail are external effects coordinated outside the domain layer.

## 4. Actors, channels, and trust boundaries

| Actor or channel | Capability |
| --- | --- |
| Public visitor | Submit a question and optional images without authentication |
| Curatorial staff | Read, assign, answer, classify, and close questions |
| Collections Management staff | Same question-management access; also receives overdue warnings |
| Direction and other groups | No initial access to the internal question API or Angular routes |
| Scheduled operator | Invoke the overdue command; the application has no embedded scheduler |

Every public field and upload is untrusted. Angular checks improve the user
experience, but authorization, schema validation, captcha verification, image
inspection, and resource limits remain server responsibilities.

## 5. Lifecycle

| Current state | Operation | Next state |
| --- | --- | --- |
| `SUBMITTED` | assign/forward | `IN_PROGRESS` |
| `SUBMITTED` | answer | `ANSWERED` |
| `SUBMITTED` | mark out of scope | `OUT_OF_SCOPE` |
| `IN_PROGRESS` | reassign/forward | `IN_PROGRESS` |
| `IN_PROGRESS` | answer | `ANSWERED` |
| `IN_PROGRESS` | mark out of scope | `OUT_OF_SCOPE` |
| `ANSWERED` | close | `CLOSED` |
| `OUT_OF_SCOPE` | close | `CLOSED` |

All other transitions are rejected. In particular, a submitted question cannot
be closed without a final response.

## 6. Public-channel requirements

### RF-001 — Unauthenticated public experience

The Angular route `/ask-museum` is lazy-loaded without an authentication guard
and uses the public shell and Portuguese/English public catalogues. The client
does not attach a bearer token or cookies to the public question API, and the
API route does not require an authenticated caller.

`/ask-museum/received` confirms acceptance. There is no public tracking page,
reference number, status query, or reply thread; the final response arrives by
e-mail.

### RF-002 — Submission contract

`POST /api/v1/public/museum-questions` accepts JSON or
`multipart/form-data` when images are present:

| Field | Required | Constraint |
| --- | --- | --- |
| `requesterName` | yes | 1–120 characters |
| `requesterEmail` | yes | valid e-mail, at most 180 characters |
| `subject` | yes | 1–200 characters |
| `message` | yes | 1–4000 characters |
| `consent` | yes | must be exactly `true` |
| `captchaToken` | yes | 1–2048 characters |
| `website` | no | honeypot, at most 255 characters |
| `attachments` | no | 0–10 PNG/JPEG files; at most 5 MiB each and 25 MiB in total |

Names, subjects, and messages are trimmed and stripped of control characters.
CR/LF is replaced in names and subjects before those values can enter e-mail
content. The requester e-mail is validated by the server.

A successful request returns `202`:

```json
{
  "status": "RECEIVED",
  "email": "visitor@example.org"
}
```

The receipt does not expose the question identifier. It currently echoes the
full e-mail address rather than a masked value.

### RF-003 — Single-step acceptance

A valid question is persisted as `SUBMITTED` in the initial request. Unlike the
public proposal channel in [SPEC-010](../010-submissao-publica/spec.md), there
is no e-mail ownership confirmation or double opt-in.

The supplied consent is an admission requirement only. It is not stored in the
question aggregate or in a separate consent record.

### RF-004 — Silent honeypot

A non-empty `website` value produces the normal `202 RECEIVED` receipt but no
rate-limit check, captcha call, upload read, question persistence, notification,
or e-mail. Request-schema validation occurs first, so even a honeypot request
must contain syntactically valid required fields, including a non-empty captcha
token.

### RF-005 — Admission controls

For a normal submission, the server applies these process-local sliding-window
limits before captcha verification:

1. 5 requests per IP address per hour;
2. 3 requests per normalized e-mail address per day;
3. 500 requests globally per hour.

An exceeded limit returns `429` with the fixed header `Retry-After: 60`.
Turnstile failure returns `403`, and verifier unavailability returns `503`.
Local/test uses an always-pass verifier; non-local startup requires a configured
Turnstile secret.

The Angular form requires a token only when a Turnstile site key is configured.
Normal runtime configuration supplies a site key. If the key is omitted while
the real API remains in use, the client submits an empty token that the API
rejects during schema validation.

### RF-006 — Image validation and storage

The API enforces the image count and byte limits and recognizes PNG/JPEG content
from its signature rather than trusting only the browser media type or filename.
Safe filenames are bounded before storage references are generated.

Files are stored below `DATA_DIR`, outside the web root, through the shared
storage adapter in [SPEC-022](../022-cifragem-e-armazenamento/spec.md). If the
question repository fails after files have been written, those files are
reclaimed. Attachment content is fixed after submission; this context provides
no public replacement or deletion operation.

### RF-007 — Persistence and staff notification

The persisted question receives a UUID, `SUBMITTED` status, creation time, and
a response deadline 15 calendar days later. In-app notifications for distinct
Curatorial and Collections Management permissions are created in the question
transaction.

After commit, a submission e-mail is sent once per distinct staff user across
those groups. If the transaction fails, written images are reclaimed and no
staff e-mail is sent.

## 7. Internal-channel requirements

### RF-008 — Authorization

Internal endpoints require a bearer token and `X-Permission-Id`. The active
permission must belong to `CURATORIAL` or `COLLECTIONS_MANAGEMENT`. The Angular
routes under `/p/museum-questions` apply the same group guard.

### RF-009 — Queue, filters, and detail

`GET /api/v1/museum-questions` returns a page ordered by `createdAt` ascending.
It accepts filters for status, exact normalized requester e-mail, assignee, and
unassigned-only records. Page size is 1–100.

List items contain the full request text and lifecycle fields plus
`attachmentCount`; attachment metadata is returned only by the detail endpoint.
The exact e-mail filter uses a keyed lookup hash over the encrypted value.

`GET /api/v1/museum-questions/{id}` returns the question and its attachment
metadata. The assignee is hydrated to a small permission/user summary; other
actor audit fields remain raw permission identifiers.

The Angular projection provides:

- **All enquiries**, initially filtered to `SUBMITTED`, with status selection
  and pagination;
- **New inquiries**, restricted to unassigned `SUBMITTED` questions;
- **My enquiries**, restricted to `IN_PROGRESS` questions assigned to the
  active permission;
- a detail view with request, inline image previews, answer composer, deadline,
  and previous questions found by the same requester e-mail.

The history tab is a query-derived list of earlier questions, not an immutable
audit log or conversation thread.

### RF-010 — Manual answer

`POST /api/v1/museum-questions/{id}/answer` accepts an `answerBody` of 1–4000
characters from `SUBMITTED` or `IN_PROGRESS`. It moves the aggregate to
`ANSWERED` and records the responding permission, answer body, answer time, and
an `answerSentAt` timestamp.

The Angular composer permits bold, italic, paragraphs, line breaks, and lists.
Both client and e-mail renderer sanitize the rich text. The API commits the
transition before attempting the requester e-mail.

### RF-011 — Out-of-scope classification

`POST /api/v1/museum-questions/{id}/mark-out-of-scope` accepts an optional
reason of at most 1000 characters from `SUBMITTED` or `IN_PROGRESS`. It moves
the aggregate to `OUT_OF_SCOPE`, records actor and time, commits, and then sends
a standard requester e-mail.

The internal reason is not included in the standard e-mail. This backend action
is implemented and tested, but its Angular controls are currently commented out
and unavailable to staff.

### RF-012 — Assignment and reassignment

`POST /api/v1/museum-questions/{id}/forward` accepts a target permission from
Curatorial or Collections Management. From `SUBMITTED` it sets `IN_PROGRESS`;
from `IN_PROGRESS` it replaces the assignee while retaining that state. A new
assignee other than the caller receives an in-app notification. No forwarding
e-mail is sent.

The Angular queue currently exposes Forward only for an unassigned `SUBMITTED`
question. It builds target choices by reading at most 100 users from the generic
identity list and filtering their permissions in the browser. Reassignment is
therefore an API-only capability.

### RF-013 — Closure

`PATCH /api/v1/museum-questions/{id}/close` is valid only from `ANSWERED` or
`OUT_OF_SCOPE`. It records the closing permission and time, moves the question
to `CLOSED`, and sends no e-mail.

### RF-014 — Attachment access

`GET /api/v1/museum-questions/{questionId}/attachments/{attachmentId}` verifies
staff access and attachment ownership. It returns the trusted media type with
`Content-Disposition: inline` and `X-Content-Type-Options: nosniff`.

### RF-015 — Response deadline and overdue warning

A question is overdue only while `SUBMITTED` or `IN_PROGRESS`, unanswered, and
past `responseDueAt`. The following command processes due, unnotified questions:

```bash
uv run python -m app.museum_questions.presentation.commands notify-overdue --limit 100
```

For each question, it creates a `MUSEUM_QUESTION_RESPONSE_OVERDUE` notification
for every Collections Management permission and records
`responseOverdueNotifiedAt`. If no collection manager exists, the marker is not
set, so the warning remains due. The command must be scheduled externally.

### RF-016 — Safe response e-mail rendering

The answer e-mail is multipart with a readable plain-text alternative and an
HTML body. The HTML renderer retains only `b`, `br`, `em`, `i`, `li`, `ol`, `p`,
`strong`, and `ul`, removes attributes, and drops blocked active-content tags.
Requester data inserted into templates is escaped.

### RF-017 — Reserved summary endpoint

The historical API contract mentions `GET /museum-questions/summary`, but no
route, use case, response schema, UI consumer, or test exists. Adding it after
the current `/{question_id}` declaration would also cause `summary` to be
interpreted as an identifier; a future static route must be declared first.

The summary is therefore not an implemented requirement or acceptance
criterion.

## 8. Invariants and error behavior

| ID | Invariant |
| --- | --- |
| INV-001 | A question cannot move directly from `SUBMITTED` to `CLOSED` |
| INV-002 | Assignment leaves the question in `IN_PROGRESS` and stores the latest assignee |
| INV-003 | A finalised question cannot be answered, classified, or reassigned |
| INV-004 | Closure never sends an e-mail |
| INV-005 | The requester e-mail is encrypted and exact lookup uses its keyed hash |
| INV-006 | A honeypot request creates no persistent or external work |
| INV-007 | Requester e-mail is attempted only after the state transaction commits |
| INV-008 | Public text and staff rich text are safely rendered |

Expected API failures include:

| Condition | Result |
| --- | --- |
| Invalid or missing public field | `422` |
| Invalid captcha | `403` |
| Captcha provider unavailable | `503` |
| Rate limit exceeded | `429` with `Retry-After: 60` |
| Too many images or invalid multipart data | `422` |
| Oversized image | `413` |
| Unsupported or signature-mismatched image | `415` |
| Missing question or attachment | `404` |
| Forbidden internal group or invalid target group | `403` |
| Invalid lifecycle transition | `409` |

## 9. Known gaps and required improvements

| ID | Gap | Required change |
| --- | --- | --- |
| GAP-001 | `answerSentAt` and `outOfScopeEmailSentAt` are set before the post-commit SMTP attempt. A delivery failure therefore leaves a false sent marker. | Introduce durable delivery state/outbox processing and set the sent timestamp only after confirmed delivery. |
| GAP-002 | Post-commit submission, answer, and out-of-scope e-mails have no durable retry or idempotency boundary. A committed submission may return an error after e-mail failure and be resubmitted. | Use an outbox with retry, stable idempotency keys, and observable terminal failure state. |
| GAP-003 | Rate limits are process-local, reset on restart, and do not coordinate replicas; `Retry-After` is always 60 seconds rather than the remaining window. | Move counters to a shared atomic store and calculate an accurate retry delay. |
| GAP-004 | The receipt and Angular route query string expose the full requester e-mail, placing personal data in browser history and potentially logs/referrers. | Stop putting the address in the URL; use navigation state or generic copy, and mask any displayed address. |
| GAP-005 | Consent is required but not persisted with wording/version, time, or provenance. | Store auditable consent evidence or explicitly justify and document a no-retention policy. |
| GAP-006 | Questions and attachments have no retention, anonymisation, or erasure workflow. | Define the legal retention period and add scheduled deletion/anonymisation with file reclamation. |
| GAP-007 | Assignment and lifecycle fields hold only the latest values; there is no immutable transition, reassignment, or delivery audit history. | Persist append-only lifecycle events with actor, time, operation, and relevant delivery outcome. |
| GAP-008 | The Angular out-of-scope action is hidden, and reassignment is not exposed even though both are supported by the API. | Decide the intended staff workflow, then expose and test the actions or remove/rescope the backend contracts. |
| GAP-009 | Forward-target discovery fetches the first 100 users through a generic endpoint that is temporarily available to every authenticated profile, then filters in the browser. | Add a narrow authorized staff-recipient endpoint with server-side group filtering and pagination/search. |
| GAP-010 | Concurrent overdue workers can select the same unclaimed rows, and the command has no built-in scheduler. | Claim/lock work or use idempotent notification keys, and document/provision the external schedule. |
| GAP-011 | Queue ordering uses only `createdAt`; equal timestamps have no stable tie-breaker. | Add `id` as a deterministic secondary order. |
| GAP-012 | The specified summary endpoint is absent and would collide with the parameter route if appended in the current order. | Either remove it from historical contracts or implement the static route before `/{question_id}` with tests and a real consumer. |
| GAP-013 | CORS is configured globally for the application, not specifically for this public channel. Local defaults may allow `*`; non-local validation forbids it. | Keep explicit production origins and avoid describing route-specific CORS guarantees that the code does not enforce. |
| GAP-014 | Empty frontend Turnstile configuration is incompatible with the API's non-empty token schema. | Fail frontend startup/config validation for real API mode, or align the local no-captcha contract across client and server. |

## 10. Acceptance criteria

### AC-001 — Public submission, receipt, and staff notification

Covered by `test_api.py::test_submit_returns_202_receipt`,
`::test_submit_notifies_access_groups_and_emails_curators_and_managers`, and
`test_use_cases.py::test_execute_persists_submitted_question`.

### AC-002 — Open-channel protections and validation

Covered by the captcha, rate-limit, honeypot, consent, e-mail, length,
whitespace, and control-character tests in `test_api.py` and
`test_use_cases.py`.

### AC-003 — Verified and bounded images

Covered by the multipart, image-count, media-signature, total-size, persistence,
and storage-cleanup tests in `test_api.py` and `test_use_cases.py`.

### AC-004 — Internal authorization, queue, and detail

Covered by the internal-group rejection, filter, pagination, assignment
hydration, detail, and attachment-detail tests in `test_api.py` and the list
authorization/filter tests in `test_use_cases.py`.

### AC-005 — Lifecycle transitions

Covered by the new-question, answer, assignment/reassignment, overdue, and
closure tests in `test_domain.py`, `test_use_cases.py`, and `test_api.py`.

### AC-006 — Commit boundary and e-mail rendering

Covered by `test_api.py::test_answer_internal_question_does_not_email_when_commit_fails`,
`::test_mark_out_of_scope_does_not_email_when_commit_fails`, and the multipart
and sanitisation tests in `test_email.py`. These tests establish ordering, not
durable delivery; GAP-001 and GAP-002 remain open.

### AC-007 — Overdue notification behavior

Covered by the overdue domain tests and
`test_use_cases.py::test_notify_overdue_questions_notifies_collection_managers_once`
and `::test_notify_overdue_questions_without_managers_does_not_mark_notified`.

### AC-008 — Angular public and staff projections

Component tests cover public receipt/form behavior, queue filtering and
forwarding, detail rendering and sanitisation, previous-requester history, and
the assigned-question list. The hidden out-of-scope control and API-only
reassignment are not accepted UI capabilities.

## 11. Non-functional requirements

- **Confidentiality**: requester name, e-mail, subject, message, answer, internal
  out-of-scope reason, and attachment filename are encrypted in the database;
  attachment bytes use the configured shared encrypted file store.
- **Least privilege**: internal question APIs and attachment reads are limited
  to Curatorial and Collections Management permissions.
- **Stored-XSS resistance**: public text is interpolated as text, and permitted
  staff answer markup is allow-listed before e-mail and UI rendering.
- **Observability**: operational failures must be logged without public message
  bodies, tokens, or requester e-mail addresses. Durable delivery observability
  remains part of GAP-001/GAP-002.
- **Bounded-context independence**: captcha and rate-limit adapters are local to
  this context so policy can evolve independently from public proposals.

## 12. Traceability

| Element | Location |
| --- | --- |
| Aggregate and transitions | `vitarerum-api/app/museum_questions/domain/models.py` |
| Public and internal use cases | `vitarerum-api/app/museum_questions/application/` |
| Repository, captcha, rate limit, e-mail, and file adapters | `vitarerum-api/app/museum_questions/infrastructure/` |
| API routes, schemas, dependencies, and overdue command | `vitarerum-api/app/museum_questions/presentation/` |
| Backend verification | `vitarerum-api/test/museum_questions/` |
| Public Angular flow | `vitarerum-ui/src/app/features/public/ask-museum/` |
| Staff Angular flow | `vitarerum-ui/src/app/features/museum-questions/` |
| Cross-cutting API rules | `docs/api_contracts/README.md` |

## 13. Open decisions

1. Is the 15-day deadline a public service promise or only an internal warning
   threshold?
2. Is one final response still the intended service model, or should a tracked
   conversation be introduced?
3. Should staff see earlier questions linked by exact e-mail, and what privacy
   and retention policy authorizes that correlation?
4. Is out-of-scope classification still part of the product workflow, given
   that its UI was intentionally disabled?
5. Is reassignment history required, or is retaining only the latest assignee
   sufficient?
