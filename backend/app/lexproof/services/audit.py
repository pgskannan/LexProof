"""Cross-cutting audit log.

A single, flat, chronological "who did what to which resource, when" feed
across LexProof's major mutating flows (contract upload, AI analysis
completion, redline review/publish, compliance approval, ...). This is the
"everything that happened in this org, recently" view flagged as missing in
the enterprise gold-standard review -- distinct from (and complementary to)
the existing per-workflow-instance history in workflow_engine.py, which only
covers the redline-approval workflow's own transitions.

Recording an audit event must never break the action being recorded, so
every call site wraps this in try/except (same defensive pattern as
VersionAnalysisService._create_notification for in-app notifications).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..repositories.firestore import FirestoreRepository

RepositoryFactory = Callable[[str], FirestoreRepository]


def record_audit_event(
    repository_factory: RepositoryFactory = FirestoreRepository,
    *,
    actor_id: str,
    action: str,
    resource_type: str,
    summary: str,
    actor_email: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    contract_id: Optional[str] = None,
    org_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Best-effort write of one audit-log entry. Never raises."""
    try:
        entries = repository_factory("audit_log")
        entry_id = str(uuid.uuid4())
        entries.set(
            entry_id,
            {
                "id": entry_id,
                "actor_id": actor_id,
                "actor_email": actor_email,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "resource_name": resource_name,
                "contract_id": contract_id,
                "summary": summary,
                "org_id": org_id,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        pass
