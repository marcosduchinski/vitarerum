"""Identity & Access domain — owns User, Group, Permission (per the PUML)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

from app.identity.domain.enums import GroupName
from app.shared.kernel import PermissionId as PermissionId

UserId = NewType("UserId", str)
GroupId = NewType("GroupId", str)
InstitutionId = NewType("InstitutionId", str)


@dataclass(slots=True)
class Institution:
    id: InstitutionId
    name: str = ""
    email: str = ""
    address: str = ""
    phone: str = ""


@dataclass(slots=True)
class User:
    id: UserId
    name: str = ""
    email: str = ""
    password_hash: str = ""


@dataclass(slots=True)
class Group:
    id: GroupId
    name: GroupName
    institution_id: InstitutionId


@dataclass(slots=True)
class Permission:
    id: PermissionId
    user_id: UserId
    group_id: GroupId
    user: User | None = None
    group: Group | None = None
