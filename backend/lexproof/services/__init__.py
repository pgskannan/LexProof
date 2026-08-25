"""Compatibility services package for historical lexproof imports."""

import sys

import app.lexproof.services as _services

globals().update(_services.__dict__)
sys.modules[__name__] = _services
sys.modules.setdefault("lexproof.services", _services)

__all__ = getattr(_services, "__all__", [])