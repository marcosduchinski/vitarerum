"""Proposal endpoints.

Split out of routes.py (HEXAGONAL_UP.md Step 7); shared helpers live in
common.py and composition in dependencies.py. Paths and contracts unchanged.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated

from fastapi import (
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.config import settings
from app.identity.public import GroupName
from app.shared.authorization import (
    require_staff,
)
from app.shared.dependencies import CallerPermission
from app.shared.persistence import run_with_unique_retry
from app.shared.uploads import (
    ALLOWED_DOCUMENT_MAX_BYTES,
    ALLOWED_DOCUMENT_MAX_COUNT,
    ensure_allowed_document,
)
from app.use_of_collections.application.authorization import (
    assert_proposal_access,
)
from app.use_of_collections.application.ports import (
    ProposalFilters,
)
from app.use_of_collections.application.use_cases import (
    AddRequestedObjects,
    AddRequestedObjectsInput,
    ApproveProposal,
    ApproveProposalInput,
    AssignProposal,
    AssignProposalInput,
    CancelProposal,
    CancelProposalInput,
    DocumentCorrectionInput,
    EditProposalDetails,
    EditProposalDetailsInput,
    ForwardProposal,
    ForwardProposalInput,
    RejectProposal,
    RejectProposalInput,
    RemoveRequestedObject,
    RemoveRequestedObjectInput,
    RequestDocumentCorrections,
    RequestDocumentCorrectionsInput,
    RequestDocuments,
    RequestDocumentsInput,
    SendMessage,
    SendMessageInput,
    SubmitDocuments,
    SubmitDocumentsInput,
    SubmitProposal,
    SubmitProposalInput,
)
from app.use_of_collections.application.use_cases import (
    RequestedDocumentInput as UseCaseDocInput,
)
from app.use_of_collections.application.use_cases import (
    RequestedObjectSnapshotInput as UseCaseObjSnapshotInput,
)
from app.use_of_collections.domain.enums import (
    ProposalStatus,
    SubmissionChannel,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    Document,
    DocumentId,
    DocumentType,
    PermissionId,
    ProposalId,
    RequestedObjectId,
)
from app.use_of_collections.presentation.common import (
    _build_document_response,
    _build_proposal_event,
    _detail_or_none,
    _detail_or_stub,
    _detail_or_stub_or_none,
    _guess_content_type,
    _handle_domain_errors,
    _load_permission_detail,
    _message_response,
    _not_found,
    _requester_contact_response,
    _require_staff_permission_target,
    _stub_perm,
    ensure_docx,
    proposals_router,
    read_upload_capped,
    route_file_reference,
    route_new_id,
    route_now,
)
from app.use_of_collections.presentation.dependencies import (
    AccessEmailSender,
    AmendmentInvitation,
    ConvRepo,
    DBSession,
    FileStorage,
    ListProposalsQuery,
    ProjectRepo,
    ProposalDetailQuery,
    ProposalRepo,
    ReferenceGenerator,
    RequesterProvisioner,
)
from app.use_of_collections.presentation.permissions import (
    hydrate_permission,
    hydrate_permission_or_stub,
)
from app.use_of_collections.presentation.schemas import (
    AddRequestedObjectsRequest,
    ApproveProposalRequest,
    AssignProposalRequest,
    CancelProposalResponse,
    ConversationResponse,
    DocumentCorrectionItemResponse,
    DocumentResponse,
    DocumentsListResponse,
    DualAggregateResponse,
    ForwardProposalRequest,
    MessageResponse,
    PaginatedProposalEventsResponse,
    PaginatedProposalsResponse,
    PermissionDetail,
    ProposalCommandResponse,
    ProposalDetailProjectSummary,
    ProposalDetailResponse,
    ProposalListItemResponse,
    ProposalSummary,
    ReasonRequest,
    RequestDocumentCorrectionsRequest,
    RequestDocumentsRequest,
    RequestedDocumentResponse,
    RequestedObjectResponse,
    SendMessageRequest,
    SubmitProposalResponse,
    UpdateProposalRequest,
    UserSummary,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Proposal endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@proposals_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmitProposalResponse,
)
async def submit_proposal(
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    conversation_repo: ConvRepo,
    file_storage: FileStorage,
    reference_generator: ReferenceGenerator,
    session: DBSession,
    documents: Annotated[list[UploadFile], File(default_factory=list)],
    title: Annotated[str | None, Form()] = None,
    intendedUse: Annotated[UseType | None, Form()] = None,
    purpose: Annotated[str | None, Form()] = None,
    beginDate: Annotated[date | None, Form()] = None,
    endDate: Annotated[date | None, Form()] = None,
    initialMessageRecipient: Annotated[str, Form()] = "",
    initialMessageSubject: Annotated[str, Form()] = "",
    initialMessageBody: Annotated[str, Form()] = "",
) -> SubmitProposalResponse:
    # Dates are optional on submit, but when both are given the range must be valid.
    if beginDate is not None and endDate is not None and endDate < beginDate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "INVALID_DATE_RANGE",
                "message": "endDate must be after beginDate",
            },
        )
    if len(documents) > ALLOWED_DOCUMENT_MAX_COUNT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Validation failed",
                "errors": [
                    {
                        "field": "documents",
                        "message": (
                            f"Attach no more than {ALLOWED_DOCUMENT_MAX_COUNT} "
                            "supporting documents."
                        ),
                    }
                ],
            },
        )

    upload_namespace = route_new_id()
    submitted_at = route_now()
    saved_references: list[str] = []
    submitted_documents: list[Document] = []
    try:
        for upload in documents:
            content = await read_upload_capped(
                upload, limit=ALLOWED_DOCUMENT_MAX_BYTES
            )
            ensure_allowed_document(content)
            file_name = upload.filename or "document"
            reference = route_file_reference("proposals", upload_namespace, file_name)
            file_reference = await file_storage.save(content, reference)
            saved_references.append(file_reference)
            submitted_documents.append(
                Document(
                    id=DocumentId(route_new_id()),
                    type=DocumentType("REQUESTER_ATTACHMENT"),
                    file_name=file_name,
                    file_reference=file_reference,
                    submitted_at=submitted_at,
                    submitted_by=caller.id,
                )
            )
    except Exception:
        for file_reference in saved_references:
            await file_storage.delete(file_reference)
        raise

    use_case = SubmitProposal(proposal_repo, conversation_repo, reference_generator)
    submit_input = SubmitProposalInput(
        title=title,
        intended_use=intendedUse,
        purpose=purpose,
        begin_date=beginDate,
        end_date=endDate,
        requested_by=caller,
        submission_channel=SubmissionChannel.AUTHENTICATED,
        initial_message_recipient=initialMessageRecipient or "collections@museum.pt",
        initial_message_subject=initialMessageSubject,
        initial_message_body=initialMessageBody,
        documents=submitted_documents,
    )
    try:
        output = await run_with_unique_retry(
            session, lambda: use_case.execute(submit_input)
        )
        await session.commit()
    except Exception:
        for file_reference in saved_references:
            await file_storage.delete(file_reference)
        raise

    assert output.proposal.requested_by is not None
    requested_by_detail = await hydrate_permission(
        output.proposal.requested_by, session
    )
    if requested_by_detail is None:
        requested_by_detail = PermissionDetail(
            permissionId=output.proposal.requested_by,
            user=UserSummary(id="", name="", email=caller.email),
            group=caller.group or GroupName.EXTERNAL,
        )

    return SubmitProposalResponse(
        proposal=ProposalSummary(
            id=output.proposal.id,
            referenceNumber=output.proposal.reference_number.value,
            title=output.proposal.title,
            status=output.proposal.status,
            submissionChannel=output.proposal.submission_channel,
            intendedUse=output.proposal.intended_use,
            beginDate=output.proposal.begin_date,
            endDate=output.proposal.end_date,
            requestedBy=requested_by_detail,
            requesterContact=_requester_contact_response(output.proposal),
            assignedTo=None,
            submittedAt=output.proposal.submitted_at,
        ),
        conversationId=output.conversation_id,
    )


@proposals_router.get("", response_model=PaginatedProposalsResponse)
async def list_proposals(
    caller: CallerPermission,
    query: ListProposalsQuery,
    status_filters: Annotated[
        list[ProposalStatus] | None, Query(alias="status")
    ] = None,
    type_filter: Annotated[UseType | None, Query(alias="type")] = None,
    assigned_to: Annotated[str | None, Query()] = None,
    requested_by_filter: Annotated[str | None, Query(alias="requested_by")] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedProposalsResponse:
    result = await query.execute(
        caller,
        ProposalFilters(
            statuses=tuple(status_filters or ()),
            use_type=type_filter,
            assigned_to=assigned_to,
            requested_by=requested_by_filter,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ),
        page,
        size,
    )
    items = [
        ProposalListItemResponse(
            id=item.proposal.id,
            referenceNumber=item.proposal.reference_number.value,
            title=item.proposal.title,
            status=item.proposal.status,
            submissionChannel=item.proposal.submission_channel,
            intendedUse=item.proposal.intended_use,
            beginDate=item.proposal.begin_date,
            endDate=item.proposal.end_date,
            requestedBy=_detail_or_stub_or_none(
                item.requested_by, item.proposal.requested_by
            ),
            requesterContact=_requester_contact_response(item.proposal),
            assignedTo=_detail_or_none(item.assigned_to),
            submittedAt=item.proposal.submitted_at,
        )
        for item in result.items
    ]
    total_pages = math.ceil(result.total / size) if size > 0 else 0
    return PaginatedProposalsResponse(
        content=items,
        page=page,
        size=size,
        totalElements=result.total,
        totalPages=total_pages,
    )


@proposals_router.get("/{proposal_id}", response_model=ProposalDetailResponse)
async def get_proposal(
    proposal_id: str,
    caller: CallerPermission,
    query: ProposalDetailQuery,
) -> ProposalDetailResponse:
    detail = await query.execute(ProposalId(proposal_id), caller)
    if detail is None:
        raise _not_found("proposal", proposal_id)
    proposal = detail.proposal
    project = detail.project

    documents = [
        DocumentResponse(
            id=d.id,
            type=d.type.value,
            fileName=d.file_name,
            fileReference=d.file_reference,
            submittedAt=d.submitted_at,
            submittedBy=_detail_or_stub_or_none(
                detail.view(d.submitted_by), d.submitted_by
            ),
        )
        for d in proposal.documents
    ]
    requested_docs = [
        RequestedDocumentResponse(
            id=rd.id,
            type=rd.type.value,
            description=rd.description,
            requestedAt=rd.requested_at,
            requestedBy=_detail_or_stub(
                detail.view(rd.requested_by),
                rd.requested_by,
                GroupName.COLLECTIONS_MANAGEMENT,
            ),
        )
        for rd in proposal.requested_documents
    ]
    requested_objects = [
        RequestedObjectResponse(
            id=ro.id,
            inventoryNumber=ro.inventory_number,
            displayTitle=ro.display_title,
            objectName=ro.object_name,
            briefDescriptionSnapshot=ro.brief_description_snapshot,
            category=ro.category,
            description=ro.description,
            requestedAt=ro.requested_at,
            requestedBy=(
                _detail_or_stub(detail.view(ro.requested_by), ro.requested_by)
                if ro.requested_by is not None
                else None
            ),
        )
        for ro in proposal.requested_objects
    ]
    correction_items = [
        DocumentCorrectionItemResponse(
            id=ci.id,
            documentType=ci.document_type.value,
            reason=ci.reason,
            status=ci.status.value,
            requestedAt=ci.requested_at,
            requestedBy=_detail_or_stub(
                detail.view(ci.requested_by),
                ci.requested_by,
                GroupName.COLLECTIONS_MANAGEMENT,
            ),
            documentId=ci.document_id,
            resolvedAt=ci.resolved_at,
        )
        for ci in proposal.correction_items
    ]

    return ProposalDetailResponse(
        id=proposal.id,
        referenceNumber=proposal.reference_number.value,
        title=proposal.title,
        status=proposal.status,
        submissionChannel=proposal.submission_channel,
        intendedUse=proposal.intended_use,
        beginDate=proposal.begin_date,
        endDate=proposal.end_date,
        requestedBy=_detail_or_stub_or_none(
            detail.view(proposal.requested_by), proposal.requested_by
        ),
        requesterContact=_requester_contact_response(proposal),
        assignedTo=_detail_or_none(detail.view(proposal.assigned_to)),
        collectionUseProject=ProposalDetailProjectSummary(
            id=project.id if project else "",
            referenceNumber=project.reference_number.value if project else "",
            title=project.title if project else "",
            status=project.status if project else UseStatus.CREATED,
            requestedBy=(
                _detail_or_none(detail.view(project.requested_by)) if project else None
            ),
        ),
        conversationId=detail.conversation_id,
        documents=documents,
        requestedDocuments=requested_docs,
        requestedObjects=requested_objects,
        correctionItems=correction_items,
        submittedAt=proposal.submitted_at,
    )


@proposals_router.patch(
    "/{proposal_id}",
    response_model=ProposalCommandResponse,
)
async def edit_proposal(
    proposal_id: str,
    body: UpdateProposalRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProposalCommandResponse:
    proposal_before = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal_before is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal_before)
    require_staff(caller)

    fields_set = body.model_fields_set
    update_begin = "beginDate" in fields_set
    update_end = "endDate" in fields_set
    # Validate the effective range — the incoming value where supplied,
    # otherwise the stored one — and surface the same 422 as approve/submit.
    effective_begin = body.beginDate if update_begin else proposal_before.begin_date
    effective_end = body.endDate if update_end else proposal_before.end_date
    if (
        effective_begin is not None
        and effective_end is not None
        and effective_end < effective_begin
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "INVALID_DATE_RANGE",
                "message": "endDate must be after beginDate",
            },
        )

    try:
        proposal = await EditProposalDetails(proposal_repo).execute(
            EditProposalDetailsInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                title=body.title,
                update_title="title" in fields_set,
                intended_use=body.intendedUse,
                update_intended_use="intendedUse" in fields_set,
                begin_date=body.beginDate,
                update_begin_date=update_begin,
                end_date=body.endDate,
                update_end_date=update_end,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
        raise
    await session.commit()
    last_event = (
        await _build_proposal_event(proposal.events[-1], session)
        if proposal.events
        else None
    )
    return ProposalCommandResponse(
        id=proposal.id,
        referenceNumber=proposal.reference_number.value,
        title=proposal.title,
        status=proposal.status,
        beginDate=proposal.begin_date,
        endDate=proposal.end_date,
        lastEvent=last_event,
    )


@proposals_router.post(
    "/{proposal_id}/assign",
    response_model=ProposalCommandResponse,
)
async def assign_proposal(
    proposal_id: str,
    body: AssignProposalRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProposalCommandResponse:
    proposal_before = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal_before is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal_before)
    require_staff(caller)
    target_permission_id = (
        PermissionId(body.targetPermissionId) if body.targetPermissionId else None
    )
    if target_permission_id is not None:
        await _require_staff_permission_target(target_permission_id, session)
    try:
        proposal = await AssignProposal(proposal_repo).execute(
            AssignProposalInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                target_permission_id=target_permission_id,
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    assigned_to = await hydrate_permission_or_stub(proposal.assigned_to, session)
    last_event = (
        await _build_proposal_event(proposal.events[-1], session)
        if proposal.events
        else None
    )
    return ProposalCommandResponse(
        id=proposal.id,
        referenceNumber=proposal.reference_number.value,
        title=proposal.title,
        status=proposal.status,
        beginDate=proposal.begin_date,
        endDate=proposal.end_date,
        assignedTo=assigned_to,
        lastEvent=last_event,
    )


@proposals_router.post(
    "/{proposal_id}/requested-objects",
    status_code=status.HTTP_201_CREATED,
    response_model=ProposalDetailResponse,
)
async def add_requested_objects(
    proposal_id: str,
    body: AddRequestedObjectsRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    detail_query: ProposalDetailQuery,
    session: DBSession,
) -> ProposalDetailResponse:
    proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal)
    try:
        await AddRequestedObjects(proposal_repo).execute(
            AddRequestedObjectsInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                objects=[
                    UseCaseObjSnapshotInput(
                        inventory_number=o.inventoryNumber,
                        display_title=o.displayTitle,
                        object_name=o.objectName,
                        brief_description_snapshot=o.briefDescriptionSnapshot,
                        category=o.category,
                        description=o.description,
                    )
                    for o in body.objects
                ],
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return await get_proposal(proposal_id, caller, detail_query)


@proposals_router.delete(
    "/{proposal_id}/requested-objects/{requested_object_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_requested_object(
    proposal_id: str,
    requested_object_id: str,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> Response:
    proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal)
    try:
        await RemoveRequestedObject(proposal_repo).execute(
            RemoveRequestedObjectInput(
                proposal_id=ProposalId(proposal_id),
                requested_object_id=RequestedObjectId(requested_object_id),
                caller=caller,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@proposals_router.post(
    "/{proposal_id}/request-documents",
    response_model=ProposalCommandResponse,
)
async def request_documents(
    proposal_id: str,
    body: RequestDocumentsRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProposalCommandResponse:
    proposal_before = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal_before is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal_before)
    require_staff(caller)
    try:
        proposal = await RequestDocuments(proposal_repo).execute(
            RequestDocumentsInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                required_documents=[
                    UseCaseDocInput(doc_type=d.type, description=d.description)
                    for d in body.requiredDocuments
                ],
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    last_event = (
        await _build_proposal_event(proposal.events[-1], session)
        if proposal.events
        else None
    )
    return ProposalCommandResponse(
        id=proposal.id,
        referenceNumber=proposal.reference_number.value,
        title=proposal.title,
        status=proposal.status,
        beginDate=proposal.begin_date,
        endDate=proposal.end_date,
        lastEvent=last_event,
    )


@proposals_router.post(
    "/{proposal_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
)
async def submit_documents(
    proposal_id: str,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    file_storage: FileStorage,
    session: DBSession,
    file: Annotated[UploadFile, File(...)],
    documentType: Annotated[str, Form(...)],
) -> DocumentResponse:
    proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal)
    if not file.filename or not file.filename.endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error": "INVALID_FILE_FORMAT",
                "message": "Only .docx files are accepted",
            },
        )
    content = await read_upload_capped(file)
    ensure_docx(content)
    try:
        document = await SubmitDocuments(proposal_repo, file_storage).execute(
            SubmitDocumentsInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                file_content=content,
                file_name=file.filename,
                document_type=documentType,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
        raise
    await session.commit()
    return await _build_document_response(document, session)


@proposals_router.get(
    "/{proposal_id}/documents",
    response_model=DocumentsListResponse,
)
async def list_documents(
    proposal_id: str,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> DocumentsListResponse:
    proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal)
    docs = [await _build_document_response(d, session) for d in proposal.documents]
    return DocumentsListResponse(proposalId=proposal_id, documents=docs)


@proposals_router.get("/{proposal_id}/documents/{document_id}")
async def download_document(
    proposal_id: str,
    document_id: str,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    file_storage: FileStorage,
) -> Response:
    proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal)
    document = next((d for d in proposal.documents if d.id == document_id), None)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "NOT_FOUND",
                "message": "Document not found for this proposal",
            },
        )
    try:
        content = await file_storage.read(document.file_reference)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "NOT_FOUND",
                "message": "Document not found for this proposal",
            },
        ) from exc
    return Response(
        content=content,
        media_type=_guess_content_type(document.file_name),
        headers={"Content-Disposition": f'attachment; filename="{document.file_name}"'},
    )


@proposals_router.post(
    "/{proposal_id}/forward",
    response_model=ProposalCommandResponse,
)
async def forward_proposal(
    proposal_id: str,
    body: ForwardProposalRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProposalCommandResponse:
    proposal_before = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal_before is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal_before)
    require_staff(caller)
    target_permission_id = PermissionId(body.targetPermissionId)
    await _require_staff_permission_target(target_permission_id, session)
    try:
        proposal = await ForwardProposal(proposal_repo).execute(
            ForwardProposalInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                target_permission_id=target_permission_id,
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
        raise
    await session.commit()
    assigned_to = await hydrate_permission_or_stub(proposal.assigned_to, session)
    last_event = (
        await _build_proposal_event(proposal.events[-1], session)
        if proposal.events
        else None
    )
    return ProposalCommandResponse(
        id=proposal.id,
        referenceNumber=proposal.reference_number.value,
        title=proposal.title,
        status=proposal.status,
        beginDate=proposal.begin_date,
        endDate=proposal.end_date,
        assignedTo=assigned_to,
        lastEvent=last_event,
    )


@proposals_router.post(
    "/{proposal_id}/approve",
    response_model=DualAggregateResponse,
)
async def approve_proposal(
    proposal_id: str,
    body: ApproveProposalRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    project_repo: ProjectRepo,
    requester_provisioner: RequesterProvisioner,
    access_email_sender: AccessEmailSender,
    reference_generator: ReferenceGenerator,
    session: DBSession,
) -> DualAggregateResponse:
    proposal_before = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal_before is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal_before)
    if body.endDate < body.beginDate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "INVALID_DATE_RANGE",
                "message": "endDate must be after beginDate",
            },
        )
    try:
        output = await ApproveProposal(
            proposal_repo, project_repo, requester_provisioner, reference_generator
        ).execute(
            ApproveProposalInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                title=body.title,
                purpose=body.purpose,
                begin_date=body.beginDate,
                end_date=body.endDate,
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
        raise
    await session.commit()
    # Only after the approval (and any newly provisioned user) is durably
    # committed do we hand out its credentials — a citizen must never receive
    # a password for an account that was rolled back. If sending fails here,
    # the approval itself is not undone: this is an operational delivery
    # problem, not a domain failure (mirrors the confirmation-e-mail ordering
    # in public_submission's SubmitPublicProposal route).
    notification = output.requester_access_notification
    if notification is not None:
        await access_email_sender.send_access_created(
            to_email=notification.email,
            requester_name=notification.name,
            login_url=f"{settings.public_origin}/login",
            temporary_password=notification.temporary_password,
        )
    last_event = (
        await _build_proposal_event(output.proposal.events[-1], session)
        if output.proposal.events
        else None
    )
    project_requested_by = await hydrate_permission_or_stub(
        output.project.requested_by, session
    )
    return DualAggregateResponse(
        proposal=ProposalCommandResponse(
            id=output.proposal.id,
            referenceNumber=output.proposal.reference_number.value,
            title=output.proposal.title,
            status=output.proposal.status,
            beginDate=output.proposal.begin_date,
            endDate=output.proposal.end_date,
            lastEvent=last_event,
        ),
        collectionUseProject=ProposalDetailProjectSummary(
            id=output.project.id,
            referenceNumber=output.project.reference_number.value,
            title=output.project.title,
            status=output.project.status,
            requestedBy=project_requested_by or _stub_perm(output.project.requested_by),
        ),
    )


@proposals_router.post(
    "/{proposal_id}/reject",
    response_model=ProposalCommandResponse,
)
async def reject_proposal(
    proposal_id: str,
    body: ReasonRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    conversation_repo: ConvRepo,
    session: DBSession,
) -> ProposalCommandResponse:
    proposal_before = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal_before is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal_before)
    requester = (
        await _load_permission_detail(proposal_before.requested_by, session)
        if proposal_before.requested_by is not None
        else None
    )
    requester_email = (
        requester.user.email
        if requester is not None
        else proposal_before.requester_contact.email.value
        if proposal_before.requester_contact is not None
        else None
    )
    if requester_email is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "MISSING_REQUESTER_CONTACT",
                "message": "Proposal has no requester contact.",
            },
        )
    try:
        output = await RejectProposal(proposal_repo, conversation_repo).execute(
            RejectProposalInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                reason=body.reason,
                requester_email=requester_email,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
        raise
    await session.commit()
    last_event = (
        await _build_proposal_event(output.proposal.events[-1], session)
        if output.proposal.events
        else None
    )
    return ProposalCommandResponse(
        id=output.proposal.id,
        referenceNumber=output.proposal.reference_number.value,
        title=output.proposal.title,
        status=output.proposal.status,
        beginDate=output.proposal.begin_date,
        endDate=output.proposal.end_date,
        lastEvent=last_event,
    )


@proposals_router.post(
    "/{proposal_id}/request-document-corrections",
    response_model=ProposalCommandResponse,
)
async def request_document_corrections(
    proposal_id: str,
    body: RequestDocumentCorrectionsRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    invitation: AmendmentInvitation,
    session: DBSession,
) -> ProposalCommandResponse:
    proposal_before = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal_before is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal_before)
    require_staff(caller)
    if not body.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "NO_CORRECTION_ITEMS",
                "message": "At least one correction item is required.",
            },
        )
    # Resolve the requester's name/e-mail: an authenticated requester via their
    # permission, otherwise the public requester contact (same order as reject).
    requester = (
        await _load_permission_detail(proposal_before.requested_by, session)
        if proposal_before.requested_by is not None
        else None
    )
    if requester is not None:
        requester_email = requester.user.email
        requester_name = requester.user.name
    elif proposal_before.requester_contact is not None:
        requester_email = proposal_before.requester_contact.email.value
        requester_name = proposal_before.requester_contact.name
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "MISSING_REQUESTER_CONTACT",
                "message": "Proposal has no requester contact.",
            },
        )
    try:
        output = await RequestDocumentCorrections(proposal_repo).execute(
            RequestDocumentCorrectionsInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                items=[
                    DocumentCorrectionInput(
                        document_type=item.documentType,
                        reason=item.reason,
                        document_id=item.documentId,
                    )
                    for item in body.items
                ],
                requester_email=requester_email,
                requester_name=requester_name,
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
        raise
    await session.commit()
    # Dispatch the tokenised e-mail invitation only after the correction items are
    # durably committed, so the citizen never gets a link to items that rolled back.
    await invitation.invite_document_corrections(
        proposal_id=ProposalId(proposal_id),
        requester_email=output.requester_email,
        requester_name=output.requester_name,
        correction_item_ids=output.correction_item_ids,
    )
    last_event = (
        await _build_proposal_event(output.proposal.events[-1], session)
        if output.proposal.events
        else None
    )
    return ProposalCommandResponse(
        id=output.proposal.id,
        referenceNumber=output.proposal.reference_number.value,
        title=output.proposal.title,
        status=output.proposal.status,
        beginDate=output.proposal.begin_date,
        endDate=output.proposal.end_date,
        lastEvent=last_event,
    )


@proposals_router.post(
    "/{proposal_id}/cancel",
    response_model=CancelProposalResponse,
)
async def cancel_proposal(
    proposal_id: str,
    body: ReasonRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    project_repo: ProjectRepo,
    session: DBSession,
) -> CancelProposalResponse:
    try:
        output = await CancelProposal(proposal_repo, project_repo).execute(
            CancelProposalInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                reason=body.reason,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
        raise
    await session.commit()
    proposal_last_event = (
        await _build_proposal_event(output.proposal.events[-1], session)
        if output.proposal.events
        else None
    )
    project_summary = None
    if output.project is not None:
        project_requested_by = await hydrate_permission_or_stub(
            output.project.requested_by, session
        )
        project_summary = ProposalDetailProjectSummary(
            id=output.project.id,
            referenceNumber=output.project.reference_number.value,
            title=output.project.title,
            status=output.project.status,
            requestedBy=project_requested_by or _stub_perm(output.project.requested_by),
        )
    return CancelProposalResponse(
        proposal=ProposalCommandResponse(
            id=output.proposal.id,
            referenceNumber=output.proposal.reference_number.value,
            title=output.proposal.title,
            status=output.proposal.status,
            beginDate=output.proposal.begin_date,
            endDate=output.proposal.end_date,
            lastEvent=proposal_last_event,
        ),
        collectionUseProject=project_summary,
    )


@proposals_router.get(
    "/{proposal_id}/events",
    response_model=PaginatedProposalEventsResponse,
)
async def list_proposal_events(
    proposal_id: str,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    session: DBSession,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedProposalEventsResponse:
    proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal)
    all_events = proposal.events
    total = len(all_events)
    page_events = all_events[page * size : page * size + size]
    items = [await _build_proposal_event(e, session) for e in page_events]
    return PaginatedProposalEventsResponse(
        proposalId=proposal_id,
        content=items,
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@proposals_router.get(
    "/{proposal_id}/conversation",
    response_model=ConversationResponse,
)
async def get_conversation(
    proposal_id: str,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    conversation_repo: ConvRepo,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConversationResponse:
    proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal)
    conversation = await conversation_repo.get_by_proposal_id(ProposalId(proposal_id))
    if conversation is None:
        raise _not_found("conversation", proposal_id)
    all_messages = conversation.messages
    total = len(all_messages)
    page_messages = all_messages[page * size : page * size + size]
    return ConversationResponse(
        conversationId=conversation.id,
        proposalId=proposal_id,
        messages=[_message_response(m) for m in page_messages],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@proposals_router.post(
    "/{proposal_id}/conversation/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=MessageResponse,
)
async def send_message(
    proposal_id: str,
    body: SendMessageRequest,
    caller: CallerPermission,
    proposal_repo: ProposalRepo,
    conversation_repo: ConvRepo,
    session: DBSession,
) -> MessageResponse:
    proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))
    if proposal is None:
        raise _not_found("proposal", proposal_id)
    assert_proposal_access(caller, proposal)
    try:
        message = await SendMessage(proposal_repo, conversation_repo).execute(
            SendMessageInput(
                proposal_id=ProposalId(proposal_id),
                caller=caller,
                recipient=body.recipient,
                subject=body.subject,
                body=body.body,
                document_ids=body.documentIds,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
        await session.rollback()
        raise
    await session.commit()
    return _message_response(message)
