# SPEC-007 — Identity, authentication, and acting permission

| Field | Value |
| --- | --- |
| Identifier | SPEC-007 |
| Status | Implemented |
| Bounded context | `app/identity` (published language in `app/identity/public.py`) |
| Derived from | Identity domain, application services, SQLAlchemy repositories, authentication routes, shared actor resolution, Angular session/guards, configuration, and automated tests |
| Related specs | Protected HTTP workflows resolve an authenticated actor here; public endpoints, operator CLIs, and scheduled/worker entry points use their separately specified access boundaries |

## 1. Problem

The museum has internal staff with distinct roles and external requesters who
do not belong to the institution. A user may belong to more than one group,
and what that user may do depends on the role in which they are acting **for a
specific request**, not on the full set of roles they hold.

Inferring the acting role from the access token would choose on the user's
behalf and could silently select the most privileged role.

## 2. Goal

Authenticate users and establish an **actor** for each protected request: the
authenticated user plus the group in which that user is acting. The server
must validate that the permission selected by the client actually belongs to
the authenticated user.

The current implementation is safe only as a predominantly single-institution
model. Although actors now carry an institution ID, login and Angular role
selection cannot unambiguously choose the same role in two institutions; see
GAP-001.

## 3. Actors and architecture

| Actor | Capability |
| --- | --- |
| Anonymous visitor | Log in, request a password reset, or confirm a reset |
| Authenticated user | Act through one owned permission, change own password, and sign out locally |
| `EXTERNAL` | Use external workflows and, currently, read the global user/group directory |
| Internal staff | Use bounded-context capabilities authorised for the selected group |
| `SYS_ADMIN` | Administer users, memberships, and institutions |
| Calling bounded context | Provision an external requester through Identity's published language |

| DDD role | Element | Responsibility |
| --- | --- | --- |
| Entity | `User` | Credential owner, status, and password-change watermark |
| Entity | `Permission` | User-to-group membership and acting identity |
| Entity | `PasswordResetToken` | Expiring, single-use reset authorisation |
| Entity | `Institution` / `Group` | Organisational and role vocabulary |
| Application services | `AuthenticateUser`, password/reset and administration use cases | Orchestrate identity operations |
| Open Host Service | `app.identity.public` | Publish actors, permission views, and requester provisioning |
| Adapter | `get_caller_permission` | Convert bearer token and permission header into a validated actor |
| Adapters | bcrypt, JWT, SMTP, in-memory rate limiter, SQLAlchemy | Technical security and persistence |

Other bounded contexts may consume Identity only through
`app.identity.public`. The shared HTTP dependency resolves the published actor;
bounded contexts then apply their own group and resource-ownership rules.

## 4. Ubiquitous language

- **User**: a person with credentials. States: `ACTIVE`, `DISABLED`.
- **Group**: an institutional role: `EXTERNAL`, `CURATORIAL`,
  `COLLECTIONS_MANAGEMENT`, `DIRECTION`, or `SYS_ADMIN`.
- **Permission**: the association between a user and a group. The client sends
  its identifier to declare the role in which the user is acting.
- **Actor**: the validated permission-and-group pair resolved for one request.
- **Institution**: the entity to which groups belong.
- **External requester**: a user in the `EXTERNAL` group, provisioned by the
  system from a public submission.

---

## 5. Functional requirements

### FR-001 — Login is the only operation that establishes a session

`POST /api/v1/auth/login`, with an email address and password, returns an
`accessToken`, the user, all permissions held by that user, and the institution
resolved from the first hydrated permission returned by the repository.

The permission list is **never empty**: a user with no group membership cannot
log in, and the refusal is indistinguishable from invalid credentials.

The JWT carries only `sub`, `iat`, and `exp`; it does not carry the active role.
Permission order has no explicit sort, so the login institution and Angular
default role may be nondeterministic.

### FR-002 — Login refusals are indistinguishable

An incorrect password, an unknown email address, a disabled user, and a user
with no permissions all produce `401` with the same message. The system does
not disclose which email addresses are registered.

This guarantee applies to login. Password-reset request responses can reveal a
known account when email delivery fails; see GAP-004.

### FR-003 — Protected requests carry identity and acting permission

Every session-protected endpoint, including
`POST /api/v1/auth/change-password`, requires both headers:

```http
Authorization: Bearer <accessToken>
X-Permission-Id: <permissionId>
```

The following Identity endpoints do not require a session:

- `POST /api/v1/auth/login`;
- `POST /api/v1/auth/password-reset/request`;
- `POST /api/v1/auth/password-reset/confirm`.

Other bounded contexts define their own explicitly public entry points.

### FR-004 — Strict `401` and `403` semantics

| Situation | Status |
| --- | --- |
| Missing or malformed `Authorization` header | `401` |
| Invalid or expired token | `401` |
| Disabled user | `401` |
| Token issued before the latest password change | `401` |
| Missing `X-Permission-Id` | `403` |
| Unknown permission | `403` |
| Permission not owned by the authenticated user | `403` |
| Acting group not authorized for the operation | `403` |

`401` means that the caller's identity is no longer valid and ends the client
session. `403` means that the identity is valid, but the selected role may not
perform the operation.

### FR-005 — The acting group is never inferred from the token

The acting group is resolved exclusively from `X-Permission-Id`, which is
always checked against the user identified by the access token. No use case
infers an acting group from the token.

### FR-006 — Password changes invalidate older sessions

Changing or resetting a password updates `passwordChangedAt`. Tokens issued
before that instant are rejected with `401`.

The comparison truncates `passwordChangedAt` to whole seconds because the JWT
`iat` claim has one-second resolution. A token issued in the same second as the
password change remains valid; this supports the immediate login that follows
a password reset.

This also leaves a sub-second window in which an older token cannot be proven
to predate the change.

### FR-007 — One password policy

The same policy governs every flow that sets a password: user creation when a
password is supplied, own-password change, administrative reset, and
self-service reset. A password must contain between 5 and 128 characters and
must not be empty or consist only of whitespace. No flow may apply a weaker
policy.

### FR-008 — Change own password

`POST /api/v1/auth/change-password` requires the current password. An incorrect
current password and a weak new password are refused. Success returns `204`,
updates `passwordChangedAt`, and invalidates tokens issued before the change.

### FR-009 — Self-service reset without account enumeration

`POST /api/v1/auth/password-reset/request` returns `204` for both known and
unknown email addresses. No token is created for an unknown email address.

A new request invalidates every unused reset token previously issued for the
same user.

### FR-010 — Short-lived, single-use reset token

`POST /api/v1/auth/password-reset/confirm` consumes an opaque token and sets a
new password. The database stores only the token's SHA-256 hash. The token
expires after `PASSWORD_RESET_TOKEN_TTL_MINUTES` (60 minutes by default) and is
marked as used after successful confirmation.

Unknown, expired, and already-used tokens all produce the same opaque `404`.

The single-use check is sequential rather than atomic; concurrent confirmations
may both pass before either transaction commits. See GAP-005.

A `SYS_ADMIN` may also issue a reset token for a user through
`POST /api/v1/users/{userId}/password-reset`; the reset is completed through
the same public confirmation endpoint and policy.

### FR-011 — Dedicated rate limits

Password-reset requests and confirmations share the process-local
`ip:{remote_ip}` bucket. Requests additionally use a normalized-email bucket;
confirmations additionally use a token-hash bucket. Exceeding a limit returns
`429` with a `Retry-After` header.

Current limits are process-local sliding windows: 5 combined request/confirm
attempts per IP per hour,
3 requests per normalized email per day, and 10 confirmations per token hash
per hour. `Retry-After` is always 60 seconds. Limits reset on process restart
and are not shared across replicas.

### FR-012 — Secrets never enter logs or representations

The raw reset token exists only in the link sent by email. The email adapter
does not log it. The representation of a provisioned requester never exposes
the generated temporary password. Stored passwords are bcrypt hashes and are
never returned by an API.

### FR-013 — External requester provisioning

The context's published language provisions an `EXTERNAL` user from an email
address and display name. If that email already has an external permission,
the permission is reused rather than duplicated. For a newly created user, a
temporary password is generated, returned once to the calling context for
delivery, and stored only as a bcrypt hash. The temporary password permits
login.

Provisioning an existing user does not verify that the user is active before
returning an actor directly to the calling context; see GAP-006.

### FR-014 — User and group administration

Any authenticated actor, including `EXTERNAL`, may list users, read a user, and
list groups. This is the behavior currently implemented; it is not an
authorization guarantee for mutation.

These global responses expose names, email addresses, status, and hydrated
permissions. This is a privacy and institution-isolation gap; see GAP-002.

Only `SYS_ADMIN` may:

- create users;
- update a user's display name;
- disable or enable a user;
- issue an administrative password reset;
- assign or remove group membership;
- read a user's permissions or list the members of a group.

Updating the display name changes **only** that name. Creating a user may omit
the password; such a user cannot log in until a password is established.

### FR-015 — Protect the last active administrator

Users are disabled and enabled through
`POST /api/v1/users/{userId}/disable` and
`POST /api/v1/users/{userId}/enable`.

An operation that would disable the last active `SYS_ADMIN`, or remove that
user's `SYS_ADMIN` group membership, is refused with `409`. Once at least one
active system administrator exists, the application does not allow an
administrative operation to leave the system without one.

The count is global, not institution-scoped, and the read-then-write check has
no lock or serializable constraint; see GAP-007.

### FR-016 — Uniqueness

User email addresses are normalized by trimming surrounding whitespace and
converting them to lowercase before lookup and persistence. They are therefore
unique without case sensitivity. The same user-and-group permission cannot
exist more than once.

### FR-017 — Institutions

Institution CRUD is restricted to `SYS_ADMIN`. A duplicate institution name
returns `409`; deleting an institution that still owns groups returns `409`.
The institution list is paginated, and group representations include their
institution identifier.

Institution names are globally unique and case-sensitive. Group names have no
database uniqueness constraint, while `get_by_name` expects at most one result
globally. This cannot safely represent the same role in multiple institutions;
see GAP-001.

### FR-018 — Angular session and role selection

After login, the Angular service stores the response in a signal and in
`localStorage` under `vitarerum.session`, selecting the first permission's
group. The top bar offers a role selector when multiple group values exist.
Changing the role selects the first permission carrying that group and returns
the user to the dashboard.

The functional authentication interceptor attaches the bearer token and active
permission ID. A `401` outside public-auth requests clears local state and
redirects to login; `403` preserves the session. Successful password change or
reset also clears local state.

Stored JSON is cast without runtime schema or expiry validation. Keeping the
bearer token in `localStorage` exposes it to successful same-origin script
injection; see GAP-003. Client route guards are navigation aids, not a security
boundary. Most identity administration routes lack `sysAdminGuard`; backend
checks protect mutations, but direct navigation reaches globally readable user
routes.

---

## 6. Enforced invariants

| ID | Invariant |
| --- | --- |
| INV-001 | The acting group is always validated against the authenticated user |
| INV-002 | `401` is reserved for authentication failure; authorization failure is always `403` |
| INV-003 | Persisted passwords exist only as bcrypt hashes |
| INV-004 | Only a SHA-256 reset-token hash is persisted |
| INV-005 | Password and reset-token values are absent from user and permission representations |
| INV-006 | Sequential administration cannot disable or remove the sole active `SYS_ADMIN` |
| INV-007 | A token provably issued before the whole-second password-change watermark is rejected |
| INV-008 | Login failures do not disclose whether an email address is registered |

Single-use reset, last-administrator preservation, cross-institution selection,
and reset-request non-enumeration are not fully guaranteed under the current
concurrency and delivery model; the gaps below define those limits.

## 7. Acceptance evidence

### AC-001 — Authentication and indistinguishable refusals

Given an active user with at least one permission and valid credentials, login
returns that user and their permissions. Unknown email addresses, incorrect
passwords, disabled users, and users without permissions are all refused as
invalid credentials.

→ `test/identity/test_auth.py::test_authenticate_success_returns_user_and_permissions`,
`test/identity/test_auth.py::test_authenticate_wrong_password_raises`,
`test/identity/test_auth.py::test_authenticate_unknown_email_raises`,
`test/identity/test_auth.py::test_authenticate_user_without_permissions_raises`,
`test/identity/test_auth.py::test_authenticate_disabled_user_raises`

### AC-002 — Login HTTP contract

Given a valid login request, the API returns the token, user, flat group values,
and institution. Invalid credentials return `401` with the same message, while
an invalid request body returns the shared `422` error envelope.

→ `test/identity/test_auth.py::test_login_success_returns_token_user_and_flat_group`,
`test/identity/test_auth.py::test_login_wrong_password_is_401_with_message`,
`test/identity/test_auth.py::test_login_disabled_user_is_401_with_message`,
`test/identity/test_auth.py::test_login_unknown_email_is_401`,
`test/identity/test_auth.py::test_login_missing_password_is_422_with_errors`

### AC-003 — `401`/`403` boundary when resolving the actor

Given a protected request, missing or invalid bearer credentials return `401`;
a missing, unknown, or unowned acting permission returns `403`; a disabled user
returns `401`; and a valid owned permission resolves to an actor.

→ `test/identity/test_auth.py::test_caller_missing_authorization_is_401`,
`test/identity/test_auth.py::test_caller_malformed_token_is_401`,
`test/identity/test_auth.py::test_caller_valid_token_missing_permission_header_is_403`,
`test/identity/test_auth.py::test_caller_unknown_permission_is_403`,
`test/identity/test_auth.py::test_caller_permission_not_owned_is_403`,
`test/identity/test_auth.py::test_caller_disabled_user_is_401`,
`test/identity/test_auth.py::test_caller_valid_and_owned_returns_actor`

### AC-004 — Password changes invalidate older sessions

Given a password-change timestamp, a token issued before it is refused, while
a token issued after it or within the same second remains valid.

→ `test/identity/test_auth.py::test_caller_token_issued_before_password_change_is_401`,
`test/identity/test_auth.py::test_caller_token_issued_after_password_change_is_valid`,
`test/identity/test_auth.py::test_caller_token_issued_same_second_as_change_is_valid`

### AC-005 — Password policy and own-password change

Given an authenticated user, the correct current password and a compliant new
password update the hash and timestamp and return `204`. An incorrect current
password or weak new password returns `400`; an unauthenticated request returns
`401`.

→ `test/identity/test_auth.py::test_change_password_success_updates_hash_and_changed_at`,
`test/identity/test_auth.py::test_change_password_wrong_current_password_raises`,
`test/identity/test_auth.py::test_change_password_weak_new_password_raises`,
`test/identity/test_auth.py::test_change_password_api_success_returns_204`,
`test/identity/test_auth.py::test_change_password_api_wrong_current_is_400`,
`test/identity/test_auth.py::test_change_password_api_weak_new_password_is_400`,
`test/identity/test_auth.py::test_change_password_api_requires_authentication`

### AC-006 — Reset without enumeration and with opaque token errors

Given an unknown email address, requesting a reset creates no token and returns
the same response as a known address. Unknown, expired, and already-used tokens
produce the same opaque error.

→ `test/identity/test_password_reset.py::test_request_reset_unknown_email_returns_none_and_creates_no_token`,
`test/identity/test_password_reset.py::test_confirm_reset_used_token_raises_opaque_error`,
`test/identity/test_password_reset.py::test_confirm_reset_expired_token_raises_opaque_error`,
`test/identity/test_password_reset.py::test_confirm_reset_unknown_token_raises_opaque_error`,
`test/identity/test_password_reset.py::test_confirm_with_invalid_token_is_404`

### AC-007 — Single-use token, replacement, and rate limiting

Given a known user, a reset request creates a token; a later request invalidates
the previous unused token. Request and confirmation limits are enforced, and a
successfully consumed token is persisted as used.

→ `test/identity/test_password_reset.py::test_request_reset_known_email_creates_token_and_returns_raw_token`,
`test/identity/test_password_reset.py::test_request_reset_invalidates_previous_unused_token`,
`test/identity/test_password_reset.py::test_request_reset_respects_rate_limit`,
`test/identity/test_password_reset.py::test_confirm_reset_respects_rate_limit`,
`test/identity/test_password_reset_token_repository.py::test_save_marks_token_used`,
`test/identity/test_password_reset_token_repository.py::test_invalidate_active_for_user_marks_only_that_users_unused_tokens`

### AC-008 — Secrets remain outside logs and representations

Given a reset email or a provisioned requester, neither the raw reset token nor
the temporary password appears in logs or object representations.

→ `test/identity/test_email.py::test_logging_sender_never_logs_the_raw_reset_token`,
`test/identity/test_provision_external_requester.py::test_provisioned_requester_repr_does_not_expose_temporary_password`

### AC-009 — Idempotent external requester provisioning

Given a public requester, provisioning creates the missing user and external
permission, reuses an existing permission for the same email address, and
produces a temporary password that permits login for a new user.

→ `test/identity/test_provision_external_requester.py::test_provision_creates_user_and_external_permission_when_absent`,
`test/identity/test_provision_external_requester.py::test_provision_reuses_existing_permission_for_same_email`,
`test/identity/test_provision_external_requester.py::test_provisioned_temporary_password_allows_login`

### AC-010 — The last active administrator is protected

Given a single active `SYS_ADMIN`, attempting to disable that user is refused.

→ `test/identity/test_auth.py::test_disable_last_active_sys_admin_is_rejected`

Removing the last active administrator's group membership is implemented by
`RemoveUserFromGroup`, but has no direct acceptance test. This is a declared
test gap.

### AC-011 — Email and permission uniqueness

Given an existing user or permission, an email that differs only by case and a
duplicate user-and-group association are refused.

→ `test/identity/test_identity_uniqueness.py::test_duplicate_email_is_rejected_case_insensitively`,
`test/identity/test_identity_uniqueness.py::test_duplicate_permission_is_rejected`

### AC-012 — Institutions are restricted to `SYS_ADMIN`

Given an institution operation, a non-administrator is forbidden. Duplicate
names and deletion while groups remain return `409`; listing is paginated and
group responses identify their institution.

→ `test/identity/test_institutions_api.py::test_non_sysadmin_is_forbidden`,
`test/identity/test_institutions_api.py::test_create_duplicate_name_returns_409`,
`test/identity/test_institutions_api.py::test_delete_institution_with_groups_returns_409`,
`test/identity/test_institutions_api.py::test_list_institutions_is_paginated`,
`test/identity/test_institutions_api.py::test_groups_listing_includes_institution_id`

### AC-013 — Group-based authorization for user administration

Given an external actor, user creation and group assignment return `403`, while
user listing succeeds for both external and administrative actors.

→ `test/identity/test_auth.py::test_external_user_cannot_create_identity_user`,
`test/identity/test_auth.py::test_external_user_cannot_assign_identity_group`,
`test/identity/test_auth.py::test_external_user_can_list_identity_users`,
`test/identity/test_auth.py::test_administration_user_can_list_identity_users`

### AC-014 — Administrative password reset

Given an existing user, an administrative reset creates a new reset token for
that user without directly changing the password.

→ `test/identity/test_auth.py::test_admin_password_reset_mints_token_for_user`

### AC-015 — Angular session, headers, role switching, and expiry handling

The client persists and rehydrates the login session, follows role switches
when selecting `X-Permission-Id`, clears state on sign-out or protected-request
`401`, and does not clear it for public-auth `401` responses.

→ `identity.service.impl.spec.ts::persists the session to storage and rehydrates a fresh instance`,
`::returns the active group permission id and follows group switches`,
`auth.interceptor.spec.ts::adds Authorization and X-Permission-Id for the active group`,
`session-expired.interceptor.spec.ts::signs out and navigates to /login on 401`,
`app-topbar.component.spec.ts::switches the active group and permission before navigating to the dashboard`

## 8. Known implementation gaps

### GAP-001 — Acting context is not multi-institution safe

**Severity: critical.** Login returns one institution chosen from an unordered
permission list, while each permission exposes only its ID and group name. The
Angular session selects by group name and cannot distinguish the same role in
two institutions. `GroupRepository.get_by_name` also assumes one global match
although the table does not enforce that invariant.

**Required change:** make the active permission—not the role enum—the client
selection unit; include institution on every login permission; scope group
lookup and uniqueness by institution; and test users spanning institutions.

### GAP-002 — Global user directory is exposed to every authenticated user

**Severity: critical.** `EXTERNAL` users can list and read all users, including
email, status, and permission membership. Queries are not institution-scoped.

**Required change:** restrict directory reads to explicit internal/admin roles,
apply institution ownership, minimise returned personal data, and add negative
cross-role and cross-institution tests.

### GAP-003 — Bearer tokens are stored in `localStorage`

**Severity: high.** Any successful same-origin script injection can read and
exfiltrate the 12-hour access token. Rehydrated JSON is not runtime-validated,
and expiry is detected only after a server `401`.

**Required change:** adopt a threat-modelled session design, preferably secure
`HttpOnly`, `Secure`, appropriately `SameSite` cookies with CSRF controls, or
short-lived memory-held access tokens plus rotating refresh protection. Enforce
a strong CSP regardless.

### GAP-004 — Reset requests can enumerate accounts on SMTP failure

**Severity: high.** Unknown emails return `204` without delivery. A known email
whose SMTP send fails returns `502`, revealing account existence under that
failure condition; response timing can also differ.

**Required change:** queue delivery behind a generic response, keep public
status/timing independent of account existence, and monitor delivery privately.

### GAP-005 — Reset-token consumption is race-prone

**Severity: high.** Concurrent confirmations can read the same active token,
both change the password, and both mark it used because consumption is not a
conditional database operation or locked transaction.

**Required change:** atomically claim the unused, unexpired token and add a
PostgreSQL concurrency test in which exactly one confirmation succeeds.

### GAP-006 — Provisioning can return an actor for a disabled user

**Severity: high.** Reusing an existing account does not check `UserStatus`.
The published use case returns an `EXTERNAL` actor directly even though normal
actor resolution would reject the disabled user.

**Required change:** reject disabled accounts uniformly or define an explicit,
audited reactivation flow; never bypass the status check through provisioning.

### GAP-007 — Last-administrator protection is non-atomic and global

**Severity: high.** Concurrent disable/removal transactions can both observe
more than one active administrator and leave none. The count is global rather
than institution-scoped, and membership removal lacks a direct acceptance test.

**Required change:** enforce the invariant under an appropriate database lock
or serializable transaction, define institution semantics, and add disable and
membership-removal concurrency tests.

### GAP-008 — Reset rate limiting is process-local

**Severity: high.** Buckets reset on restart and are independent across
replicas. Client IP is taken from the framework request peer and may represent
a reverse proxy unless trusted forwarding is configured. `Retry-After` does not
reflect the remaining window.

**Required change:** use a shared atomic rate-limit store, define trusted-proxy
handling, return an accurate retry delay, and monitor abuse without logging
secrets. Decide whether intake should share the confirmation IP bucket: the
current shared bucket lets reset requests exhaust the allowance needed to use
an already issued link. Existing rate-limit tests do not establish independent
request/confirmation budgets.

### GAP-009 — Access-token lifecycle has no explicit revocation or refresh

**Severity: medium.** Sign-out is client-only; a copied token remains valid
until expiry unless the password changes or the user is disabled. Tokens have
no issuer, audience, JWT ID, or server-side session record. Whole-second `iat`
also leaves a sub-second invalidation ambiguity.

**Required change:** define issuer/audience, shorten access lifetime, introduce
rotating revocable sessions where required, and document key rotation.

### GAP-010 — Password policy is too weak for privileged accounts

**Severity: high.** Five characters is insufficient for administrative access,
and the policy has no compromised-password screening or adaptive controls.

**Required change:** adopt a modern length-oriented policy, prevent known
compromised passwords, support password managers, and consider phishing-
resistant MFA for privileged groups.

### GAP-011 — Post-commit email failures produce ambiguous outcomes

**Severity: medium.** Password changes and token issuance commit before email.
An SMTP failure can return `500`/`502` even though the password changed or old
reset links were invalidated, inviting unsafe retries and confusing users.

**Required change:** use a transactional outbox and make command success
independent from asynchronous notification delivery.

### GAP-012 — Identity administration validation and client guards are uneven

**Severity: medium.** Request schemas accept plain unbounded strings rather
than validated email/name/contact types. Most `/p/admin` routes lack an admin
guard, although backend mutation checks remain authoritative.

**Required change:** add bounded normalized schemas, align route guards for UX,
and retain server authorization as the security boundary.

## 9. Non-functional requirements

- **Secure configuration**: outside local and test environments, `JWT_SECRET`
  must differ from the development default and contain at least 32 bytes; CORS
  must not allow the wildcard origin.
- **Access-token lifetime**: `ACCESS_TOKEN_TTL_MINUTES`, 12 hours by default.
- **Context boundary**: other bounded contexts use Identity only through
  `app.identity.public`.
- **Server authority**: Angular guards and menus improve navigation but never
  replace backend permission and ownership checks.
- **Personal-data minimisation**: identity responses should expose only the
  user and permission attributes required by the caller's task.
- **Failure safety**: committed credential changes and email-delivery status
  must be distinguishable to operators without leaking account existence.

## 10. Traceability

| Element | Location |
| --- | --- |
| Domain model (FR-006, FR-010) | `app/identity/domain/models.py`, `domain/enums.py` |
| Password policy (FR-007) | `app/identity/application/password_policy.py` |
| Use cases (FR-001, FR-008–FR-017) | `app/identity/application/use_cases.py` |
| Actor resolution (FR-003–FR-006) | `app/shared/dependencies.py` |
| Hashing, tokens, email, and rate limiting (FR-010–FR-012) | `app/identity/infrastructure/{security,email,rate_limiter}.py` |
| Published language (FR-013) | `app/identity/public.py` |
| Angular session and headers (FR-003–FR-006) | `vitarerum-ui/src/app/core/auth/` |
| Angular login, reset, password change, and role selector | `vitarerum-ui/src/app/features/auth/`, `features/account/change-password/`, `shared/layout/topbar/` |
| Angular administration | `vitarerum-ui/src/app/features/admin/` |
| Public API contract | OpenAPI schema at `/openapi.json`; cross-cutting rules in `docs/api_contracts/README.md` |

## 11. Open product decisions

1. Is the current minimum password length of five characters appropriate for
   the installation's risk profile?
2. Should access tokens support explicit revocation, in addition to
   invalidation through password changes?
3. The domain anticipates multiple institutions but does not exercise them.
   Which actor-resolution and administration rules must change when more than
   one institution is active?
4. Should `EXTERNAL` actors be allowed to list and read all identity users, as
   the current implementation and tests permit, or should those reads be
   restricted to internal roles?
5. Is local bearer-token storage an accepted MVP risk, or must the session move
   to an `HttpOnly` cookie/rotating-token design before production use?
6. Must system-administrator availability be guaranteed globally or once per
   institution?
