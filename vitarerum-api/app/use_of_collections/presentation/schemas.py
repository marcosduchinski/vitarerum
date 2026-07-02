from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.identity.public import GroupName
from app.use_of_collections.domain.enums import (
    MediaType,
    ProposalEventType,
    ProposalStatus,
    UseEventType,
    UseResult,
    UseStatus,
    UseType,
)

# ── Shared permission detail ──────────────────────────────────────────────────


class UserSummary(BaseModel):
    id: str
    name: str
    email: str


class PermissionDetail(BaseModel):
    permissionId: str
    user: UserSummary
    group: GroupName


# ── Intended use (use type + free-text description) ──────────────────────────


class IntendedUseRequest(BaseModel):
    useType: UseType
    description: str = ""


class IntendedUseResponse(BaseModel):
    useType: UseType
    description: str


# ── Proposal request/response schemas ────────────────────────────────────────


class SubmitProposalRequest(BaseModel):
    # All proposal-defining fields are optional: a proposal can be created as a
    # stub and completed in a later step. See SubmitProposal use case.
    title: str | None = None
    intendedUse: IntendedUseRequest | None = None
    purpose: str | None = None
    beginDate: date | None = None
    endDate: date | None = None
    initialMessageRecipient: str = ""
    initialMessageSubject: str = ""
    initialMessageBody: str = ""


class UpdateProposalRequest(BaseModel):
    # Partial update: an omitted key leaves the field unchanged, while an
    # explicit null clears it. The route distinguishes the two via
    # ``model_fields_set``. ``intendedUse`` is replaced as a whole object.
    title: str | None = None
    intendedUse: IntendedUseRequest | None = None
    beginDate: date | None = None
    endDate: date | None = None


class RequesterContactResponse(BaseModel):
    name: str
    email: str


class ProposalSummary(BaseModel):
    id: str
    referenceNumber: str
    title: str | None = None
    status: ProposalStatus
    intendedUse: IntendedUseResponse | None = None
    beginDate: date | None = None
    endDate: date | None = None
    requestedBy: PermissionDetail | None = None
    requesterContact: RequesterContactResponse | None = None
    assignedTo: PermissionDetail | None
    submittedAt: datetime


class CollectionUseProjectSummary(BaseModel):
    id: str
    referenceNumber: str
    title: str
    purpose: str
    note: str | None
    intendedUse: IntendedUseResponse
    status: UseStatus
    beginDate: date
    endDate: date
    requestedBy: PermissionDetail | None = None


class SubmitProposalResponse(BaseModel):
    proposal: ProposalSummary
    conversationId: str


class ProposalEventResponse(BaseModel):
    occurredAt: datetime
    type: ProposalEventType
    triggeredBy: PermissionDetail | None = None
    note: str | None


class RequestedDocumentResponse(BaseModel):
    id: str
    type: str
    description: str
    requestedAt: datetime
    requestedBy: PermissionDetail


class RequestedObjectResponse(BaseModel):
    id: str
    inventoryNumber: str
    displayTitle: str | None = None
    objectName: str | None = None
    briefDescriptionSnapshot: str | None = None
    category: str
    description: str
    requestedAt: datetime
    requestedBy: PermissionDetail


class DocumentResponse(BaseModel):
    id: str
    type: str
    fileName: str
    fileReference: str
    submittedAt: datetime
    submittedBy: PermissionDetail | None = None


class ProposalDetailProjectSummary(BaseModel):
    id: str
    referenceNumber: str
    title: str
    status: UseStatus
    requestedBy: PermissionDetail | None = None


class ProposalDetailResponse(BaseModel):
    id: str
    referenceNumber: str
    title: str | None = None
    status: ProposalStatus
    intendedUse: IntendedUseResponse | None = None
    beginDate: date | None = None
    endDate: date | None = None
    requestedBy: PermissionDetail | None = None
    requesterContact: RequesterContactResponse | None = None
    assignedTo: PermissionDetail | None
    collectionUseProject: ProposalDetailProjectSummary
    conversationId: str | None
    documents: list[DocumentResponse]
    requestedDocuments: list[RequestedDocumentResponse]
    requestedObjects: list[RequestedObjectResponse]
    submittedAt: datetime


class ProposalListItemProposalProjectSummary(BaseModel):
    id: str
    referenceNumber: str
    title: str
    status: UseStatus


class ProposalListItemResponse(BaseModel):
    id: str
    referenceNumber: str
    title: str | None = None
    status: ProposalStatus
    intendedUse: IntendedUseResponse | None = None
    beginDate: date | None = None
    endDate: date | None = None
    requestedBy: PermissionDetail | None = None
    requesterContact: RequesterContactResponse | None = None
    assignedTo: PermissionDetail | None
    submittedAt: datetime


class PaginatedProposalsResponse(BaseModel):
    content: list[ProposalListItemResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class PaginatedProposalEventsResponse(BaseModel):
    proposalId: str
    content: list[ProposalEventResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class DocumentsListResponse(BaseModel):
    proposalId: str
    documents: list[DocumentResponse]


class MessageAttachmentResponse(BaseModel):
    documentId: str
    fileName: str


class MessageResponse(BaseModel):
    id: str
    sentAt: datetime
    sender: str
    recipient: str
    subject: str
    body: str
    attachments: list[MessageAttachmentResponse]


class ConversationResponse(BaseModel):
    conversationId: str
    proposalId: str
    messages: list[MessageResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class SendMessageRequest(BaseModel):
    recipient: str
    subject: str
    body: str
    documentIds: list[str] = []


class AssignProposalRequest(BaseModel):
    targetPermissionId: str | None = None
    note: str | None = None


class RequestedDocumentInput(BaseModel):
    type: str
    description: str


class RequestDocumentsRequest(BaseModel):
    requiredDocuments: list[RequestedDocumentInput]
    note: str | None = None


class RequestedObjectSnapshotInput(BaseModel):
    """Caller-supplied inventory snapshot: the user picks objects from a catalog
    search result, so the display fields are known client-side.
    inventoryNumber/displayTitle/objectName are required; briefDescriptionSnapshot
    is optional."""

    inventoryNumber: str
    displayTitle: str
    objectName: str
    briefDescriptionSnapshot: str | None = None
    category: str = ""
    description: str = ""


class AddRequestedObjectsRequest(BaseModel):
    objects: list[RequestedObjectSnapshotInput]


class ForwardProposalRequest(BaseModel):
    targetPermissionId: str
    note: str | None = None


class NoteRequest(BaseModel):
    note: str | None = None


class ApproveProposalRequest(BaseModel):
    title: str
    purpose: str
    beginDate: date
    endDate: date
    note: str | None = None


class ReasonRequest(BaseModel):
    reason: str


class ProposalCommandResponse(BaseModel):
    id: str
    referenceNumber: str
    title: str | None = None
    status: ProposalStatus
    beginDate: date | None = None
    endDate: date | None = None
    assignedTo: PermissionDetail | None = None
    lastEvent: ProposalEventResponse | None = None


class DualAggregateResponse(BaseModel):
    proposal: ProposalCommandResponse
    collectionUseProject: ProposalDetailProjectSummary


class CancelProposalResponse(BaseModel):
    proposal: ProposalCommandResponse
    collectionUseProject: ProposalDetailProjectSummary | None = None


# ── Project request/response schemas ─────────────────────────────────────────


class AttachmentResponse(BaseModel):
    fileReference: str
    fileName: str
    mediaType: MediaType
    uploadedAt: datetime
    note: str | None = None


# ── Object access log (per-project register of accessed objects) ─────────────


class AddLogEntryRequest(BaseModel):
    collectionUseObjectId: str = Field(min_length=1)
    numberOfObjects: int = Field(ge=1)
    observations: str | None = None


class EditLogEntryRequest(BaseModel):
    addedAt: datetime | None = None
    numberOfObjects: int | None = Field(default=None, ge=1)
    observations: str | None = None


class ObjectLogEntryResponse(BaseModel):
    id: str
    collectionUseObjectId: str
    numberOfObjects: int
    addedAt: datetime
    addedBy: PermissionDetail
    observations: str | None
    attachments: list[AttachmentResponse]


class ObjectAccessLogResponse(BaseModel):
    id: str
    referenceNumber: str
    projectId: str
    dateConclusion: datetime | None
    curator: PermissionDetail | None


class PaginatedLogEntriesResponse(BaseModel):
    projectId: str
    accessLog: ObjectAccessLogResponse | None
    content: list[ObjectLogEntryResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


# ── Object occurrence log (per-project register of object occurrences) ───────


class AddOccurrenceEntryRequest(BaseModel):
    collectionUseObjectId: str = Field(min_length=1)
    numberOfObjects: int = Field(ge=1)
    occurrenceDate: datetime
    location: str = Field(min_length=1)
    detailedDescription: str = Field(min_length=1)
    testimonial: str | None = None


class EditOccurrenceEntryRequest(BaseModel):
    numberOfObjects: int | None = Field(default=None, ge=1)
    occurrenceDate: datetime | None = None
    location: str | None = Field(default=None, min_length=1)
    detailedDescription: str | None = Field(default=None, min_length=1)
    testimonial: str | None = None


class ObjectOccurrenceEntryResponse(BaseModel):
    id: str
    collectionUseObjectId: str
    numberOfObjects: int
    occurrenceDate: datetime
    location: str
    reportedBy: PermissionDetail
    detailedDescription: str
    testimonial: str | None
    attachments: list[AttachmentResponse]


class ObjectOccurrenceLogResponse(BaseModel):
    id: str
    referenceNumber: str
    projectId: str
    dateConclusion: datetime | None
    curator: PermissionDetail | None


class PaginatedOccurrenceEntriesResponse(BaseModel):
    projectId: str
    occurrenceLog: ObjectOccurrenceLogResponse | None
    content: list[ObjectOccurrenceEntryResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


# ── Publication log (per-project register of publications/outputs) ───────────


class AddPublicationEntryRequest(BaseModel):
    note: str = Field(min_length=1)


class EditPublicationEntryRequest(BaseModel):
    note: str = Field(min_length=1)


class PublicationLogEntryResponse(BaseModel):
    id: str
    addedAt: datetime
    addedBy: PermissionDetail
    note: str
    attachments: list[AttachmentResponse]


class PublicationLogResponse(BaseModel):
    id: str
    referenceNumber: str
    projectId: str
    curator: PermissionDetail | None


class PaginatedPublicationEntriesResponse(BaseModel):
    projectId: str
    publicationLog: PublicationLogResponse | None
    content: list[PublicationLogEntryResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class UseEventResponse(BaseModel):
    occurredAt: datetime
    type: UseEventType
    triggeredBy: PermissionDetail
    note: str | None


class ProposalRefSummary(BaseModel):
    id: str
    referenceNumber: str
    title: str
    status: ProposalStatus
    beginDate: date
    endDate: date
    submittedAt: datetime | None = None
    assignedTo: PermissionDetail | None = None


class ProjectListItemResponse(BaseModel):
    id: str
    referenceNumber: str
    title: str
    purpose: str
    note: str | None
    intendedUse: IntendedUseResponse
    status: UseStatus
    result: UseResult | None
    beginDate: date
    endDate: date
    proposal: ProposalRefSummary | None = None
    requestedBy: PermissionDetail | None = None


class CollectionUseObjectResponse(BaseModel):
    """Project-owned object snapshot (copied from the proposal at approval).
    Journal entries reference these by ``id`` via ``collectionUseObjectId``."""

    id: str
    inventoryNumber: str
    displayTitle: str | None = None
    objectName: str | None = None
    briefDescriptionSnapshot: str | None = None
    category: str
    description: str


class ProjectDetailResponse(BaseModel):
    id: str
    referenceNumber: str
    title: str
    purpose: str
    note: str | None
    intendedUse: IntendedUseResponse
    status: UseStatus
    result: UseResult | None
    beginDate: date
    endDate: date
    authorisedBy: PermissionDetail | None = None
    authorisedAt: datetime | None = None
    proposal: ProposalRefSummary | None = None
    requestedBy: PermissionDetail | None = None
    objects: list[CollectionUseObjectResponse] = []


class PaginatedProjectsResponse(BaseModel):
    content: list[ProjectListItemResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class PaginatedEventsResponse(BaseModel):
    projectId: str
    content: list[UseEventResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class ProjectCommandResponse(BaseModel):
    id: str
    referenceNumber: str
    status: UseStatus
    result: UseResult | None = None
    lastEvent: UseEventResponse | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"error": "NOT_FOUND", "message": "Resource not found"}
        }
    )
    error: str
    message: str
