# SPEC-020 — External Resource Publication

| Field | Value |
| --- | --- |
| Identifier | SPEC-020 |
| Status | Implemented (with declared integration-client, audit, immutable-disclosure, privacy, and security-control gaps) |
| Bounded context | `app/external_publications` |
| Derived from | Backend, frontend, migrations, Published Languages, diagrams, user documentation, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-013](../013-mapeamento-cidoc-crm/spec.md), [SPEC-015](../015-relatorio-visita-in-situ/spec.md), [SPEC-017](../017-narrativa-museologica/spec.md), [SPEC-023](../023-fronteiras-e-envelope-de-erro/spec.md) |

## 1. Problem

Selected museum information must sometimes be shared outside the authenticated
application: for example, an approved proposal with a partner, a collection-use
project with another institution, or an in-situ visit report with a semantic
data consumer.

Manual exports lose operational control. The institution cannot reliably know
which grant exposed a resource, when it expires, whether it was used, or how to
withdraw it. A public link also creates a security boundary: the secret in the
URL acts as a bearer credential and the chosen profile determines the disclosed
data.

## 2. Goal and scope

This context owns explicit, revocable external-publication grants, opaque token
generation and resolution, content-profile projection, access-attempt records,
and the system-administration registry.

The current end-to-end product supports bearer-token links only. It does not
produce a frozen export: every successful request reads the current resource
through the owning context's Published Language. It also does not provide token
rotation, recipient identity, download packaging, public catalogue discovery,
or an Angular view of access history.

## 3. Strategic context

External Publications is a supporting context and does not own proposals,
projects, reports, narratives, or CIDOC records.

| Relationship | Responsibility |
| --- | --- |
| External Publications → Use of Collections | Read approved proposals and in-progress or completed projects through its Published Language. |
| External Publications → Reports | Read in-situ reports, narrative snapshots, and CIDOC metadata through its Published Language. |
| Reports → CIDOC CRM | Build JSON-LD when no stored narrative snapshot document is available. |
| Reports → External Publications | Revoke grants before deleting an in-situ report. |
| Angular administration → External Publications | List grants and eligible resources, create token links, and revoke grants. |

These readers are anti-corruption layers: the publication context receives
narrow external views instead of importing neighbouring domain models.

## 4. Ubiquitous language and domain model

### 4.1 External publication

`ExternalPublication` is the revocable grant. It records:

- resource type and identifier;
- status `PUBLISHED` or `REVOKED`;
- access mode `TOKEN` or `INTEGRATION_CLIENT`;
- profile `SUMMARY`, `DETAIL`, or `JSON_LD`;
- token hash or integration-client identifier;
- optional expiration;
- creation and publication actor/time; and
- optional revocation actor/time.

Publishing creates a UUID and enters `PUBLISHED`. Revocation is idempotent: a
second call preserves the first revocation actor and timestamp. There is no
restore, edit, delete, or token-rotation transition.

### 4.2 Resource types and eligibility

| Resource type | Creation-time eligibility | Resolution-time behaviour |
| --- | --- | --- |
| `PROPOSAL` | Exists and is `APPROVED`. | Re-read on every request; a proposal no longer approved appears not found. |
| `PROJECT` | Exists and is `IN_PROGRESS` or `COMPLETED`. | Re-read on every request; a project outside those states appears not found. |
| `IN_SITU_VISIT_REPORT` | Exists and its selected narrative fact snapshot has `cidoc_conforms = true`. | Re-read on every request, but conformance is not rechecked by the resolver. |

For proposals and projects, the owning reader deliberately returns `None` for
both a missing resource and an ineligible state. The application therefore
cannot distinguish those causes despite defining `PublishedResourceNotEligible`.
That distinct exception is currently used only for a report found without
positive CIDOC conformance.

### 4.3 Access modes

| Mode | Domain requirement | Operational status |
| --- | --- | --- |
| `TOKEN` | A token hash must be present. | Implemented in the API and Angular UI. |
| `INTEGRATION_CLIENT` | An integration-client identifier must be present. | Enum and columns exist, but creation input, authentication, resolution route, and UI support do not. API creation with this mode always fails domain validation. |

The token generator uses `secrets.token_urlsafe(32)`, providing 32 random bytes,
and stores only its SHA-256 hash. The raw token is returned in the generated URL
only by the creation response. Subsequent list and revoke responses set `url`
to `null`, so a lost URL cannot be recovered.

### 4.4 Content profiles

| Profile | Public representation |
| --- | --- |
| `SUMMARY` | Resource metadata with selected heavy fields removed. |
| `DETAIL` | Fuller proposal, project, or report representation. For reports, it also permits the separate JSON-LD route. |
| `JSON_LD` | Valid only when creating an in-situ report grant; the base report response remains JSON and the semantic document is served from the separate JSON-LD route. |

`SUMMARY` is a field-selection rule, not a general privacy classification. A
proposal summary still exposes intended use and linked project ID; a project
summary exposes origin/proposal IDs; and a report summary exposes visitor and
place names, dates, project and record IDs, conformance data, mapping versions,
and a JSON-LD URL. The URL is present even when the summary profile makes that
route return `409`.

### 4.5 Access attempt

`ExternalPublicationAccess` records the request time, access mode, outcome,
optional publication and integration-client identifiers, a hash of the remote
address, and the raw `User-Agent` header.

Unknown tokens produce `DENIED` rows without a publication identifier. Known
but expired, revoked, or currently unavailable resources produce `DENIED` rows
linked to the grant. A normal resolved resource produces `GRANTED`.

The remote-address value is an unsalted SHA-256 digest of
`request.client.host`. It is pseudonymous rather than reliably anonymous,
especially for the small IPv4 search space. Its accuracy also depends on the
deployment's trusted-proxy configuration.

## 5. Authorisation and trust boundary

Creating, listing, and revoking grants, listing eligible resources, and reading
a grant's access history require the active group to be `SYS_ADMIN`. The
Angular route also uses `sysAdminGuard`; the backend remains authoritative.

Public resource and JSON-LD routes require no authenticated application
identity. Possession of the token is sufficient, so the complete URL must be
handled as a secret. Revoked, expired, unknown, and currently unavailable
grants all use opaque `404 EXTERNAL_PUBLICATION_NOT_FOUND` semantics.

The API constructs the public URL from the inbound request's scheme and host.
Correct links therefore depend on proxy and forwarded-host configuration; the
application has no canonical public-origin setting in this context.

## 6. Functional requirements

### FR-001 — List publishable resources

`GET /api/v1/external-publications/publishable-resources` requires
`resourceType` and accepts `q`, `page`, and `size` (maximum 100). It delegates to
the owning Published Language and returns lightweight picker entries.

Proposal and report queries are paginated in their repositories. The project
reader independently loads enough in-progress and completed rows, merges and
sorts them in memory by begin date, and slices the requested page.

### FR-002 — Create a token publication

`POST /api/v1/external-publications` verifies the resource, generates and hashes
one token, persists the grant, commits, and returns `201` with its one-time URL.
The Angular wizard always sends `accessMode: TOKEN` and guides the administrator
through resource type, eligible resource, profile/expiration, and review.

The API accepts a missing expiration and normalises naive timestamps to UTC.
Neither the domain nor the UI rejects an expiration at or before creation time;
such a grant is created successfully but is immediately inaccessible.

Multiple active grants for the same resource, profile, and expiration are
allowed. Each has an independent token and lifecycle.

### FR-003 — Enforce profile compatibility

Creating `JSON_LD` for a proposal or project returns `422
INVALID_EXTERNAL_PUBLICATION`. The Angular UI disables that combination and
automatically changes it back to `DETAIL` when the resource type changes.

Both `DETAIL` and `JSON_LD` report grants may retrieve the semantic document.
`SUMMARY` may not.

### FR-004 — List the publication registry

`GET /api/v1/external-publications` returns grants newest first and supports
resource type, exact resource ID, status, profile, free-text query, page, and
size filters. Free text performs a contains match over publication and resource
IDs.

Responses expose lifecycle timestamps but not creation/revocation actor IDs,
integration-client ID, or token hash. They never reconstruct a token URL.

The Angular registry displays filters, current-page counts, pagination, and
revoke actions. Its Copy button is effectively available only for a newly
created grant still held in component state; after a reload, list entries have
no URL.

### FR-005 — Revoke idempotently

`PATCH /api/v1/external-publications/{publicationId}/revoke` changes a live
grant to `REVOKED` and records the active permission and current time. Repeating
the request succeeds without modifying the existing revocation metadata.

The Angular action has no confirmation dialog. Revocation does not erase the
stored token hash or historical access rows.

### FR-006 — Resolve a public token

`GET /api/v1/external/publications/{token}` hashes the supplied token, resolves
the grant, checks status and expiration, and loads the current resource. It
commits an access row on both success and opaque not-found outcomes.

The response is a live projection, not the state captured when the link was
created. Changes to eligible content can therefore change what the same URL
reveals over time. Proposal/project state changes can also make the link
inaccessible without marking the grant `REVOKED`; report conformance changes do
not have the same effect.

### FR-007 — Project response data by profile

For `SUMMARY`, proposal purpose and requested objects are omitted; project
purpose, intended use, and objects are omitted; report narrative is omitted.
For `DETAIL`, those fields are included when available. Object details include
internal IDs, inventory numbers, titles/names, category, snapshot description,
and description.

No explicit `Cache-Control` header is added to the base public-resource
response.

### FR-008 — Serve report JSON-LD

`GET /api/v1/external/publications/{token}/json-ld` resolves the same grant and
then permits only in-situ reports with `DETAIL` or `JSON_LD`. It returns
`application/ld+json` with `Cache-Control: private, max-age=300`.

The report reader prefers JSON-LD stored in the selected narrative's fact
snapshot and otherwise asks the CIDOC context to build the document. If the
grant is valid but its type/profile/document is incompatible, the endpoint
returns `409 JSON_LD_UNAVAILABLE`.

The shared resolver records `GRANTED` before those compatibility and document
checks. Consequently, a request that ultimately receives this `409` is
incorrectly audited as granted.

### FR-009 — Record and list access attempts

`GET /api/v1/external-publications/{publicationId}/accesses` returns the known
grant's access rows newest first, with pagination up to 100 entries per page.
It includes network hash and raw user-agent values.

There is no Angular service or page for this endpoint. Denials for unknown
tokens have no publication ID and are not retrievable through any HTTP list
endpoint, even though they are stored.

### FR-010 — Delete a published report safely

The in-situ report deletion workflow revokes its external publications before
removing the report. It records the deleting permission as revoker and retains
access history. Equivalent automatic revocation is not a generic capability of
this context for all resource types.

## 7. HTTP surface and failures

| Endpoint | Method | Caller |
| --- | --- | --- |
| `/api/v1/external-publications` | `GET`, `POST` | `SYS_ADMIN` |
| `/api/v1/external-publications/publishable-resources` | `GET` | `SYS_ADMIN` |
| `/api/v1/external-publications/{publicationId}/accesses` | `GET` | `SYS_ADMIN` |
| `/api/v1/external-publications/{publicationId}/revoke` | `PATCH` | `SYS_ADMIN` |
| `/api/v1/external/publications/{token}` | `GET` | Token bearer |
| `/api/v1/external/publications/{token}/json-ld` | `GET` | Token bearer |

| Situation | Result |
| --- | --- |
| Administrative caller is not `SYS_ADMIN` | `403` |
| Invalid enum, timestamp, page, or size | `422` validation envelope |
| Missing/ineligible proposal or project at creation | `404 PUBLISHED_RESOURCE_NOT_FOUND` |
| Missing report at creation | `404 PUBLISHED_RESOURCE_NOT_FOUND` |
| Report is not positively CIDOC-conformant at creation | `409 PUBLISHED_RESOURCE_NOT_ELIGIBLE` |
| Invalid profile/mode domain combination | `422 INVALID_EXTERNAL_PUBLICATION` |
| Unknown administrative publication ID | `404 EXTERNAL_PUBLICATION_NOT_FOUND` |
| Unknown, revoked, expired, or currently unavailable public token | `404 EXTERNAL_PUBLICATION_NOT_FOUND` |
| JSON-LD not allowed or unavailable after a valid resolution | `409 JSON_LD_UNAVAILABLE` |

The public `404` response deliberately avoids distinguishing invalid tokens
from grants that once existed.

## 8. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | A token grant contains a token hash; the raw token is never persisted. |
| INV-002 | `JSON_LD` profile is valid only for an in-situ report. |
| INV-003 | Revocation is terminal and idempotent. |
| INV-004 | A grant is inaccessible at or after its expiration instant. |
| INV-005 | Public lookup uses opaque not-found semantics for invalid and inaccessible grants. |
| INV-006 | Grant management and access-history reads require `SYS_ADMIN`. |
| INV-007 | Creating a proposal/project grant requires the owning reader to return an eligible resource. |
| INV-008 | Creating a report grant requires positive CIDOC conformance. |

“Every externally denied or granted operation is recorded accurately” is an
intended rule, not a current invariant: JSON-LD compatibility failures are
recorded as granted, and downstream response-serialization failures occur after
the grant record has already been written.

## 9. Acceptance and test traceability

| Behaviour | Representative automated evidence |
| --- | --- |
| One-time token hashing | `test/external_publications/test_use_cases.py::test_create_external_publication_hashes_token_once` |
| Reject non-conformant report | `test/external_publications/test_use_cases.py::test_rejects_non_conformant_report_publication` |
| Delegate publishable-resource listing | `test/external_publications/test_use_cases.py::test_list_publishable_resources_delegates_by_type` |
| Opaque revoked-token semantics | `test/external_publications/test_use_cases.py::test_resolve_returns_404_semantics_for_revoked_publication` |
| Expiration and naive-time normalisation | `test/external_publications/test_use_cases.py::test_domain_blocks_expired_publication`, `test/external_publications/test_use_cases.py::test_domain_normalizes_naive_expiration_before_access_check` |
| Granted access record | `test/external_publications/test_use_cases.py::test_resolve_records_granted_access` |
| JSON-LD detail and summary rules | `test/external_publications/test_use_cases.py::test_json_ld_is_returned_for_report_detail_publication`, `test/external_publications/test_use_cases.py::test_json_ld_rejects_summary_profile` |
| Public summary and JSON-LD media type | `test/external_publications/test_api.py::test_public_summary_response_omits_heavy_fields`, `test/external_publications/test_api.py::test_json_ld_route_uses_json_ld_content_type` |
| Administrative authorisation | `test/external_publications/test_api.py::test_sys_admin_can_list_external_publications`, `test/external_publications/test_api.py::test_staff_cannot_manage_external_publications` |
| Angular create workflow | `external-publications-page.component.spec.ts` |

There are no automated tests for invalid-token denial records, known-resource
denials, access-history listing, idempotent revocation metadata, past expiration
at creation, duplicate grants, integration-client mode, actor response fields,
URL construction behind proxies, JSON-LD audit accuracy, report eligibility
after publication, rate limiting, or PostgreSQL persistence constraints.

## 10. Non-functional requirements

- **Secret handling:** 256 bits of token entropy are generated with the platform
  cryptographic RNG; only SHA-256 hashes are stored.
- **Architecture:** resource reads cross Published Languages and ACL adapters;
  publication storage contains no foreign key to owning resource tables.
- **Auditability:** creation and revocation actors are stored, but omitted from
  API responses; access attempts are stored, but only known-grant rows have an
  administrative read endpoint.
- **Privacy:** access rows retain pseudonymous network data and raw user-agent
  strings without a documented retention period.
- **Availability:** every invalid-token probe causes a database insert and
  commit; there is no rate limit or write-suppression policy at this boundary.
- **Caching:** JSON-LD permits private caching for five minutes, while the base
  resource has no explicit cache policy; neither guarantees immediate removal
  from a consumer's cache after revocation.
- **Search:** unbounded free-text values become leading-wildcard `ILIKE`
  predicates; indexes do not efficiently support those searches.

## 11. Known gaps and recommended changes

| ID | Priority | Finding | Recommended change |
| --- | --- | --- | --- |
| GAP-001 | Critical | `INTEGRATION_CLIENT` is advertised by the request schema and domain but cannot be created or authenticated end to end. | Remove it from the public contract until supported, or add client identity input, credential authentication, resolver routing, authorisation policy, revocation, UI, and tests. |
| GAP-002 | High | JSON-LD requests returning `409` are recorded as `GRANTED`. | Move the success record after all profile/type/document checks, record failed operations as `DENIED` with a reason, and test both outcomes. |
| GAP-003 | High | A grant exposes mutable live data, so its disclosed content can expand after administrative approval. | Decide explicitly between live projection and immutable publication snapshot. For live data, re-run disclosure policy on every access and show administrators what changed; for snapshots, persist versioned payloads/hashes. |
| GAP-004 | High | Report CIDOC conformance is checked only at creation, unlike proposal/project eligibility on every resolution; reports with changed conformance or flagged narrative findings may remain public. | Define one consistent continuing-eligibility rule and require human narrative approval before initial and subsequent disclosure. |
| GAP-005 | High | Invalid-token probes always create database rows, with no rate limit, bounded retention, or aggregation. | Apply gateway/application throttling, cap token length before hashing, aggregate hostile probes, and establish deletion/retention policy. |
| GAP-006 | High | `SUMMARY` still exposes personal names, internal/linkage IDs, dates, intended use, and semantic metadata. | Define per-resource disclosure schemas from data-classification and privacy requirements; remove internal IDs and personal data unless explicitly justified. |
| GAP-007 | High | Raw `User-Agent` and an unsalted IP hash are retained and returned to admins without a retention policy. | Use a keyed, rotating pseudonym where correlation is necessary, truncate/sanitise user agents, restrict access, and document retention and lawful purpose. |
| GAP-008 | Medium | The raw URL is recoverable only during creation, but the UI neither clearly labels it one-time nor provides a dedicated copy action in the receipt. | Add a one-time-secret warning, explicit Copy/Download receipt action, confirmation before closing, and recovery guidance based on revoke/reissue. |
| GAP-009 | Medium | Expirations in the past are accepted and the UI permits no-expiry grants without additional confirmation. | Require `expiresAt > now`, define a default/maximum lifetime, and require an explicit exception for non-expiring links. |
| GAP-010 | Medium | Revocation has no UI confirmation and `private, max-age=300` may leave JSON-LD usable from a client cache after revocation. | Confirm destructive intent and use an approved cache policy, normally `no-store` for bearer-token responses requiring immediate revocation. |
| GAP-011 | Medium | Access history is implemented only in the backend; unknown-token denials are not queryable at all. | Add a protected audit UI, global security view for unlinked denials, outcome/reason filters, actor-friendly metadata, and export/retention controls. |
| GAP-012 | Medium | Multiple equivalent active grants are allowed and there is no rotation operation. | Warn on duplicates, show all grants for a resource, and implement atomic rotation/reissue that revokes the former token. |
| GAP-013 | Medium | Public URL generation trusts the effective inbound request origin. | Configure and validate one canonical public base URL and explicitly configure trusted proxies/hosts. |
| GAP-014 | Medium | Creation/revocation actors are persisted but omitted from admin responses. | Expose resolved audit actors to authorised administrators without leaking permission IDs publicly. |
| GAP-015 | Low | Search terms and raw user-agent values have no application-level length bound; leading-wildcard search is poorly indexed. | Add bounded request/header lengths and use exact/prefix or trigram-indexed search as required. |
| GAP-016 | Low | The flow diagram calls the response DTO “stable” and places access recording ambiguously around JSON-LD checks. | Update the diagram to show live resource resolution, continuing eligibility differences, one-time token disclosure, and final-outcome audit placement. |

## 12. Traceability

| Element | Location |
| --- | --- |
| Grant, access record, enums, and lifecycle | `vitarerum-api/app/external_publications/domain/models.py` |
| Create, list, resolve, JSON-LD, access-history, and revoke use cases | `vitarerum-api/app/external_publications/application/use_cases.py` |
| Published-reader ports and projection views | `vitarerum-api/app/external_publications/application/ports.py` |
| ACL adapters for owning contexts | `vitarerum-api/app/external_publications/infrastructure/acls.py` |
| SQLAlchemy models and repositories | `vitarerum-api/app/external_publications/infrastructure/` |
| Administrative and public HTTP routes | `vitarerum-api/app/external_publications/presentation/` |
| Token generation and hashing | `vitarerum-api/app/shared/tokens.py` |
| Collection-use Published Language | `vitarerum-api/app/use_of_collections/public.py` |
| Report Published Language | `vitarerum-api/app/reports/public.py` |
| Angular administration | `vitarerum-ui/src/app/features/admin/external-publications/` |
| Backend and Angular tests | `vitarerum-api/test/external_publications/` and `external-publications-page.component.spec.ts` |
| Flow diagram | `docs/diagrams/external-publications-flow.puml` and generated SVG |
| Administrator how-to | `docs/manual/how-to/administracao/publicar-recurso-externo.md` |

## 13. Open product decisions

1. Is a publication an immutable approved snapshot or an always-current view of
   the source resource?
2. Which exact fields belong in each resource's `SUMMARY` and `DETAIL` public
   disclosure schema?
3. Must every grant expire, and what default and maximum lifetimes apply?
4. Is integration-client access still an MVP requirement, and which identity
   and credential lifecycle owns it?
5. What lawful purpose and retention period apply to access network metadata?
6. Should a report automatically become inaccessible if CIDOC conformance or
   narrative review changes after publication?
7. How quickly must revocation invalidate browser, proxy, and downstream caches?
