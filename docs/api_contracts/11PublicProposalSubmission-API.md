# Public Proposal Submission — API Contract

Human-readable companion to the machine spec
[`public-proposals.openapi.yaml`](./public-proposals.openapi.yaml) (OpenAPI 3.1) and the
runnable reference [`public-proposals-reference-impl.py`](./public-proposals-reference-impl.py)
(FastAPI). If the three ever disagree, **the YAML is the source of truth.**

These endpoints let **any citizen** open a collection-use proposal without an account.
They back the public frontend at `/submit-proposal`
(`src/app/features/public/`).

---

## Trust model (read first)

Every field is **untrusted input from the open internet**. The frontend's client-side
validation, the Cloudflare Turnstile token, and the honeypot are **deterrents only** — the
real protection MUST be enforced server-side:

| # | Protection | Where |
|---|------------|-------|
| 1 | **Verify the Turnstile token** via Cloudflare `siteverify` (secret key stays on the server) | `POST /public/proposals` |
| 2 | **Rate-limit** per IP, per e-mail, and globally → `429` + `Retry-After` | both endpoints |
| 3 | **Validate & sanitise**: length caps, strip control chars, reject CR/LF in e-mail-bound fields, escape on render in the staff UI (stored-XSS defence) | both |
| 4 | **Double opt-in**: create a *pending, unverified* record + e-mail a single-use signed TTL token; materialise the proposal only on confirm; discard unconfirmed after TTL | both |
| 5 | **Honeypot** `website`: if non-empty, `202` with **no work** (accept-and-drop) | `POST /public/proposals` |
| 6 | **No file uploads; no cookies/credentials**; CORS locked to the public origin; WAF/bot-management at the edge | both |

> Distinct from the authenticated `POST /proposals` (which needs a session + `X-Permission-Id`).
> A public submission has no account, so it captures the citizen's own name + e-mail.

---

## Base URL

| Environment | URL |
|---|---|
| Local dev | `http://127.0.0.1:8000/api/v1` |
| Production | `https://api.vitarerum.example/api/v1` (behind WAF / Cloudflare) |

Authentication: **none.** These endpoints must not accept or rely on auth headers/cookies.

---

## 1. `POST /public/proposals` — open a pending submission (opt-in step 1)

Validates the payload, verifies the Turnstile token, applies rate limits, and — on success —
creates a pending record and e-mails a confirmation link to `citizenEmail`. **No proposal is
visible to staff until the citizen confirms.**

### Request body

| Field | Type | Required | Constraints |
|---|---|---|---|
| `citizenName` | string | ✅ | 1–120 chars |
| `citizenEmail` | string (email) | ✅ | ≤180 chars; confirmation link sent here |
| `subject` | string | ✅ | 1–160 chars |
| `body` | string | ✅ | 1–4000 chars |
| `consent` | boolean | ✅ | **must be `true`** (RGPD) |
| `captchaToken` | string | ✅ | Turnstile response token; server verifies via `siteverify` |
| `website` | string | — | **honeypot** — should be empty (≤255 chars accepted); non-empty ⇒ silent accept-and-drop (`202`, no work). Not schema-rejected, so a bot cannot tell the field is monitored. |

```json
{
  "citizenName": "Pedro Silva",
  "citizenEmail": "pedro@example.test",
  "subject": "Acesso à Coleção de Zoologia",
  "body": "Gostaria de estudar um espécime para a minha tese de mestrado.",
  "consent": true,
  "captchaToken": "0.AbC...turnstile-response-token",
  "website": ""
}
```

### Responses

| Status | Meaning | Body |
|---|---|---|
| `202` | Accepted; confirmation e-mail sent (or honeypot drop) | `PublicSubmissionReceipt` |
| `422` | Validation failed (missing/invalid fields, consent not given) | `ServerError` |
| `403` | Turnstile verification failed (missing/invalid/expired) | `ServerError` |
| `429` | Rate limit exceeded (`Retry-After` header) | `ServerError` |
| `503` | Captcha provider unreachable | `ServerError` |

```json
// 202 — PublicSubmissionReceipt
{ "status": "PENDING_CONFIRMATION", "email": "pedro@example.test" }
```

---

## 2. `POST /public/proposals/confirm` — confirm via e-mailed token (opt-in step 2)

Consumes the single-use token from the confirmation link. On success the pending submission is
materialised into the staff proposal queue. Re-clicking an already-used link returns
`ALREADY_CONFIRMED` (idempotent).

### Request body

| Field | Type | Required | Constraints |
|---|---|---|---|
| `token` | string | ✅ | single-use, signed, expiring token from the e-mailed link |

```json
{ "token": "eyJhbGciOiJIUzI1NiIs...single-use-signed-token" }
```

### Responses

`200` for **all** of the outcomes below — `EXPIRED`/`INVALID` are deliberately *not* HTTP errors,
so the public page can render a friendly message. Reserve non-2xx for unexpected server faults
(and `429` for rate limiting).

| `status` | Meaning |
|---|---|
| `CONFIRMED` | Proposal created and forwarded to staff (`referenceNumber` present) |
| `ALREADY_CONFIRMED` | Link already used; proposal already exists |
| `EXPIRED` | Token past its TTL; citizen must resubmit |
| `INVALID` | Token malformed/unknown |

```json
// 200 — PublicConfirmationResult
{ "status": "CONFIRMED", "referenceNumber": "VRP-20260625-0007" }
```

---

## Shared schemas

### `ServerError`
The error body the frontend's `toApiError()`
(`src/app/core/http/api-error.model.ts`) consumes — it reads `message` and, for validation,
the field-error array. Request-validation failures (`422`) carry the array under `errors`
(the API's global validation handler); `toApiError()` reads both `errors` and `fieldErrors`.

```json
{
  "message": "Validation failed",
  "errors": [
    { "field": "citizenEmail", "message": "A valid e-mail address is required." }
  ]
}
```

---

## Implementation notes (deployed behaviour)

The deployed API differs from the literal OpenAPI schema in two deliberate spots; the
behaviour below is authoritative for these two points:

- **Validation status is `422`, not `400`.** Invalid bodies are rejected by request
  validation, which the API normalises app-wide to `422` with `{ "message", "errors": [{ "field", "message" }] }`.
- **The honeypot is not capped at length 0.** The OpenAPI lists `website maxLength: 0`,
  but enforcing that would `422` a filled honeypot — revealing to a bot that the field is
  watched. To keep the silent accept-and-drop, the field accepts a bounded value (≤255) and
  the server drops it (`202`, no work).

---

## Frontend integration notes

- The SPA posts these unauthenticated; `auth.interceptor.ts` adds no headers when there is no
  session. Ensure the endpoints reject any stray credentials.
- The confirmation link must point at the SPA route
  `/submit-proposal/confirm?token=…`; that page POSTs the token to endpoint #2.
- Public Turnstile **site key** ships in the SPA via `turnstile-site-key`
  (`src/config/environment.json`). The **secret key** lives only on the server.
- Dev uses Cloudflare's always-passing test keys
  (site `1x00000000000000000000AA`, secret `1x0000000000000000000000000000000AA`).
