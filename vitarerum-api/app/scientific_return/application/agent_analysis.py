from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.identity.public import Actor, GroupName
from app.scientific_return.application.ports import (
    FULL_AGENTIC_READER_PROMPT_ID_PREFIX,
    ScientificReturnRepository,
)
from app.scientific_return.application.use_cases import CandidateNotFound
from app.scientific_return.domain.enums import AgentAnalysisFeedback
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidatePublicationId,
)
from app.shared.authorization import require_group

_REVIEW_GROUPS = (
    GroupName.CURATORIAL,
    GroupName.COLLECTIONS_MANAGEMENT,
    GroupName.DIRECTION,
)


class AgentAnalysisNotFound(LookupError):
    pass


def _now() -> datetime:
    return datetime.now(tz=UTC)


class ListCandidateAgentAnalyses:
    def __init__(self, repository: ScientificReturnRepository) -> None:
        self._repository = repository

    async def execute(
        self, candidate_id: CandidatePublicationId, caller: Actor
    ) -> list[CandidateAgentAnalysis]:
        require_group(caller, *_REVIEW_GROUPS)
        candidate = await self._repository.get_candidate(candidate_id)
        if candidate is None:
            raise CandidateNotFound(f"Candidate {candidate_id} not found")
        analyses = await self._repository.list_agent_analyses(candidate_id)
        return [
            analysis
            for analysis in analyses
            if analysis.prompt_version_id.startswith(
                FULL_AGENTIC_READER_PROMPT_ID_PREFIX
            )
        ]


@dataclass(frozen=True, slots=True)
class RecordAgentAnalysisFeedbackInput:
    analysis_id: CandidateAgentAnalysisId
    feedback: AgentAnalysisFeedback
    comment: str | None
    caller: Actor


class RecordAgentAnalysisFeedback:
    def __init__(self, repository: ScientificReturnRepository) -> None:
        self._repository = repository

    async def execute(
        self, data: RecordAgentAnalysisFeedbackInput
    ) -> CandidateAgentAnalysis:
        require_group(data.caller, *_REVIEW_GROUPS)
        analysis = await self._repository.get_agent_analysis(data.analysis_id)
        if analysis is None or not analysis.prompt_version_id.startswith(
            FULL_AGENTIC_READER_PROMPT_ID_PREFIX
        ):
            raise AgentAnalysisNotFound(f"Agent analysis {data.analysis_id} not found")
        analysis.record_feedback(data.feedback, data.comment, data.caller.id, _now())
        await self._repository.save_agent_analysis(analysis)
        return analysis
