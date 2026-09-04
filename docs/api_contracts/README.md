---
status: current
---

# Cross-Cutting API Contract

What every Vitarerum endpoint shares: how a caller authenticates, how the acting
role is chosen, what a failure looks like, and how collections are paged.

Read this once. The per-endpoint request and response schemas are generated from
the code and served as OpenAPI. Note the schema sits at the **application root**,
not under the API prefix: `/openapi.json`, interactive at `/docs`. Those are
always current, so this document deliberately does not repeat them. The rules
and invariants behind each context live in
[`docs/specs/`](../specs/README.md).

## Base URL

The API and the Angular application are served from **one origin**: the
production image builds the UI into the FastAPI runtime. API routes live under
`/api/v1`; every other path falls back to the SPA.

| Environment | Base URL |
| --- | --- |
| Local dev (API only) | `http://127.0.0.1:8000/api/v1` |
| Local dev (Angular dev server) | `http://localhost:4200`, calling the API at whatever `api-base-url` names |
| Deployed | `<application origin>/api/v1` |

There is no separate API host in the deployed image, so a client that already
loaded the page can call the API with a relative path.

The Angular application does not compile the API location in. It fetches
`/config/environment.json` at startup and reads `api-base-url` from it — `/api/v1`
in the integrated image, an absolute URL when the API runs elsewhere. That file
is served with `Cache-Control: no-cache` precisely so a stale copy cannot outlive
a deployment.

---

## Session and acting role

### Getting a session

`POST /auth/login` returns an `accessToken`, the authenticated `user`, the
`permissions` that user holds, and the `institution` they act within.

### Every authenticated request sends two headers

```http
Authorization: Bearer <accessToken>
X-Permission-Id: <permissionId>
```

**This is the part OpenAPI cannot express, and the most common source of
integration bugs.** The two headers answer different questions:

| Header | Answers |
| --- | --- |
| `Authorization` | *Who* is calling — the authenticated user |
| `X-Permission-Id` | *As what* they are calling — the role they are acting in |

One person may hold several permissions — a curator who is also a researcher,
for instance. The token alone does not say which of them is acting, and the
server will not guess: authorization is decided against the permission named in
`X-Permission-Id`, and every audit record stores that permission, not the user.

A client therefore keeps the chosen permission alongside the token and sends it
on every call. Switching role is a change of header, not a new login.

### `401` versus `403`

The distinction is strict and load-bearing: **`401` means the session is over
and the client should log the user out; `403` means the session is fine but this
role may not do this.** Never treat them the same.

| Situation | Status |
| --- | --- |
| `Authorization` header missing or malformed | `401` |
| Token invalid or expired | `401` |
| User disabled | `401` |
| Token issued before the user's last password change | `401` |
| `X-Permission-Id` missing | `403` |
| Permission unknown | `403` |
| Permission does not belong to the authenticated user | `403` |
| Acting group not authorized for the operation | `403` |

A token is valid for 12 hours by default (`ACCESS_TOKEN_TTL_MINUTES`). Changing
or resetting a password invalidates every token issued before that moment, so a
stolen token stops working as soon as the owner reacts.

### Group vocabulary

`X-Permission-Id` resolves to exactly one group:

| Group | Typical scope |
| --- | --- |
| `EXTERNAL` | Researcher or citizen; sees only their own proposals and projects |
| `CURATORIAL` | Curatorial staff; the **only** group that approves a proposal |
| `COLLECTIONS_MANAGEMENT` | Collections management staff |
| `DIRECTION` | Direction staff |
| `SYS_ADMIN` | System administration; sole administrator of the object catalog |

"Staff" throughout the contracts means any group other than `EXTERNAL`.
Group membership is checked **on the server**; the fact that the frontend menu
hides an action is not a security boundary.

---

## Endpoints that take no session

Three sets of routes are reachable without `Authorization`:

| Routes | Trust model |
| --- | --- |
| `/api/v1/auth/*` | Login, password change, password-reset request and confirm |
| `/api/v1/public/*` | Public proposal submission, public museum questions, public document templates. Protected by captcha, consent and double opt-in rather than by a session |
| `/api/v1/external/publications/{token}` | A published report and its JSON-LD, reachable by unguessable token; the token *is* the authorization |

Everything else requires both headers.

---

## Error envelope

Every failure — from any context — comes back in one of four shapes. A client
should read `message`, `errors` and `fieldErrors`, and may read `error` when it
needs to branch on a specific cause. Any other key is a superset and should be
ignored.

### Request validation — `422`

```json
{
  "message": "Validation failed",
  "errors": [{ "field": "beginDate", "message": "Input should be a valid date" }]
}
```

`field` is the dotted path into the request body or query, with the `body` and
`query` prefixes stripped.

### Authorization — `403`

```json
{ "error": "ACCESS_DENIED", "message": "..." }
{ "error": "INSUFFICIENT_GROUP", "message": "..." }
```

`ACCESS_DENIED` means the acting role may not touch *this* resource;
`INSUFFICIENT_GROUP` means the role is wrong for the operation regardless of
resource.

### Everything else — typed code plus message

```json
{ "error": "PROJECT_NOT_FOUND", "message": "No project found with id missing" }
{ "error": "INVALID_TRANSITION", "message": "Cannot cancel a rejected proposal" }
```

`message` is always present. `error` carries the machine-readable code and is
documented per endpoint in each context's contract. Some responses add
`fieldErrors` or `dependencies`.

**`404` is used where `403` might be expected.** Asking for a resource that
belongs to another project, another institution or another user answers `404`,
not `403` — the existence of other people's records is not disclosed. Do not
read a `404` as proof that an identifier is invalid.

### Storage failure — `500`

```json
{ "error": "FILE_UNREADABLE", "message": "Stored file could not be read." }
{ "error": "FIELD_UNREADABLE", "message": "Stored field could not be read." }
```

Returned when an encrypted file or field does not decrypt. The message is
deliberately generic; the detail goes to the server log and never to the
response.

---

## Pagination

Every paged collection uses the same envelope:

```json
{
  "content": [ ... ],
  "page": 0,
  "size": 20,
  "totalElements": 137,
  "totalPages": 7
}
```

| Parameter | Rule |
| --- | --- |
| `page` | Zero-based. Minimum 0, default 0 |
| `size` | Minimum 1, **maximum 100**. Default 20 on almost every endpoint |

Two endpoints differ in default only, never in maximum: the curatorial knowledge
listing defaults to 25, and the audit-trail revisions to 100. A `size` above 100
is a `422`, not a silent clamp.

Non-paginated list endpoints return a bare JSON array. When a card only needs a
count, read `totalElements` from a page of `size=1` rather than fetching
everything.

---

## Conventions

**Timestamps.** All persisted timestamps are timezone-aware and stored in UTC;
they serialize as ISO 8601. Date-only fields (`beginDate`, `endDate`) carry no
time. Some examples in the older contracts omit the offset — the schema in
OpenAPI is authoritative.

**Uploads.** Multipart uploads are read in chunks and refused before the whole
body is buffered. Above the global cap (`MAX_UPLOAD_BYTES`, 25 MB by default)
the response is `413`:

```json
{ "error": "FILE_TOO_LARGE", "message": "File exceeds the ...-byte limit" }
```

Individual contexts impose tighter limits and allowed types on top of this —
proposal documents, question images and journal attachments each have their own
rules, documented in their contracts.

**Idempotency.** Only the autonomous scientific-return flow takes an
`Idempotency-Key` header, and there it is required, not optional. The key is
bound to one target: reusing it for a different target is a `422`. See
[SPEC-024](../specs/024-investigacao-agentica-autonoma/spec.md).

**Deletion.** `204` with no body where a resource is removed outright; some
endpoints instead return the resource in its new state because the caller needs
to see what was recorded. Several "deletions" are state changes, not removals.

**CORS.** Configured per environment. Outside local and test, a wildcard origin
is refused at startup rather than silently accepted.

---

## Typed error codes

Every `error` value the application can return, paired with its status and the
context that raises it. Generated from the exception sites in the code, so this
is the complete set — not a sample. The OpenAPI schema does **not** carry these:
it declares response bodies only for `422` validation failures.

A code maps to exactly one status. Branch on `error`, not on the message text,
which is prose and may change.

### 400 Bad Request

| Code | Raised by |
| --- | --- |
| `INCORRECT_CURRENT_PASSWORD` | identity |
| `INVALID_NARRATIVE_TYPE` | AI narrative / prompts, reports |
| `WEAK_PASSWORD` | identity |

### 403 Forbidden

| Code | Raised by |
| --- | --- |
| `ACCESS_DENIED` | cross-cutting, notifications, use of collections |
| `DIRECTION_READ_ONLY` | use of collections |
| `INSUFFICIENT_GROUP` | cross-cutting, use of collections |
| `OUT_OF_SCOPE` | public submission |

### 404 Not Found

| Code | Raised by |
| --- | --- |
| `AMENDMENT_UNAVAILABLE` | public submission |
| `DOCUMENT_TEMPLATE_NOT_FOUND` | document templates |
| `GROUP_NOT_FOUND` | identity |
| `INSTITUTION_NOT_FOUND` | identity |
| `IN_SITU_VISIT_NOT_FOUND` | AI narrative / prompts, CIDOC-CRM mapping |
| `MUSEUM_QUESTION_ATTACHMENT_NOT_FOUND` | museum questions |
| `MUSEUM_QUESTION_NOT_FOUND` | museum questions |
| `NARRATIVE_NOT_FOUND` | AI narrative / prompts |
| `NOT_FOUND` | notifications, use of collections |
| `PERMISSION_NOT_FOUND` | identity, use of collections |
| `PROJECT_NOT_FOUND` | CIDOC-CRM mapping, reports |
| `PROMPT_VERSION_NOT_FOUND` | AI narrative / prompts |
| `REPORT_NOT_FOUND` | reports |
| `USER_NOT_FOUND` | identity |

### 409 Conflict

| Code | Raised by |
| --- | --- |
| `COLLECTION_AREA_IN_USE` | object catalog |
| `COLLECTION_AREA_NAME_ALREADY_EXISTS` | object catalog |
| `COLLECTION_NAME_ALREADY_EXISTS` | object catalog |
| `EMAIL_ALREADY_EXISTS` | identity |
| `FULL_AGENTIC_ALREADY_RUNNING` | scientific return |
| `FULL_AGENTIC_DISABLED` | scientific return |
| `INSTITUTION_IN_USE` | identity |
| `INSTITUTION_NAME_ALREADY_EXISTS` | identity |
| `INVALID_MUSEUM_QUESTION_TRANSITION` | museum questions |
| `INVALID_TRANSITION` | use of collections |
| `INVALID_USE_TYPE` | CIDOC-CRM mapping, reports |
| `LAST_ACTIVE_SYS_ADMIN` | identity |
| `MISSING_REQUESTER_CONTACT` | use of collections |
| `PERMISSION_ALREADY_EXISTS` | identity |
| `PROJECT_OBJECT_HAS_DEPENDENCIES` | use of collections |
| `PROPOSAL_NOT_PENDING` | public submission |
| `PUBLICATION_ENTRY_IN_USE` | use of collections |
| `SCIENTIFIC_RETURN_INVESTIGATION_RUNNING` | scientific return |
| `VISIT_NOT_EVIDENCED` | CIDOC-CRM mapping, reports |

### 413 Content Too Large

| Code | Raised by |
| --- | --- |
| `FILE_TOO_LARGE` | cross-cutting, museum questions, public submission |

### 415 Unsupported Media Type

| Code | Raised by |
| --- | --- |
| `INVALID_FILE_FORMAT` | cross-cutting, use of collections |
| `UNSUPPORTED_FILE_TYPE` | cross-cutting |

### 422 Unprocessable Content

| Code | Raised by |
| --- | --- |
| `DOCUMENT_ENTRY_LIMIT_EXCEEDED` | use of collections |
| `INVALID_COLLECTION_AREA_NAME` | object catalog |
| `INVALID_COLLECTION_NAME` | object catalog |
| `INVALID_DATE_RANGE` | use of collections |
| `INVALID_PERMISSION_TARGET` | museum questions, use of collections |
| `INVALID_SPREADSHEET` | object catalog |
| `NO_CORRECTION_ITEMS` | use of collections |
| `PERMISSION_NOT_CURATORIAL` | object catalog |
| `PROMPT_VERSION_NARRATIVE_TYPE_MISMATCH` | AI narrative / prompts |
| `SEMANTIC_VALIDATION_FAILED` | AI narrative / prompts, CIDOC-CRM mapping, reports |
| `UNSATISFIED_CORRECTION` | public submission |
| `VALIDATION_ERROR` | public submission, use of collections |

### 500 Internal Server Error

| Code | Raised by |
| --- | --- |
| `FIELD_UNREADABLE` | cross-cutting |
| `FILE_UNREADABLE` | cross-cutting |

### 502 Bad Gateway

| Code | Raised by |
| --- | --- |
| `EMAIL_DELIVERY_FAILED` | identity |

### 503 Service Unavailable

| Code | Raised by |
| --- | --- |
| `FULL_AGENTIC_CIRCUIT_OPEN` | scientific return |
| `FULL_AGENTIC_SOURCE_CONFIGURATION_INVALID` | scientific return |
| `MODEL_UNAVAILABLE` | AI narrative / prompts, reports |
| `NARRATIVE_PROMPT_UNAVAILABLE` | AI narrative / prompts, reports |
| `SCIENTIFIC_RETURN_AGENT_DISABLED` | scientific return |

### 504 Gateway Timeout

| Code | Raised by |
| --- | --- |
| `MODEL_TIMEOUT` | AI narrative / prompts, reports |

---

## Where the rest lives

| You need | Go to |
| --- | --- |
| Request and response schemas, status codes, field types | OpenAPI at `/openapi.json`, or `/docs` |
| Authorization rules, state transitions, invariants, side effects | [`docs/specs/`](../specs/README.md) |
| Per-context endpoint documentation | The numbered contracts in this directory |
| Boundaries and the error envelope as a verified rule | [SPEC-023](../specs/023-fronteiras-e-envelope-de-erro/spec.md) |
| Identity, permissions and the `401`/`403` rule | [SPEC-007](../specs/007-identidade-e-acesso/spec.md) |
