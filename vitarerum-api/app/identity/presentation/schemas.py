from pydantic import BaseModel

from app.identity.domain.enums import GroupName


class UserSummary(BaseModel):
    id: str
    name: str
    email: str


class PermissionDetail(BaseModel):
    permissionId: str
    user: UserSummary
    group: GroupName


class CreateUserRequest(BaseModel):
    name: str
    email: str
    password: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthUser(BaseModel):
    id: str
    email: str
    displayName: str


class AuthPermission(BaseModel):
    permissionId: str
    group: GroupName


class LoginResponse(BaseModel):
    accessToken: str
    user: AuthUser
    permissions: list[AuthPermission]


class UserDetailResponse(BaseModel):
    id: str
    name: str
    email: str
    permissions: list[PermissionDetail]


class UserListItemResponse(BaseModel):
    id: str
    name: str
    email: str
    permissions: list[PermissionDetail]


class PaginatedUsersResponse(BaseModel):
    content: list[UserListItemResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class GroupResponse(BaseModel):
    id: str
    name: GroupName


class GroupsListResponse(BaseModel):
    groups: list[GroupResponse]


class UserPermissionsResponse(BaseModel):
    userId: str
    permissions: list[PermissionDetail]


class GroupMemberResponse(BaseModel):
    permissionId: str
    user: UserSummary


class PaginatedGroupMembersResponse(BaseModel):
    group: GroupResponse
    content: list[GroupMemberResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int
