from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.museum_narrative.presentation.routes import museum_narrative_router
from app.ai.museum_question_triage.presentation.routes import (
    museum_question_triage_router,
)
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
from app.public_submission.presentation.dependencies import (
    get_amendment_invitation_adapter,
)
from app.public_submission.presentation.routes import router as public_proposals_router
from app.reports.in_situ_visit.presentation.routes import reports_router
from app.shared.exceptions import AccessDenied, InsufficientGroup
from app.use_of_collections.presentation.dependencies import get_amendment_invitation
from app.use_of_collections.presentation.routes import projects_router, proposals_router

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
app.include_router(internal_museum_questions_router, prefix=prefix)
app.include_router(museum_question_triage_router, prefix=prefix)


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
