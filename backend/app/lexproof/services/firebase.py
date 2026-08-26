"""Process-wide Firebase Admin initialization."""
from __future__ import annotations
import logging
from typing import Any
from ..config import LexProofSettings, get_settings
from ..config.firebase_credentials import configured_service_account_path, local_service_account_path

logger = logging.getLogger(__name__)
_app: Any = None


def initialize_firebase(settings: LexProofSettings | None = None) -> Any:
    global _app
    if _app is not None:
        return _app
    settings = settings or get_settings()
    if not settings.has_firebase_credentials():
        raise RuntimeError("Firebase Admin credentials are not configured")
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise RuntimeError("firebase-admin is required for Firebase integration") from exc

    configured_path = configured_service_account_path()
    local_path = local_service_account_path()
    if configured_path:
        credential = credentials.Certificate(str(configured_path))
        logger.info("Initializing Firebase Admin with GOOGLE_APPLICATION_CREDENTIALS")
        _app = firebase_admin.initialize_app(credential, {"projectId": settings.project_id})
    elif local_path.is_file():
        credential = credentials.Certificate(str(local_path))
        logger.info("Initializing Firebase Admin with the local service-account file")
        _app = firebase_admin.initialize_app(credential, {"projectId": settings.project_id})
    else:
        logger.info("Initializing Firebase Admin with Google Application Default Credentials")
        options = {"projectId": settings.project_id} if settings.project_id else None
        _app = firebase_admin.initialize_app(options=options)
    return _app


def firebase_is_initialized() -> bool:
    return _app is not None


def reset_firebase_for_tests() -> None:
    global _app
    _app = None
