"""Tests for the self-service password-reset flow: RequestPasswordReset and
ConfirmPasswordReset use cases, plus the HTTP endpoints end-to-end."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_async_session
from app.identity.application.password_policy import WeakPassword
from app.identity.application.ports import UserFilters
from app.identity.application.use_cases import (
    ConfirmPasswordReset,
    InvalidOrExpiredResetToken,
    RateLimitExceeded,
    RequestPasswordReset,
)
from app.identity.domain.models import PasswordResetToken, User, UserId
from app.identity.infrastructure.security import BcryptPasswordHasher
from app.identity.presentation.dependencies import get_password_email_sender
from app.main import app


def hash_token(raw_token: str) -> str:
    """Test-local copy of the use case's private hashing helper, so this
    module doesn't depend on an internal (underscore-prefixed) symbol."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@pytest.fixture(autouse=True)
def _reset_rate_limiter_singleton():
    """The HTTP-level tests below share the process-wide rate-limiter
    singleton the route composition root uses (by design, so limits hold
    across requests in production). Without a reset, the ASGI test client's
    fixed "unknown" remote IP would pool hits across every test in this
    module and trip RATE_LIMIT_PER_IP well before any single test does."""
    from app.identity.presentation.dependencies import _rate_limiter

    _rate_limiter._buckets.clear()
    yield


# ── doubles ───────────────────────────────────────────────────────────────────


class PlainHasher:
    def hash(self, plain: str) -> str:
        return f"hashed:{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed:{plain}"


class InMemoryUserRepository:
    def __init__(self, users: list[User]) -> None:
        self._by_email = {u.email: u for u in users}
        self._by_id = {u.id: u for u in users}

    async def add(self, user: User) -> None:
        self._by_email[user.email] = user
        self._by_id[user.id] = user

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self._by_id.get(user_id)

    async def list(
        self, filters: UserFilters, page: int, size: int
    ) -> tuple[list[User], int]:
        users = list(self._by_email.values())
        return users, len(users)

    async def update(self, user: User) -> None:
        self._by_email[user.email] = user
        self._by_id[user.id] = user


class InMemoryPasswordResetTokenRepository:
    def __init__(self) -> None:
        self._by_hash: dict[str, PasswordResetToken] = {}

    async def add(self, token: PasswordResetToken) -> None:
        self._by_hash[token.token_hash] = token

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        return self._by_hash.get(token_hash)

    async def save(self, token: PasswordResetToken) -> None:
        self._by_hash[token.token_hash] = token

    async def invalidate_active_for_user(self, user_id: UserId, now: datetime) -> None:
        for token in self._by_hash.values():
            if token.user_id == user_id and not token.is_used:
                token.used_at = now


class FixedClock:
    def __init__(self, when: datetime) -> None:
        self._when = when

    def now(self) -> datetime:
        return self._when


class AllowAllRateLimiter:
    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        return False


class AlwaysBlockRateLimiter:
    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        return True


def _user(email: str = "alice@x.org") -> User:
    return User(id=UserId("u1"), name="Alice Ferreira", email=email, password_hash="")


# ── RequestPasswordReset ───────────────────────────────────────────────────────


async def test_request_reset_unknown_email_returns_none_and_creates_no_token() -> None:
    tokens = InMemoryPasswordResetTokenRepository()
    uc = RequestPasswordReset(
        InMemoryUserRepository([]),
        tokens,
        AllowAllRateLimiter(),
        FixedClock(datetime.now(UTC)),
        timedelta(minutes=60),
    )

    outcome = await uc.execute(email="ghost@x.org", remote_ip="1.2.3.4")

    assert outcome is None
    assert tokens._by_hash == {}


async def test_request_reset_known_email_creates_token_and_returns_raw_token() -> None:
    tokens = InMemoryPasswordResetTokenRepository()
    uc = RequestPasswordReset(
        InMemoryUserRepository([_user()]),
        tokens,
        AllowAllRateLimiter(),
        FixedClock(datetime.now(UTC)),
        timedelta(minutes=60),
    )

    outcome = await uc.execute(email="alice@x.org", remote_ip="1.2.3.4")

    assert outcome is not None
    assert outcome.email == "alice@x.org"
    assert outcome.raw_token
    stored = await tokens.get_by_hash(hash_token(outcome.raw_token))
    assert stored is not None
    assert not stored.is_used


async def test_request_reset_invalidates_previous_unused_token() -> None:
    tokens = InMemoryPasswordResetTokenRepository()
    now = datetime.now(UTC)
    uc = RequestPasswordReset(
        InMemoryUserRepository([_user()]),
        tokens,
        AllowAllRateLimiter(),
        FixedClock(now),
        timedelta(minutes=60),
    )

    first = await uc.execute(email="alice@x.org", remote_ip="1.2.3.4")
    assert first is not None
    first_stored = await tokens.get_by_hash(hash_token(first.raw_token))
    assert first_stored is not None and not first_stored.is_used

    second = await uc.execute(email="alice@x.org", remote_ip="1.2.3.4")
    assert second is not None

    first_stored_after = await tokens.get_by_hash(hash_token(first.raw_token))
    assert first_stored_after is not None and first_stored_after.is_used
    second_stored = await tokens.get_by_hash(hash_token(second.raw_token))
    assert second_stored is not None and not second_stored.is_used


async def test_request_reset_respects_rate_limit() -> None:
    uc = RequestPasswordReset(
        InMemoryUserRepository([_user()]),
        InMemoryPasswordResetTokenRepository(),
        AlwaysBlockRateLimiter(),
        FixedClock(datetime.now(UTC)),
        timedelta(minutes=60),
    )

    with pytest.raises(RateLimitExceeded):
        await uc.execute(email="alice@x.org", remote_ip="1.2.3.4")


# ── ConfirmPasswordReset ───────────────────────────────────────────────────────


async def test_confirm_reset_valid_token_changes_password() -> None:
    hasher = PlainHasher()
    users = InMemoryUserRepository([_user()])
    tokens = InMemoryPasswordResetTokenRepository()
    now = datetime.now(UTC)
    await tokens.add(
        PasswordResetToken(
            id="t1",
            user_id=UserId("u1"),
            token_hash=hash_token("raw-token"),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
    )
    uc = ConfirmPasswordReset(
        users, tokens, hasher, AllowAllRateLimiter(), FixedClock(now)
    )

    user = await uc.execute(
        raw_token="raw-token", new_password="a-strong-new-password", remote_ip="1.2.3.4"
    )

    assert hasher.verify("a-strong-new-password", user.password_hash)
    assert user.password_changed_at == now
    stored_token = await tokens.get_by_hash(hash_token("raw-token"))
    assert stored_token is not None and stored_token.is_used


async def test_confirm_reset_used_token_raises_opaque_error() -> None:
    hasher = PlainHasher()
    users = InMemoryUserRepository([_user()])
    tokens = InMemoryPasswordResetTokenRepository()
    now = datetime.now(UTC)
    await tokens.add(
        PasswordResetToken(
            id="t1",
            user_id=UserId("u1"),
            token_hash=hash_token("raw-token"),
            created_at=now,
            expires_at=now + timedelta(hours=1),
            used_at=now,
        )
    )
    uc = ConfirmPasswordReset(
        users, tokens, hasher, AllowAllRateLimiter(), FixedClock(now)
    )

    with pytest.raises(InvalidOrExpiredResetToken):
        await uc.execute(
            raw_token="raw-token",
            new_password="a-strong-new-password",
            remote_ip="1.2.3.4",
        )


async def test_confirm_reset_expired_token_raises_opaque_error() -> None:
    hasher = PlainHasher()
    users = InMemoryUserRepository([_user()])
    tokens = InMemoryPasswordResetTokenRepository()
    now = datetime.now(UTC)
    await tokens.add(
        PasswordResetToken(
            id="t1",
            user_id=UserId("u1"),
            token_hash=hash_token("raw-token"),
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
    )
    uc = ConfirmPasswordReset(
        users, tokens, hasher, AllowAllRateLimiter(), FixedClock(now)
    )

    with pytest.raises(InvalidOrExpiredResetToken):
        await uc.execute(
            raw_token="raw-token",
            new_password="a-strong-new-password",
            remote_ip="1.2.3.4",
        )


async def test_confirm_reset_unknown_token_raises_opaque_error() -> None:
    uc = ConfirmPasswordReset(
        InMemoryUserRepository([_user()]),
        InMemoryPasswordResetTokenRepository(),
        PlainHasher(),
        AllowAllRateLimiter(),
        FixedClock(datetime.now(UTC)),
    )

    with pytest.raises(InvalidOrExpiredResetToken):
        await uc.execute(
            raw_token="does-not-exist",
            new_password="a-strong-new-password",
            remote_ip="1.2.3.4",
        )


async def test_confirm_reset_weak_new_password_raises() -> None:
    users = InMemoryUserRepository([_user()])
    tokens = InMemoryPasswordResetTokenRepository()
    now = datetime.now(UTC)
    await tokens.add(
        PasswordResetToken(
            id="t1",
            user_id=UserId("u1"),
            token_hash=hash_token("raw-token"),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
    )
    uc = ConfirmPasswordReset(
        users, tokens, PlainHasher(), AllowAllRateLimiter(), FixedClock(now)
    )

    with pytest.raises(WeakPassword):
        await uc.execute(
            raw_token="raw-token", new_password="short", remote_ip="1.2.3.4"
        )


async def test_confirm_reset_respects_rate_limit() -> None:
    uc = ConfirmPasswordReset(
        InMemoryUserRepository([_user()]),
        InMemoryPasswordResetTokenRepository(),
        PlainHasher(),
        AlwaysBlockRateLimiter(),
        FixedClock(datetime.now(UTC)),
    )

    with pytest.raises(RateLimitExceeded):
        await uc.execute(
            raw_token="whatever",
            new_password="a-strong-new-password",
            remote_ip="1.2.3.4",
        )


# ── HTTP endpoints, end-to-end against a real (in-memory sqlite) session ──────


async def _sqlite_session_factory() -> async_sessionmaker:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


class _SqliteSessionProvider:
    """Yields a single shared session across the request and later assertions,
    mirroring how the app's own get_async_session is a per-request dependency."""

    def __init__(self, factory: async_sessionmaker) -> None:
        self._factory = factory
        self.session = factory()

    async def __call__(self):  # noqa: ANN204
        yield self.session


async def _create_user(session, email: str, password: str) -> None:  # noqa: ANN001
    """Creates a user with an EXTERNAL permission, so login (which requires
    at least one group membership) can succeed for the reset/login assertions."""
    from app.identity.application.use_cases import CreateUser
    from app.identity.domain.enums import GroupName
    from app.identity.infrastructure.models import (
        GroupRecord,
        InstitutionRecord,
        PermissionRecord,
    )
    from app.identity.infrastructure.repositories import SqlAlchemyUserRepository

    user = await CreateUser(
        SqlAlchemyUserRepository(session), BcryptPasswordHasher()
    ).execute(name="Alice Ferreira", email=email, password=password)
    session.add(
        InstitutionRecord(id="inst-1", name="MUHNAC", email="", address="", phone="")
    )
    session.add(GroupRecord(id="g1", name=GroupName.EXTERNAL, institution_id="inst-1"))
    session.add(PermissionRecord(id="perm-1", user_id=user.id, group_id="g1"))
    await session.commit()


async def test_request_then_confirm_password_reset_end_to_end() -> None:
    factory = await _sqlite_session_factory()
    provider = _SqliteSessionProvider(factory)
    app.dependency_overrides[get_async_session] = provider
    try:
        await _create_user(provider.session, "alice@x.org", "old-password")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_resp = await client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": "alice@x.org"},
            )
            assert request_resp.status_code == 204

            unknown_resp = await client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": "ghost@x.org"},
            )
            # Same 204 for an unknown address — no enumeration signal.
            assert unknown_resp.status_code == 204
    finally:
        app.dependency_overrides.clear()


async def test_confirm_with_invalid_token_is_404() -> None:
    factory = await _sqlite_session_factory()
    provider = _SqliteSessionProvider(factory)
    app.dependency_overrides[get_async_session] = provider
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/password-reset/confirm",
                json={
                    "token": "not-a-real-token",
                    "newPassword": "a-strong-new-password",
                },
            )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


class _CapturingEmailSender:
    """Stands in for SMTP/logging so the test can read the raw reset token
    the route would otherwise only ever put in an outbound e-mail."""

    def __init__(self) -> None:
        self.last_reset_token: str | None = None
        self.changed_notice_sent_to: list[str] = []

    async def send_password_reset(
        self, to_email: str, display_name: str, token: str
    ) -> None:
        self.last_reset_token = token

    async def send_password_changed_notice(
        self, to_email: str, display_name: str
    ) -> None:
        self.changed_notice_sent_to.append(to_email)


async def test_confirm_with_valid_token_changes_password_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # sqlite/aiosqlite round-trips DateTime(timezone=True) columns as naive,
    # which would otherwise crash the tz-aware-vs-naive comparison inside
    # PasswordResetToken.is_expired. Postgres (production) has no such gap;
    # this keeps both sides of the comparison consistently naive for the
    # duration of this sqlite-backed test only.
    from app.identity.infrastructure.clock import SystemClock

    monkeypatch.setattr(SystemClock, "now", lambda self: datetime.now())

    factory = await _sqlite_session_factory()
    provider = _SqliteSessionProvider(factory)
    sender = _CapturingEmailSender()
    app.dependency_overrides[get_async_session] = provider
    app.dependency_overrides[get_password_email_sender] = lambda: sender
    try:
        await _create_user(provider.session, "alice@x.org", "old-password")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_resp = await client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": "alice@x.org"},
            )
            assert request_resp.status_code == 204
            assert sender.last_reset_token is not None

            confirm_resp = await client.post(
                "/api/v1/auth/password-reset/confirm",
                json={
                    "token": sender.last_reset_token,
                    "newPassword": "a-strong-new-password",
                },
            )
            assert confirm_resp.status_code == 204
            assert sender.changed_notice_sent_to == ["alice@x.org"]

            # Reusing the same (now-consumed) token fails opaquely.
            reuse_resp = await client.post(
                "/api/v1/auth/password-reset/confirm",
                json={
                    "token": sender.last_reset_token,
                    "newPassword": "another-strong-password",
                },
            )
            assert reuse_resp.status_code == 404

            old_login = await client.post(
                "/api/v1/auth/login",
                json={"email": "alice@x.org", "password": "old-password"},
            )
            assert old_login.status_code == 401

            new_login = await client.post(
                "/api/v1/auth/login",
                json={"email": "alice@x.org", "password": "a-strong-new-password"},
            )
            assert new_login.status_code == 200
    finally:
        app.dependency_overrides.clear()


async def test_confirm_with_weak_password_and_valid_token_is_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # See the comment in test_confirm_with_valid_token_changes_password_end_to_end:
    # sqlite round-trips DateTime(timezone=True) as naive, unlike Postgres.
    from app.identity.infrastructure.clock import SystemClock

    monkeypatch.setattr(SystemClock, "now", lambda self: datetime.now())

    factory = await _sqlite_session_factory()
    provider = _SqliteSessionProvider(factory)
    sender = _CapturingEmailSender()
    app.dependency_overrides[get_async_session] = provider
    app.dependency_overrides[get_password_email_sender] = lambda: sender
    try:
        await _create_user(provider.session, "alice@x.org", "old-password")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": "alice@x.org"},
            )
            assert sender.last_reset_token is not None

            resp = await client.post(
                "/api/v1/auth/password-reset/confirm",
                json={"token": sender.last_reset_token, "newPassword": "short"},
            )
        assert resp.status_code == 400
        assert resp.json()["error"] == "WEAK_PASSWORD"
    finally:
        app.dependency_overrides.clear()
