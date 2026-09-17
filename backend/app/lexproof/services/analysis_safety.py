"""Bounded, secret-free diagnostics for AI analysis failures.

Shared by production analysis (``version_analysis.py``) and the isolated
benchmark runner so both record failures the same way: a single-line, size-bounded
summary with credentials redacted, never a raw provider payload.
"""

from __future__ import annotations

import re

MAX_ERROR_DETAIL = 2000


def redact_sensitive(text: str) -> str:
    """Remove credential-looking fragments from a diagnostic string."""
    redacted = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", text)
    return re.sub(
        r"(?i)(api[_ -]?key|token|secret|password|authorization)\s*[:=]\s*['\"]?[^\s'\",;]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
    )


def sanitize_error_text(text: str | None, *, limit: int = MAX_ERROR_DETAIL) -> str:
    """Collapse whitespace, redact secrets and bound the length of a diagnostic."""
    detail = (text or "").replace("\r", " ").replace("\n", " ")
    return redact_sensitive(detail)[:limit]


def sanitize_analysis_error(exc: BaseException, *, limit: int = MAX_ERROR_DETAIL) -> str:
    """Store a safe, bounded summary of the failure without leaking secrets."""
    detail = str(exc) or exc.__class__.__name__
    return sanitize_error_text(detail, limit=limit)
