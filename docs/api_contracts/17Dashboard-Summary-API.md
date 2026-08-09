# Dashboard Summary API Contract

Backs `/p/dashboard`, replacing the current static/hardcoded placeholder
(`vitarerum-ui/src/app/features/dashboard/dashboard.component.ts`) with
real, role-scoped counts. Every summary endpoint below is a thin
aggregation over data that already exists — no new domain concept, no new
table beyond what each bounded context already persists.

Two kinds of endpoints power the dashboard:

- **New summary endpoints** (this contract): needed where a card requires
  grouping by status/assignment and today would otherwise cost one HTTP
  call per bucket (see "Existing endpoints reused as-is" below for the
  cards that need **no** backend change at all).
- **Existing endpoints, called as-is**: some cards only need a single
  total already returned by pagination (`totalElements`) or the length of
  a non-paginated list — no new endpoint, just a frontend call. Listed at
  the end so implementers don't duplicate work that already exists.

All summary endpoints require a session (`Authorization: Bearer …` +
`X-Permission-Id`) and are **staff-only** (`403 INSUFFICIENT_GROUP` for
`EXTERNAL`, mirroring the existing list endpoints they aggregate), with
one exception noted below (Proposals summary also serves `EXTERNAL`,
scoped to the caller's own proposals, matching `GET /proposals` today).

## Base URL

| Environment | URL |
|---|---|
| Local dev | `http://127.0.0.1:8000/api/v1` |
| Production | `https://api.vitarerum.example/api/v1` |

---

## New summary endpoints

### `GET /proposals/summary`

Added to the existing `proposals_router` (`/proposals`,
`app/use_of_collections/presentation/proposal_routes.py`). Powers the
"New proposals" / "My assignments" / "Other's assignments" / "Approved" /
"Rejected or cancelled" dashboard cards — the same five buckets the menu
already exposes as separate screens
(`vitarerum-ui/src/app/shared/layout/menu/app-menu.component.ts:27-53`),
today only obtainable by calling `GET /proposals` five times and reading
`totalElements` from each.

Bucket semantics **must match** the filters each existing screen already
sends, not be reinvented:

| Bucket | Existing screen | Filter it already uses |
|---|---|---|
| `newProposals` | `proposals-new-page.component.ts:82` | `status=SUBMITTED` (no assignee — status alone identifies the unassigned inbox) |
| `myAssignments` | `proposals-my-assignments-page.component.ts:104-106` | `status=PENDING & assignedTo=<callerPermissionId>` |
| `othersAssignments` | `proposals-others-page.component.ts:73-83` | `status=PENDING`, **assigned to someone other than the caller** — today computed by filtering client-side after fetching a page, which this endpoint should instead compute correctly server-side over the full set |
| `approved` | `proposals-approved-page.component.ts:67-68` | `status=APPROVED` |
| `rejectedOrCancelled` | `proposals-rejected-page.component.ts:69-70` | `status=[REJECTED, CANCELLED]` |

Authorization: same scope as `GET /proposals` — staff see the whole
catalogue's counts; `EXTERNAL` gets counts scoped to proposals it
requested (`requested_by = caller`), and `othersAssignments`/
`myAssignments` are meaningless for `EXTERNAL` and should be omitted
(`null`), not `0` (there is no assignment concept from that caller's
point of view).

**Response `200`**

```json
{
  "newProposals": 12,
  "myAssignments": 3,
  "othersAssignments": 5,
  "approved": 40,
  "rejectedOrCancelled": 8
}
```

For `EXTERNAL` callers:

```json
{
  "newProposals": null,
  "myAssignments": null,
  "othersAssignments": null,
  "approved": 2,
  "rejectedOrCancelled": 1
}
```

**`403`** — no session / not staff or requester (should not normally
happen, since `EXTERNAL` is allowed here unlike the other three summaries
below).

---

### `GET /collection-use-projects/summary`

Added to the existing `projects_router`
(`/collection-use-projects`, `app/use_of_collections/presentation/project_routes.py`).
Powers "Active projects" and the per-status project cards. Bucket names
map 1:1 to `UseStatus`, matching the four existing screens exactly:

| Bucket | Existing screen | `status` value |
|---|---|---|
| `pending` | `projects-pending-page.component.ts:78` | `CREATED` |
| `inProgress` | `projects-in-progress-page.component.ts:76` | `IN_PROGRESS` |
| `completed` | `projects-completed-page.component.ts:78` | `COMPLETED` |
| `cancelled` | `projects-cancelled-page.component.ts:78` | `CANCELLED` |

Authorization: same scope as `GET /collection-use-projects` — staff see
every project; `EXTERNAL` gets counts scoped to `requestedBy = caller`
(`requestedBy` filter already exists on the list endpoint, alias
`requestedBy`, camelCase — note the existing list endpoint uses camelCase
query aliases here, unlike `/proposals`, which uses snake_case; this
inconsistency is pre-existing, not introduced by this contract).

**Response `200`**

```json
{ "pending": 6, "inProgress": 8, "completed": 21, "cancelled": 2 }
```

**`403`** — no session.

---

### `GET /museum-questions/summary`

Added to the existing internal router (`/museum-questions`,
`app/museum_questions/presentation/routes.py`, the `internal_router`
mounted as `internal_museum_questions_router` in `app/main.py`). Powers
the "Public Inquiries" pending-count card (Use of Collections section of
the menu, see the `MUSEUM_QUESTIONS_ITEM` → renamed "Public Inquiries"
entry). Staff-only — this is the internal/staff-facing router, distinct
from the public submission API (`13MuseumQuestions-Public-API.md`).

Buckets map 1:1 to `MuseumQuestionStatus`:

```json
{ "submitted": 9, "answered": 120, "outOfScope": 3, "closed": 45 }
```

The dashboard card should highlight `submitted` (pending staff review) as the
actionable number, the rest as context.

**`403 INSUFFICIENT_GROUP`** — caller is not staff.

---

### `GET /admin/collection-data-sources/summary`

Added to the existing `collection_data_sources_router`
(`/admin/collection-data-sources`,
`app/collection_object_index/presentation/routes.py`). This is the one
card with **no existing equivalent anywhere in the UI today** — there is
currently no cross-collection view of the catalogue; `GET
.../collections/{id}/documents` only reports per collection
(`15CollectionDataSources-Admin-API.md`), so answering "how many
documents across the whole catalogue still need reindexing" today
requires opening every collection by hand.

Authorization mirrors `GET /admin/collection-data-sources/collections`
(same "manageable" scoping used by `ListManageableCollections`,
`app/collection_object_index/application/use_cases.py`): SYS_ADMIN and
COLLECTIONS_MANAGEMENT get counts across the **entire** catalogue;
CURATORIAL gets counts scoped to the collections it curates only — this
is meant to be an actionable "things I can fix" number, not a global
statistic a curator can't act on. DIRECTION (read-only staff) may call it
too, scoped like a curator with zero curated collections (all counts
`0`), consistent with it seeing the read-only catalogue elsewhere.

**Response `200`**

```json
{
  "collections": 14,
  "liveDocuments": 37,
  "documentsByStatus": { "UPLOADED": 2, "INDEXED": 33, "ERROR": 2 },
  "documentsPendingReindex": 5
}
```

`documentsPendingReindex` counts live source documents where
`contentMatchesSearchableColumns = false` (see
`15CollectionDataSources-Admin-API.md` § Source documents) — the legacy
searchable-columns backlog introduced by the `searchableColumns`
migration. This is the number the dashboard card should surface most
prominently; it currently has no other visibility path in the product.

**`403`** — caller is not staff.

---

## Existing endpoints reused as-is (no new backend work)

These dashboard cards are already fully served by endpoints that exist
today — do **not** build a summary endpoint for them, just call the
existing one from the frontend and read the field noted:

| Card | Existing endpoint | Field to read |
|---|---|---|
| Recent visit reports | `GET /reports/collection-use/in_situ_visit` (`10Reports-InSituVisit.md`) | `totalElements` (no status concept exists for reports — this is a plain count, not a breakdown) |
| Users | `GET /users` (`01Identity context.md`) | `totalElements` (paginated) |
| Groups | `GET /groups` | `len(groups)` (returns the full list, not paginated) |
| Institutions | `GET /institutions` | `totalElements` (paginated) |
| AI Prompt templates | `GET /ai/prompts` (`16AI-Prompts-Admin-API.md`) | `len(...)` (returns the full list, not paginated) |

---

## Notes

- The static placeholder being replaced lives at
  `vitarerum-ui/src/app/features/dashboard/dashboard.component.ts` — no
  `DashboardSummary` model, service, or mock exists yet on the frontend.
- `docs/plans/plano-permissoes-recursos-admin.md` lists a `dashboard.view`
  permission resource and an access-control layer (`/p/admin/access-control`,
  migration `0015_access_control`) as if partly implemented — **this does
  not exist in the current codebase** (the real `0015` migration is
  `0015_museum_question_triages`; there is no `Resource`/
  `GroupResourcePermission` model, no access-control router, no frontend
  service). Treat that plan as aspirational/stale with respect to
  authorization; the summary endpoints here should use the same
  `require_staff` / group-check patterns already used by the endpoints
  they aggregate, not a permission system that isn't built yet.
- None of these endpoints should introduce pagination, filtering, or
  write behavior — they are read-only, no-parameter (or caller-scoped
  only) aggregates. If a future need arises for date-range or
  per-collection breakdowns, that's a new, separate endpoint, not an
  extension of these.
