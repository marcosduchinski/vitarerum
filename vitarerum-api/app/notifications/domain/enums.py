from enum import StrEnum


class NotificationKind(StrEnum):
    PROPOSAL_ASSIGNED = "PROPOSAL_ASSIGNED"
    PROPOSAL_FORWARDED = "PROPOSAL_FORWARDED"


class RelatedResourceType(StrEnum):
    PROPOSAL = "PROPOSAL"
    PROJECT = "PROJECT"

