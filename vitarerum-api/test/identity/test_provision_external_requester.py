from app.identity.application.use_cases import ProvisionExternalRequester
from app.identity.domain.enums import GroupName
from app.identity.domain.models import (
    Group,
    GroupId,
    InstitutionId,
    Permission,
    User,
    UserId,
)

# ── doubles ───────────────────────────────────────────────────────────────────


class InMemoryUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self._by_email = {u.email: u for u in (users or [])}

    async def add(self, user: User) -> None:
        self._by_email[user.email] = user

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: UserId) -> User | None:
        return next((u for u in self._by_email.values() if u.id == user_id), None)


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


def _external_group() -> Group:
    return Group(
        id=GroupId("group-external"),
        name=GroupName.EXTERNAL,
        institution_id=InstitutionId("inst-1"),
    )


def _make_provisioner(
    users: list[User] | None = None,
) -> tuple[ProvisionExternalRequester, InMemoryPermissionRepository]:
    permission_repo = InMemoryPermissionRepository()
    provisioner = ProvisionExternalRequester(
        user_repo=InMemoryUserRepository(users),
        group_repo=InMemoryGroupRepository([_external_group()]),
        permission_repo=permission_repo,
    )
    return provisioner, permission_repo


# ── tests ─────────────────────────────────────────────────────────────────────


async def test_provision_creates_user_and_external_permission_when_absent() -> None:
    provisioner, permission_repo = _make_provisioner()

    provisioned = await provisioner.execute("Pedro@Example.test", "Pedro Silva")

    assert provisioned.user_created is True
    assert provisioned.actor.group == GroupName.EXTERNAL
    assert provisioned.actor.email == "pedro@example.test"
    assert len(permission_repo.items) == 1


async def test_provision_reuses_existing_permission_for_same_email() -> None:
    existing_user = User(
        id=UserId("u1"), name="Pedro Silva", email="pedro@example.test"
    )
    provisioner, permission_repo = _make_provisioner(users=[existing_user])

    first = await provisioner.execute("pedro@example.test", "Pedro Silva")
    second = await provisioner.execute("pedro@example.test", "Pedro Silva")

    assert first.user_created is False
    assert second.user_created is False
    assert first.actor.id == second.actor.id
    assert len(permission_repo.items) == 1
