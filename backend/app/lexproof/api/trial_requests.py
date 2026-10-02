"""Public "Request a trial" endpoint for the marketing site.

No login. Stores each request in the Firestore collection `trial_requests`
for the team to review and provision by hand. Light abuse protection: a
honeypot field, strict field limits, and a per-IP rate limit.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from ..repositories.firestore import FirestoreRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])

TRIAL_REQUESTS_COLLECTION = "trial_requests"
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 3600
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,253}\.[A-Za-z]{2,24}$")
ROLES = {"legal", "procurement", "compliance_audit", "executive", "it_security", "other"}
TEAM_SIZES = {"1-10", "11-50", "51-200", "201-1000", "1000+"}


class TrialRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    work_email: str = Field(min_length=6, max_length=254)
    company: str = Field(min_length=2, max_length=160)
    role: str = Field(max_length=40)
    team_size: str | None = Field(default=None, max_length=20)
    use_case: str | None = Field(default=None, max_length=2000)
    consent: bool
    request_type: str = Field(default="trial", max_length=10)
    website: str | None = Field(default=None, max_length=200)  # honeypot: real people leave it empty

    @field_validator("full_name", "company", "use_case", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("work_email", mode="before")
    @classmethod
    def _email(cls, value: Any) -> str:
        email = str(value or "").strip().lower()
        if not _EMAIL_RE.match(email):
            raise ValueError("Enter a valid work email address")
        return email

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in ROLES:
            raise ValueError("Choose a role from the list")
        return value

    @field_validator("request_type")
    @classmethod
    def _request_type(cls, value: str) -> str:
        if value not in {"trial", "demo"}:
            raise ValueError("Unknown request type")
        return value

    @field_validator("team_size")
    @classmethod
    def _team_size(cls, value: str | None) -> str | None:
        if value and value not in TEAM_SIZES:
            raise ValueError("Choose a team size from the list")
        return value or None


class _RateLimiter:
    def __init__(self, max_hits: int, window_seconds: int, clock: Callable[[], float] = time.monotonic):
        self.max_hits, self.window, self.clock = max_hits, window_seconds, clock
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(recent) >= self.max_hits:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True


_limiter = _RateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_SECONDS)


def _repository() -> FirestoreRepository:
    return FirestoreRepository(TRIAL_REQUESTS_COLLECTION)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() if forwarded else "") or (request.client.host if request.client else "unknown")


@router.post("/trial-requests", status_code=status.HTTP_201_CREATED)
def create_trial_request(payload: TrialRequest, request: Request) -> dict[str, Any]:
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Please agree to be contacted about your trial.")
    ip_hash = hashlib.sha256(_client_ip(request).encode()).hexdigest()[:16]
    if not _limiter.allow(ip_hash):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    request_id = str(uuid.uuid4())
    if payload.website:
        # Bot filled the hidden field: pretend success, store nothing.
        logger.info("trial request honeypot triggered ip_hash=%s", ip_hash)
        return {"id": request_id, "status": "received"}
    record = {
        **payload.model_dump(exclude={"website"}),
        "id": request_id,
        "status": "new",
        "source": "website",
        "ip_hash": ip_hash,
        "user_agent": (request.headers.get("user-agent") or "")[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _repository().set(request_id, record)
    logger.info("%s request stored id=%s company=%s", payload.request_type, request_id, payload.company)
    return {"id": request_id, "status": "received"}
