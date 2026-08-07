import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.museum_narrative.presentation.routes import museum_narrative_router
from app.ai.museum_question_triage.presentation.routes import (
    museum_question_triage_router,
)
from app.ai.prompts.presentation.routes import ai_prompts_router
from app.cidoc_crm.in_situ_visit_mapping.presentation.routes import (
    in_situ_visit_router,
    project_export_router,
)
from app.collection_object_index.presentation.routes import (
    collection_data_sources_router,
    object_search_router,
)
from app.config import settings
from app.document_templates.presentation.routes import (
    document_templates_router,
    public_document_templates_router,
)
from app.external_publications.presentation.routes import (
    external_public_router,
    external_publications_router,
)
from app.identity.presentation.auth_routes import auth_router
from app.identity.presentation.routes import (
    groups_router,
    institutions_router,
    users_router,
)
from app.museum_questions.presentation.routes import (
    internal_router as internal_museum_questions_router,
)
from app.museum_questions.presentation.routes import (
    router as museum_questions_router,
)
from app.notifications.presentation.routes import notifications_router
from app.public_submission.presentation.dependencies import (
    get_amendment_invitation_adapter,
)
from app.public_submission.presentation.routes import router as public_proposals_router
from app.reference_numbers.presentation.routes import reference_policies_router
from app.reports.in_situ_visit.presentation.routes import reports_router
from app.shared.exceptions import AccessDenied, InsufficientGroup
from app.shared.field_encryption import CorruptedEncryptedField
from app.shared.file_encryption import CorruptedEncryptedFile
from app.use_of_collections.presentation.dependencies import get_amendment_invitation
from app.use_of_collections.presentation.routes import projects_router, proposals_router

STATIC_DIR = (Path(__file__).resolve().parent.parent / "static").resolve()
API_PREFIX = settings.api_v1_prefix.strip("/")
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Reshape 422s to the contract's {message, errors:[{field, message}]} form."""
    errors = [
        {
            "field": ".".join(str(p) for p in err["loc"] if p not in ("body", "query")),
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=jsonable_encoder({"message": "Validation failed", "errors": errors}),
    )


@app.exception_handler(AccessDenied)
async def access_denied_handler(request: Request, exc: AccessDenied) -> JSONResponse:
    """Authorization policy exceptions map to the contract's 403 bodies."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "ACCESS_DENIED", "message": str(exc)},
    )


@app.exception_handler(InsufficientGroup)
async def insufficient_group_handler(
    request: Request, exc: InsufficientGroup
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "INSUFFICIENT_GROUP", "message": str(exc)},
    )


@app.exception_handler(CorruptedEncryptedFile)
async def corrupted_encrypted_file_handler(
    request: Request, exc: CorruptedEncryptedFile
) -> JSONResponse:
    logger.error("[storage] undecryptable file: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "FILE_UNREADABLE",
            "message": "Stored file could not be read.",
        },
    )


@app.exception_handler(CorruptedEncryptedField)
async def corrupted_encrypted_field_handler(
    request: Request, exc: CorruptedEncryptedField
) -> JSONResponse:
    logger.error("[storage] undecryptable field: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "FIELD_UNREADABLE",
            "message": "Stored field could not be read.",
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Normalise HTTPException bodies to {message, errors?} for the frontend."""
    detail = exc.detail
    if isinstance(detail, dict):
        body = {"message": detail.get("message") or detail.get("error") or "Error"}
        # Preserve the machine-readable code and field errors as a superset; the
        # frontend reads only `message`/`errors`/`fieldErrors` and ignores the rest.
        if "error" in detail:
            body["error"] = detail["error"]
        if "errors" in detail:
            body["errors"] = detail["errors"]
        if "fieldErrors" in detail:
            body["fieldErrors"] = detail["fieldErrors"]
        if "dependencies" in detail:
            body["dependencies"] = detail["dependencies"]
    else:
        body = {"message": str(detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(body),
        headers=getattr(exc, "headers", None),
    )


prefix = settings.api_v1_prefix
app.include_router(auth_router, prefix=prefix)
app.include_router(proposals_router, prefix=prefix)
app.include_router(projects_router, prefix=prefix)
app.include_router(users_router, prefix=prefix)
app.include_router(groups_router, prefix=prefix)
app.include_router(institutions_router, prefix=prefix)
app.include_router(public_proposals_router, prefix=prefix)
app.include_router(in_situ_visit_router, prefix=prefix)
app.include_router(project_export_router, prefix=prefix)
app.include_router(museum_narrative_router, prefix=prefix)
app.include_router(reports_router, prefix=prefix)
app.include_router(document_templates_router, prefix=prefix)
app.include_router(public_document_templates_router, prefix=prefix)
app.include_router(collection_data_sources_router, prefix=prefix)
app.include_router(object_search_router, prefix=prefix)
app.include_router(museum_questions_router, prefix=prefix)
app.include_router(notifications_router, prefix=prefix)
app.include_router(internal_museum_questions_router, prefix=prefix)
app.include_router(museum_question_triage_router, prefix=prefix)
app.include_router(ai_prompts_router, prefix=prefix)
app.include_router(reference_policies_router, prefix=prefix)
app.include_router(external_publications_router, prefix=prefix)
app.include_router(external_public_router, prefix=prefix)


# Composition root: bind the staff endpoint's AmendmentInvitationPort (defaulted
# to a logging no-op inside use_of_collections) to the real token-minting /
# e-mailing adapter that lives in the public-submission context. main.py is the
# only module allowed to import both contexts, so the wiring lives here.
app.dependency_overrides[get_amendment_invitation] = get_amendment_invitation_adapter


@app.get(f"{prefix}/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "application": settings.app_name,
    }


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str) -> FileResponse:
    if full_path == API_PREFIX or full_path.startswith(f"{API_PREFIX}/"):
        raise HTTPException(status_code=404)

    candidate = (STATIC_DIR / full_path).resolve()
    if candidate.is_relative_to(STATIC_DIR) and candidate.is_file():
        return FileResponse(candidate)

    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(index_file)
