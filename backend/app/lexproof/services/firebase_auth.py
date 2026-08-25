"""Server-side Firebase ID token verification."""
from __future__ import annotations
from typing import Any
from .firebase import initialize_firebase
from ..config import LexProofSettings


class FirebaseAuthenticationError(Exception):
    """Raised when a Firebase ID token cannot be verified."""


def verify_firebase_token(token: str, settings: LexProofSettings | None = None) -> dict[str, Any]:
    if not token or token.lower().startswith("bearer "):
        token = token[7:] if token.lower().startswith("bearer ") else token
    if not token:
        raise FirebaseAuthenticationError("Firebase ID token is required")
    try:
        initialize_firebase(settings)
        from firebase_admin import auth
        return auth.verify_id_token(token)
    except FirebaseAuthenticationError:
        raise
    except Exception as exc:
        raise FirebaseAuthenticationError("Invalid Firebase ID token") from exc
