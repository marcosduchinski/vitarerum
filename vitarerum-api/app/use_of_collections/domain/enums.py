from enum import StrEnum

# UseType was promoted to the Shared Kernel so the ProposalChat context can use
# the taxonomy without importing User Request. Re-exported here so existing
# imports (and the SQLAlchemy `use_type` enum bound to this class) keep working.
from app.shared.kernel import UseType as UseType


class UseStatus(StrEnum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class UseResult(StrEnum):
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MediaType(StrEnum):
    DOCUMENT = "DOCUMENT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    OTHER = "OTHER"


class UseEventType(StrEnum):
    REQUESTED = "REQUESTED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ProposalStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ProposalEventType(StrEnum):
    SUBMITTED = "SUBMITTED"
    ASSIGNED = "ASSIGNED"
    FORWARDED = "FORWARDED"
    DOCUMENTS_REQUESTED = "DOCUMENTS_REQUESTED"
    DOCUMENTS_SUBMITTED = "DOCUMENTS_SUBMITTED"
    REVIEW_STARTED = "REVIEW_STARTED"
    REFERRED_TO_DIRECTION = "REFERRED_TO_DIRECTION"
    DIRECTION_CLARIFIED = "DIRECTION_CLARIFIED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
