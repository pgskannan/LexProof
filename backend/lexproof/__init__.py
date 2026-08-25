"""Compatibility package for the backend's historical lexproof namespace."""

import sys

import app.lexproof as _app_lexproof

globals().update(_app_lexproof.__dict__)
sys.modules[__name__] = _app_lexproof
sys.modules.setdefault("lexproof", _app_lexproof)

__all__ = getattr(_app_lexproof, "__all__", [])