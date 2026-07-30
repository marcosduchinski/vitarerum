from __future__ import annotations

import math
from typing import Annotated, Protocol

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.external_publications.application.ports import (
    PublicationFilters,
    PublishableResourceFilters,
    PublishedInSituVisitReportView,
    PublishedProjectView,
    PublishedProposalView,
)
from app.external_publications.application.use_cases import (
    CreateExternalPublicationInput,
    JsonLdUnavailable,
    PublicationNotFound,
    PublishedResourceNotEligible,
    PublishedResourceNotFound,
)
from app.external_publications.domain.models import (
    ExternalPublication,
    ExternalPublicationId,
    ExternalPublicationProfile,
    ExternalPublicationResourceType,
    ExternalPublicationStatus,
)
from app.external_publications.presentation.dependencies import (
    CreateUseCase,
    DBSession,
    JsonLdUseCase,
    ListAccessesUseCase,
    ListPublishableUseCase,
    ListUseCase,
    ResolveUseCase,
    RevokeUseCase,
)
from app.external_publications.presentation.schemas import (
    CreateExternalPublicationRequest,
    ExternalCidocResponse,
    ExternalInSituVisitReportResponse,
    ExternalNarrativeResponse,
    ExternalObjectResponse,
    ExternalProjectResponse,
    ExternalProposalResponse,
    ExternalPublicationAccessResponse,
    ExternalPublicationResponse,
    PaginatedExternalPublicationAccessesResponse,
    PaginatedExternalPublicationsResponse,
    PaginatedPublishableResourcesResponse,
    PublishableResourceResponse,
)
from app.identity.public import GroupName
from app.shared.authorization import require_group
from app.shared.dependencies import CallerPermission
from app.shared.tokens import hash_opaque_token

external_publications_router = APIRouter(
    prefix="/external-publications",
    tags=["external-publications"],
)
external_public_router = APIRouter(
    prefix="/external/publications",
    tags=["external-publications-public"],
)


class _ObjectLike(Protocol):
    id: str
    inventory_number: str
    display_title: str | None
    object_name: str | None
    brief_description_snapshot: str | None
    category: str
    description: str


@external_publications_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ExternalPublicationResponse,
)
async def create_external_publication(
    request: Request,
    body: CreateExternalPublicationRequest,
    caller: CallerPermission,
    use_case: CreateUseCase,
    session: DBSession,
) -> ExternalPublicationResponse:
    require_group(caller, GroupName.SYS_ADMIN)
    try:
        output = await use_case.execute(
            CreateExternalPublicationInput(
                resource_type=body.resourceType,
                resource_id=body.resourceId,
                access_mode=body.accessMode,
                profile=body.profile,
                expires_at=body.expiresAt,
                created_by=caller.id,
            )
        )
    except PublishedResourceNotFound as exc:
        raise _not_found("PUBLISHED_RESOURCE_NOT_FOUND", str(exc)) from None
    except PublishedResourceNotEligible as exc:
        raise _conflict("PUBLISHED_RESOURCE_NOT_ELIGIBLE", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable("INVALID_EXTERNAL_PUBLICATION", str(exc)) from None
    await session.commit()
    url = (
        str(request.url_for("get_external_publication", token=output.token))
        if output.token is not None
        else None
    )
    return _publication_response(output.publication, url=url)


@external_publications_router.get(
    "",
    response_model=PaginatedExternalPublicationsResponse,
)
async def list_external_publications(
    caller: CallerPermission,
    use_case: ListUseCase,
    resource_type: Annotated[
        ExternalPublicationResourceType | None,
        Query(alias="resourceType"),
    ] = None,
    resource_id: Annotated[str | None, Query(alias="resourceId")] = None,
    publication_status: Annotated[
        ExternalPublicationStatus | None,
        Query(alias="status"),
    ] = None,
    profile: ExternalPublicationProfile | None = None,
    q: str | None = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedExternalPublicationsResponse:
    require_group(caller, GroupName.SYS_ADMIN)
    items, total = await use_case.execute(
        PublicationFilters(
            resource_type=resource_type,
            resource_id=resource_id,
            status=publication_status,
            profile=profile,
            q=q,
        ),
        page,
        size,
    )
    return PaginatedExternalPublicationsResponse(
        content=[_publication_response(item) for item in items],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@external_publications_router.get(
    "/publishable-resources",
    response_model=PaginatedPublishableResourcesResponse,
)
async def list_publishable_resources(
    caller: CallerPermission,
    use_case: ListPublishableUseCase,
    resource_type: Annotated[
        ExternalPublicationResourceType,
        Query(alias="resourceType"),
    ],
    q: str | None = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedPublishableResourcesResponse:
    require_group(caller, GroupName.SYS_ADMIN)
    items, total = await use_case.execute(
        PublishableResourceFilters(resource_type=resource_type, q=q),
        page,
        size,
    )
    return PaginatedPublishableResourcesResponse(
        content=[
            PublishableResourceResponse(
                id=item.id,
                resourceType=item.resource_type,
                reference=item.reference,
                title=item.title,
                status=item.status,
                subtitle=item.subtitle,
            )
            for item in items
        ],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@external_publications_router.get(
    "/{publication_id}/accesses",
    response_model=PaginatedExternalPublicationAccessesResponse,
)
async def list_external_publication_accesses(
    publication_id: str,
    caller: CallerPermission,
    use_case: ListAccessesUseCase,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedExternalPublicationAccessesResponse:
    require_group(caller, GroupName.SYS_ADMIN)
    try:
        items, total = await use_case.execute(
            ExternalPublicationId(publication_id),
            page,
            size,
        )
    except PublicationNotFound as exc:
        raise _not_found("EXTERNAL_PUBLICATION_NOT_FOUND", str(exc)) from None
    return PaginatedExternalPublicationAccessesResponse(
        content=[
            ExternalPublicationAccessResponse(
                id=item.id,
                publicationId=item.publication_id,
                accessedAt=item.accessed_at,
                accessMode=item.access_mode,
                integrationClientId=item.integration_client_id,
                remoteAddrHash=item.remote_addr_hash,
                userAgent=item.user_agent,
                outcome=item.outcome,
            )
            for item in items
        ],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@external_publications_router.patch(
    "/{publication_id}/revoke",
    response_model=ExternalPublicationResponse,
)
async def revoke_external_publication(
    publication_id: str,
    caller: CallerPermission,
    use_case: RevokeUseCase,
    session: DBSession,
) -> ExternalPublicationResponse:
    require_group(caller, GroupName.SYS_ADMIN)
    try:
        publication = await use_case.execute(
            ExternalPublicationId(publication_id),
            caller.id,
        )
    except PublicationNotFound as exc:
        raise _not_found("EXTERNAL_PUBLICATION_NOT_FOUND", str(exc)) from None
    await session.commit()
    return _publication_response(publication)


@external_public_router.get("/{token}", name="get_external_publication")
async def get_external_publication(
    token: str,
    request: Request,
    use_case: ResolveUseCase,
    session: DBSession,
) -> (
    ExternalProposalResponse
    | ExternalProjectResponse
    | ExternalInSituVisitReportResponse
):
    try:
        resolved = await use_case.execute(
            token,
            remote_addr_hash=_remote_addr_hash(request),
            user_agent=request.headers.get("user-agent"),
        )
    except PublicationNotFound as exc:
        await session.commit()
        raise _not_found("EXTERNAL_PUBLICATION_NOT_FOUND", str(exc)) from None
    await session.commit()
    json_ld_url = str(request.url_for("get_external_publication_json_ld", token=token))
    return _resource_response(
        resolved.resource,
        resolved.publication.profile,
        json_ld_url,
    )


@external_public_router.get("/{token}/json-ld", name="get_external_publication_json_ld")
async def get_external_publication_json_ld(
    token: str,
    request: Request,
    use_case: JsonLdUseCase,
    session: DBSession,
) -> Response:
    try:
        document = await use_case.execute(
            token,
            remote_addr_hash=_remote_addr_hash(request),
            user_agent=request.headers.get("user-agent"),
        )
    except PublicationNotFound as exc:
        await session.commit()
        raise _not_found("EXTERNAL_PUBLICATION_NOT_FOUND", str(exc)) from None
    except JsonLdUnavailable as exc:
        await session.commit()
        raise _conflict("JSON_LD_UNAVAILABLE", str(exc)) from None
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(document),
        media_type="application/ld+json",
        headers={"Cache-Control": "private, max-age=300"},
    )


def _publication_response(
    publication: ExternalPublication,
    *,
    url: str | None = None,
) -> ExternalPublicationResponse:
    return ExternalPublicationResponse(
        id=publication.id,
        resourceType=publication.resource_type,
        resourceId=publication.resource_id,
        status=publication.status,
        accessMode=publication.access_mode,
        profile=publication.profile,
        expiresAt=publication.expires_at,
        url=url,
        createdAt=publication.created_at,
        publishedAt=publication.published_at,
        revokedAt=publication.revoked_at,
    )


def _resource_response(
    resource: object,
    profile: ExternalPublicationProfile,
    json_ld_url: str,
) -> (
    ExternalProposalResponse
    | ExternalProjectResponse
    | ExternalInSituVisitReportResponse
):
    if isinstance(resource, PublishedProposalView):
        is_summary = profile == ExternalPublicationProfile.SUMMARY
        return ExternalProposalResponse(
            id=resource.id,
            referenceNumber=resource.reference_number,
            title=resource.title,
            purpose=None if is_summary else resource.purpose,
            intendedUse=resource.intended_use,
            status=resource.status,
            beginDate=resource.begin_date,
            endDate=resource.end_date,
            submittedAt=resource.submitted_at,
            requestedObjects=[
                _object_response(obj) for obj in resource.requested_objects
            ]
            if not is_summary
            else [],
            projectId=resource.project_id,
        )
    if isinstance(resource, PublishedProjectView):
        is_summary = profile == ExternalPublicationProfile.SUMMARY
        return ExternalProjectResponse(
            id=resource.id,
            referenceNumber=resource.reference_number,
            title=resource.title,
            purpose=None if is_summary else resource.purpose,
            intendedUse=None if is_summary else resource.intended_use,
            status=resource.status,
            beginDate=resource.begin_date,
            endDate=resource.end_date,
            objects=[_object_response(obj) for obj in resource.objects]
            if not is_summary
            else [],
            originProjectId=resource.origin_project_id,
            proposalId=resource.proposal_id,
        )
    if isinstance(resource, PublishedInSituVisitReportView):
        is_summary = profile == ExternalPublicationProfile.SUMMARY
        return ExternalInSituVisitReportResponse(
            id=resource.id,
            projectId=resource.project_id,
            createdAt=resource.created_at,
            code=resource.code,
            visitorName=resource.visitor_name,
            placeName=resource.place_name,
            visitBeginDate=resource.visit_begin_date,
            visitEndDate=resource.visit_end_date,
            narrative=(
                ExternalNarrativeResponse(
                    id=resource.narrative.id,
                    text=resource.narrative.text,
                )
                if resource.narrative is not None and not is_summary
                else None
            ),
            cidoc=ExternalCidocResponse(
                recordId=resource.cidoc.record_id,
                jsonLdUrl=json_ld_url,
                conforms=resource.cidoc.conforms,
                mappingVersion=resource.cidoc.mapping_version,
                crmVersion=resource.cidoc.crm_version,
            ),
        )
    raise TypeError(f"Unsupported external resource type {type(resource).__name__}")


def _object_response(obj: _ObjectLike) -> ExternalObjectResponse:
    return ExternalObjectResponse(
        id=obj.id,
        inventoryNumber=obj.inventory_number,
        displayTitle=obj.display_title,
        objectName=obj.object_name,
        briefDescriptionSnapshot=obj.brief_description_snapshot,
        category=obj.category,
        description=obj.description,
    )


def _remote_addr_hash(request: Request) -> str | None:
    if request.client is None:
        return None
    return hash_opaque_token(request.client.host)


def _not_found(error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": error, "message": message},
    )


def _conflict(error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": error, "message": message},
    )


def _unprocessable(error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error": error, "message": message},
    )
