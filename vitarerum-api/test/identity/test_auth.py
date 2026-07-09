from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient

from app.database import get_async_session
from app.identity.application.password_policy import WeakPassword
from app.identity.application.ports import UserFilters
from app.identity.application.read_models import Actor
from app.identity.application.use_cases import (
    AuthenticateUser,
    ChangeOwnPassword,
    IncorrectCurrentPassword,
    InvalidCredentials,
)
from app.identity.domain.enums import GroupName
from app.identity.domain.models import (
    Group,
    GroupId,
    InstitutionId,
    Permission,
    PermissionId,
    User,
    UserId,
)
from app.identity.infrastructure import security
from app.identity.infrastructure.models import (
    GroupRecord,
    InstitutionRecord,
    PermissionRecord,
    UserRecord,
)
from app.identity.infrastructure.security import (
    BcryptPasswordHasher,
    TokenError,
    create_access_token,
    decode_access_token,
)
from app.main import app
from app.shared.dependencies import get_caller_permission

# ── doubles ───────────────────────────────────────────────────────────────────


class PlainHasher:
    """Fast, deterministic stand-in for bcrypt in use-case unit tests."""

    def hash(self, plain: str) -> str:
        return f"hashed:{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed:{plain}"


class InMemoryUserRepository:
    def __init__(self, users: list[User]) -> None:
        self._by_email = {u.email: u for u in users}

    async def add(self, user: User) -> None:
        self._by_email[user.email] = user

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: UserId) -> User | None:
        return next((u for u in self._by_email.values() if u.id == user_id), None)

    async def list(
        self, filters: UserFilters, page: int, size: int
    ) -> tuple[list[User], int]:
        users = list(self._by_email.values())
        return users, len(users)

    async def update(self, user: User) -> None:
        self._by_email[user.email] = user


class FixedClock:
    def __init__(self, when: datetime) -> None:
        self._when = when

    def now(self) -> datetime:
        return self._when


class InMemoryPermissionRepository:
    def __init__(self, by_user: dict[str, list[Permission]]) -> None:
        self._by_user = by_user

    async def add(self, permission: Permission) -> None:
        self._by_user.setdefault(permission.user_id, []).append(permission)

    async def get_by_user_and_group(
        self, user_id: UserId, group_id: GroupId
    ) -> Permission | None:
        return next(
            (p for p in self._by_user.get(user_id, []) if p.group_id == group_id), None
        )

    async def get_by_user_id(self, user_id: UserId) -> list[Permission]:
        return self._by_user.get(user_id, [])

    async def get_by_group_id(
        self, group_id: GroupId, page: int, size: int
    ) -> tuple[list[Permission], int]:
        perms = [
            p
            for perms in self._by_user.values()
            for p in perms
            if p.group_id == group_id
        ]
        return perms, len(perms)

    async def delete(self, permission_id: PermissionId) -> None:
        for perms in self._by_user.values():
            perms[:] = [p for p in perms if p.id != permission_id]


def _user(password_hash: str) -> User:
    return User(
        id=UserId("u1"),
        name="Alice Ferreira",
        email="alice@x.org",
        password_hash=password_hash,
    )


def _perm(user: User, group: GroupName) -> Permission:
    return Permission(
        id=PermissionId("perm-1"),
        user_id=UserId("u1"),
        group_id=GroupId("g1"),
        user=user,
        group=Group(
            id=GroupId("g1"), name=group, institution_id=InstitutionId("inst-1")
        ),
    )


# ── AuthenticateUser (login business logic) ───────────────────────────────────


async def test_authenticate_success_returns_user_and_permissions() -> None:
    hasher = PlainHasher()
    user = _user(hasher.hash("secret"))
    perms = [_perm(user, GroupName.CURATORIAL)]
    uc = AuthenticateUser(
        InMemoryUserRepository([user]),
        InMemoryPermissionRepository({UserId("u1"): perms}),
        hasher,
    )

    got_user, got_perms = await uc.execute("alice@x.org", "secret")

    assert got_user.id == "u1"
    assert [p.group.name for p in got_perms] == [GroupName.CURATORIAL]


async def test_authenticate_wrong_password_raises() -> None:
    hasher = PlainHasher()
    user = _user(hasher.hash("secret"))
    perms = [_perm(user, GroupName.CURATORIAL)]
    uc = AuthenticateUser(
        InMemoryUserRepository([user]),
        InMemoryPermissionRepository({UserId("u1"): perms}),
        hasher,
    )

    with pytest.raises(InvalidCredentials):
        await uc.execute("alice@x.org", "wrong")


async def test_authenticate_unknown_email_raises() -> None:
    uc = AuthenticateUser(
        InMemoryUserRepository([]),
        InMemoryPermissionRepository({}),
        PlainHasher(),
    )

    with pytest.raises(InvalidCredentials):
        await uc.execute("nobody@x.org", "secret")


async def test_authenticate_user_without_permissions_raises() -> None:
    hasher = PlainHasher()
    user = _user(hasher.hash("secret"))
    uc = AuthenticateUser(
        InMemoryUserRepository([user]),
        InMemoryPermissionRepository({UserId("u1"): []}),
        hasher,
    )

    with pytest.raises(InvalidCredentials):
        await uc.execute("alice@x.org", "secret")


# ── ChangeOwnPassword ──────────────────────────────────────────────────────────


async def test_change_password_success_updates_hash_and_changed_at() -> None:
    hasher = PlainHasher()
    user = _user(hasher.hash("old-password"))
    repo = InMemoryUserRepository([user])
    changed_at = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
    uc = ChangeOwnPassword(repo, hasher, FixedClock(changed_at))

    updated = await uc.execute(
        email="alice@x.org",
        current_password="old-password",
        new_password="a-strong-new-password",
    )

    assert hasher.verify("a-strong-new-password", updated.password_hash)
    assert updated.password_changed_at == changed_at
    stored = await repo.get_by_email("alice@x.org")
    assert stored is not None
    assert stored.password_hash == updated.password_hash


async def test_change_password_wrong_current_password_raises() -> None:
    hasher = PlainHasher()
    user = _user(hasher.hash("old-password"))
    uc = ChangeOwnPassword(
        InMemoryUserRepository([user]), hasher, FixedClock(datetime.now(UTC))
    )

    with pytest.raises(IncorrectCurrentPassword):
        await uc.execute(
            email="alice@x.org",
            current_password="wrong",
            new_password="a-strong-new-password",
        )


async def test_change_password_weak_new_password_raises() -> None:
    hasher = PlainHasher()
    user = _user(hasher.hash("old-password"))
    uc = ChangeOwnPassword(
        InMemoryUserRepository([user]), hasher, FixedClock(datetime.now(UTC))
    )

    with pytest.raises(WeakPassword):
        await uc.execute(
            email="alice@x.org",
            current_password="old-password",
            new_password="short",
        )


# ── get_caller_permission (401 auth vs 403 authz) ─────────────────────────────


def _perm_record(
    user_id: str,
    group: GroupName,
    password_changed_at: datetime | None = None,
) -> PermissionRecord:
    record = PermissionRecord(id="perm-1", user_id=user_id, group_id="g1")
    record.user = UserRecord(
        id=user_id,
        name="Alice",
        email="a@x.org",
        password_hash="",
        password_changed_at=password_changed_at,
    )
    record.group = GroupRecord(id="g1", name=group)
    return record


class FakeSession:
    def __init__(self, record: PermissionRecord | None) -> None:
        self._record = record

    async def get(self, model, pk, options=None):  # noqa: ANN001
        return self._record


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    """The credentials object the HTTPBearer scheme yields for a valid header."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_caller_missing_authorization_is_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_caller_permission(
            FakeSession(None), credentials=None, x_permission_id="perm-1"
        )
    assert exc.value.status_code == 401


async def test_caller_malformed_token_is_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_caller_permission(
            FakeSession(None),
            credentials=_bearer("nonsense"),
            x_permission_id="perm-1",
        )
    assert exc.value.status_code == 401


async def test_caller_valid_token_missing_permission_header_is_403() -> None:
    credentials = _bearer(create_access_token("u1"))
    with pytest.raises(HTTPException) as exc:
        await get_caller_permission(
            FakeSession(None), credentials=credentials, x_permission_id=None
        )
    assert exc.value.status_code == 403


async def test_caller_unknown_permission_is_403() -> None:
    credentials = _bearer(create_access_token("u1"))
    with pytest.raises(HTTPException) as exc:
        await get_caller_permission(
            FakeSession(None), credentials=credentials, x_permission_id="perm-1"
        )
    assert exc.value.status_code == 403


async def test_caller_permission_not_owned_is_403() -> None:
    credentials = _bearer(create_access_token("u1"))
    record = _perm_record("someone-else", GroupName.CURATORIAL)
    with pytest.raises(HTTPException) as exc:
        await get_caller_permission(
            FakeSession(record), credentials=credentials, x_permission_id="perm-1"
        )
    assert exc.value.status_code == 403


async def test_caller_valid_and_owned_returns_actor() -> None:
    credentials = _bearer(create_access_token("u1"))
    record = _perm_record("u1", GroupName.CURATORIAL)
    actor = await get_caller_permission(
        FakeSession(record), credentials=credentials, x_permission_id="perm-1"
    )
    assert actor.id == "perm-1"
    assert actor.group == GroupName.CURATORIAL
    assert actor.email == "a@x.org"


async def test_caller_token_issued_before_password_change_is_401() -> None:
    credentials = _bearer(create_access_token("u1"))
    changed_at = datetime.now(UTC) + timedelta(seconds=1)
    record = _perm_record("u1", GroupName.CURATORIAL, password_changed_at=changed_at)
    with pytest.raises(HTTPException) as exc:
        await get_caller_permission(
            FakeSession(record), credentials=credentials, x_permission_id="perm-1"
        )
    assert exc.value.status_code == 401


async def test_caller_token_issued_after_password_change_is_valid() -> None:
    changed_at = datetime.now(UTC) - timedelta(hours=1)
    credentials = _bearer(create_access_token("u1"))
    record = _perm_record("u1", GroupName.CURATORIAL, password_changed_at=changed_at)
    actor = await get_caller_permission(
        FakeSession(record), credentials=credentials, x_permission_id="perm-1"
    )
    assert actor.id == "perm-1"


async def test_caller_token_issued_same_second_as_change_is_valid() -> None:
    """Regression: JWT `iat` has whole-second resolution, but
    password_changed_at keeps microseconds. A fresh login minted in the same
    wall-clock second as the change (the normal case right after a reset)
    must not be rejected as stale just because its floored iat sorts before
    the sub-second change timestamp."""
    token = create_access_token("u1")
    credentials = _bearer(token)
    issued_at = decode_access_token(token).issued_at
    changed_at = issued_at + timedelta(microseconds=474224)
    record = _perm_record("u1", GroupName.CURATORIAL, password_changed_at=changed_at)

    actor = await get_caller_permission(
        FakeSession(record), credentials=credentials, x_permission_id="perm-1"
    )

    assert actor.id == "perm-1"


# ── security primitives ───────────────────────────────────────────────────────


def test_bcrypt_hash_is_not_plaintext_and_verifies() -> None:
    hasher = BcryptPasswordHasher()
    hashed = hasher.hash("s3cret")
    assert hashed != "s3cret"
    assert hasher.verify("s3cret", hashed)
    assert not hasher.verify("wrong", hashed)
    assert not hasher.verify("s3cret", "")  # no stored hash


def test_token_roundtrip() -> None:
    decoded = decode_access_token(create_access_token("u1"))
    assert decoded.user_id == "u1"
    assert decoded.issued_at is not None


def test_decode_garbage_token_raises() -> None:
    with pytest.raises(TokenError):
        decode_access_token("not-a-jwt")


def test_expired_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security.settings, "access_token_ttl_minutes", -1)
    expired = security.create_access_token("u1")
    with pytest.raises(TokenError):
        security.decode_access_token(expired)


# ── POST /auth/login (HTTP shape) ─────────────────────────────────────────────


class _LoginResult:
    def __init__(self, user_record, perm_records):  # noqa: ANN001
        self._user = user_record
        self._perms = perm_records

    def scalar_one_or_none(self):
        return self._user

    def scalar_one(self):
        return len(self._perms)

    def scalars(self):
        perms = self._perms

        class _Scalars:
            def all(self):
                return perms

        return _Scalars()


class LoginSession:
    """Returns a fixed user via scalar_one_or_none and permissions via scalars();
    institution lookups (session.get) return the provided record, if any."""

    def __init__(self, user_record, perm_records, institution_record=None):  # noqa: ANN001
        self._result = _LoginResult(user_record, perm_records)
        self._institution = institution_record

    async def execute(self, *args, **kwargs):
        return self._result

    async def get(self, *args, **kwargs):
        return self._institution

    async def commit(self):
        return None


@asynccontextmanager
async def login_client(  # noqa: ANN001
    user_record, perm_records, institution_record=None
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_async_session] = lambda: LoginSession(
        user_record, perm_records, institution_record
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _login_records(password: str):
    hasher = BcryptPasswordHasher()
    user_rec = UserRecord(
        id="u1",
        name="Alice Ferreira",
        email="alice@x.org",
        password_hash=hasher.hash(password),
    )
    perm_rec = PermissionRecord(id="perm-1", user_id="u1", group_id="g1")
    perm_rec.user = user_rec
    perm_rec.group = GroupRecord(
        id="g1", name=GroupName.COLLECTIONS_MANAGEMENT, institution_id="inst-1"
    )
    return user_rec, [perm_rec]


async def test_login_success_returns_token_user_and_flat_group() -> None:
    user_rec, perm_recs = _login_records("secret")
    institution_rec = InstitutionRecord(
        id="inst-1", name="MUHNAC", email="", address="", phone=""
    )
    async with login_client(user_rec, perm_recs, institution_rec) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "alice@x.org", "password": "secret"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["accessToken"]
    assert decode_access_token(body["accessToken"]).user_id == "u1"
    assert body["user"] == {
        "id": "u1",
        "email": "alice@x.org",
        "displayName": "Alice Ferreira",
    }
    # group is the bare enum string, not a {id, name} object.
    assert body["permissions"] == [
        {"permissionId": "perm-1", "group": "COLLECTIONS_MANAGEMENT"}
    ]
    # institution is resolved via the principal's group.
    assert body["institution"] == {"id": "inst-1", "name": "MUHNAC"}


async def test_login_wrong_password_is_401_with_message() -> None:
    user_rec, perm_recs = _login_records("secret")
    async with login_client(user_rec, perm_recs) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "alice@x.org", "password": "WRONG"},
        )

    assert resp.status_code == 401
    assert resp.json() == {"message": "Invalid email or password"}


async def test_login_unknown_email_is_401() -> None:
    async with login_client(None, []) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@x.org", "password": "secret"},
        )

    assert resp.status_code == 401


async def test_login_missing_password_is_422_with_errors() -> None:
    async with login_client(None, []) as client:
        resp = await client.post("/api/v1/auth/login", json={"email": "a@x.org"})

    assert resp.status_code == 422
    body = resp.json()
    assert body["message"] == "Validation failed"
    assert any(e["field"] == "password" for e in body["errors"])


# ── POST /auth/change-password (HTTP shape) ───────────────────────────────────


class ChangePasswordSession:
    """Fake session backing a single UserRecord for both the get_by_email
    lookup and the update-by-id write the route performs."""

    def __init__(self, user_record: UserRecord) -> None:
        self._user_record = user_record

    async def execute(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        record = self._user_record

        class _Result:
            def scalar_one_or_none(self) -> UserRecord:
                return record

        return _Result()

    async def get(self, model, pk, options=None):  # noqa: ANN001
        return self._user_record if pk == self._user_record.id else None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


@asynccontextmanager
async def change_password_client(user_record: UserRecord) -> AsyncIterator[AsyncClient]:
    actor = Actor(
        id=PermissionId("perm-1"), group=GroupName.CURATORIAL, email=user_record.email
    )
    app.dependency_overrides[get_caller_permission] = lambda: actor
    app.dependency_overrides[get_async_session] = lambda: ChangePasswordSession(
        user_record
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _password_user_record(password: str) -> UserRecord:
    hasher = BcryptPasswordHasher()
    return UserRecord(
        id="u1",
        name="Alice Ferreira",
        email="alice@x.org",
        password_hash=hasher.hash(password),
    )


async def test_change_password_api_success_returns_204() -> None:
    user_rec = _password_user_record("old-password")
    async with change_password_client(user_rec) as client:
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={
                "currentPassword": "old-password",
                "newPassword": "a-strong-new-password",
            },
        )

    assert resp.status_code == 204
    assert user_rec.password_changed_at is not None


async def test_change_password_api_wrong_current_is_400() -> None:
    user_rec = _password_user_record("old-password")
    async with change_password_client(user_rec) as client:
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={"currentPassword": "WRONG", "newPassword": "a-strong-new-password"},
        )

    assert resp.status_code == 400
    assert resp.json()["error"] == "INCORRECT_CURRENT_PASSWORD"


async def test_change_password_api_weak_new_password_is_400() -> None:
    user_rec = _password_user_record("old-password")
    async with change_password_client(user_rec) as client:
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={"currentPassword": "old-password", "newPassword": "short"},
        )

    assert resp.status_code == 400
    assert resp.json()["error"] == "WEAK_PASSWORD"


async def test_change_password_api_requires_authentication() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={
                "currentPassword": "old-password",
                "newPassword": "a-strong-new-password",
            },
        )

    assert resp.status_code == 401


@asynccontextmanager
async def caller_client(caller: Permission) -> AsyncIterator[AsyncClient]:
    # Routes depend on get_caller_permission, which returns an Actor (the post-JWT
    # caller view); build one from the Permission fixture so require_group sees a
    # GroupName, not a Group object.
    actor = Actor(
        id=PermissionId(caller.id),
        group=caller.group.name if caller.group else None,
        email=caller.user.email if caller.user else "",
    )
    app.dependency_overrides[get_caller_permission] = lambda: actor
    app.dependency_overrides[get_async_session] = lambda: LoginSession(None, [])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_external_user_cannot_create_identity_user() -> None:
    caller = _perm(_user(""), GroupName.EXTERNAL)

    async with caller_client(caller) as client:
        resp = await client.post(
            "/api/v1/users",
            json={
                "name": "New User",
                "email": "new@example.org",
                "password": "secret",
            },
        )

    assert resp.status_code == 403
    assert resp.json()["error"] == "INSUFFICIENT_GROUP"


async def test_external_user_can_list_identity_users() -> None:
    # Listing users is intentionally open to any authenticated caller (the
    # SYS_ADMIN check on list_users is deliberately relaxed); external callers
    # therefore get 200, not 403.
    caller = _perm(_user(""), GroupName.EXTERNAL)

    async with caller_client(caller) as client:
        resp = await client.get("/api/v1/users")

    assert resp.status_code == 200
    assert resp.json()["content"] == []


async def test_administration_user_can_list_identity_users() -> None:
    caller = _perm(_user(""), GroupName.SYS_ADMIN)

    async with caller_client(caller) as client:
        resp = await client.get("/api/v1/users")

    assert resp.status_code == 200
    assert resp.json()["content"] == []


async def test_external_user_cannot_assign_identity_group() -> None:
    caller = _perm(_user(""), GroupName.EXTERNAL)

    async with caller_client(caller) as client:
        resp = await client.post("/api/v1/users/user-2/groups/group-2")

    assert resp.status_code == 403
    assert resp.json()["error"] == "INSUFFICIENT_GROUP"
