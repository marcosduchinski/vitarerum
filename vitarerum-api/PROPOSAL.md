# Identity & Proposal Setup

Step-by-step curl commands to seed the identity context and create proposals.
All commands assume the server is running at `http://localhost:8000`.

**Group IDs (seeded by `scripts/seed.sql`):**

| Group | ID |
|-------|-----|
| EXTERNAL | `grp-ext` |
| CURATORIAL | `grp-cur` |
| COLLECTIONS_MANAGEMENT | `grp-col` |
| DIRECTION | `grp-dir` |
| SYS_ADMIN | `grp-sys-admin` |

> **Bootstrap:** user and group administration calls below use `perm-sys-admin`,
> which is seeded by `scripts/seed.sql`. Proposal calls use an EXTERNAL permission,
> such as the seeded `perm-ext` or the `permissionId` returned when assigning Bruno
> to EXTERNAL in step 2.

---

## 1. Create users

These examples include `password` so the users can authenticate after their group
permissions are assigned in step 2.

```bash
# Curator 1
curl -s -X POST http://localhost:8000/api/v1/users \
  -H "X-Permission-Id: perm-sys-admin" \
  -H "Content-Type: application/json" \
  -d '{"name": "Carla Sousa", "email": "carla@museum.pt", "password": "password"}' | python3 -m json.tool

# Curator 2
curl -s -X POST http://localhost:8000/api/v1/users \
  -H "X-Permission-Id: perm-sys-admin" \
  -H "Content-Type: application/json" \
  -d '{"name": "Diogo Lopes", "email": "diogo@museum.pt", "password": "password"}' | python3 -m json.tool

# Collections management
curl -s -X POST http://localhost:8000/api/v1/users \
  -H "X-Permission-Id: perm-sys-admin" \
  -H "Content-Type: application/json" \
  -d '{"name": "Eva Rodrigues", "email": "eva@museum.pt", "password": "password"}' | python3 -m json.tool

# Direction
curl -s -X POST http://localhost:8000/api/v1/users \
  -H "X-Permission-Id: perm-sys-admin" \
  -H "Content-Type: application/json" \
  -d '{"name": "Fernando Costa", "email": "fernando@museum.pt", "password": "password"}' | python3 -m json.tool

# Researcher 2
curl -s -X POST http://localhost:8000/api/v1/users \
  -H "X-Permission-Id: perm-sys-admin" \
  -H "Content-Type: application/json" \
  -d '{"name": "Bruno Mendes", "email": "bruno@research.pt", "password": "password"}' | python3 -m json.tool
```

---

## 2. Assign users to groups

Replace `{userId}` with the `id` returned in step 1.
The response contains the `permissionId` — save these for subsequent calls.
A user cannot log in until they have at least one group permission.

```bash
# Carla → CURATORIAL
curl -s -X POST http://localhost:8000/api/v1/users/{carla-id}/groups/grp-cur \
  -H "X-Permission-Id: perm-sys-admin" | python3 -m json.tool

# Diogo → CURATORIAL
curl -s -X POST http://localhost:8000/api/v1/users/{diogo-id}/groups/grp-cur \
  -H "X-Permission-Id: perm-sys-admin" | python3 -m json.tool

# Eva → COLLECTIONS_MANAGEMENT
curl -s -X POST http://localhost:8000/api/v1/users/{eva-id}/groups/grp-col \
  -H "X-Permission-Id: perm-sys-admin" | python3 -m json.tool

# Fernando → DIRECTION
curl -s -X POST http://localhost:8000/api/v1/users/{fernando-id}/groups/grp-dir \
  -H "X-Permission-Id: perm-sys-admin" | python3 -m json.tool

# Bruno → EXTERNAL
curl -s -X POST http://localhost:8000/api/v1/users/{bruno-id}/groups/grp-ext \
  -H "X-Permission-Id: perm-sys-admin" | python3 -m json.tool
```

---

## 3. Create proposals

Uses `X-Permission-Id` of the researcher submitting the form.

```bash
# Proposal 1 — Alice, IN_SITU_VISIT
curl -s -X POST http://localhost:8000/api/v1/proposals \
  -H "X-Permission-Id: perm-ext" \
  -F "title=Study of 18th-century ceramics" \
  -F "intendedUse=IN_SITU_VISIT" \
  -F "purpose=Doctoral thesis on glazing techniques in Portuguese ceramics." \
  -F "beginDate=2026-07-01" \
  -F "endDate=2026-07-31" \
  -F "initialMessageSubject=Study of 18th-century ceramics" \
  -F "initialMessageBody=Dear team, I would like to request access to study the 18th-century ceramics collection for my doctoral thesis on glazing techniques." \
  -F "documents=@/path/to/support.pdf" | python3 -m json.tool

# Proposal 2 — Alice, EXHIBITION
curl -s -X POST http://localhost:8000/api/v1/proposals \
  -H "X-Permission-Id: perm-ext" \
  -F "title=Loan request for travelling exhibition" \
  -F "intendedUse=EXHIBITION" \
  -F "purpose=Temporary loan of three azulejo panels for a European travelling exhibition." \
  -F "beginDate=2026-09-01" \
  -F "endDate=2026-12-31" \
  -F "initialMessageSubject=Loan request for azulejo panels" \
  -F "initialMessageBody=We are organising a travelling exhibition on Portuguese tile art and would like to request a temporary loan of three azulejo panels." | python3 -m json.tool
```

Authenticated submissions use `multipart/form-data`. Name and e-mail are taken
from the logged-in permission; the persisted proposal response includes
`submissionChannel: "AUTHENTICATED"`. The public confirmation flow materialises
proposals with `submissionChannel: "PUBLIC"`.

---

## 4. Verify

```bash
# List all groups and their members
curl -s http://localhost:8000/api/v1/groups \
  -H "X-Permission-Id: perm-sys-admin" | python3 -m json.tool

curl -s http://localhost:8000/api/v1/groups/grp-cur/users \
  -H "X-Permission-Id: perm-sys-admin" | python3 -m json.tool

# List all proposals as a staff member (use Carla's permissionId from step 2)
curl -s "http://localhost:8000/api/v1/proposals?page=0&size=10" \
  -H "X-Permission-Id: {carla-permission-id}" | python3 -m json.tool

# Check a proposal's conversation (use proposalId from step 3)
curl -s http://localhost:8000/api/v1/proposals/{proposalId}/conversation \
  -H "X-Permission-Id: {carla-permission-id}" | python3 -m json.tool
```
