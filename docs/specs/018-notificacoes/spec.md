# SPEC-018 — In-App Notifications

| Field | Value |
| --- | --- |
| Identifier | SPEC-018 |
| Status | Implemented (with declared idempotency, privacy, navigation, resilience, and retention gaps) |
| Bounded context | `app/notifications` |
| Derived from | Backend, frontend, migrations, emitting contexts, architecture contracts, diagrams, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md), [SPEC-007](../007-identidade-e-acesso/spec.md), [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-011](../011-perguntas-ao-museu/spec.md) |

## 1. Problem

Museum work is asynchronous. Proposals arrive and move between teams,
documents and corrections are submitted, public questions become overdue, and
scientific-return monitoring finds candidates. Without an internal signal,
staff must repeatedly inspect each workflow to discover what changed.

The system also supports one user acting through multiple permissions. A
notification addressed only to the user would mix unrelated roles and could
expose work outside the permission currently in use.

## 2. Goal and scope

This context stores in-app notifications addressed to a specific permission,
lists the visible notifications of the active permission, calculates its unread
count, and supports read and clear operations.

It does not determine workflow recipients, authorise access to the related
resource, send email, guarantee delivery, or own the business event that caused
the notification. Those responsibilities remain with the emitting context.

## 3. Strategic context

Notifications is a generic supporting context. Proposal, public-submission,
museum-question, and scientific-return workflows use its Published Language to
request a notification without importing persistence details.

| Relationship | Responsibility |
| --- | --- |
| Emitting context → Notifications | Select recipients and metadata, invoke `notify` or `notify_many`, and commit the shared transaction. |
| Notifications → Identity | Resolve the permission that triggered an item into a user/group view for presentation. |
| Notifications → Angular topbar | Expose the active permission's unread count and recent visible items. |
| Emitting context → Email adapter | Send any corresponding email after its database commit; email is not owned by this context. |

The dispatcher and emitter normally share the request's database session, so
notification persistence is committed atomically with the originating business
change. Email, where implemented, is a separate post-commit side effect and may
fail after the in-app item has been stored.

## 4. Ubiquitous language and domain model

### 4.1 Notification

`Notification` is a mutable entity containing:

- generated identifier;
- recipient permission identifier;
- kind;
- optional related-resource type, identifier, and display label;
- optional triggering permission;
- optional free-text note;
- creation time;
- optional read time; and
- optional clear time.

New identifiers and timestamps are produced by the application dispatcher.
The domain object itself contains no creation, read, or clear behaviour; those
transitions live in application services and repository updates. For this small
generic context that is workable, although it is an anemic domain model.

### 4.2 Active permission

The authenticated request supplies an active `PermissionId`. All user-facing
queries and bulk mutations are scoped to that identifier, not merely to the
authenticated user. Switching role in Angular resets local notification state
and loads the new permission's unread count.

### 4.3 Visible, unread, and cleared

- **Visible:** `cleared_at` is null.
- **Unread:** both `read_at` and `cleared_at` are null.
- **Cleared:** hidden from lists and unread counts but retained in the table.

Clearing an unread item sets both `cleared_at` and `read_at` to the same current
time. There is no restore operation or cleared-item endpoint.

### 4.4 Notification kinds

| Kind | Typical emitter |
| --- | --- |
| `PROPOSAL_SUBMITTED` | Public submission and proposal intake |
| `PROPOSAL_ASSIGNED` | Proposal assignment |
| `PROPOSAL_FORWARDED` | Proposal forwarding |
| `PROPOSAL_REFERRED_TO_DIRECTION` | Referral to direction |
| `PROPOSAL_RETURNED_TO_STAFF` | Return from direction |
| `PROPOSAL_TAKEN_OVER` | Proposal takeover |
| `PROPOSAL_DOCUMENTS_SUBMITTED` | Requested-document submission |
| `PROPOSAL_CORRECTIONS_SUBMITTED` | Public correction submission |
| `MUSEUM_QUESTION_SUBMITTED` | New public museum question |
| `MUSEUM_QUESTION_FORWARDED` | Question forwarded to another permission |
| `MUSEUM_QUESTION_RESPONSE_OVERDUE` | Overdue-question task |
| `SCIENTIFIC_RETURN_CANDIDATES_FOUND` | Scientific-return monitoring |

Related resource types are `PROPOSAL`, `PROJECT`, and `MUSEUM_QUESTION`.

## 5. Authorisation and privacy

All notification HTTP endpoints call `require_staff`; `EXTERNAL` receives
`403`. The active permission can list, count, mark, or clear only its own items.

Marking another permission's known notification ID returns `403 ACCESS_DENIED`,
whereas an unknown ID returns `404 NOT_FOUND`. This distinction reveals whether
a guessed notification identifier exists.

List and mark-read responses resolve `triggered_by` into a principal containing
permission ID, group, user ID, name, and email address. The topbar uses the name
but does not display the returned email, so the API exposes more personal data
than the current interface needs.

Related-resource access is not validated by this context. Opening a notification
may still be rejected by the destination context if the current permission no
longer has access.

## 6. Functional requirements

### FR-001 — Create an unread notification

The Published Language exposes a dispatcher with `notify(...)` and
`notify_many(...)`. A new item has no read or clear timestamp and can include
optional actor, resource, label, and note metadata.

Creation has no standalone public HTTP endpoint. Emitting contexts obtain a
dispatcher bound to their database session and decide when the transaction is
committed.

The dispatcher does not verify that recipient, actor, or resource identifiers
exist. It also does not validate string lengths against persistence limits:
resource IDs allow 36 characters and labels allow 128 characters in the table.

### FR-002 — Deduplicate recipients within one fan-out call

`notify_many(...)` preserves first-seen order and creates at most one item per
permission identifier within that invocation. It performs sequential inserts.

There is no business-event identifier, idempotency key, unique database
constraint, or duplicate lookup. Repeating `notify` or `notify_many` for the
same event creates new rows. Delivery is therefore at-most-once only within one
in-memory recipient iterable, not across retries or concurrent requests.

### FR-003 — Let emitters suppress self-notification

The notification dispatcher does not compare `recipient_permission_id` with
`triggered_by`. Several proposal and museum-question routes explicitly avoid
notifying the acting permission, while system-originated events use a null
actor. Self-notification prevention is an emitter policy, not a notification
context invariant.

### FR-004 — List visible notifications

`GET /api/v1/notifications` accepts:

| Query parameter | Rule |
| --- | --- |
| `page` | Zero-based, default `0`, minimum `0` |
| `size` | Default `20`, range `1..100` |
| `unreadOnly` | Boolean, default `false` |

Items are restricted to the active permission, exclude cleared rows, and are
ordered by creation time then identifier, both descending. The response uses
the common camelCase pagination envelope.

There are no filters for notification kind, resource type, date, actor, or
related resource.

### FR-005 — Resolve triggering principals

The list use case collects distinct non-null triggering permission IDs from the
requested page and resolves each one once through `identity.public`. A missing
or removed actor is returned as null.

Resolution is deduplicated but sequential; a page with many distinct actors can
produce up to one identity query per actor in addition to the notification
queries.

### FR-006 — Count unread notifications

`GET /api/v1/notifications/unread-count` returns the number of visible rows for
the active permission whose `read_at` is null.

The Angular facade loads this count when a staff permission becomes active and
polls it every 45 seconds. The badge renders exact values from one through nine
and `9+` above that threshold.

### FR-007 — Mark one notification as read

`POST /api/v1/notifications/{notificationId}/read` sets `read_at` once and
returns the hydrated item. Repeating the call for the same recipient preserves
the original timestamp, making the transition idempotent.

The operation checks recipient ownership after loading the row. It does not
reject an already cleared item, although such an item is no longer list-visible.

In the topbar, selecting an item waits for mark-read to succeed before closing
the popover and navigating to its related resource.

### FR-008 — Mark all visible unread notifications as read

`POST /api/v1/notifications/read-all` atomically sets one current timestamp on
all visible unread rows for the active permission and returns the affected-row
count. Already read or cleared rows are excluded.

The Angular facade immediately assigns a client-generated timestamp to its
currently loaded items and sets the local unread count to zero. The exact server
timestamps appear after a reload.

### FR-009 — Clear all visible notifications

`POST /api/v1/notifications/clear-all` sets `cleared_at` on every visible row of
the active permission and marks previously unread rows as read. It returns the
number of hidden rows and does not affect another permission.

The operation is a soft hide, not deletion. It includes both read and unread
items, has no confirmation in the current topbar, and has no undo.

### FR-010 — Present recent notifications in Angular

The staff topbar popover:

- loads the first eight visible notifications when opened;
- displays generated copy, optional note, actor, resource label, and time;
- visually distinguishes unread items;
- marks an item read before following its route;
- supports mark-all-read and clear-all; and
- resets when the active permission changes.

There is no full notification-centre page, pagination control, unread-only UI,
manual refresh action, or visible error state. Only the count is refreshed by
the 45-second timer; the open list is not live-updated.

Navigation maps proposals, projects, and museum questions to frontend routes.
Items without a supported resource type or ID can still be marked read but do
not navigate.

### FR-011 — Coordinate email outside this context

Some emitting workflows also send email. They persist and commit the business
change and in-app notification first, then call their own email adapter. The
notification record does not track email attempt, provider message ID, success,
failure, or retry state.

## 7. HTTP surface and failure semantics

| Endpoint | Behaviour |
| --- | --- |
| `GET /api/v1/notifications` | Paginated visible list for the active permission |
| `GET /api/v1/notifications/unread-count` | Active permission's unread count |
| `POST /api/v1/notifications/{notificationId}/read` | Idempotently mark one owned item read |
| `POST /api/v1/notifications/read-all` | Mark all visible unread items read |
| `POST /api/v1/notifications/clear-all` | Hide all visible items |

| Situation | Result |
| --- | --- |
| Unauthenticated request | `401` through the shared authentication boundary |
| `EXTERNAL` caller | `403` |
| Existing item belongs to another permission | `403 ACCESS_DENIED` |
| Unknown notification ID | `404 NOT_FOUND` |
| Invalid page, size, or boolean query | `422` validation envelope |

## 8. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | Every notification is addressed to one permission, never directly to a user. |
| INV-002 | User-facing list, count, and bulk operations are scoped to the active permission. |
| INV-003 | A visible unread item has neither `read_at` nor `cleared_at`. |
| INV-004 | Marking an owned notification read more than once preserves its first read time. |
| INV-005 | Clearing hides rather than deletes and also removes the item from unread counts. |
| INV-006 | `notify_many` creates at most one item per recipient inside one call. |
| INV-007 | The emitting context owns recipient selection, self-notification policy, transaction commit, and any email. |

Recipient, actor, and resource IDs are plain strings without foreign keys.
Database integrity does not ensure that their referenced records still exist.

## 9. Acceptance and test traceability

| Behaviour | Representative automated evidence |
| --- | --- |
| Create an unread item | `test_use_cases.py::test_create_notification_persists_unread_item` |
| Deduplicate one fan-out call | `test_use_cases.py::test_create_notification_many_dedupes_recipients` |
| Resolve each actor once per page | `test_use_cases.py::test_list_notifications_dedupes_triggered_by_resolution` |
| Idempotent and recipient-scoped mark-read | `test_use_cases.py::test_mark_read_is_idempotent_and_scoped_to_recipient` |
| Permission-scoped read-all | `test_use_cases.py::test_mark_all_read_scopes_to_active_permission` |
| Permission-scoped soft clear | `test_use_cases.py::test_clear_all_hides_notifications_and_scopes_to_active_permission`, `test_repository_and_api.py::test_repo_clear_all_hides_active_permission` |
| Persistence and list/count/read routes | `test_repository_and_api.py::test_sqlalchemy_notification_repository_round_trip_and_mark_all_read`, `test_repository_and_api.py::test_notifications_routes_list_filter_count_and_mark_read` |
| HTTP isolation and external rejection | `test_repository_and_api.py::test_notification_routes_reject_other_recipient_and_external_callers` |
| Topbar copy, links, and clear behaviour | `app-topbar.component.spec.ts` |

Backend tests cover the notification context directly. The Angular API service
and facade currently have no dedicated unit tests; topbar tests exercise a
subset through a mock API.

## 10. Non-functional requirements

- **Architecture:** emitting contexts depend on `notifications.public`; direct
  table writes outside the context are not part of the contract.
- **Transactionality:** notification inserts participate in the emitter's
  database transaction when the supplied dispatcher uses the same session.
- **Polling:** unread count is eventually refreshed every 45 seconds while a
  staff permission is active; there is no push channel.
- **Retention:** clearing is permanent hiding at the API level, but the row is
  retained indefinitely unless an external maintenance policy removes it.
- **Performance:** list requires count plus page queries and up to one sequential
  identity resolution per distinct actor; fan-out inserts are sequential.
- **Accessibility:** the bell and notification rows are buttons with labels, and
  the popover is keyboard-operable through PrimeNG behaviour.

## 11. Known gaps and recommended changes

| Priority | Finding | Recommended change |
| --- | --- | --- |
| High | Notifications have no business-event identity or database uniqueness; retries and concurrent emitters can create duplicates. | Require an idempotency/event key and enforce recipient-plus-event uniqueness in persistence. |
| High | Self-notification suppression is inconsistently delegated to emitters despite being described previously as a global invariant. | Define the intended policy and enforce it centrally or provide a dispatcher option with tests for explicit exceptions. |
| High | Hosted workflows can commit successfully and then fail to send their companion email without retry/audit state. | Add an outbox and delivery state when email is a required consequence of the same business event. |
| Medium | Mark-read returns `403` for a foreign existing ID and `404` for an unknown ID, enabling existence probing. | Return the same opaque `404` for missing and non-owned notification IDs. |
| Medium | The API returns the triggering user's email although the topbar uses only their name. | Minimise the principal DTO for notifications or justify and authorise email disclosure. |
| Medium | Notification creation does not validate recipient/resource IDs or label lengths; oversized values fail at flush/commit. | Validate public dispatcher inputs against storage limits and add boundary tests. |
| Medium | Topbar operations and count polling have no error handling or visible retry state; a failed mark-read prevents navigation. | Catch failures in the facade, expose an error signal, allow retry, and decide whether navigation may proceed independently. |
| Medium | “Clear all” hides all history without confirmation or undo and there is no cleared-item view. | Add confirmation and either restore/history support or explicit retention language. |
| Medium | Only eight recent items are visible and there is no full notification centre despite a paginated API. | Add a notification page with pagination and unread/kind filters if workload exceeds the topbar MVP. |
| Medium | Actor resolution is an N+1 pattern across distinct actors and fan-out inserts are sequential. | Add a batch permission reader and bulk repository insert before notification volume grows. |
| Medium | No composite indexes match recipient, clear/read state, and newest-first ordering. | Measure production queries and add targeted partial/composite indexes if volume warrants it. |
| Low | Notes for scientific-return and direction notifications can appear twice because generated copy includes the note and the template renders it again. | Keep the note out of generated copy or suppress the separate note element for those kinds. |
| Low | Polling refreshes only the badge; an already open popover can remain stale. | Refresh the visible page with the count or adopt a push/event mechanism when needed. |
| Low | There are no direct frontend tests for the API service, facade polling, permission switching, or network failures. | Add focused service/facade tests with fake timers and error cases. |
| Low | The current flow diagram shows the dispatcher resolving recipients and sending email, but emitters select recipients and own email delivery. | Update the PlantUML sequence so Identity and email interactions originate from the emitting context. |

## 12. Traceability

| Element | Location |
| --- | --- |
| Notification entity and enums | `vitarerum-api/app/notifications/domain/` |
| Dispatcher and user-facing use cases | `vitarerum-api/app/notifications/application/` |
| SQLAlchemy mapping and repository | `vitarerum-api/app/notifications/infrastructure/` |
| HTTP API and identity hydration | `vitarerum-api/app/notifications/presentation/` |
| Published Language used by emitters | `vitarerum-api/app/notifications/public.py` |
| Emitting workflows | `vitarerum-api/app/public_submission/`, `app/use_of_collections/`, `app/museum_questions/`, and `app/scientific_return/` |
| Angular API, facade, and models | `vitarerum-ui/src/app/features/notifications/` |
| Angular topbar presentation | `vitarerum-ui/src/app/shared/layout/topbar/` |
| Backend tests | `vitarerum-api/test/notifications/` |
| Flow diagram | `docs/diagrams/notifications-flow.puml` and generated SVG |

## 13. Open product decisions

1. Which business events require both in-app and email delivery, and what retry
   guarantee is required for each channel?
2. Should self-notification always be suppressed, or are there event types where
   confirmation to the actor is useful?
3. How long must read and cleared notifications be retained, and must users be
   able to restore cleared items?
4. Is the eight-item topbar sufficient for the MVP, or is a searchable,
   paginated notification centre required?
5. Which notification metadata may include personal or sensitive case data?
6. Should clicking a notification navigate when marking it read fails?
