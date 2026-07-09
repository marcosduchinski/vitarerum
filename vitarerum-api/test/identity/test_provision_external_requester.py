from app.identity.application.ports import PasswordHasher, UserFilters
from app.identity.application.read_models import Actor
from app.identity.application.use_cases import (
    AuthenticateUser,
    ProvisionedRequester,
    ProvisionExternalRequester,
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
from app.identity.infrastructure.security import BcryptPasswordHasher

# ── doubles ───────────────────────────────────────────────────────────────────


class PlainHasher:
    """Fast, deterministic stand-in for bcrypt in tests that don't need to
    prove real hash/verify compatibility (see ``test_auth.py``)."""

    def hash(self, plain: str) -> str:
        return f"hashed:{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed:{plain}"


class InMemoryUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self._by_email = {u.email: u for u in (users or [])}

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


class InMemoryGroupRepository:
    def __init__(self, groups: list[Group]) -> None:
        self._groups = groups

    async def get_by_name(self, name: GroupName) -> Group | None:
        return next((g for g in self._groups if g.name == name), None)


class InMemoryPermissionRepository:
    def __init__(self) -> None:
        self.items: list[Permission] = []

    async def add(self, permission: Permission) -> None:
        self.items.append(permission)

    async def get_by_user_id(self, user_id: UserId) -> list[Permission]:
        return [p for p in self.items if p.user_id == user_id]

    async def get_by_user_and_group(
        self, user_id: UserId, group_id: GroupId
    ) -> Permission | None:
        return next(
            (
                p
                for p in self.items
                if p.user_id == user_id and p.group_id == group_id
            ),
            None,
        )

    async def get_by_group_id(
        self, group_id: GroupId, page: int, size: int
    ) -> tuple[list[Permission], int]:
        perms = [p for p in self.items if p.group_id == group_id]
        return perms, len(perms)

    async def delete(self, permission_id: PermissionId) -> None:
        self.items = [p for p in self.items if p.id != permission_id]


def _external_group() -> Group:
    return Group(
        id=GroupId("group-external"),
        name=GroupName.EXTERNAL,
        institution_id=InstitutionId("inst-1"),
    )


def _make_provisioner(
    users: list[User] | None = None,
    hasher: PasswordHasher | None = None,
) -> tuple[
    ProvisionExternalRequester, InMemoryUserRepository, InMemoryPermissionRepository
]:
    user_repo = InMemoryUserRepository(users)
    permission_repo = InMemoryPermissionRepository()
    provisioner = ProvisionExternalRequester(
        user_repo=user_repo,
        group_repo=InMemoryGroupRepository([_external_group()]),
        permission_repo=permission_repo,
        hasher=hasher or PlainHasher(),
    )
    return provisioner, user_repo, permission_repo


# ── tests ─────────────────────────────────────────────────────────────────────


async def test_provision_creates_user_and_external_permission_when_absent() -> None:
    provisioner, user_repo, permission_repo = _make_provisioner()

    provisioned = await provisioner.execute("Pedro@Example.test", "Pedro Silva")

    assert provisioned.user_created is True
    assert provisioned.actor.group == GroupName.EXTERNAL
    assert provisioned.actor.email == "pedro@example.test"
    assert len(permission_repo.items) == 1

    # A temporary password was generated and hashed onto the new user — never
    # stored in the clear.
    assert provisioned.temporary_password is not None
    created_user = await user_repo.get_by_email("pedro@example.test")
    assert created_user is not None
    assert created_user.password_hash != provisioned.temporary_password
    assert PlainHasher().verify(
        provisioned.temporary_password, created_user.password_hash
    )


async def test_provision_reuses_existing_permission_for_same_email() -> None:
    existing_user = User(
        id=UserId("u1"),
        name="Pedro Silva",
        email="pedro@example.test",
        password_hash="hashed:existing-password",
    )
    provisioner, user_repo, permission_repo = _make_provisioner(users=[existing_user])

    first = await provisioner.execute("pedro@example.test", "Pedro Silva")
    second = await provisioner.execute("pedro@example.test", "Pedro Silva")

    assert first.user_created is False
    assert second.user_created is False
    assert first.actor.id == second.actor.id
    assert len(permission_repo.items) == 1

    # Neither call touches the password of an already-existing user.
    assert first.temporary_password is None
    assert second.temporary_password is None
    unchanged_user = await user_repo.get_by_email("pedro@example.test")
    assert unchanged_user is not None
    assert unchanged_user.password_hash == "hashed:existing-password"


async def test_provisioned_requester_repr_does_not_expose_temporary_password() -> None:
    provisioned = ProvisionedRequester(
        actor=Actor(
            id=PermissionId("perm-1"),
            group=GroupName.EXTERNAL,
            email="pedro@example.test",
        ),
        user_created=True,
        temporary_password="super-secret-value",
    )

    assert "super-secret-value" not in repr(provisioned)


async def test_provisioned_temporary_password_allows_login() -> None:
    provisioner, user_repo, permission_repo = _make_provisioner(
        hasher=BcryptPasswordHasher()
    )

    provisioned = await provisioner.execute("pedro@example.test", "Pedro Silva")
    assert provisioned.temporary_password is not None

    user, permissions = await AuthenticateUser(
        user_repo, permission_repo, BcryptPasswordHasher()
    ).execute("pedro@example.test", provisioned.temporary_password)

    assert user.email == "pedro@example.test"
    assert [p.id for p in permissions] == [provisioned.actor.id]
