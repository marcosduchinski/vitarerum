"""Collection Data Sources management endpoints.

Staff-only, with two scopes (enforced by the use cases — the frontend menu is
not a security boundary): SYS_ADMIN alone administers the collection catalog
(create/rename/remove a collection, assign/remove curators) — removal is
permanent, taking curators/documents/index/files with it; SYS_ADMIN and
COLLECTIONS_MANAGEMENT manage any collection's source documents, CURATORIAL
manages only assigned collections.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError

from app.collection_object_index.application.ports import (
    CollectionObjectSearchQuery,
    SearchHit,
)
from app.collection_object_index.application.read_models import CollectionView
from app.collection_object_index.application.use_cases import (
    AssignCollectionCurator,
    CreateCollection,
    CreateCollectionInput,
    DeleteSourceDocument,
    GetCollection,
    ListCollectionSourceDocuments,
    ListCuratorCandidates,
    ListManageableCollections,
    ListSearchableCollections,
    ReindexSourceDocument,
    RemoveCollection,
    RemoveCollectionCurator,
    SearchCollectionObjects,
    UpdateCollection,
    UpdateCollectionInput,
    UploadSourceDocument,
    UploadSourceDocumentInput,
)
from app.collection_object_index.domain.models import (
    CollectionId,
    CollectionNotFound,
    SourceDocument,
    SourceDocumentId,
    SourceDocumentNotFound,
)
from app.collection_object_index.presentation.dependencies import (
    CollectionRepo,
    DBSession,
    IndexClock,
    ObjectIndex,
    SourceDocumentRepo,
    SourceFileStorage,
    SourceParser,
)
from app.collection_object_index.presentation.schemas import (
    AssignCuratorRequest,
    CollectionResponse,
    CreateCollectionRequest,
    CuratorCandidateResponse,
    CuratorResponse,
    SearchableCollectionResponse,
    SearchHitResponse,
    SearchResultResponse,
    SourceDocumentResponse,
    UpdateCollectionRequest,
)
from app.identity.public import GroupName, get_permission_reader
from app.identity.public import PermissionId as IdentityPermissionId
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission
from app.shared.kernel import PermissionId
from app.shared.uploads import ensure_xlsx, read_upload_capped, safe_basename

logger = logging.getLogger(__name__)

collection_data_sources_router = APIRouter(
    prefix="/admin/collection-data-sources", tags=["collection-data-sources"]
)

# Read-only, broadly staff-accessible search over indexed collection objects —
# a separate router (and top-level path) from the admin management one above,
# matching the "Objects -> Search" menu entry.
object_search_router = APIRouter(prefix="/objects", tags=["objects-search"])


def _not_found(resource: str, code: str, resource_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": code,
            "message": f"No {resource} found with id {resource_id}",
        },
    )


def _collection_name_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "COLLECTION_NAME_ALREADY_EXISTS",
            "message": "A collection with this name already exists",
        },
    )


def _invalid_collection_name(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error": "INVALID_COLLECTION_NAME", "message": str(exc)},
    )


def _permission_not_curatorial() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "error": "PERMISSION_NOT_CURATORIAL",
            "message": "Only permissions in the CURATORIAL group can be assigned "
            "as curators",
        },
    )


def _document_response(document: SourceDocument) -> SourceDocumentResponse:
    return SourceDocumentResponse(
        id=document.id,
        collectionId=document.collection_id,
        fileName=document.file_name,
        sourceKind=document.source_kind.value,
        status=document.status.value,
        errorMessage=document.error_message,
        rowCount=document.row_count,
        uploadedAt=document.uploaded_at,
        indexedAt=document.indexed_at,
    )


async def _collection_response(
    view: CollectionView, session: DBSession
) -> CollectionResponse:
    # Curator names/e-mails come from Identity's published reader; a curator
    # whose permission no longer resolves still lists by permission id.
    reader = get_permission_reader(session)
    curators = []
    for assignment in view.curators:
        detail = await reader.get_detail(IdentityPermissionId(assignment.permission_id))
        curators.append(
            CuratorResponse(
                permissionId=assignment.permission_id,
                name=detail.user.name if detail else None,
                email=detail.user.email if detail else None,
                assignedAt=assignment.assigned_at,
            )
        )
    return CollectionResponse(
        id=view.collection.id,
        name=view.collection.name,
        curators=curators,
        documentCount=view.document_count,
        manageable=view.manageable,
    )


@collection_data_sources_router.get(
    "/collections", response_model=list[CollectionResponse]
)
async def list_collections(
    caller: CallerPermission,
    collections: CollectionRepo,
    session: DBSession,
) -> list[CollectionResponse]:
    require_staff(caller)
    views = await ListManageableCollections(collections).execute(caller)
    return [await _collection_response(view, session) for view in views]


@collection_data_sources_router.post(
    "/collections",
    status_code=status.HTTP_201_CREATED,
    response_model=CollectionResponse,
)
async def create_collection(
    body: CreateCollectionRequest,
    caller: CallerPermission,
    collections: CollectionRepo,
    clock: IndexClock,
    session: DBSession,
) -> CollectionResponse:
    try:
        collection = await CreateCollection(collections, clock).execute(
            CreateCollectionInput(caller=caller, name=body.name)
        )
    except ValueError as exc:
        raise _invalid_collection_name(exc) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise _collection_name_conflict() from exc
    await session.commit()
    view = await GetCollection(collections).execute(caller, collection.id)
    return await _collection_response(view, session)


@collection_data_sources_router.get(
    "/collections/{collection_id}", response_model=CollectionResponse
)
async def get_collection(
    collection_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    session: DBSession,
) -> CollectionResponse:
    require_staff(caller)
    try:
        view = await GetCollection(collections).execute(
            caller, CollectionId(collection_id)
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    return await _collection_response(view, session)


@collection_data_sources_router.patch(
    "/collections/{collection_id}", response_model=CollectionResponse
)
async def update_collection(
    collection_id: str,
    body: UpdateCollectionRequest,
    caller: CallerPermission,
    collections: CollectionRepo,
    clock: IndexClock,
    session: DBSession,
) -> CollectionResponse:
    try:
        await UpdateCollection(collections, clock).execute(
            UpdateCollectionInput(
                caller=caller,
                collection_id=CollectionId(collection_id),
                name=body.name,
            )
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    except ValueError as exc:
        raise _invalid_collection_name(exc) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise _collection_name_conflict() from exc
    await session.commit()
    view = await GetCollection(collections).execute(caller, CollectionId(collection_id))
    return await _collection_response(view, session)


@collection_data_sources_router.delete(
    "/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_collection(
    collection_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    documents: SourceDocumentRepo,
    index: ObjectIndex,
    storage: SourceFileStorage,
    session: DBSession,
) -> Response:
    """Permanently removes the collection and everything under it — curator
    assignments, source documents, indexed rows, and their files. This cannot
    be undone."""
    try:
        file_references = await RemoveCollection(collections, documents, index).execute(
            caller, CollectionId(collection_id)
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    await session.commit()
    # Best-effort file cleanup after the durable delete: storage.delete() is
    # idempotent, so attempting every reference (live or already
    # soft-deleted) is safe; a failure here is logged, not raised — the
    # collection is already gone from the database either way.
    for file_reference in file_references:
        try:
            await storage.delete(file_reference)
        except Exception:
            logger.warning(
                "Failed to delete file %r after removing collection %s",
                file_reference,
                collection_id,
                exc_info=True,
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@collection_data_sources_router.get(
    "/curator-candidates", response_model=list[CuratorCandidateResponse]
)
async def list_curator_candidates(
    caller: CallerPermission,
    session: DBSession,
) -> list[CuratorCandidateResponse]:
    reader = get_permission_reader(session)
    candidates = await ListCuratorCandidates(reader).execute(caller)
    return [
        CuratorCandidateResponse(
            permissionId=c.permission_id, name=c.user.name, email=c.user.email
        )
        for c in candidates
    ]


@collection_data_sources_router.get(
    "/collections/{collection_id}/documents",
    response_model=list[SourceDocumentResponse],
)
async def list_collection_documents(
    collection_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    documents: SourceDocumentRepo,
) -> list[SourceDocumentResponse]:
    require_staff(caller)
    try:
        result = await ListCollectionSourceDocuments(collections, documents).execute(
            caller, CollectionId(collection_id)
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    return [_document_response(d) for d in result]


@collection_data_sources_router.post(
    "/collections/{collection_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceDocumentResponse,
)
async def upload_collection_document(
    collection_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    documents: SourceDocumentRepo,
    storage: SourceFileStorage,
    parser: SourceParser,
    index: ObjectIndex,
    clock: IndexClock,
    session: DBSession,
    file: Annotated[UploadFile, File()],
) -> SourceDocumentResponse:
    require_staff(caller)
    content = await read_upload_capped(file)
    ensure_xlsx(content)
    try:
        result = await UploadSourceDocument(
            collections, documents, storage, parser, index, clock
        ).execute(
            UploadSourceDocumentInput(
                caller=caller,
                collection_id=CollectionId(collection_id),
                file_name=safe_basename(file.filename or "", default="objects.xlsx"),
                content=content,
            )
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    try:
        await session.commit()
    except Exception:
        if result.created:
            await storage.delete(result.document.file_reference)
        raise
    # Committed: a replaced previous version's file is now safe to reclaim.
    if result.replaced_file_reference is not None:
        await storage.delete(result.replaced_file_reference)
    return _document_response(result.document)


@collection_data_sources_router.delete(
    "/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_collection_document(
    document_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    documents: SourceDocumentRepo,
    index: ObjectIndex,
    clock: IndexClock,
    storage: SourceFileStorage,
    session: DBSession,
) -> Response:
    require_staff(caller)
    try:
        file_reference = await DeleteSourceDocument(
            collections, documents, index, clock
        ).execute(caller, SourceDocumentId(document_id))
    except SourceDocumentNotFound as exc:
        raise _not_found(
            "source document", "SOURCE_DOCUMENT_NOT_FOUND", document_id
        ) from exc
    await session.commit()
    # Remove the file only after the soft-delete is durable.
    await storage.delete(file_reference)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@collection_data_sources_router.post(
    "/documents/{document_id}/reindex", response_model=SourceDocumentResponse
)
async def reindex_collection_document(
    document_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    documents: SourceDocumentRepo,
    storage: SourceFileStorage,
    parser: SourceParser,
    index: ObjectIndex,
    clock: IndexClock,
    session: DBSession,
) -> SourceDocumentResponse:
    require_staff(caller)
    try:
        document = await ReindexSourceDocument(
            collections, documents, storage, parser, index, clock
        ).execute(caller, SourceDocumentId(document_id))
    except SourceDocumentNotFound as exc:
        raise _not_found(
            "source document", "SOURCE_DOCUMENT_NOT_FOUND", document_id
        ) from exc
    except FileNotFoundError as exc:
        raise _not_found(
            "source document file", "SOURCE_DOCUMENT_NOT_FOUND", document_id
        ) from exc
    await session.commit()
    return _document_response(document)


@collection_data_sources_router.post(
    "/collections/{collection_id}/curators",
    status_code=status.HTTP_201_CREATED,
    response_model=CuratorResponse,
)
async def assign_collection_curator(
    collection_id: str,
    body: AssignCuratorRequest,
    caller: CallerPermission,
    collections: CollectionRepo,
    clock: IndexClock,
    session: DBSession,
) -> CuratorResponse:
    require_staff(caller)
    # The target must resolve to an existing permission in the CURATORIAL group.
    reader = get_permission_reader(session)
    detail = await reader.get_detail(IdentityPermissionId(body.permissionId))
    if detail is None:
        raise _not_found("permission", "PERMISSION_NOT_FOUND", body.permissionId)
    if detail.group != GroupName.CURATORIAL:
        raise _permission_not_curatorial()
    try:
        assignment = await AssignCollectionCurator(collections, clock).execute(
            caller, CollectionId(collection_id), PermissionId(body.permissionId)
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    await session.commit()
    return CuratorResponse(
        permissionId=assignment.permission_id,
        name=detail.user.name,
        email=detail.user.email,
        assignedAt=assignment.assigned_at,
    )


@collection_data_sources_router.delete(
    "/collections/{collection_id}/curators/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_collection_curator(
    collection_id: str,
    permission_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    session: DBSession,
) -> Response:
    require_staff(caller)
    try:
        await RemoveCollectionCurator(collections).execute(
            caller, CollectionId(collection_id), PermissionId(permission_id)
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Objects -> Search (read side) ────────────────────────────────────────────


def _search_hit_response(hit: SearchHit) -> SearchHitResponse:
    return SearchHitResponse(
        collectionId=hit.collection_id,
        collectionName=hit.collection_name,
        sourceDocumentId=hit.source_document_id,
        fileName=hit.file_name,
        sheet=hit.sheet,
        rowNumber=hit.row_number,
        cells=dict(hit.cells),
        highlight=hit.highlight,
    )


@object_search_router.get(
    "/search/collections", response_model=list[SearchableCollectionResponse]
)
async def list_searchable_collections(
    caller: CallerPermission,
    collections: CollectionRepo,
) -> list[SearchableCollectionResponse]:
    results = await ListSearchableCollections(collections).execute(caller)
    return [SearchableCollectionResponse(id=c.id, name=c.name) for c in results]


@object_search_router.get("/search", response_model=SearchResultResponse)
async def search_collection_objects(
    caller: CallerPermission,
    index: ObjectIndex,
    q: Annotated[str, Query(min_length=1)],
    collectionId: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SearchResultResponse:
    result = await SearchCollectionObjects(index).execute(
        caller,
        CollectionObjectSearchQuery(
            q=q,
            collection_id=CollectionId(collectionId) if collectionId else None,
            page=page,
            size=size,
        ),
    )
    return SearchResultResponse(
        total=result.total,
        page=page,
        size=size,
        items=[_search_hit_response(hit) for hit in result.items],
    )
