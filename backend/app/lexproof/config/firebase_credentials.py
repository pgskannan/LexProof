"""Shared Firebase credential source detection."""
from __future__ import annotations

import os
from pathlib import Path


def local_service_account_path() -> Path:
    """Return the developer-only service-account path used by Firebase setup."""
    return Path(__file__).resolve().parents[3] / "firebase-service-account.json"


def configured_service_account_path() -> Path | None:
    """Return an existing GOOGLE_APPLICATION_CREDENTIALS file, if configured."""
    configured_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if configured_path:
        path = Path(configured_path)
        if path.is_file():
            return path
    return None


def has_file_credentials() -> bool:
    """Whether a configured or local Firebase service-account file exists."""
    return configured_service_account_path() is not None or local_service_account_path().is_file()
