from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.identity.application.ports import UserFilters
from app.identity.application.read_models import PermissionView, UserView
from app.identity.domain.enums import GroupName, UserStatus
from app.identity.domain.models import (
    Group,
    GroupId,
    Institution,
    InstitutionId,
    PasswordResetToken,
    Permission,
    PermissionId,
    User,
    UserId,
)
from app.identity.infrastructure.models import (
    GroupRecord,
    InstitutionRecord,
    PasswordResetTokenRecord,
    PermissionRecord,
    UserRecord,
)

_PERMISSION_EAGER = [
    selectinload(PermissionRecord.user),
    selectinload(PermissionRecord.group),
]


# ── domain ↔ record mappers ──────────────────────────────────────────────────


def user_to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        name=user.name,
        email=user.email,
        password_hash=user.password_hash,
        status=user.status,
        password_changed_at=user.password_changed_at,
    )


def user_to_domain(record: UserRecord) -> User:
    return User(
        id=UserId(record.id),
        name=record.name,
        email=record.email,
        password_hash=record.password_hash,
        status=record.status or UserStatus.ACTIVE,
        password_changed_at=record.password_changed_at,
    )


def group_to_record(group: Group) -> GroupRecord:
    return GroupRecord(
        id=group.id,
        name=group.name,
        institution_id=group.institution_id,
    )


def group_to_domain(record: GroupRecord) -> Group:
    return Group(
        id=GroupId(record.id),
        name=record.name,
        institution_id=InstitutionId(record.institution_id),
    )


def institution_to_record(institution: Institution) -> InstitutionRecord:
    return InstitutionRecord(
        id=institution.id,
        name=institution.name,
        email=institution.email,
        address=institution.address,
        phone=institution.phone,
    )


def institution_to_domain(record: InstitutionRecord) -> Institution:
    return Institution(
        id=InstitutionId(record.id),
        name=record.name,
        email=record.email,
        address=record.address,
        phone=record.phone,
    )


def permission_to_record(permission: Permission) -> PermissionRecord:
    return PermissionRecord(
        id=permission.id,
        user_id=permission.user_id,
        group_id=permission.group_id,
    )


def permission_to_domain(record: PermissionRecord) -> Permission:
    user = user_to_domain(record.user) if record.user else None
    group = group_to_domain(record.group) if record.group else None
    return Permission(
        id=PermissionId(record.id),
        user_id=UserId(record.user_id),
        group_id=GroupId(record.group_id),
        user=user,
        group=group,
    )


def permission_to_view(record: PermissionRecord) -> PermissionView:
    return PermissionView(
        permission_id=record.id,
        user=UserView(
            id=record.user.id if record.user else "",
            name=record.user.name if record.user else "",
            email=record.user.email if record.user else "",
            status=record.user.status if record.user and record.user.status else None,
            password_changed_at=(
                record.user.password_changed_at if record.user else None
            ),
        ),
        group=record.group.name if record.group else GroupName.EXTERNAL,
        institution_id=record.group.institution_id if record.group else None,
    )


class SqlAlchemyPermissionReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_detail(self, permission_id: PermissionId) -> PermissionView | None:
        record = await self._session.get(
            PermissionRecord,
            permission_id,
            options=_PERMISSION_EAGER,
        )
        if record is None:
            return None
        return permission_to_view(record)

    async def get_details(
        self, permission_ids: tuple[PermissionId, ...]
    ) -> list[PermissionView]:
        if not permission_ids:
            return []
        stmt = (
            select(PermissionRecord)
            .where(PermissionRecord.id.in_(permission_ids))
            .options(*_PERMISSION_EAGER)
        )
        result = await self._session.execute(stmt)
        return [permission_to_view(record) for record in result.scalars().all()]

    async def list_by_group(self, group: GroupName) -> list[PermissionView]:
        stmt = (
            select(PermissionRecord)
            .join(PermissionRecord.group)
            .join(PermissionRecord.user)
            .where(GroupRecord.name == group)
            .options(*_PERMISSION_EAGER)
            .order_by(UserRecord.name)
        )
        result = await self._session.execute(stmt)
        return [permission_to_view(r) for r in result.scalars().all()]


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        self._session.add(user_to_record(user))
        await self._session.flush()

    async def get_by_id(self, user_id: UserId) -> User | None:
        record = await self._session.get(UserRecord, user_id)
        return user_to_domain(record) if record else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserRecord).where(UserRecord.email == email)
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return user_to_domain(record) if record else None

    async def list(
        self,
        filters: UserFilters,
        page: int,
        size: int,
    ) -> tuple[list[User], int]:
        base_stmt = select(UserRecord)
        if filters.search:
            pattern = f"%{filters.search}%"
            base_stmt = base_stmt.where(
                UserRecord.name.ilike(pattern) | UserRecord.email.ilike(pattern)
            )
        if filters.group_id:
            base_stmt = base_stmt.join(
                PermissionRecord,
                PermissionRecord.user_id == UserRecord.id,
            ).where(PermissionRecord.group_id == filters.group_id)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        data_stmt = base_stmt.offset(page * size).limit(size)
        data_result = await self._session.execute(data_stmt)
        records = data_result.scalars().all()
        return [user_to_domain(r) for r in records], total

    async def update(self, user: User) -> None:
        record = await self._session.get(UserRecord, user.id)
        if record is None:
            return
        record.name = user.name
        record.email = user.email
        record.password_hash = user.password_hash
        record.status = user.status
        record.password_changed_at = user.password_changed_at
        await self._session.flush()


class SqlAlchemyGroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, group_id: GroupId) -> Group | None:
        record = await self._session.get(GroupRecord, group_id)
        return group_to_domain(record) if record else None

    async def get_by_name(self, name: GroupName) -> Group | None:
        stmt = select(GroupRecord).where(GroupRecord.name == name)
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return group_to_domain(record) if record else None

    async def list(self) -> list[Group]:
        stmt = select(GroupRecord).order_by(GroupRecord.name)
        result = await self._session.execute(stmt)
        return [group_to_domain(r) for r in result.scalars().all()]

    async def count_by_institution(self, institution_id: InstitutionId) -> int:
        stmt = select(func.count()).where(GroupRecord.institution_id == institution_id)
        result = await self._session.execute(stmt)
        return result.scalar_one()


class SqlAlchemyInstitutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, institution: Institution) -> None:
        self._session.add(institution_to_record(institution))
        await self._session.flush()

    async def get_by_id(self, institution_id: InstitutionId) -> Institution | None:
        record = await self._session.get(InstitutionRecord, institution_id)
        return institution_to_domain(record) if record else None

    async def get_by_name(self, name: str) -> Institution | None:
        stmt = select(InstitutionRecord).where(InstitutionRecord.name == name)
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return institution_to_domain(record) if record else None

    async def list(self, page: int, size: int) -> tuple[list[Institution], int]:
        base_stmt = select(InstitutionRecord)
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        data_stmt = (
            base_stmt.order_by(InstitutionRecord.name).offset(page * size).limit(size)
        )
        data_result = await self._session.execute(data_stmt)
        records = data_result.scalars().all()
        return [institution_to_domain(r) for r in records], total

    async def update(self, institution: Institution) -> None:
        record = await self._session.get(InstitutionRecord, institution.id)
        if record is None:
            return
        record.name = institution.name
        record.email = institution.email
        record.address = institution.address
        record.phone = institution.phone
        await self._session.flush()

    async def delete(self, institution_id: InstitutionId) -> None:
        record = await self._session.get(InstitutionRecord, institution_id)
        if record:
            await self._session.delete(record)
            await self._session.flush()


class SqlAlchemyPermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, permission: Permission) -> None:
        self._session.add(permission_to_record(permission))
        await self._session.flush()

    async def get_by_user_and_group(
        self, user_id: UserId, group_id: GroupId
    ) -> Permission | None:
        stmt = (
            select(PermissionRecord)
            .where(
                PermissionRecord.user_id == user_id,
                PermissionRecord.group_id == group_id,
            )
            .options(*_PERMISSION_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return permission_to_domain(record) if record else None

    async def get_by_user_id(self, user_id: UserId) -> list[Permission]:
        stmt = (
            select(PermissionRecord)
            .where(PermissionRecord.user_id == user_id)
            .options(*_PERMISSION_EAGER)
        )
        result = await self._session.execute(stmt)
        return [permission_to_domain(r) for r in result.scalars().all()]

    async def get_by_group_id(
        self, group_id: GroupId, page: int, size: int
    ) -> tuple[list[Permission], int]:
        base_stmt = select(PermissionRecord).where(
            PermissionRecord.group_id == group_id
        )
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        data_stmt = (
            base_stmt.options(*_PERMISSION_EAGER).offset(page * size).limit(size)
        )
        data_result = await self._session.execute(data_stmt)
        records = data_result.scalars().all()
        return [permission_to_domain(r) for r in records], total

    async def count_active_by_group_name(self, group: GroupName) -> int:
        stmt = (
            select(func.count(func.distinct(UserRecord.id)))
            .select_from(PermissionRecord)
            .join(PermissionRecord.group)
            .join(PermissionRecord.user)
            .where(GroupRecord.name == group, UserRecord.status == UserStatus.ACTIVE)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def delete(self, permission_id: PermissionId) -> None:
        record = await self._session.get(PermissionRecord, permission_id)
        if record:
            await self._session.delete(record)
            await self._session.flush()


def password_reset_token_to_record(
    token: PasswordResetToken,
) -> PasswordResetTokenRecord:
    return PasswordResetTokenRecord(
        id=token.id,
        user_id=token.user_id,
        token_hash=token.token_hash,
        created_at=token.created_at,
        expires_at=token.expires_at,
        used_at=token.used_at,
    )


def password_reset_token_to_domain(
    record: PasswordResetTokenRecord,
) -> PasswordResetToken:
    return PasswordResetToken(
        id=record.id,
        user_id=UserId(record.user_id),
        token_hash=record.token_hash,
        created_at=record.created_at,
        expires_at=record.expires_at,
        used_at=record.used_at,
    )


class SqlAlchemyPasswordResetTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: PasswordResetToken) -> None:
        self._session.add(password_reset_token_to_record(token))
        await self._session.flush()

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetTokenRecord).where(
            PasswordResetTokenRecord.token_hash == token_hash
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return password_reset_token_to_domain(record) if record else None

    async def save(self, token: PasswordResetToken) -> None:
        record = await self._session.get(PasswordResetTokenRecord, token.id)
        if record is None:
            return
        record.used_at = token.used_at
        await self._session.flush()

    async def invalidate_active_for_user(self, user_id: UserId, now: datetime) -> None:
        stmt = (
            update(PasswordResetTokenRecord)
            .where(
                PasswordResetTokenRecord.user_id == user_id,
                PasswordResetTokenRecord.used_at.is_(None),
            )
            .values(used_at=now)
        )
        await self._session.execute(stmt)
