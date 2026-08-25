"""Compatibility export for the shared authentication dependency."""

from ..services.auth import get_current_user

__all__ = ["get_current_user"]