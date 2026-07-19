"""Collection Data Sources management endpoints.

Staff-only, with two scopes (enforced by the use cases — the frontend menu is
not a security boundary): SYS_ADMIN alone administers the collection catalog
(create/rename/remove a collection, assign/remove curators, and manage
collection areas — create/rename/remove/move collections between areas) —
collection removal is permanent, taking curators/documents/index/files with
it, while area removal is blocked while any collection is still assigned to
it; SYS_ADMIN and COLLECTIONS_MANAGEMENT manage any collection's source
documents, CURATORIAL manages only assigned collections.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError

from app.collection_object_index.application.ports import (
    CollectionObjectSearchQuery,
    InvalidSpreadsheet,
    SearchHit,
)
from app.collection_object_index.application.read_models import (
    CollectionAreaView,
    CollectionView,
)
from app.collection_object_index.application.use_cases import (
    AssignCollectionCurator,
    CreateCollection,
    CreateCollectionArea,
    CreateCollectionAreaInput,
    CreateCollectionInput,
    DeleteSourceDocument,
    GetCollection,
    ListCollectionAreas,
    ListCollectionSourceDocuments,
    ListCuratorCandidates,
    ListManageableCollections,
    ListSearchableCollections,
    ListSourceDocumentColumns,
    MoveCollectionToArea,
    MoveCollectionToAreaInput,
    PreviewSourceDocumentColumns,
    ReindexSourceDocument,
    RemoveCollection,
    RemoveCollectionArea,
    RemoveCollectionCurator,
    SearchCollectionObjects,
    UpdateCollection,
    UpdateCollectionArea,
    UpdateCollectionAreaInput,
    UpdateCollectionInput,
    UpdateSourceDocumentObjectMapping,
    UpdateSourceDocumentObjectMappingInput,
    UploadSourceDocument,
    UploadSourceDocumentInput,
)
from app.collection_object_index.domain.models import (
    CollectionAreaId,
    CollectionAreaInUse,
    CollectionAreaNotFound,
    CollectionId,
    CollectionNotFound,
    ObjectSnapshotMapping,
    SourceDocument,
    SourceDocumentId,
    SourceDocumentMappingInvalid,
    SourceDocumentNotFound,
    SourceDocumentSearchableColumnsEmpty,
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
    CollectionAreaResponse,
    CollectionResponse,
    CreateCollectionAreaRequest,
    CreateCollectionRequest,
    CuratorCandidateResponse,
    CuratorResponse,
    MoveCollectionToAreaRequest,
    ObjectSearchSnapshotResponse,
    SearchableCollectionResponse,
    SearchHitResponse,
    SearchMatchReasonResponse,
    SearchResultResponse,
    SourceDocumentColumnsResponse,
    SourceDocumentObjectMappingResponse,
    SourceDocumentResponse,
    UpdateCollectionAreaRequest,
    UpdateCollectionRequest,
    UpdateSourceDocumentObjectMappingRequest,
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


def _collection_area_not_found(area_id: str) -> HTTPException:
    return _not_found("collection area", "COLLECTION_AREA_NOT_FOUND", area_id)


def _collection_area_name_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "COLLECTION_AREA_NAME_ALREADY_EXISTS",
            "message": "A collection area with this name already exists",
        },
    )


def _invalid_collection_area_name(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error": "INVALID_COLLECTION_AREA_NAME", "message": str(exc)},
    )


def _collection_area_in_use(area_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "COLLECTION_AREA_IN_USE",
            "message": f"Collection area {area_id} still has collections assigned "
            "to it",
        },
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
    mapping = document.object_snapshot_mapping
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
        contentMatchesSearchableColumns=document.content_matches_searchable_columns,
        objectMapping=(
            SourceDocumentObjectMappingResponse(
                inventoryNumberColumn=mapping.inventory_number_column,
                displayTitleColumn=mapping.display_title_column,
                displayTitleColumns=list(mapping.display_title_columns),
                objectNameColumn=mapping.object_name_column,
                descriptionColumns=list(mapping.description_columns),
                searchableColumns=list(mapping.searchable_columns),
            )
            if mapping is not None
            else None
        ),
    )


def _mapping_from_form(
    *,
    inventory_number_column: str,
    display_title_column: str | None,
    display_title_columns_json: str | None,
    object_name_column: str | None,
    description_columns_json: str,
    searchable_columns_json: str,
) -> ObjectSnapshotMapping:
    try:
        raw_description_columns = json.loads(description_columns_json)
    except json.JSONDecodeError as exc:
        raise SourceDocumentMappingInvalid("descriptionColumns must be JSON.") from exc
    if not isinstance(raw_description_columns, list) or not all(
        isinstance(column, str) for column in raw_description_columns
    ):
        raise SourceDocumentMappingInvalid("descriptionColumns must be a string list.")
    try:
        raw_searchable_columns = json.loads(searchable_columns_json)
    except json.JSONDecodeError as exc:
        raise SourceDocumentMappingInvalid("searchableColumns must be JSON.") from exc
    if not isinstance(raw_searchable_columns, list) or not all(
        isinstance(column, str) for column in raw_searchable_columns
    ):
        raise SourceDocumentMappingInvalid("searchableColumns must be a string list.")
    display_title_columns: tuple[str, ...]
    if display_title_columns_json:
        try:
            raw_display_title_columns = json.loads(display_title_columns_json)
        except json.JSONDecodeError as exc:
            raise SourceDocumentMappingInvalid(
                "displayTitleColumns must be JSON."
            ) from exc
        if not isinstance(raw_display_title_columns, list) or not all(
            isinstance(column, str) for column in raw_display_title_columns
        ):
            raise SourceDocumentMappingInvalid(
                "displayTitleColumns must be a string list."
            )
        display_title_columns = tuple(raw_display_title_columns)
    else:
        display_title_columns = (display_title_column or "",)
    return ObjectSnapshotMapping(
        inventory_number_column=inventory_number_column,
        display_title_columns=display_title_columns,
        object_name_column=object_name_column,
        description_columns=tuple(raw_description_columns),
        searchable_columns=tuple(raw_searchable_columns),
    )


def _mapping_error(exc: SourceDocumentMappingInvalid) -> HTTPException:
    error = (
        "SOURCE_DOCUMENT_SEARCHABLE_COLUMNS_EMPTY"
        if isinstance(exc, SourceDocumentSearchableColumnsEmpty)
        else "SOURCE_DOCUMENT_MAPPING_INVALID"
    )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error": error, "message": str(exc)},
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
        areaId=view.collection.area_id,
        areaName=view.area_name,
        name=view.collection.name,
        curators=curators,
        documentCount=view.document_count,
        manageable=view.manageable,
    )


def _area_response(view: CollectionAreaView) -> CollectionAreaResponse:
    return CollectionAreaResponse(
        id=view.area.id, name=view.area.name, collectionCount=view.collection_count
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
            CreateCollectionInput(
                caller=caller,
                name=body.name,
                area_id=CollectionAreaId(body.areaId),
            )
        )
    except CollectionAreaNotFound as exc:
        raise _collection_area_not_found(body.areaId) from exc
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


@collection_data_sources_router.post(
    "/collections/{collection_id}/move-area", response_model=CollectionResponse
)
async def move_collection_to_area(
    collection_id: str,
    body: MoveCollectionToAreaRequest,
    caller: CallerPermission,
    collections: CollectionRepo,
    clock: IndexClock,
    session: DBSession,
) -> CollectionResponse:
    try:
        await MoveCollectionToArea(collections, clock).execute(
            MoveCollectionToAreaInput(
                caller=caller,
                collection_id=CollectionId(collection_id),
                area_id=CollectionAreaId(body.areaId),
            )
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    except CollectionAreaNotFound as exc:
        raise _collection_area_not_found(body.areaId) from exc
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


# ── Collection areas (catalogue classification, SYS_ADMIN only) ────────────


@collection_data_sources_router.get(
    "/areas", response_model=list[CollectionAreaResponse]
)
async def list_collection_areas(
    caller: CallerPermission,
    collections: CollectionRepo,
) -> list[CollectionAreaResponse]:
    views = await ListCollectionAreas(collections).execute(caller)
    return [_area_response(v) for v in views]


@collection_data_sources_router.post(
    "/areas",
    status_code=status.HTTP_201_CREATED,
    response_model=CollectionAreaResponse,
)
async def create_collection_area(
    body: CreateCollectionAreaRequest,
    caller: CallerPermission,
    collections: CollectionRepo,
    clock: IndexClock,
    session: DBSession,
) -> CollectionAreaResponse:
    try:
        area = await CreateCollectionArea(collections, clock).execute(
            CreateCollectionAreaInput(caller=caller, name=body.name)
        )
    except ValueError as exc:
        raise _invalid_collection_area_name(exc) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise _collection_area_name_conflict() from exc
    await session.commit()
    return CollectionAreaResponse(id=area.id, name=area.name, collectionCount=0)


@collection_data_sources_router.patch(
    "/areas/{area_id}", response_model=CollectionAreaResponse
)
async def update_collection_area(
    area_id: str,
    body: UpdateCollectionAreaRequest,
    caller: CallerPermission,
    collections: CollectionRepo,
    clock: IndexClock,
    session: DBSession,
) -> CollectionAreaResponse:
    try:
        area = await UpdateCollectionArea(collections, clock).execute(
            UpdateCollectionAreaInput(
                caller=caller, area_id=CollectionAreaId(area_id), name=body.name
            )
        )
    except CollectionAreaNotFound as exc:
        raise _collection_area_not_found(area_id) from exc
    except ValueError as exc:
        raise _invalid_collection_area_name(exc) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise _collection_area_name_conflict() from exc
    await session.commit()
    counts = await collections.count_collections_by_area()
    return CollectionAreaResponse(
        id=area.id, name=area.name, collectionCount=counts.get(area.id, 0)
    )


@collection_data_sources_router.delete(
    "/areas/{area_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_collection_area(
    area_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    session: DBSession,
) -> Response:
    try:
        await RemoveCollectionArea(collections).execute(
            caller, CollectionAreaId(area_id)
        )
    except CollectionAreaNotFound as exc:
        raise _collection_area_not_found(area_id) from exc
    except CollectionAreaInUse as exc:
        raise _collection_area_in_use(area_id) from exc
    await session.commit()
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
    inventoryNumberColumn: Annotated[str, Form(min_length=1, max_length=255)],
    displayTitleColumn: Annotated[str | None, Form(max_length=255)] = None,
    displayTitleColumns: Annotated[str | None, Form()] = None,
    objectNameColumn: Annotated[str | None, Form(max_length=255)] = None,
    descriptionColumns: Annotated[str, Form()] = "[]",
    searchableColumns: Annotated[str, Form()] = "[]",
) -> SourceDocumentResponse:
    require_staff(caller)
    content = await read_upload_capped(file)
    ensure_xlsx(content)
    try:
        mapping = _mapping_from_form(
            inventory_number_column=inventoryNumberColumn,
            display_title_column=displayTitleColumn,
            display_title_columns_json=displayTitleColumns,
            object_name_column=objectNameColumn,
            description_columns_json=descriptionColumns,
            searchable_columns_json=searchableColumns,
        )
        result = await UploadSourceDocument(
            collections, documents, storage, parser, index, clock
        ).execute(
            UploadSourceDocumentInput(
                caller=caller,
                collection_id=CollectionId(collection_id),
                file_name=safe_basename(file.filename or "", default="objects.xlsx"),
                content=content,
                object_mapping=mapping,
            )
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    except SourceDocumentMappingInvalid as exc:
        raise _mapping_error(exc) from exc
    except InvalidSpreadsheet as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "INVALID_SPREADSHEET", "message": str(exc)},
        ) from exc
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


@collection_data_sources_router.post(
    "/collections/{collection_id}/documents/columns-preview",
    response_model=SourceDocumentColumnsResponse,
)
async def preview_collection_document_columns(
    collection_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    parser: SourceParser,
    file: Annotated[UploadFile, File()],
) -> SourceDocumentColumnsResponse:
    require_staff(caller)
    content = await read_upload_capped(file)
    ensure_xlsx(content)
    try:
        columns = await PreviewSourceDocumentColumns(collections, parser).execute(
            caller, CollectionId(collection_id), content
        )
    except CollectionNotFound as exc:
        raise _not_found("collection", "COLLECTION_NOT_FOUND", collection_id) from exc
    except InvalidSpreadsheet as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "INVALID_SPREADSHEET", "message": str(exc)},
        ) from exc
    return SourceDocumentColumnsResponse(columns=columns)


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
    except SourceDocumentMappingInvalid as exc:
        raise _mapping_error(exc) from exc
    await session.commit()
    return _document_response(document)


@collection_data_sources_router.get(
    "/documents/{document_id}/columns", response_model=SourceDocumentColumnsResponse
)
async def list_source_document_columns(
    document_id: str,
    caller: CallerPermission,
    collections: CollectionRepo,
    documents: SourceDocumentRepo,
    index: ObjectIndex,
) -> SourceDocumentColumnsResponse:
    require_staff(caller)
    try:
        columns = await ListSourceDocumentColumns(
            collections, documents, index
        ).execute(caller, SourceDocumentId(document_id))
    except SourceDocumentNotFound as exc:
        raise _not_found(
            "source document", "SOURCE_DOCUMENT_NOT_FOUND", document_id
        ) from exc
    return SourceDocumentColumnsResponse(columns=columns)


@collection_data_sources_router.put(
    "/documents/{document_id}/object-mapping", response_model=SourceDocumentResponse
)
async def update_source_document_object_mapping(
    document_id: str,
    payload: UpdateSourceDocumentObjectMappingRequest,
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
        document = await UpdateSourceDocumentObjectMapping(
            collections, documents, storage, parser, index, clock
        ).execute(
            UpdateSourceDocumentObjectMappingInput(
                caller=caller,
                document_id=SourceDocumentId(document_id),
                inventory_number_column=payload.inventoryNumberColumn,
                display_title_columns=tuple(
                    payload.displayTitleColumns
                    or (
                        [payload.displayTitleColumn]
                        if payload.displayTitleColumn
                        else []
                    )
                ),
                object_name_column=payload.objectNameColumn,
                description_columns=tuple(payload.descriptionColumns),
                searchable_columns=tuple(payload.searchableColumns),
            )
        )
    except SourceDocumentNotFound as exc:
        raise _not_found(
            "source document", "SOURCE_DOCUMENT_NOT_FOUND", document_id
        ) from exc
    except SourceDocumentMappingInvalid as exc:
        raise _mapping_error(exc) from exc
    except InvalidSpreadsheet as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "INVALID_SPREADSHEET", "message": str(exc)},
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
    snapshot = hit.object_snapshot
    return SearchHitResponse(
        collectionId=hit.collection_id,
        collectionName=hit.collection_name,
        sourceDocumentId=hit.source_document_id,
        fileName=hit.file_name,
        sheet=hit.sheet,
        rowNumber=hit.row_number,
        cells=dict(hit.cells),
        highlight=hit.highlight,
        objectSnapshot=(
            ObjectSearchSnapshotResponse(
                inventoryNumber=snapshot.inventory_number,
                displayTitle=snapshot.display_title,
                objectName=snapshot.object_name,
                briefDescriptionSnapshot=snapshot.brief_description_snapshot,
                category=snapshot.category,
            )
            if snapshot is not None
            else None
        ),
        matchReasons=[
            SearchMatchReasonResponse(
                method=reason.method,
                label=reason.label,
                columns=list(reason.columns),
            )
            for reason in hit.match_reasons
        ],
    )


@object_search_router.get(
    "/search/collections", response_model=list[SearchableCollectionResponse]
)
async def list_searchable_collections(
    caller: CallerPermission,
    collections: CollectionRepo,
    index: ObjectIndex,
) -> list[SearchableCollectionResponse]:
    results = await ListSearchableCollections(collections, index).execute(caller)
    return [
        SearchableCollectionResponse(
            id=c.id,
            name=c.name,
            searchableColumns=list(c.searchable_columns),
            searchableColumnsTotal=c.searchable_columns_total,
        )
        for c in results
    ]


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
