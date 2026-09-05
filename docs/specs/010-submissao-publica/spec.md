# SPEC-010 — Public proposal submission and amendment channel

| Field | Value |
| --- | --- |
| Identifier | SPEC-010 |
| Status | Implemented (with declared retention, distributed-rate-limit, and server-validation gaps) |
| Bounded context | `app/public_submission` |
| Written from | `app/public_submission/`, the public Angular feature, `test/public_submission/`, and the document-correction flow in Use of Collections |
| Related specs | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-007](../007-identidade-e-acesso/spec.md), [SPEC-019](../019-numeros-de-referencia/spec.md), [SPEC-022](../022-cifragem-e-armazenamento/spec.md) |
| Architecture decision | [ADR-0001](../../architecture/adr/0001-submission-channel.md) |

## 1. Problem

A citizen without an institutional account must be able to request access to
the museum's collections. An unauthenticated endpoint that writes directly to
the staff queue would expose the institution to spam, impersonation, hostile
uploads, and unnecessary processing costs.

After submission, staff may also need a safe way to request a missing or
replacement document without creating an account for the citizen or exposing
the complete proposal.

## 2. Goal

Accept proposal submissions from the open internet and materialise them in the
staff queue only after the owner of the supplied e-mail address confirms the
request. If staff asks for document corrections while the proposal is pending,
provide a narrow, expiring, single-use amendment channel scoped to those
corrections.

This spec describes the implemented behavior. Properties that the current
system does not guarantee are listed in Section 8.

## 3. Ubiquitous language and trust model

- **Pending public submission**: unverified form data and supporting files held
  before e-mail confirmation. It is not yet a Use of Collections proposal.
- **Confirmation token**: opaque random value sent to the citizen. It allows at
  most one proposal to be materialised, while repeated successful clicks remain
  idempotent.
- **Double opt-in**: submission followed by proof of control over the supplied
  e-mail address.
- **Amendment token**: opaque bearer capability restricted to specified open
  document-correction items on one pending proposal.
- **Honeypot**: hidden `website` field whose non-empty value triggers a silent
  accept-and-drop response.

Every public field and upload is untrusted. Angular validation, Turnstile, and
the honeypot improve usability or deter abuse; authorization, validation, file
inspection, and resource limits remain server responsibilities.

---

## 4. Public submission requirements

### FR-001 — Unauthenticated public experience

The Angular route `/submit-proposal` is lazy-loaded without an authentication
guard. It provides the form, the receipt page, the confirmation page, and the
amendment page under the same public shell. Public copy is available from the
Portuguese and English catalogues.

The client does not attach a bearer token or cookies to the public proposal
API. The API routes themselves do not require an authenticated actor.

### FR-002 — Submission contract

`POST /api/v1/public/proposals` accepts `multipart/form-data`:

| Field | Required | Constraint |
| --- | --- | --- |
| `citizenName` | yes | 1–120 characters |
| `citizenEmail` | yes | valid e-mail, at most 180 characters |
| `subject` | yes | 1–160 characters |
| `body` | yes | 1–4000 characters |
| `useType` | yes | `EXHIBITION`, `IN_SITU_VISIT`, or `OTHER` |
| `proposedBeginDate` | yes | ISO 8601 date |
| `proposedEndDate` | yes | ISO 8601 date |
| `consent` | yes | must be `true` |
| `captchaToken` | yes | 1–2048 characters and verified by the server outside local/test |
| `website` | no | honeypot, at most 255 characters |
| `documents` | yes | 1–5 PDF, JPEG, PNG, or DOCX files; at most 10 MiB each |

Names, subjects, and bodies are trimmed and stripped of control characters.
CR/LF is replaced in names and subjects before those values can enter an
e-mail header. The citizen e-mail is validated by the server.

The successful response is `202`:

```json
{
  "status": "PENDING_CONFIRMATION",
  "email": "citizen@example.org"
}
```

The response echoes the validated e-mail address. No proposal is visible to
staff at this stage.

### FR-003 — Client-side guidance

The Angular form checks required fields, e-mail shape, consent, the date order,
the document count, and the per-file size before submission. It also displays
the required document templates for the selected use type.

The API accepts all three `useType` values. The current UI warns that only
`IN_SITU_VISIT` is operational and that `EXHIBITION` and `OTHER` will be
implemented later; it does not disable their submission.

If no Turnstile site key is configured, the Angular widget is hidden. Local and
test backend environments use an always-pass verifier; non-local startup rejects
the bundled Turnstile test secret.

### FR-004 — Silent honeypot

A non-empty `website` value returns the same `202 PENDING_CONFIRMATION` receipt
as a human submission but performs no rate-limit check, captcha call, upload
read, persistence, or e-mail send. The schema accepts a bounded value instead
of returning `422`, which would reveal the trap to a bot.

### FR-005 — Admission before upload buffering

For a normal submission, the server applies these gates before reading uploaded
files:

1. a process-local sliding-window limit of 50 requests per IP per hour;
2. 50 requests per normalized e-mail address per day;
3. 500 requests globally per hour;
4. server-side Turnstile verification.

Exceeded limits return `429` with `Retry-After: 60`. Invalid captcha returns
`403`; an unavailable captcha provider returns `503`.

### FR-006 — Upload validation and storage

The server reads each upload with a hard 10 MiB cap and requires 1–5 files. It
recognizes PDF, JPEG, PNG, and DOCX by content signature or DOCX container
structure rather than trusting only the filename or media type.

Too many or missing files return `422`, an oversized file returns `413`, and an
unsupported file returns `415`. Safe filenames are bounded before a storage
reference is generated. Files are stored below `DATA_DIR`, outside the web
root, through the shared storage adapter described by
[SPEC-022](../022-cifragem-e-armazenamento/spec.md).

### FR-007 — Pending record and confirmation e-mail

After validation, the server stores the files and a pending aggregate containing
the citizen details, intended use, dates, consent, and file references. It
generates the confirmation token with `secrets.token_urlsafe(32)`.

The pending transaction is committed before the confirmation e-mail is sent.
If persistence fails after files were written, those files are reclaimed. In
local/development without SMTP, the confirmation link is logged instead of
sent. The link opens `/submit-proposal/confirm?token=...`.

The confirmation token is an opaque random bearer value; it is **not signed**
and is stored in raw form in the pending-submission row. Section 8 records the
resulting security and retention limitations.

### FR-008 — Confirmation outcomes

`POST /api/v1/public/proposals/confirm` accepts the token in a JSON body. It has
a process-local limit of 50 requests per IP per hour. Expected outcomes return
`200` so that the public page can display a stable message:

| `status` | Meaning |
| --- | --- |
| `CONFIRMED` | The proposal was created; `referenceNumber` is present |
| `ALREADY_CONFIRMED` | The same pending row already materialised a proposal; its reference is returned |
| `EXPIRED` | The pending row was found after its configured lifetime and was deleted |
| `INVALID` | No pending row matches the token |

Only rate limiting and unexpected failures use non-2xx responses. The default
confirmation lifetime is 24 hours and is configured by
`public_confirm_token_ttl_hours`.

### FR-009 — Idempotent and concurrent confirmation

Confirmation loads the pending row with a database row lock. The first valid
request materialises the proposal and changes the pending status to
`CONFIRMED`; a repeated or concurrent request returns `ALREADY_CONFIRMED`
without creating a second proposal. A confirmed pending row does not expire.

Reference-number allocation runs inside the shared uniqueness-retry boundary,
so a concurrent uniqueness collision can be retried.

### FR-010 — Proposal materialisation

Confirmation creates a Use of Collections proposal with:

- `submissionChannel = PUBLIC` as the explicit origin required by ADR-0001;
- no authenticated `requestedBy` value;
- the citizen's name and e-mail as `requesterContact`;
- the selected `useType` and proposed dates;
- the form subject and body as the initial conversation message;
- every uploaded file as a `PUBLIC_SUBMISSION` document with no submitting
  permission.

The pending row retains the generated reference so later clicks can return the
same result.

### FR-011 — Staff notification after confirmation

On the first successful confirmation, in-app notifications are created in the
same transaction for the distinct staff permissions returned from the
Curatorial, Collections Management, Direction, and System Administration
groups. If one user holds several permissions, those are still distinct in-app
recipients.

After commit, proposal-submitted e-mail is sent once per distinct staff user.
An idempotent `ALREADY_CONFIRMED` response sends neither notification nor
e-mail again.

### FR-012 — Reactive expiry cleanup

When a citizen attempts to confirm an expired pending submission, the server
deletes its uploaded files and pending row, then returns `EXPIRED`. A second
attempt returns `INVALID`.

This cleanup is reactive: the live system only discovers an expired submission
when its link is used. It does not currently purge never-clicked submissions in
the background.

---

## 5. Amendment-channel requirements

### FR-013 — Scoped invitation

When staff requests document corrections under
[SPEC-008](../008-proposta-uso-de-colecoes/spec.md), the integration adapter
generates an opaque random token and stores only its SHA-256 hash. The durable
token records one proposal, the encrypted requester e-mail, the authorized
correction-item IDs, creation and expiry times, and eventual use time.

The token transaction is committed before the invitation e-mail is sent. The
link opens `/submit-proposal/edit?token=...`. Amendment tokens currently reuse
`public_confirm_token_ttl_hours`, whose default is 24 hours.

### FR-014 — Amendment API

All amendment routes are unauthenticated bearer-token endpoints under
`/api/v1`:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/public/proposals/amendments/{token}` | Return the proposal reference, status, expiry, open scoped correction items, and scoped current documents |
| `POST /api/v1/public/proposals/amendments/{token}/documents` | Upload a replacement or missing document |
| `DELETE /api/v1/public/proposals/amendments/{token}/documents/{documentId}` | Remove a scoped document and reclaim its stored file |
| `POST /api/v1/public/proposals/amendments/{token}/submit` | Resolve the scoped corrections, notify assigned staff, and mark the token used |

The upload, delete, and submit routes have the same process-local 50-per-IP per
hour limit. The read-only `GET` route does not currently apply this limit.

### FR-015 — Narrow read model and opaque failures

The amendment view exposes only correction items named by the token that are
still `REQUESTED`, plus documents referenced by those items. It does not expose
the complete proposal.

Unknown, expired, and used tokens all return `404 AMENDMENT_UNAVAILABLE`. A
missing proposal uses the same opaque response. A proposal that is no longer
`PENDING` returns `409 PROPOSAL_NOT_PENDING`.

### FR-016 — Scoped document changes

An amendment upload must use a document type present in the token's still-open
correction scope. The server trims the free-text `documentType`; the normalized
value must be non-empty and at most 128 characters. It returns the normalized
value in the document response. A type outside the scope returns
`403 OUT_OF_SCOPE`; an invalid type returns `422 VALIDATION_ERROR`.

The upload uses the same 10 MiB and supported-content rules as initial intake.
Uploading a valid replacement atomically detaches the flagged old document and
reclaims its file. Deletion is restricted to document IDs in the active scope;
deleting an already-detached scoped document is treated as idempotent `204`.

### FR-017 — Amendment completion

Final submission succeeds only if every still-open correction item named by the
token is satisfied by an appropriate current document. Otherwise it returns
`422 UNSATISFIED_CORRECTION` and leaves the corrections open.

On success, the correction items become `RESOLVED`, the proposal remains
`PENDING`, and the token receives `usedAt`. If the proposal is assigned, an
in-app notification is persisted for that permission in the same transaction.
After commit, an e-mail is sent to the assigned staff user. Reusing the link
then returns the opaque amendment `404`.

---

## 6. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | A pending public submission is not a staff-visible proposal |
| INV-002 | A public proposal is materialised only after a valid confirmation |
| INV-003 | A pending public submission contains between one and five documents |
| INV-004 | One confirmation token materialises at most one proposal |
| INV-005 | A confirmed pending row never expires and preserves its proposal reference |
| INV-006 | A non-empty honeypot produces no persistence, upload read, captcha call, or e-mail |
| INV-007 | A public proposal has `submissionChannel = PUBLIC`, a requester contact, and no authenticated requester at creation |
| INV-008 | Only the SHA-256 hash of an amendment token is stored |
| INV-009 | An amendment token authorizes only its still-open correction items while the proposal remains `PENDING` |
| INV-010 | An amendment cannot be completed until each scoped correction has a satisfying document |
| INV-011 | Public submission and amendment endpoints require no authenticated credentials |

## 7. Failure responses

| Situation | Response |
| --- | --- |
| Invalid form, consent, date syntax, file count, or amendment document type | `422` |
| Invalid Turnstile token | `403` |
| Amendment operation outside the token scope | `403 OUT_OF_SCOPE` |
| Unknown, expired, or used amendment token | `404 AMENDMENT_UNAVAILABLE` |
| Proposal no longer pending during amendment | `409 PROPOSAL_NOT_PENDING` |
| File above 10 MiB | `413` |
| Unsupported file content | `415` |
| Process-local request limit exceeded | `429` with `Retry-After` |
| Turnstile provider unavailable | `503` |

Handled failures use the shared error-envelope rules in
[SPEC-023](../023-fronteiras-e-envelope-de-erro/spec.md).

## 8. Declared implementation gaps

These are properties of the current repository, not hypothetical future work:

1. There is no scheduled purge for pending submissions whose confirmation link
   is never clicked. Their encrypted personal fields, raw confirmation token,
   database rows, and files can remain indefinitely.
2. Confirmation tokens are opaque random values but are stored raw, not hashed
   or signed. Amendment tokens use the stronger hash-at-rest design.
3. The sliding-window limiter is in memory and process-local. Limits are not
   coordinated across replicas and are reset when a process restarts.
4. The amendment `GET` route has no application rate limit, although the three
   mutating amendment routes do.
5. The Angular form rejects an end date earlier than the start date, but the
   public API and proposal constructor do not enforce that ordering. A direct
   API caller can therefore persist an inverted interval.
6. E-mails are sent after commit without a durable outbox or retry queue. If an
   SMTP call fails, durable state can exist without the intended confirmation,
   amendment, or staff e-mail being delivered.
7. CORS is configured globally from `cors_origins` with credentials enabled.
   Non-local startup forbids the wildcard, but it does not require the list to
   equal `public_origin`. The current public Angular client sends no credentials;
   CORS itself is not a route-level security boundary.
8. Backend route coverage exercises intake, confirmation, notification, and
   amendment completion, while the amendment read/upload/delete error matrix is
   covered mainly through domain and application tests rather than complete HTTP
   tests. There is no end-to-end browser scenario for the full double-opt-in or
   amendment journey.

## 9. Acceptance criteria

### AC-001 — Valid intake creates only a pending submission

Given a valid form and supporting file, when the citizen submits it, the API
returns `202 PENDING_CONFIRMATION`, stores the proposed dates and files, and
sends the confirmation link only after commit.

→ `test/public_submission/test_api.py::test_submit_returns_202_receipt`,
`::test_submit_persists_proposed_dates`, `::test_submit_does_not_email_when_commit_fails`

### AC-002 — Honeypot performs no work

Given a non-empty `website`, the API returns the normal receipt without
validating documents, persisting data, or sending e-mail.

→ `test/public_submission/test_api.py::test_submit_honeypot_returns_202_no_work`,
`::test_submit_honeypot_skips_document_validation`

→ `test/public_submission/test_use_cases.py::test_honeypot_accepts_and_drops`

### AC-003 — Abuse gates run before file reads

Given a rate-limited request or failed captcha without documents, the API
returns the admission error rather than a document-validation error.

→ `test/public_submission/test_api.py::test_submit_rate_limited_before_reading_uploads`,
`::test_submit_captcha_checked_before_reading_uploads`,
`::test_submit_rate_limited_429_with_retry_after`, `::test_submit_captcha_failure_403`

### AC-004 — Form and file constraints are enforced

Given missing consent, invalid use type, missing/too many documents, an
oversized file, or unsupported content, the API rejects the request with the
documented status.

→ `test/public_submission/test_api.py::test_submit_missing_consent_is_rejected`,
`::test_submit_invalid_use_type_is_rejected`, `::test_submit_missing_documents_is_rejected`,
`::test_submit_too_many_documents_is_rejected`, `::test_submit_oversized_document_is_rejected`,
`::test_submit_unsupported_document_is_rejected`

### AC-005 — Double opt-in is idempotent

Given a stored pending submission, the first valid confirmation creates one
public proposal and returns its reference; a second confirmation returns
`ALREADY_CONFIRMED`. An unknown token returns `200 INVALID`.

→ `test/public_submission/test_api.py::test_submit_then_confirm_flow`,
`::test_confirm_unknown_token_returns_200_invalid`

→ `test/public_submission/test_use_cases.py::test_confirm_materialises_proposal`,
`::test_confirm_twice_is_already_confirmed`, `::test_confirm_uses_locking_read`,
`::test_confirm_retries_reference_number_conflict`

### AC-006 — Expired confirmation cleanup is reactive

Given an expired pending submission whose link is clicked, its files and row are
deleted and the result is `EXPIRED`. Confirmed submissions never expire.

→ `test/public_submission/test_use_cases.py::test_confirm_expired_token_reclaims_files_and_row`

→ `test/public_submission/test_domain.py::test_is_expired_true_after_ttl`,
`::test_confirmed_submission_never_expires`

### AC-007 — Staff effects are not repeated

Given multiple staff permissions belonging to one user, the first confirmation
dispatches one batch of in-app notifications and one e-mail to that user. A
repeated confirmation dispatches neither again.

→ `test/public_submission/test_api.py::test_confirm_public_proposal_notifies_staff_once`

### AC-008 — Amendment tokens expire and are single-use

Given a fresh amendment token, it is active until its expiry or final use; once
used it cannot be marked used again.

→ `test/public_submission/test_domain.py::test_amendment_token_is_active_when_fresh`,
`::test_amendment_token_expires_after_ttl`,
`::test_amendment_token_mark_used_is_single_use`

### AC-009 — Amendment scope and document normalization hold

Given a scoped correction, an out-of-scope type is rejected before storage;
free-text types are trimmed; blank types are rejected; a valid replacement
detaches the flagged file.

→ `test/use_of_collections/test_correction_flow.py::test_amendment_upload_out_of_scope_is_rejected`,
`::test_amendment_upload_free_text_type_trims_and_matches_scope`,
`::test_amendment_upload_blank_type_rejected`,
`::test_amendment_upload_replaces_flagged_document`

### AC-010 — Unsatisfied amendments cannot complete

Given an open correction with no satisfying document, final submission fails.
After a valid upload, submission resolves the scoped correction while leaving
the proposal pending.

→ `test/use_of_collections/test_correction_flow.py::test_amendment_submit_without_document_is_rejected`,
`::test_amendment_add_then_submit_resolves`

### AC-011 — Amendment completion notifies assigned staff

Given an assigned pending proposal with satisfied corrections, final submission
marks the token used and sends the in-app and e-mail notifications to the
assignee.

→ `test/public_submission/test_api.py::test_submit_amendment_notifies_assigned_staff`

### AC-012 — Public Angular validation and localization

The public form uses translated catalogues, sends all required values, blocks
missing consent/dates/documents and invalid date order, and shows document
templates for the selected use type. The amendment page preserves the requested
free-text document type when calling the API.

→ frontend: `public-submit-proposal-page.component.spec.ts`,
`public-submission-edit-page.component.spec.ts`, and `i18n/catalogs/catalogs.spec.ts`

## 10. Non-functional requirements

- **Privacy**: explicit consent is required. Sensitive pending-submission and
  amendment-contact fields use shared field encryption outside local/test.
- **Storage**: uploaded files remain outside any web root. Production requires
  the shared file-encryption key. Antivirus scanning is a deployment concern
  and is not implemented in this context.
- **Browser boundary**: production must configure explicit CORS origins. Public
  requests remain unauthenticated regardless of browser origin.
- **Edge protection**: a WAF or bot-management layer may complement, but does
  not replace, server-side validation and admission controls.
- **Rendering**: all stored public strings remain untrusted and must be escaped
  when shown in the staff interface.

## 11. Traceability

| Element | Location |
| --- | --- |
| Pending aggregate and amendment-token domain model | `vitarerum-api/app/public_submission/domain/` |
| Intake and confirmation use cases | `vitarerum-api/app/public_submission/application/` |
| Captcha, process-local limiter, e-mail, token, and repositories | `vitarerum-api/app/public_submission/infrastructure/` |
| Public submission, confirmation, and amendment endpoints | `vitarerum-api/app/public_submission/presentation/` |
| Amendment correction rules | `vitarerum-api/app/use_of_collections/application/use_cases/proposal.py`, `domain/models.py` |
| Staff correction invitation port and composition | `vitarerum-api/app/use_of_collections/application/ports.py`, `app/public_submission/infrastructure/amendment.py`, `app/main.py` |
| Public Angular routes and pages | `vitarerum-ui/src/app/features/public/public.routes.ts`, `submit-proposal/` |
| Public API client and models | `vitarerum-ui/src/app/features/public/services/public-proposal-api.service.ts`, `models/public-proposal.model.ts` |
| Submission-channel decision | `docs/architecture/adr/0001-submission-channel.md` |

## 12. Open questions

1. What retention period and scheduled purge policy should apply to unconfirmed
   submissions and expired amendment records?
2. Should confirmation tokens migrate to hash-at-rest storage while preserving
   idempotent `ALREADY_CONFIRMED` behavior?
3. Which shared limiter should enforce consistent limits across replicas?
4. Should confirmation-link resend and durable e-mail retry be introduced, and
   how should they avoid becoming bulk-mail vectors?
5. Should amendment reads have a separate, less restrictive rate limit?
6. Should the API enforce the proposed-date order already enforced by Angular?
