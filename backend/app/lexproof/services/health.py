"""Health checks for LexProof cloud foundations."""
from fastapi import APIRouter
from ..config import get_settings
from .firebase import firebase_is_initialized

router = APIRouter(tags=["health"])


def _status(ready: bool, service: str) -> dict[str, str]:
    return {"status": "ok" if ready else "not_configured", "service": service}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "lexproof"}


@router.get("/health/firebase")
async def firebase_health() -> dict[str, str]:
    return _status(firebase_is_initialized() or get_settings().has_firebase_credentials(), "firebase")


@router.get("/health/gcp")
async def gcp_health() -> dict[str, str]:
    return _status(get_settings().has_gcp_project(), "google_cloud")


@router.get("/health/ai")
async def ai_health() -> dict[str, str]:
    return _status(get_settings().has_ai_configuration(), "vertex_ai")
