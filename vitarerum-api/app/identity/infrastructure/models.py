"""Identity ORM records. The tables stay in the single shared database
(recorded decision in HEXAGONAL_UP.md); only the Python module is Identity's."""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.identity.domain.enums import GroupName


class InstitutionRecord(Base):
    __tablename__ = "identity_institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="", unique=True)
    email: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(String(512), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")


class UserRecord(Base):
    __tablename__ = "identity_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    # Emails are normalized to lowercase before write, so a plain unique index
    # gives case-insensitive uniqueness portably (no functional index needed).
    email: Mapped[str] = mapped_column(String(255), default="", unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), default="")


class GroupRecord(Base):
    __tablename__ = "identity_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[GroupName] = mapped_column(
        SAEnum(GroupName, name="identity_group_name")
    )
    institution_id: Mapped[str] = mapped_column(
        ForeignKey("identity_institutions.id"), index=True
    )

    institution: Mapped[InstitutionRecord] = relationship()


class PermissionRecord(Base):
    __tablename__ = "identity_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_permission_user_group"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("identity_groups.id"), index=True)

    user: Mapped[UserRecord] = relationship()
    group: Mapped[GroupRecord] = relationship()
