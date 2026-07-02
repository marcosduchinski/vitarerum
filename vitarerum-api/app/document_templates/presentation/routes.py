"""Document template endpoints.

Two routers: a public, unauthenticated one used by the citizen submission screen
(list + download), and a staff-only management router (CRUD + file upload).
"""

from __future__ import annotations

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

from app.document_templates.application.use_cases import (
    DeleteDocumentTemplate,
    DownloadedTemplate,
    GetDocumentTemplateFile,
    ListDocumentTemplates,
    PublishDocumentTemplate,
    PublishDocumentTemplateInput,
    ReplaceDocumentTemplateFile,
    ReplaceDocumentTemplateFileInput,
    UpdateDocumentTemplateMetadata,
    UpdateDocumentTemplateMetadataInput,
)
from app.document_templates.domain.models import (
    DocumentTemplate,
    DocumentTemplateId,
    DocumentTemplateNotFound,
)
from app.document_templates.presentation.dependencies import (
    DBSession,
    TemplateClock,
    TemplateFileStorage,
    TemplateRepo,
)
from app.document_templates.presentation.schemas import (
    DocumentTemplateResponse,
    PublicDocumentTemplateResponse,
    UpdateDocumentTemplateRequest,
)
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission
from app.shared.kernel import UseType
from app.shared.uploads import (
    content_disposition_attachment,
    ensure_docx,
    guess_content_type,
    read_upload_capped,
    safe_basename,
)

public_document_templates_router = APIRouter(
    prefix="/public", tags=["public-document-templates"]
)
document_templates_router = APIRouter(
    prefix="/document-templates", tags=["document-templates"]
)


def _to_response(template: DocumentTemplate) -> DocumentTemplateResponse:
    return DocumentTemplateResponse(
        id=template.id,
        useType=template.use_type,
        title=template.title,
        description=template.description,
        mandatory=template.mandatory,
        active=template.active,
        displayOrder=template.display_order,
        fileName=template.file_name,
        uploadedAt=template.uploaded_at,
    )


def _not_found(template_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "DOCUMENT_TEMPLATE_NOT_FOUND",
            "message": f"No document template with id {template_id}",
        },
    )


def _file_response(downloaded: DownloadedTemplate) -> Response:
    return Response(
        content=downloaded.content,
        media_type=guess_content_type(downloaded.file_name),
        headers={
            "Content-Disposition": content_disposition_attachment(downloaded.file_name)
        },
    )


# ── Public endpoints ──────────────────────────────────────────────────────────


@public_document_templates_router.get(
    "/document-templates",
    response_model=list[PublicDocumentTemplateResponse],
)
async def list_public_document_templates(
    repo: TemplateRepo,
    use_type: Annotated[UseType, Query(alias="useType")],
) -> list[PublicDocumentTemplateResponse]:
    templates = await ListDocumentTemplates(repo).execute(
        use_type=use_type, active_only=True
    )
    return [
        PublicDocumentTemplateResponse(
            id=t.id,
            title=t.title,
            description=t.description,
            mandatory=t.mandatory,
        )
        for t in templates
    ]


@public_document_templates_router.get("/document-templates/{template_id}/file")
async def download_public_document_template(
    template_id: str,
    repo: TemplateRepo,
    file_storage: TemplateFileStorage,
) -> Response:
    try:
        # Public callers only ever see active templates — a deactivated one is
        # 404 even to someone who knows its id.
        downloaded = await GetDocumentTemplateFile(repo, file_storage).execute(
            DocumentTemplateId(template_id), active_only=True
        )
    except DocumentTemplateNotFound as exc:
        raise _not_found(template_id) from exc
    except FileNotFoundError as exc:
        raise _not_found(template_id) from exc
    return _file_response(downloaded)


# ── Staff management endpoints ────────────────────────────────────────────────


@document_templates_router.get("", response_model=list[DocumentTemplateResponse])
async def list_document_templates(
    caller: CallerPermission,
    repo: TemplateRepo,
    use_type: Annotated[UseType | None, Query(alias="useType")] = None,
) -> list[DocumentTemplateResponse]:
    require_staff(caller)
    templates = await ListDocumentTemplates(repo).execute(
        use_type=use_type, active_only=False
    )
    return [_to_response(t) for t in templates]


@document_templates_router.get("/{template_id}/file")
async def download_document_template(
    template_id: str,
    caller: CallerPermission,
    repo: TemplateRepo,
    file_storage: TemplateFileStorage,
) -> Response:
    # Staff may download any template, including inactive ones (to review before
    # re-activating or replacing).
    require_staff(caller)
    try:
        downloaded = await GetDocumentTemplateFile(repo, file_storage).execute(
            DocumentTemplateId(template_id)
        )
    except DocumentTemplateNotFound as exc:
        raise _not_found(template_id) from exc
    except FileNotFoundError as exc:
        raise _not_found(template_id) from exc
    return _file_response(downloaded)


@document_templates_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentTemplateResponse,
)
async def create_document_template(
    caller: CallerPermission,
    repo: TemplateRepo,
    file_storage: TemplateFileStorage,
    clock: TemplateClock,
    session: DBSession,
    file: Annotated[UploadFile, File()],
    useType: Annotated[UseType, Form()],
    title: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    mandatory: Annotated[bool, Form()] = False,
    active: Annotated[bool, Form()] = True,
    displayOrder: Annotated[int, Form()] = 0,
) -> DocumentTemplateResponse:
    require_staff(caller)
    content = await read_upload_capped(file)
    ensure_docx(content)
    template = await PublishDocumentTemplate(repo, file_storage, clock).execute(
        PublishDocumentTemplateInput(
            use_type=useType,
            title=title,
            description=description,
            mandatory=mandatory,
            active=active,
            display_order=displayOrder,
            file_name=safe_basename(file.filename or "", default="template.docx"),
            content=content,
            uploaded_by=caller.id,
        )
    )
    try:
        await session.commit()
    except Exception:
        await file_storage.delete(template.file_reference)
        raise
    return _to_response(template)


@document_templates_router.patch(
    "/{template_id}", response_model=DocumentTemplateResponse
)
async def update_document_template(
    template_id: str,
    body: UpdateDocumentTemplateRequest,
    caller: CallerPermission,
    repo: TemplateRepo,
    session: DBSession,
) -> DocumentTemplateResponse:
    require_staff(caller)
    try:
        template = await UpdateDocumentTemplateMetadata(repo).execute(
            UpdateDocumentTemplateMetadataInput(
                template_id=DocumentTemplateId(template_id),
                title=body.title,
                description=body.description,
                mandatory=body.mandatory,
                active=body.active,
                display_order=body.displayOrder,
            )
        )
    except DocumentTemplateNotFound as exc:
        raise _not_found(template_id) from exc
    await session.commit()
    return _to_response(template)


@document_templates_router.put(
    "/{template_id}/file", response_model=DocumentTemplateResponse
)
async def replace_document_template_file(
    template_id: str,
    caller: CallerPermission,
    repo: TemplateRepo,
    file_storage: TemplateFileStorage,
    session: DBSession,
    file: Annotated[UploadFile, File()],
) -> DocumentTemplateResponse:
    require_staff(caller)
    content = await read_upload_capped(file)
    ensure_docx(content)
    try:
        template, old_reference = await ReplaceDocumentTemplateFile(
            repo, file_storage
        ).execute(
            ReplaceDocumentTemplateFileInput(
                template_id=DocumentTemplateId(template_id),
                file_name=safe_basename(file.filename or "", default="template.docx"),
                content=content,
            )
        )
    except DocumentTemplateNotFound as exc:
        raise _not_found(template_id) from exc
    try:
        await session.commit()
    except Exception:
        if template.file_reference != old_reference:
            await file_storage.delete(template.file_reference)
        raise
    # Committed: the old file is now safe to remove.
    if old_reference != template.file_reference:
        await file_storage.delete(old_reference)
    return _to_response(template)


@document_templates_router.delete(
    "/{template_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_document_template(
    template_id: str,
    caller: CallerPermission,
    repo: TemplateRepo,
    file_storage: TemplateFileStorage,
    session: DBSession,
) -> Response:
    require_staff(caller)
    try:
        file_reference = await DeleteDocumentTemplate(repo, file_storage).execute(
            DocumentTemplateId(template_id)
        )
    except DocumentTemplateNotFound as exc:
        raise _not_found(template_id) from exc
    await session.commit()
    # Remove the file only after the row is durably gone.
    await file_storage.delete(file_reference)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
