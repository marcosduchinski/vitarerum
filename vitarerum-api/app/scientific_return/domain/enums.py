from enum import StrEnum


class WatchStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class QueryStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class QueryType(StrEnum):
    INVENTORY = "INVENTORY"
    AUTHOR_INVENTORY = "AUTHOR_INVENTORY"
    INVENTORY_OBJECT = "INVENTORY_OBJECT"
    AUTHOR_OBJECT = "AUTHOR_OBJECT"


class CandidateStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"
    SNOOZED = "SNOOZED"


class EvidenceType(StrEnum):
    INVENTORY_NUMBER = "INVENTORY_NUMBER"
    AUTHOR = "AUTHOR"
    OBJECT_NAME = "OBJECT_NAME"
    AUTHOR_INVENTORY = "AUTHOR_INVENTORY"
    INVENTORY_OBJECT = "INVENTORY_OBJECT"
    AUTHOR_OBJECT = "AUTHOR_OBJECT"


class EvidenceStrength(StrEnum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    WEAK = "WEAK"


class DecisionType(StrEnum):
    CONFIRM = "CONFIRM"
    CORRECT_AND_CONFIRM = "CORRECT_AND_CONFIRM"
    DISMISS = "DISMISS"
    SNOOZE = "SNOOZE"


class AgentAnalysisStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentRecommendedAction(StrEnum):
    PRESENT_FOR_REVIEW = "PRESENT_FOR_REVIEW"
    SEARCH_INVENTORY_VARIANTS = "SEARCH_INVENTORY_VARIANTS"
    SEARCH_AUTHOR_VARIANTS = "SEARCH_AUTHOR_VARIANTS"
    SEARCH_TAXON_VARIANTS = "SEARCH_TAXON_VARIANTS"
    SEARCH_FULL_TEXT = "SEARCH_FULL_TEXT"
    DEPRIORITIZE = "DEPRIORITIZE"
    STOP_INSUFFICIENT_EVIDENCE = "STOP_INSUFFICIENT_EVIDENCE"


class AgentConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AgentAnalysisFeedback(StrEnum):
    USEFUL = "USEFUL"
    PARTIALLY_USEFUL = "PARTIALLY_USEFUL"
    NOT_USEFUL = "NOT_USEFUL"


class InvestigationObjective(StrEnum):
    """What an agentic investigation is trying to achieve."""

    DISCOVER_CANDIDATE = "DISCOVER_CANDIDATE"
    ENRICH_CANDIDATE = "ENRICH_CANDIDATE"


class InvestigationStatus(StrEnum):
    CREATED = "CREATED"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    VALIDATING = "VALIDATING"
    EXECUTING = "EXECUTING"
    REFLECTING = "REFLECTING"
    AWAITING_HUMAN_REVIEW = "AWAITING_HUMAN_REVIEW"
    STOPPED = "STOPPED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_INVESTIGATION_STATUSES


_TERMINAL_INVESTIGATION_STATUSES = frozenset(
    {
        InvestigationStatus.AWAITING_HUMAN_REVIEW,
        InvestigationStatus.STOPPED,
        InvestigationStatus.FAILED,
    }
)


class IterationStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InvestigationMode(StrEnum):
    """Single operating mode, chosen instead of combinable feature flags.

    Each mode strictly contains the previous one, so raising the mode can only
    add capability and lowering it can only remove capability.
    """

    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    POLICY_ONLY = "POLICY_ONLY"
    SUPERVISED = "SUPERVISED"
    SCHEDULED = "SCHEDULED"

    @property
    def may_execute_tools(self) -> bool:
        return self in {InvestigationMode.SUPERVISED, InvestigationMode.SCHEDULED}

    @property
    def may_evaluate_policy(self) -> bool:
        return self not in {InvestigationMode.DISABLED, InvestigationMode.SHADOW}


class StopReason(StrEnum):
    """Typed reason an investigation ended. Every investigation must have one."""

    EVIDENCE_SUFFICIENT = "EVIDENCE_SUFFICIENT"
    NO_RESULTS = "NO_RESULTS"
    NO_EVIDENCE_ADDED = "NO_EVIDENCE_ADDED"
    NO_PROGRESS = "NO_PROGRESS"
    ACTION_REJECTED = "ACTION_REJECTED"
    QUERY_REPEATED = "QUERY_REPEATED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    ITERATION_LIMIT_REACHED = "ITERATION_LIMIT_REACHED"
    CANDIDATE_LIMIT_REACHED = "CANDIDATE_LIMIT_REACHED"
    REASONER_UNAVAILABLE = "REASONER_UNAVAILABLE"
    INVALID_PLAN = "INVALID_PLAN"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    TOOL_FAILED = "TOOL_FAILED"
    CANDIDATE_ALREADY_DECIDED = "CANDIDATE_ALREADY_DECIDED"
    PRESENTED_FOR_REVIEW = "PRESENTED_FOR_REVIEW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PolicyRejectionReason(StrEnum):
    """Why the deterministic policy refused a proposed action.

    The reason is recorded verbatim so a reviewer can tell a model that asked
    for something forbidden from one that asked for something merely redundant.
    """

    ACTION_NOT_ALLOWED = "ACTION_NOT_ALLOWED"
    SOURCE_NOT_ALLOWED = "SOURCE_NOT_ALLOWED"
    OBJECT_NOT_IN_SNAPSHOT = "OBJECT_NOT_IN_SNAPSHOT"
    OBJECT_ID_REQUIRED = "OBJECT_ID_REQUIRED"
    INVENTORY_MISSING = "INVENTORY_MISSING"
    NO_NEW_QUERY_VARIANT = "NO_NEW_QUERY_VARIANT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    ITERATION_LIMIT_REACHED = "ITERATION_LIMIT_REACHED"
    CANDIDATE_LIMIT_REACHED = "CANDIDATE_LIMIT_REACHED"
    CANDIDATE_ALREADY_DECIDED = "CANDIDATE_ALREADY_DECIDED"
    MODE_FORBIDS_EXECUTION = "MODE_FORBIDS_EXECUTION"
    INVESTIGATION_NOT_ACTIONABLE = "INVESTIGATION_NOT_ACTIONABLE"


class AgentProgress(StrEnum):
    """The model's structured verdict on what the iteration achieved."""

    CANDIDATE_CREATED = "CANDIDATE_CREATED"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    NO_NEW_EVIDENCE = "NO_NEW_EVIDENCE"
    NO_RESULTS = "NO_RESULTS"
    FAILED = "FAILED"


class InventoryVariantKind(StrEnum):
    """Why a generated inventory query differs from the recorded number.

    The kind is persisted with each agent query so a reviewer can tell which
    rewriting rule retrieved a publication.
    """

    EXACT = "EXACT"
    WITHOUT_INSTITUTION = "WITHOUT_INSTITUTION"
    NUMBER_PADDING = "NUMBER_PADDING"
    INSTITUTION_ALIAS = "INSTITUTION_ALIAS"
    SEPARATOR = "SEPARATOR"
