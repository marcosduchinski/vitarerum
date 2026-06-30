# Identity context

All paths are relative to the configured API base URL and the `/api/v1` prefix
(e.g. `http://127.0.0.1:8000/api/v1`). Content type is `application/json` unless noted.

---

## Authentication

`POST /auth/login` is the **only endpoint that establishes a session**. Every other
endpoint in this and every other context is protected and requires the headers described
in [Authenticated requests](#authenticated-requests).

### `POST /auth/login`

**Description** — Authenticate a user by email + password and return an access token plus
the principal's identity and group permissions.

**Request body**
```json
{
  "email": "alice@ext.example.com",
  "password": "string"
}
```

**Response `200 OK`**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": "uuid",
    "email": "alice@ext.example.com",
    "displayName": "Alice Ferreira"
  },
  "permissions": [
    { "permissionId": "uuid", "group": "COLLECTIONS_MANAGEMENT" },
    { "permissionId": "uuid", "group": "CURATORIAL" }
  ],
  "institution": { "id": "uuid", "name": "MUHNAC" }
}
```

`accessToken`, `user`, and `permissions` are required and `permissions` is **non-empty** —
a user with no group membership cannot log in (treated as invalid credentials).

`institution` is the institution the principal acts within, resolved at login via their
group (`Group → institutionId → Institution`). It is **nullable** — if the acting group's
institution cannot be resolved it is omitted/`null` — so clients must treat it as optional.
Today the system is single-institution, so every group resolves to the same one. Clients
use this to display the active institution (e.g. in the top bar) without a separate request.

> ⚠️ **`group` is a flat enum string here, not an object.** This matches the embedded
> `PermissionDetail` shape returned by the read endpoints (`GET /users`,
> `GET /users/{user_id}`, and `GET /users/{user_id}/permissions`). The only current
> identity response that embeds a group object is `POST /users/{user_id}/groups/{group_id}`,
> which returns `group` as `{ "id", "name" }`.

Client behaviour driven by this response:
- `availableGroups` = `permissions.map(p => p.group)`.
- The active group defaults to `permissions[0].group`; the user may switch among
  `availableGroups`.
- The **active permission id** is the `permissionId` whose `group` equals the active group;
  it is sent as `X-Permission-Id` on every subsequent request.

**Response `401 Unauthorized`** — invalid credentials. The login page shows the failure
and does **not** redirect (a `401` from `/auth/login` is exempt from the session-expiry
handling below).
```json
{ "message": "Invalid email or password" }
```

**Response `422 Unprocessable Entity`** — malformed request.
```json
{ "message": "Validation failed", "errors": [ { "field": "email", "message": "required" } ] }
```

---

## Authenticated requests

After login the client attaches these headers to **all** requests to every other endpoint:

```
Authorization   : Bearer <accessToken>
X-Permission-Id : <active permission id>
```

The backend, on every protected endpoint:

1. **Authenticates** the `Authorization: Bearer` token (a signed JWT). A missing,
   malformed, or expired token is rejected with **`401`**.
2. **Authorizes against `X-Permission-Id`** — the permission (user + group) the request
   acts as. The backend verifies the permission id **belongs to the authenticated user**;
   a mismatch (or unknown/missing permission id) is rejected with **`403`**.

`X-Permission-Id` changes when the user switches active group, so the same token may arrive
paired with different permission ids over a session. It is the authoritative "acting role"
for each request; the group is never inferred from the token alone.

### Session expiry semantics

- A `401` on **any endpoint except `/auth/login`** means the session is expired/invalid:
  the client clears the local session and redirects to `/login`.
- The backend therefore returns **`401` only for authentication failure** (bad/expired
  token) and **`403` for authorization failure** ("authenticated but not allowed"), which
  does **not** log the user out.

---

### Bootstrap

User, group, and institution **administration** endpoints — `POST /users`,
`POST`/`DELETE /users/{user_id}/groups/{group_id}`,
`GET /users/{user_id}/permissions`, `GET /groups/{group_id}/users`, and all
`/institutions` endpoints — require a caller permission in the `SYS_ADMIN` group. The
**read** endpoints `GET /users`, `GET /users/{user_id}`, and `GET /groups` are open to any
authenticated caller (no `SYS_ADMIN` requirement). A clean database therefore needs one
out-of-band bootstrap step after migrations: run `scripts/seed.sql` to create the default
institution, the fixed groups (each linked to that institution via `institution_id`), and
an initial `SYS_ADMIN` permission (`perm-sys-admin`) for local development and smoke
testing.

---

### `POST /users`

**Description** — Create a new user. Returns the created user with an empty `permissions`
list (groups are assigned separately via `POST /users/{user_id}/groups/{group_id}`).

**Request body**
```json
{
  "name": "string",
  "email": "string",
  "password": "string"
}
```

`password` is optional. When provided it is hashed (bcrypt); a user created without one
has no usable password until set. The password is never returned in any response. Login
also requires at least one group permission, so a newly created user can authenticate
only after `POST /users/{user_id}/groups/{group_id}` assigns them to a group.

**Response `201 Created`**
```json
{
  "id": "uuid",
  "name": "string",
  "email": "string",
  "permissions": []
}
```

Emails are normalized (trimmed + lowercased) and unique. A duplicate returns:

**Response `409 Conflict`**
```json
{
  "error": "EMAIL_ALREADY_EXISTS",
  "message": "A user with this email already exists"
}
```

---

### `GET /users`

**Description** — List all users, optionally filtered by group. Open to any
authenticated caller (no `SYS_ADMIN` requirement).

**Query parameters**
```
group_id   : UUID     (optional) filter by group
search     : String   (optional) filter by name or email
page       : Integer  (default 0)
size       : Integer  (default 20)
```

`page` is zero-based. `size` must be between 1 and 100.

**Response `200 OK`**
```json
{
  "content": [
    {
      "id": "uuid",
      "name": "string",
      "email": "string",
      "permissions": [
        {
          "permissionId": "uuid",
          "user": {
            "id": "uuid",
            "name": "string",
            "email": "string"
          },
          "group": "CURATORIAL"
        }
      ]
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 45,
  "totalPages": 3
}
```

---

### `GET /users/{user_id}`

**Description** — Get full detail of a specific user including all their group
permissions. Open to any authenticated caller (no `SYS_ADMIN` requirement).

**Path parameters**
```
user_id : UUID (required)
```

**Response `200 OK`**
```json
{
  "id": "uuid",
  "name": "string",
  "email": "string",
  "permissions": [
    {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "COLLECTIONS_MANAGEMENT"
    },
    {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "CURATORIAL"
    }
  ]
}
```

**Response `404 Not Found`**
```json
{
  "error": "USER_NOT_FOUND",
  "message": "No user found with id uuid"
}
```

---

### `POST /users/{user_id}/groups/{group_id}`

**Description** — Assign a user to a group, creating a new `Permission`. Idempotent — if the assignment already exists, returns the existing permission.

**Path parameters**
```
user_id  : UUID (required)
group_id : UUID (required)
```

**Request body** — none required.

**Response `201 Created`**
```json
{
  "permissionId": "uuid",
  "user": {
    "id": "uuid",
    "name": "string",
    "email": "string"
  },
  "group": {
    "id": "uuid",
    "name": "DIRECTION"
  }
}
```

Idempotent — if the assignment already exists the existing permission is returned (also
with `201 Created`). A `(user_id, group_id)` pair is unique; in the rare case a concurrent
request wins the race, the loser receives:

**Response `409 Conflict`**
```json
{
  "error": "PERMISSION_ALREADY_EXISTS",
  "message": "User is already assigned to this group"
}
```

**Response `404 Not Found`**
```json
{
  "error": "USER_NOT_FOUND | GROUP_NOT_FOUND",
  "message": "string"
}
```

---

### `DELETE /users/{user_id}/groups/{group_id}`

**Description** — Remove a user from a group, revoking the corresponding `Permission`.

**Path parameters**
```
user_id  : UUID (required)
group_id : UUID (required)
```

**Response `204 No Content`**

**Response `404 Not Found`**
```json
{
  "error": "PERMISSION_NOT_FOUND",
  "message": "User uuid is not a member of group uuid"
}
```

---

### `GET /users/{user_id}/permissions`

**Description** — List all permissions for a specific user — every group they belong to and the corresponding permission identity.

**Path parameters**
```
user_id : UUID (required)
```

Requires `SYS_ADMIN`. The endpoint lists permissions by `user_id`; it does not currently
return `404` for an unknown user id, so an unknown user with no permissions is returned as
an empty list.

**Response `200 OK`**
```json
{
  "userId": "uuid",
  "permissions": [
    {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      },
      "group": "EXTERNAL"
    }
  ]
}
```

---

### `GET /groups`

**Description** — List all groups. Since groups are defined by the `GroupName` enum they
are fixed — this endpoint returns the institutional groups, their IDs, and the institution
each belongs to (`institutionId`). Open to any authenticated caller (no `SYS_ADMIN`
requirement).

**Response `200 OK`**
```json
{
  "groups": [
    {
      "id": "uuid",
      "name": "EXTERNAL",
      "institutionId": "uuid"
    },
    {
      "id": "uuid",
      "name": "CURATORIAL",
      "institutionId": "uuid"
    },
    {
      "id": "uuid",
      "name": "COLLECTIONS_MANAGEMENT",
      "institutionId": "uuid"
    },
    {
      "id": "uuid",
      "name": "DIRECTION",
      "institutionId": "uuid"
    },
    {
      "id": "uuid",
      "name": "SYS_ADMIN",
      "institutionId": "uuid"
    }
  ]
}
```

---

### `GET /groups/{group_id}/users`

**Description** — List all users belonging to a specific group, with their permission for that group.

**Path parameters**
```
group_id : UUID (required)
```

**Query parameters**
```
page : Integer (default 0)
size : Integer (default 20)
```

Requires `SYS_ADMIN`. `page` is zero-based. `size` must be between 1 and 100.

**Response `200 OK`**
```json
{
  "group": {
    "id": "uuid",
    "name": "CURATORIAL",
    "institutionId": "uuid"
  },
  "content": [
    {
      "permissionId": "uuid",
      "user": {
        "id": "uuid",
        "name": "string",
        "email": "string"
      }
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 5,
  "totalPages": 1
}
```

**Response `404 Not Found`**
```json
{
  "error": "GROUP_NOT_FOUND",
  "message": "No group found with id uuid"
}
```

---

## Institutions

An `Institution` is the organisation a `Group` belongs to (`Group → institutionId →
Institution`). All `/institutions` endpoints require a caller permission in the `SYS_ADMIN`
group. The institution payload is `{ id, name, email, address, phone }`; `name` is required
and unique, the other fields default to an empty string.

### `POST /institutions`

**Description** — Create an institution.

**Request body**
```json
{
  "name": "string",
  "email": "string",
  "address": "string",
  "phone": "string"
}
```

`name` is required; `email`, `address`, and `phone` are optional (default `""`).

**Response `201 Created`**
```json
{
  "id": "uuid",
  "name": "string",
  "email": "string",
  "address": "string",
  "phone": "string"
}
```

**Response `409 Conflict`** — name already in use.
```json
{
  "error": "INSTITUTION_NAME_ALREADY_EXISTS",
  "message": "An institution with this name already exists"
}
```

---

### `GET /institutions`

**Description** — List institutions, ordered by name.

**Query parameters**
```
page : Integer (default 0)
size : Integer (default 20)
```

`page` is zero-based. `size` must be between 1 and 100.

**Response `200 OK`**
```json
{
  "content": [
    {
      "id": "uuid",
      "name": "string",
      "email": "string",
      "address": "string",
      "phone": "string"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

---

### `GET /institutions/{institution_id}`

**Description** — Get a single institution.

**Path parameters**
```
institution_id : UUID (required)
```

**Response `200 OK`**
```json
{
  "id": "uuid",
  "name": "string",
  "email": "string",
  "address": "string",
  "phone": "string"
}
```

**Response `404 Not Found`**
```json
{
  "error": "INSTITUTION_NOT_FOUND",
  "message": "No institution found with id uuid"
}
```

---

### `PUT /institutions/{institution_id}`

**Description** — Replace an institution's editable fields. The request shape and
constraints match `POST /institutions` (`name` required and unique).

**Path parameters**
```
institution_id : UUID (required)
```

**Request body** — same as `POST /institutions`.

**Response `200 OK`** — the updated institution (same shape as `GET /institutions/{id}`).

**Response `404 Not Found`** — `INSTITUTION_NOT_FOUND`.

**Response `409 Conflict`** — `INSTITUTION_NAME_ALREADY_EXISTS`.

---

### `DELETE /institutions/{institution_id}`

**Description** — Delete an institution. Blocked while the institution still owns groups
(an institution can only be removed once no group references it).

**Path parameters**
```
institution_id : UUID (required)
```

**Response `204 No Content`**

**Response `404 Not Found`**
```json
{
  "error": "INSTITUTION_NOT_FOUND",
  "message": "No institution found with id uuid"
}
```

**Response `409 Conflict`** — the institution still owns one or more groups.
```json
{
  "error": "INSTITUTION_IN_USE",
  "message": "Institution uuid still owns groups"
}
```

---

A few conventions applied consistently across all contracts:

**IDs are UUIDs** throughout, matching the model. **Enum values are returned as strings** (`"CURATORIAL"` not `1`) for readability. **The embedded permission shape (`PermissionDetail`)** used across all contexts is `{ "permissionId", "user": { "id", "name", "email" }, "group": "<GROUP_NAME>" }` — the group is a flat enum string, not a nested object. The one exception is the `POST /users/{user_id}/groups/{group_id}` response, which returns the group as a nested `{ "id", "name" }` object. **Group objects** elsewhere — the `GET /groups` list entries and the `group` envelope of `GET /groups/{group_id}/users` — are `{ "id", "name", "institutionId" }`; note the assign response's nested group is the only group object that omits `institutionId`. **Pagination** follows a consistent envelope with `content`, `page`, `size`, `totalElements`, and `totalPages`.

**Authentication** — except for `POST /auth/login`, every endpoint here and in the other contexts requires `Authorization: Bearer <accessToken>` and `X-Permission-Id: <permission id>` headers; see [Authenticated requests](#authenticated-requests). `401` is reserved for authentication failure (and logs the client out); `403` for authorization failure.

**Error responses** always carry a human-readable `message`. Where applicable they also include a machine-readable `error` code (e.g. `USER_NOT_FOUND`) and, for `422` validation failures, an `errors` array of `{ field, message }` (the alternative `fieldErrors` object map is also accepted by the client). The `error` code is a backend convenience the frontend ignores.
