"""
Reference implementation of the Vitarerum public proposal submission endpoints.

This is a *runnable specification*, not production code — it is meant to show the
backend team exactly how the protections in `docs/public-proposals.openapi.yaml`
fit together. Swap the in-memory stores and the stub mailer for real
infrastructure (DB, queue, transactional e-mail, distributed rate-limiter).

The defences that actually matter all live here, server-side:
  1. Turnstile token verified via Cloudflare `siteverify` (secret never leaves server)
  2. Rate-limit per IP + per e-mail + global
  3. Strict input validation + sanitisation (length caps, control-char/CRLF stripping)
  4. Double opt-in: pending record + single-use signed TTL token; materialise on confirm
  5. Honeypot accept-and-drop
  6. No credentials/cookies; CORS locked; no file uploads

Run:
    pip install "fastapi[standard]" httpx itsdangerous
    TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA \
        uvicorn public_proposals_reference_impl:app --port 8000
"""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, EmailStr, Field, field_validator

# ── Config ───────────────────────────────────────────────────────────────────
TURNSTILE_SECRET_KEY = os.environ["TURNSTILE_SECRET_KEY"]
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_SECRET = os.environ.get("CONFIRM_TOKEN_SECRET", "change-me-in-prod")
TOKEN_TTL_SECONDS = 24 * 60 * 60  # 24h
ALLOWED_ORIGIN = os.environ.get("PUBLIC_ORIGIN", "http://localhost:4321")

# Rate limits: (max_requests, window_seconds)
RATE_LIMIT_PER_IP = (5, 60 * 60)        # 5 submissions / hour / IP
RATE_LIMIT_PER_EMAIL = (3, 24 * 60 * 60)  # 3 / day / e-mail
RATE_LIMIT_GLOBAL = (500, 60 * 60)      # 500 / hour overall (spike guard)

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
CRLF = re.compile(r"[\r\n]")

app = FastAPI(title="Vitarerum — Public Proposal Submission (reference)")

# These endpoints take NO cookies/credentials. Lock CORS to the public origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


# ── Request / response models (mirror the OpenAPI schemas) ───────────────────
class PublicProposalSubmission(BaseModel):
    citizenName: str = Field(min_length=1, max_length=120)
    citizenEmail: EmailStr = Field(max_length=180)
    subject: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    consent: Literal[True]  # must be exactly true; anything else 422s
    captchaToken: str = Field(min_length=1, max_length=2048)
    # Honeypot: bounded but NOT capped at 0 — a length-0 cap would 422 a filled
    # field, revealing to the bot that it is monitored. The handler below silently
    # accept-and-drops a non-empty value instead (202, no work).
    website: str = Field(default="", max_length=255)

    @field_validator("citizenName", "subject", "body")
    @classmethod
    def strip_control_chars(cls, v: str) -> str:
        # Store as plain text; the staff UI must still escape on render (defence in depth).
        return CONTROL_CHARS.sub("", v).strip()

    @field_validator("citizenName", "subject")
    @classmethod
    def no_crlf(cls, v: str) -> str:
        # These may end up in an e-mail subject/display name → forbid header injection.
        return CRLF.sub(" ", v)


class PublicSubmissionReceipt(BaseModel):
    status: Literal["PENDING_CONFIRMATION"] = "PENDING_CONFIRMATION"
    email: EmailStr


class PublicConfirmationRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


class PublicConfirmationResult(BaseModel):
    status: Literal["CONFIRMED", "ALREADY_CONFIRMED", "EXPIRED", "INVALID"]
    referenceNumber: str | None = None


# ── In-memory stores (replace with DB / Redis / real mailer) ─────────────────
@dataclass
class _Hits:
    times: deque[float] = field(default_factory=deque)


_rate_buckets: dict[str, _Hits] = defaultdict(_Hits)
_pending: dict[str, dict] = {}      # token_id -> submission snapshot
_consumed_tokens: set[str] = set()  # single-use guard
_serializer = URLSafeTimedSerializer(TOKEN_SECRET, salt="public-proposal-confirm")
_ref_seq = 0


def _too_many(key: str, limit: tuple[int, int]) -> bool:
    max_n, window = limit
    now = time.time()
    hits = _rate_buckets[key]
    while hits.times and hits.times[0] <= now - window:
        hits.times.popleft()
    if len(hits.times) >= max_n:
        return True
    hits.times.append(now)
    return False


async def _verify_turnstile(token: str, ip: str) -> bool:
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(
            TURNSTILE_VERIFY_URL,
            data={"secret": TURNSTILE_SECRET_KEY, "response": token, "remoteip": ip},
        )
    resp.raise_for_status()
    return bool(resp.json().get("success"))


def _send_confirmation_email(to: str, token: str) -> None:
    # Replace with a transactional e-mail provider. The link points at the
    # public SPA route that POSTs the token back to /public/proposals/confirm.
    link = f"{ALLOWED_ORIGIN}/submit-proposal/confirm?token={token}"
    print(f"[mail] To: {to}\n[mail] Confirm your request: {link}")


def _err(status: int, message: str, **extra) -> JSONResponse:
    # Matches the ServerError shape the frontend's toApiError() reads.
    return JSONResponse(status_code=status, content={"message": message, **extra})


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.post("/api/v1/public/proposals", response_model=PublicSubmissionReceipt, status_code=202)
async def submit_public_proposal(
    submission: PublicProposalSubmission,
    request: Request,
):
    ip = request.client.host if request.client else "unknown"

    # 1) Honeypot: accept-and-drop. Return 202 so a bot learns nothing.
    if submission.website:
        return PublicSubmissionReceipt(email=submission.citizenEmail)

    # 2) Rate limits (IP, e-mail, global) → 429.
    if (
        _too_many(f"ip:{ip}", RATE_LIMIT_PER_IP)
        or _too_many(f"email:{submission.citizenEmail.lower()}", RATE_LIMIT_PER_EMAIL)
        or _too_many("global", RATE_LIMIT_GLOBAL)
    ):
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "60"},
            content={"message": "Too many requests. Please try again later."},
        )

    # 3) Verify the Turnstile token server-side.
    try:
        ok = await _verify_turnstile(submission.captchaToken, ip)
    except (httpx.HTTPError, ValueError):
        return _err(503, "Captcha provider unreachable; please retry.")
    if not ok:
        return _err(403, "Captcha verification failed.")

    # 4) Double opt-in: stash a pending record keyed by a single-use signed token.
    token_id = os.urandom(16).hex()
    _pending[token_id] = submission.model_dump()
    token = _serializer.dumps(token_id)
    _send_confirmation_email(submission.citizenEmail, token)

    return PublicSubmissionReceipt(email=submission.citizenEmail)


@app.post("/api/v1/public/proposals/confirm", response_model=PublicConfirmationResult)
async def confirm_public_proposal(payload: PublicConfirmationRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    if _too_many(f"confirm-ip:{ip}", RATE_LIMIT_PER_IP):
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "60"},
            content={"message": "Too many requests."},
        )

    # Friendly statuses are returned as 200 so the SPA can render a message.
    try:
        token_id = _serializer.loads(payload.token, max_age=TOKEN_TTL_SECONDS)
    except SignatureExpired:
        return PublicConfirmationResult(status="EXPIRED")
    except BadSignature:
        return PublicConfirmationResult(status="INVALID")

    if token_id in _consumed_tokens:
        # Idempotent re-click of an already-used link.
        return PublicConfirmationResult(status="ALREADY_CONFIRMED")

    snapshot = _pending.pop(token_id, None)
    if snapshot is None:
        return PublicConfirmationResult(status="INVALID")

    _consumed_tokens.add(token_id)
    reference = _materialise_proposal(snapshot)
    return PublicConfirmationResult(status="CONFIRMED", referenceNumber=reference)


def _materialise_proposal(snapshot: dict) -> str:
    """Create the real proposal in the staff queue. Stubbed here."""
    global _ref_seq
    _ref_seq += 1
    reference = f"VRP-{time.strftime('%Y%m%d')}-{_ref_seq:04d}"
    print(f"[proposal] Created {reference} from {snapshot['citizenEmail']}")
    return reference
