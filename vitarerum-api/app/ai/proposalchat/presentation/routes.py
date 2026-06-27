"""ProposalChat endpoints (the driving adapter).

Two staff-only reads/actions over the triage context. Errors use the shared
``{ "error": CODE, "message": str }`` shape via ``HTTPException(detail=...)`` and
``main.py``'s normaliser; staff denial flows through ``AccessDenied`` → 403.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.ai.proposalchat.application.authorization import assert_triage_access
from app.ai.proposalchat.application.use_cases import SuggestIntendedUseCommand
from app.ai.proposalchat.domain.models import EmptyMessageBody
from app.ai.proposalchat.domain.ports import (
    ConversationNotFoundError,
    MessageNotFoundError,
    ModelTimeout,
    ModelUnavailable,
)
from app.ai.proposalchat.presentation.dependencies import (
    SuggestUseCase,
    TriageContextUseCase,
)
from app.ai.proposalchat.presentation.schemas import (
    FocusMessageModel,
    IntendedUseModel,
    ProposalSummaryModel,
    SuggestionBody,
    SuggestionRequest,
    SuggestionResponse,
    SuggestionSource,
    TriageContextResponse,
)
from app.shared.dependencies import CallerPermission

proposalchat_router = APIRouter(prefix="/proposalchat", tags=["proposalchat"])


def _not_found(code: str, conversation_id: str, message_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": code,
            "message": (
                f"No message found with id {message_id} "
                f"in conversation {conversation_id}"
                if code == "MESSAGE_NOT_FOUND"
                else f"No conversation found with id {conversation_id}"
            ),
        },
    )


@proposalchat_router.get("/context", response_model=TriageContextResponse)
async def get_context(
    caller: CallerPermission,
    use_case: TriageContextUseCase,
    conversationId: Annotated[str, Query()],
    messageId: Annotated[str, Query()],
) -> TriageContextResponse:
    assert_triage_access(caller)
    try:
        context = await use_case.execute(conversationId, messageId)
    except ConversationNotFoundError:
        raise _not_found("CONVERSATION_NOT_FOUND", conversationId, messageId) from None
    except MessageNotFoundError:
        raise _not_found("MESSAGE_NOT_FOUND", conversationId, messageId) from None

    return TriageContextResponse(
        conversationId=conversationId,
        focusMessage=FocusMessageModel(
            messageId=messageId,
            sentAt=context.focus.sent_at,
            sender=context.focus.sender,
            subject=context.focus.subject,
            body=context.focus.body,
        ),
        proposal=ProposalSummaryModel(
            proposalId=context.proposal.proposal_id,
            referenceNumber=context.proposal.reference_number,
            title=context.proposal.title,
            status=context.proposal.status,
            intendedUse=IntendedUseModel(
                useType=context.proposal.intended_use.use_type.value,
                description=context.proposal.intended_use.description,
            ),
        ),
    )


@proposalchat_router.post(
    "/intended-use-suggestions",
    response_model=SuggestionResponse,
    status_code=status.HTTP_200_OK,
)
async def suggest_intended_use(
    body: SuggestionRequest,
    caller: CallerPermission,
    service: SuggestUseCase,
) -> SuggestionResponse:
    assert_triage_access(caller)
    try:
        suggestion = await service.handle(
            SuggestIntendedUseCommand(
                conversation_id=body.conversationId,
                message_id=body.messageId,
            )
        )
    except EmptyMessageBody as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "EMPTY_MESSAGE_BODY", "message": str(exc)},
        ) from None
    except ConversationNotFoundError:
        raise _not_found(
            "CONVERSATION_NOT_FOUND", body.conversationId, body.messageId
        ) from None
    except MessageNotFoundError:
        raise _not_found(
            "MESSAGE_NOT_FOUND", body.conversationId, body.messageId
        ) from None
    except ModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "MODEL_UNAVAILABLE", "message": str(exc)},
        ) from None
    except ModelTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": "MODEL_TIMEOUT", "message": str(exc)},
        ) from None

    return SuggestionResponse(
        suggestion=SuggestionBody(
            intendedUse=IntendedUseModel(
                useType=suggestion.use_type.value,
                description=suggestion.description,
            ),
            confidence=suggestion.confidence.value,
            rationale=suggestion.rationale,
            source=SuggestionSource(
                conversationId=suggestion.source_conversation_id,
                messageId=suggestion.source_message_id,
            ),
        )
    )
