# SPEC-021 — Dashboard Summaries

| Field | Value |
| --- | --- |
| Identifier | SPEC-021 |
| Status | Specified, not implemented |
| Contexts involved | `use_of_collections`, `museum_questions`, `collection_object_index`, and the Angular dashboard |
| Derived from | Proposed API contract, backend and frontend implementation, related specifications, diagrams, user documentation, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-007](../007-identidade-e-acesso/spec.md), [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-011](../011-perguntas-ao-museu/spec.md), [SPEC-014](../014-catalogo-e-indice-de-objetos/spec.md), [SPEC-018](../018-notificacoes/spec.md) |

> **Verified status.** None of the four summary endpoints specified here has a
> route, schema, use case, repository query, Angular client, or automated test.
> The dashboard itself is implemented, but currently shows role-owned project
> TODO post-its rather than these aggregate indicators. Requirements and
> acceptance criteria for summary counts therefore remain proposed behaviour.

## 1. Problem

Operational screens expose totals for proposals, projects, public enquiries,
and collection source documents, but those totals are spread across separate
queries and pages. Building a role-aware overview from the current list APIs
would require several requests and, in two existing proposal screens, still
produce incomplete counts because client-side filtering is limited to the
first 100 rows.

The catalogue has a further cross-collection need: staff can see and reindex an
outdated document after opening its collection, but there is no single count of
all live documents whose indexed content no longer matches their searchable
column mapping.

## 2. Goal and scope

Provide small, read-only, caller-scoped aggregations over data already owned by
the participating bounded contexts. Each context remains responsible for its
own summary endpoint and vocabulary; no central Dashboard bounded context,
cross-context database query, new domain aggregate, or new persistence table is
introduced.

The planned feature covers four summary contracts and their Angular cards. The
existing dashboard TODO widget remains a separate implemented capability. Date
ranges, trends, charts, arbitrary filters, exports, and historical snapshots
are outside this specification.

## 3. Strategic design

Dashboard counts are application read models, not domain entities. Each owning
context should implement an application query over its repository port and map
the result at its existing presentation boundary.

| Owner | Planned responsibility |
| --- | --- |
| Use of Collections | Count proposals by workflow/assignment bucket and projects by `UseStatus`. |
| Museum Questions | Count enquiries by every `MuseumQuestionStatus`. |
| Collection Object Index | Count manageable collections and their live source documents. |
| Angular dashboard | Request only summaries visible to the active role and link each card to its corresponding operational screen. |

The Identity session and active `X-Permission-Id` determine scope. The backend
must not trust the UI to hide a card or supply another permission's identifier.

### 3.1 Count/list parity

A card must use the same predicate and caller scope as the screen it opens. The
predicate should be shared at the repository/query level where practical;
copying filters into unrelated route code invites drift.

Parity means the count equals `totalElements` from the corresponding list with
the same caller and filters at the same database state. It does not mean several
independent HTTP calls form one transactionally consistent global snapshot.

## 4. Current dashboard behaviour

`/p/dashboard` is available to every authenticated role. Its implemented widget
calls:

`GET /api/v1/collection-use-projects/my-todo-items?completed=false&page=0&size=20`

For staff, it displays up to 20 open TODOs owned by the active permission,
newest first. Each post-it links to the originating project's TODO tab and can
be completed directly. The response's full `totalElements` is used to show how
many items are outside the visible slice. Changing the active role changes the
permission header and reloads the resource.

For `EXTERNAL`, the Angular loader returns an empty local page and makes no TODO
request. The screen then shows the empty staff-TODO message; it has no
role-specific external dashboard content.

The widget is implemented with a standalone, `OnPush`, signal-based Angular
component and `resource()`. A load failure is held by the Angular resource but
is not mapped to the component's displayed `error` signal; it can therefore be
presented as an empty state rather than an actionable load error. The visible
count badge uses the slice length, not the full total.

## 5. Planned functional requirements

### FR-001 — Common summary contract

Each planned endpoint:

- requires an authenticated session and active permission;
- accepts no pagination, filter, search, or date parameters;
- derives its scope exclusively from the caller;
- performs no write or side effect;
- returns all declared buckets, including zero-valued buckets; and
- uses `null` only where a bucket has no meaning for an allowed role.

Future analytical dimensions should use separate versioned contracts rather
than silently changing the semantics or cost of these operational summaries.

### FR-002 — Proposal summary

`GET /api/v1/proposals/summary`

For staff, the planned response contains these buckets:

| Bucket | Predicate and corresponding screen |
| --- | --- |
| `newProposals` | `status = SUBMITTED`; New Proposals. Assignment moves a proposal to `PENDING`, so no separate unassigned predicate is currently required. |
| `myAssignments` | `status = PENDING AND assigned_to = caller.permission_id`; My Assignments. |
| `othersAssignments` | `status = PENDING AND assigned_to IS NOT NULL AND assigned_to <> caller.permission_id`; Other's Assignments. |
| `approved` | `status = APPROVED`; Approved. |
| `rejectedOrCancelled` | `status IN (REJECTED, CANCELLED)`; Rejected / Cancelled. |

`othersAssignments` must be counted in the database over the complete scoped
set. The current Angular page fetches at most 100 `PENDING` proposals and then
filters them in memory, so both its rows and its displayed total may be
incomplete. The summary endpoint must not reproduce that defect.

The proposals route and current Angular adapter both support repeated `status`
parameters. The summary repository query should apply the same OR semantics
without loading proposal rows merely to count them.

The static `/summary` route must be declared before the existing
`/{proposal_id}` route.

### FR-003 — Proposal scope for external callers

The proposal list query forces a non-staff caller to
`requested_by = caller.permission_id`, regardless of a supplied filter. The
summary must enforce the same rule server-side.

Under the currently proposed contract, `newProposals`, `myAssignments`, and
`othersAssignments` are `null` for `EXTERNAL`; `approved` and
`rejectedOrCancelled` count only that caller's proposals. This shape is
backward-compatible with the proposal document but does not summarise the
actual My Proposals screen, which lists the caller's proposals in every state,
including `SUBMITTED` and `PENDING`. A useful external-dashboard contract
therefore remains a product decision rather than a completed design.

Planned response for staff:

```json
{
  "newProposals": 12,
  "myAssignments": 3,
  "othersAssignments": 5,
  "approved": 40,
  "rejectedOrCancelled": 8
}
```

### FR-004 — Project summary

`GET /api/v1/collection-use-projects/summary`

| Bucket | `UseStatus` | Corresponding screen |
| --- | --- | --- |
| `pending` | `CREATED` | Pending |
| `inProgress` | `IN_PROGRESS` | In Progress |
| `completed` | `COMPLETED` | Completed |
| `cancelled` | `CANCELLED` | Cancelled |

Staff counts cover all projects, matching the current list query. A non-staff
caller is forcibly scoped to projects it requested. The response is:

```json
{
  "pending": 6,
  "inProgress": 8,
  "completed": 21,
  "cancelled": 2
}
```

The static `/summary` route must be declared before the existing
`/{project_id}` route.

### FR-005 — Museum-question summary

`GET /api/v1/museum-questions/summary`

The summary must represent all five current domain states:

```json
{
  "submitted": 9,
  "inProgress": 4,
  "answered": 120,
  "outOfScope": 3,
  "closed": 45
}
```

This corrects the earlier four-bucket proposal, which claimed a one-to-one
mapping while omitting `IN_PROGRESS`. The New Inquiries screen corresponds more
precisely to `SUBMITTED AND assigned_to IS NULL`; My Enquiries corresponds to
`IN_PROGRESS AND assigned_to = caller.permission_id`. A simple status total is
useful context but is not interchangeable with either personal/actionable
queue. Card labels and links must state which measure they display.

The existing context authorises only `CURATORIAL` and
`COLLECTIONS_MANAGEMENT`, not every staff group. The summary must use the same
`require_museum_question_access` policy unless product policy explicitly
changes. It must be declared before `GET /museum-questions/{question_id}` so
`summary` is not interpreted as an identifier.

### FR-006 — Collection-source summary

`GET /api/v1/admin/collection-data-sources/summary`

The planned response is:

```json
{
  "collections": 14,
  "liveDocuments": 37,
  "documentsByStatus": {
    "UPLOADED": 2,
    "INDEXED": 33,
    "ERROR": 2
  },
  "documentsPendingReindex": 5
}
```

Only live documents (`deleted_at IS NULL`) contribute to document totals.
`documentsByStatus` must include `UPLOADED`, `INDEXED`, and `ERROR` keys even
when their value is zero. `documentsPendingReindex` counts live documents where
`content_matches_searchable_columns = false`, independently of their status.

The pending condition is already visible on each document after opening a
collection and has a guarded reindex action. What is missing is a scoped,
cross-collection backlog total.

### FR-007 — Collection-source scope

The catalogue summary is an actionable management scope:

| Active group | Collections included |
| --- | --- |
| `SYS_ADMIN` | All collections. |
| `COLLECTIONS_MANAGEMENT` | All collections. |
| `CURATORIAL` | Only collections assigned to the active permission. |
| `DIRECTION` | Empty scope; every count is zero. |
| `EXTERNAL` | Forbidden. |

This does **not** exactly mirror `ListManageableCollections`: that query returns
all catalogue collections to any staff caller and marks each row with a
`manageable` flag. The planned summary instead mirrors the existing mutation
scope enforced by `require_collection_scope`, because it is intended to count
work the caller can perform. This distinction must be retained in the use-case
name and tests.

### FR-008 — Reuse existing endpoints where one total is sufficient

No dedicated summary endpoint is required merely to obtain these existing
totals:

| Potential card | Existing endpoint | Value |
| --- | --- | --- |
| In-situ visit reports | `GET /api/v1/reports/collection-use/in_situ_visit` | `totalElements` |
| Users | `GET /api/v1/users` | `totalElements` |
| Groups | `GET /api/v1/groups` | Length of `groups` |
| Institutions | `GET /api/v1/institutions` | `totalElements` |
| Prompt templates | `GET /api/v1/ai/prompts` | Response-array length |

Reuse does not make every card suitable for every role. Reports and prompts are
staff-only, institutions are `SYS_ADMIN`-only, and the current users/groups
list routes permit any authenticated caller despite exposing identity data.
The dashboard must maintain an explicit role-to-widget matrix and must not issue
requests that the active role is not authorised or intended to see.

### FR-009 — Angular summary integration

The future Angular implementation should:

- keep the current TODO widget;
- introduce typed summary models and API adapters within the owning features;
- request independent visible cards concurrently;
- refetch role-dependent resources when the active permission changes;
- show loading, error with retry, empty/zero, and loaded states distinctly;
- display a last-refreshed indication if values can become stale; and
- link each card to the exact list route represented by its predicate.

The dashboard must not calculate `othersAssignments`, status unions, or caller
scope by downloading rows and filtering them in the browser.

## 6. Planned authorisation matrix

| Summary | `EXTERNAL` | `CURATORIAL` | `COLLECTIONS_MANAGEMENT` | `DIRECTION` | `SYS_ADMIN` |
| --- | --- | --- | --- | --- | --- |
| Proposals | Own scoped subset | All | All | All | All |
| Projects | Own scoped subset | All | All | All | All |
| Museum questions | Forbidden | Allowed | Allowed | Forbidden | Forbidden under current policy |
| Collection sources | Forbidden | Assigned collections | All | Zero-valued management scope | All |

The `SYS_ADMIN` exclusion from Museum Questions is current application policy,
not a general claim that administrators can never receive that role. Supporting
it requires an explicit policy change in the owning context.

## 7. Intended invariants

| ID | Invariant |
| --- | --- |
| INV-001 | Every actionable bucket uses the same predicate and caller scope as its linked operational list. |
| INV-002 | Non-staff proposal/project counts are always restricted to the active permission's resources. |
| INV-003 | A meaningless bucket is `null`; a meaningful empty bucket is numeric zero. |
| INV-004 | Summary queries perform no writes and accept no caller-controlled scope. |
| INV-005 | Every current enum state represented by a by-status summary has an explicit response bucket. |
| INV-006 | Catalogue totals exclude soft-deleted documents. |
| INV-007 | Catalogue management counts include only collections the active role can mutate. |
| INV-008 | Static summary routes take precedence over identifier routes. |

These are intended invariants and are not enforced because the summary feature
has not been implemented.

## 8. Planned acceptance criteria

| ID | Criterion | Automated evidence |
| --- | --- | --- |
| AC-001 | Each proposal bucket equals the equivalent repository count for staff. | Not implemented |
| AC-002 | `othersAssignments` counts more than 100 matching rows correctly and excludes unassigned/current-caller rows. | Not implemented |
| AC-003 | External proposal/project summaries cannot widen or spoof their caller scope. | Not implemented |
| AC-004 | All four `UseStatus` values are counted and zero buckets remain present. | Not implemented |
| AC-005 | All five `MuseumQuestionStatus` values are counted; only the two authorised groups can call the endpoint. | Not implemented |
| AC-006 | Both static `/summary` routes preceding identifier routes resolve as summaries, not IDs. | Not implemented |
| AC-007 | Catalogue totals exclude deleted documents and count stale searchable content across the exact management scope. | Not implemented |
| AC-008 | Changing active Angular permission cancels/invalidates stale card state and loads the new role's allowed cards. | Not implemented |
| AC-009 | One card failure does not hide successful independent cards, and retry is available. | Not implemented |
| AC-010 | Card links open lists whose `totalElements` matches the card under an unchanged database state. | Not implemented |

Existing evidence covers only the separate TODO widget:
`test_project_todos.py::test_dashboard_postits_list_only_current_staff_profile_items`,
`test_project_todos.py::test_dashboard_postits_paginate_and_order_by_project`,
and `dashboard.component.spec.ts`.

## 9. Non-functional requirements

- **Architecture:** aggregate queries remain inside their owning bounded
  contexts and depend on repository ports, not neighbouring ORM tables.
- **Performance:** each context should use conditional aggregation/grouping
  rather than one full-row query per bucket. Indexes should be evaluated using
  realistic status, assignee, requester, collection, deletion, and stale-
  content distributions.
- **Consistency:** a single endpoint's buckets should come from one database
  statement or transactionally consistent read. Cards from separate contexts
  are independent observations and need not share a global snapshot.
- **Resilience:** Angular cards fail independently and expose retry; absence of
  one optional summary must not blank the dashboard or the TODO widget.
- **Security:** every query derives scope from the validated active permission;
  no role-sensitive count is inferred solely in the browser.
- **Accessibility:** card names, counts, freshness, loading, and failures must be
  available without relying on colour, and links need descriptive accessible
  names.

## 10. Known gaps and recommended changes

| Priority | Finding | Recommended change |
| --- | --- | --- |
| High | None of the four summary contracts is implemented or tested. | Implement one application read query and repository aggregation per owning context, then add API contract and Angular tests. |
| High | The earlier museum-question response omitted `IN_PROGRESS` and its `submitted` count did not exactly match the actionable New Inquiries queue. | Keep all five status buckets and either add explicit `unassignedSubmitted`/`myInProgress` counts or label status totals as context rather than personal queues. |
| High | The proposed external proposal response ignores the caller's `SUBMITTED` and `PENDING` proposals and therefore cannot represent My Proposals. | Define a dedicated external summary, such as total/by-status counts, or restrict the five-bucket staff contract to staff callers. |
| High | Current Other's Assignments and Rejected / Cancelled Angular pages fetch at most 100 rows and paginate/filter locally. | Add server-side not-equal assignment filtering and correct repeated-status serialisation independently of the dashboard work. |
| Medium | The catalogue proposal said it mirrored the collection list, but the list exposes all collections with `manageable` flags while the desired count is mutation-scoped. | Name and test the summary as a management backlog and reuse the `can_manage_all_collections`/curated-ID policy. |
| Medium | The current dashboard masks TODO load failures as an empty result and labels the visible-slice count as the open count. | Map `postitsResource.error()` to an error state with retry and label/display `totalElements` separately from visible items. |
| Medium | Reusing identity list endpoints for cards inherits inconsistent authorisation: users and groups are visible to every authenticated role, while institutions require `SYS_ADMIN`. | Decide intended Identity visibility first; show only authorised cards and tighten the underlying endpoints if broad access is temporary. |
| Medium | Four independent summary calls can produce a visually mixed-time dashboard and repeated database load on navigation. | Fetch cards concurrently, show freshness, measure query cost, and introduce short caller-aware caching only when invalidation/staleness requirements are defined. |
| Medium | The planned Angular card set and role-to-widget visibility are not specified visually or in routes. | Define the MVP card matrix, ordering, labels, zero states, target routes, responsive layout, and per-card failure behaviour before implementation. |
| Low | The dashboard diagram shows a single nonexistent `/api/v1/dashboard/summary` endpoint plus Notifications, contradicting the four context-owned endpoints. | Redraw it with the implemented TODO request and the four independently proposed summary routes, clearly marking current versus planned flows. |
| Low | The companion proposal still calls the dashboard a static placeholder and describes only four museum-question states. | Align `docs/proposals/17Dashboard-Summary-API.md` after the product decisions above. |

## 11. Traceability

| Element | Current or planned location |
| --- | --- |
| Proposal and project list scope | `vitarerum-api/app/use_of_collections/application/queries.py` |
| Proposal and project routes | `vitarerum-api/app/use_of_collections/presentation/proposal_routes.py`, `project_routes.py` |
| Proposal/project repository filters | `vitarerum-api/app/use_of_collections/application/ports.py` and `infrastructure/repositories.py` |
| Museum-question status and access policy | `vitarerum-api/app/museum_questions/domain/models.py`, `application/use_cases.py` |
| Museum-question routes | `vitarerum-api/app/museum_questions/presentation/routes.py` |
| Collection management scope | `vitarerum-api/app/collection_object_index/application/authorization.py` |
| Collection/document queries and persistence | `vitarerum-api/app/collection_object_index/application/use_cases.py`, `infrastructure/repositories.py` |
| Existing TODO endpoint and use case | `vitarerum-api/app/use_of_collections/presentation/project_routes.py`, `application/use_cases/project_todos.py` |
| Existing Angular dashboard | `vitarerum-ui/src/app/features/dashboard/` |
| Dashboard user documentation | `docs/manual/user-manual.md#30-painel-dashboard-pdashboard` |
| Companion proposal | `docs/proposals/17Dashboard-Summary-API.md` |
| Diagram requiring alignment | `docs/diagrams/dashboard-summary-flow.puml` and generated SVG |

## 12. Open product and implementation decisions

1. Should `EXTERNAL` receive a distinct My Proposals/My Projects summary, or
   should operational summary cards remain staff-only?
2. Does the Museum Questions card represent all status totals, the shared
   unassigned queue, the active permission's assigned queue, or more than one
   of these?
3. Which cards are visible to each active group, especially `SYS_ADMIN` and
   `DIRECTION`, whose current menus intentionally differ from other staff?
4. What maximum staleness is acceptable, and is caller-aware caching warranted
   after query measurement?
5. Should card refresh be manual, on navigation/role change, periodically
   polled, or invalidated by successful mutations?
6. Must the four context summaries be visually timestamped as independent
   observations, or is eventual consistency implicit for this operational UI?
