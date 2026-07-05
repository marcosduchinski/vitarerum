# Museum Questions — Public API Contract

## Purpose and scope

`Pergunte ao Museu` ("Ask the Museum") is a lightweight, unauthenticated channel for simple
citizen questions — a deliberate sibling to the formal `submit-proposal` flow
(`11PublicProposalSubmission-API.md`), not a replacement for it.

| | Ask the Museum | Submit a proposal |
|---|---|---|
| Purpose | Simple questions, especially about in-situ visits for research | Formal access request: dates, supporting documents, staff review |
| Persistence | Single `MuseumQuestion` row, `SUBMITTED` | Double opt-in → materialised `Proposal` |
| Follow-up | One reply e-mail from staff; no thread, no public status check | Full proposal lifecycle with staff conversation |

**Current scope**: only questions related to the use of collections, especially in-situ
visits for research, receive a manual reply. Anything else is later marked out of scope by
staff (see `14MuseumQuestions-Internal-API.md`) and closed with an
automatic e-mail — it is **not** rejected at submission time. The public form displays this
alert:

> Neste momento, o Pergunte ao Museu está disponível apenas para perguntas relacionadas ao
> uso de coleções, especialmente visitas in situ para investigação. Perguntas sobre
> exposições, empréstimos, eventos, atividades educativas ou outros serviços do museu serão
> encerradas com uma resposta automática por e-mail.

## Trust model (read first)

Every field is **untrusted input from the open internet**. Client-side validation, the
Turnstile token, and the honeypot are deterrents only — the real protection is server-side:

| # | Protection | Where |
|---|------------|-------|
| 1 | **Verify the Turnstile token** via Cloudflare `siteverify` (own adapter, duplicated from `public_submission` — see the plan's "Decisões de arquitetura") | `POST /public/museum-questions` |
| 2 | **Rate-limit** per IP, per e-mail, and globally → `429` + `Retry-After` (same policy/limits as `public_submission`, own in-process implementation) | same |
| 3 | **Validate & sanitise**: length caps, strip control chars, reject CR/LF in name/subject, escape on render in the staff UI (stored-XSS defence) | same |
| 4 | **Honeypot** `website`: if non-empty, `202` with **no work** (accept-and-drop) | same |
| 5 | **No cookies/credentials; CORS locked to the public origin.** No file uploads for this flow. | same |

Unlike `submit-proposal`, there is **no double opt-in** — a valid submission is persisted as
`SUBMITTED` in a single call; there is no confirmation e-mail/link to click.

## Base URL

| Environment | URL |
|---|---|
| Local dev | `http://127.0.0.1:8000/api/v1` |
| Production | `https://api.vitarerum.example/api/v1` (behind WAF / Cloudflare) |

Authentication: **none.**

---

## `POST /public/museum-questions` — submit a question

Validates the payload, verifies the Turnstile token, applies rate limits, and — on success —
persists the question as `SUBMITTED`. There is no staff-visible identifier returned; the
citizen only ever sees the masked confirmation screen.

### Request body

Content type: `application/json`.

| Field | Type | Required | Constraints |
|---|---|---|---|
| `requesterName` | string | ✅ | 1–120 chars |
| `requesterEmail` | string (email) | ✅ | ≤180 chars; staff replies here |
| `subject` | string | ✅ | 1–200 chars |
| `message` | string | ✅ | 1–4000 chars |
| `consent` | boolean | ✅ | **must be `true`** (RGPD) |
| `captchaToken` | string | ✅ | Turnstile response token; server verifies via `siteverify` |
| `website` | string | — | **honeypot** — should be empty (≤255 chars accepted); non-empty ⇒ silent accept-and-drop (`202`, no work) |

```http
POST /api/v1/public/museum-questions
Content-Type: application/json

{
  "requesterName": "Ana Souza",
  "requesterEmail": "ana@example.test",
  "subject": "Dúvida sobre visita in situ",
  "message": "Gostaria de agendar uma visita para pesquisa.",
  "consent": true,
  "captchaToken": "0.AbC...turnstile-response-token",
  "website": ""
}
```

### Responses

| Status | Meaning | Body |
|---|---|---|
| `202` | Accepted; question persisted as `SUBMITTED` (or honeypot drop) | `MuseumQuestionReceipt` |
| `422` | Validation failed (missing/invalid fields, consent not given) | `ServerError` |
| `403` | Turnstile verification failed (missing/invalid/expired) | `ServerError` |
| `429` | Rate limit exceeded (`Retry-After` header) | `ServerError` |
| `503` | Captcha provider unreachable | `ServerError` |

```json
// 202 — MuseumQuestionReceipt
{ "status": "RECEIVED", "email": "ana@example.test" }
```

---

## Shared schemas

### `ServerError`

The error body the frontend's `toApiError()` (`src/app/core/http/api-error.model.ts`)
consumes. Request-validation failures (`422`) carry a field-error array under `errors`.

```json
{
  "message": "Validation failed",
  "errors": [
    { "field": "requesterEmail", "message": "A valid e-mail address is required." }
  ]
}
```

---

## Frontend integration notes

- Mounted at `/ask-museum` (form) and `/ask-museum/received` (confirmation), reached from
  the new public landing page at `/public` (two choices: Ask the Museum vs Request an
  in-situ visit). `/submit-proposal` keeps working directly for existing bookmarks — the
  landing page is additive, not a redirect.
- The SPA posts this unauthenticated; `auth.interceptor.ts` adds no headers when there is no
  session.
- Public Turnstile **site key** ships in the SPA via `turnstile-site-key`
  (`src/config/environment.json`) — the same key already used by `submit-proposal`. The
  **secret key** lives only on the server (`turnstile_secret_key` setting, also shared).
- Dev uses Cloudflare's always-passing test keys, same as `submit-proposal`.
- Message/subject/answer content is untrusted citizen input: render as plain text
  everywhere, never `[innerHTML]`/`bypassSecurityTrustHtml` (same discipline as the
  `ts_headline` highlight in Objects → Search).

---

## Internal follow-up

The internal staff response section (list, answer, mark out of scope, close) is a separate
workflow — see `docs/plans/museum-questions-response-section-plan.md` and
`14MuseumQuestions-Internal-API.md`. The `museum_questions` table has the columns that
section uses (`answered_*`, `out_of_scope_*`, `closed_at`/`closed_by`).
