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


class InstitutionSummary(BaseModel):
    id: str
    name: str


class LoginResponse(BaseModel):
    accessToken: str
    user: AuthUser
    permissions: list[AuthPermission]
    # The institution the principal acts within (resolved via their group).
    institution: InstitutionSummary | None = None


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
    institutionId: str


class GroupsListResponse(BaseModel):
    groups: list[GroupResponse]


class CreateInstitutionRequest(BaseModel):
    name: str
    email: str = ""
    address: str = ""
    phone: str = ""


class UpdateInstitutionRequest(BaseModel):
    name: str
    email: str = ""
    address: str = ""
    phone: str = ""


class InstitutionResponse(BaseModel):
    id: str
    name: str
    email: str
    address: str
    phone: str


class PaginatedInstitutionsResponse(BaseModel):
    content: list[InstitutionResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


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
