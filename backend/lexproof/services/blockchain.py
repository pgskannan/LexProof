"""Compatibility shim for historical lexproof.services.blockchain imports."""

import sys

from app.lexproof.services import blockchain as _blockchain

globals().update(_blockchain.__dict__)
sys.modules[__name__] = _blockchain
sys.modules.setdefault("lexproof.services.blockchain", _blockchain)

__all__ = getattr(_blockchain, "__all__", [])