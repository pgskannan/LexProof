"""Portfolio-wide trend analytics endpoints -- powers the Portfolio Trends page."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..repositories.firestore import EvidenceAnchorRepository, FirestoreRepository
from ..services.auth import get_current_org_member
from ..services.portfolio_analytics import (
    PortfolioAnalyticsService,
    compute_executive_metrics,
    compute_portfolio_metrics,
)

router = APIRouter(tags=["portfolio-analytics"])

# The executive summary aggregates six collections for the whole org and still
# takes several seconds against real Firestore even after batching, which left
# the "Why LexProof?" page on skeletons on every visit. A short per-org cache
# makes repeat visits instant; one minute of staleness is fine for a KPI view.
EXECUTIVE_SUMMARY_TTL_SECONDS = 60.0
_executive_summary_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def reset_executive_summary_cache() -> None:
    """Test hook: drop every cached executive summary."""
    _executive_summary_cache.clear()


def _service() -> PortfolioAnalyticsService:
    return PortfolioAnalyticsService(
        snapshots=FirestoreRepository("portfolio_snapshots"),
        contracts=FirestoreRepository("contracts"),
        findings=FirestoreRepository("risk_findings"),
        proposals=FirestoreRepository("redline_proposals"),
        passports=FirestoreRepository("legal_passports"),
    )


@router.get("/orgs/{org_id}/portfolio-snapshots")
def list_portfolio_snapshots(
    org_id: str,
    limit: int = Query(180, ge=1, le=365),
    member: dict[str, Any] = Depends(get_current_org_member),
) -> dict[str, Any]:
    """Any active member can read the trend. Returns snapshots oldest-first,
    ready to plot directly."""
    return {"snapshots": _service().list_snapshots(org_id, limit=limit)}


@router.post("/orgs/{org_id}/portfolio-snapshots")
def capture_portfolio_snapshot(
    org_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
) -> dict[str, Any]:
    """Capture (or refresh) today's snapshot for this org. Any active member
    can trigger it -- there is no scheduler in this app, so the frontend calls
    this opportunistically on page load; it is idempotent per calendar day, so
    repeated calls just refresh today's numbers rather than creating noise."""
    return _service().capture_snapshot(org_id)


@router.get("/orgs/{org_id}/executive-summary")
def get_executive_summary(
    org_id: str,
    member: dict[str, Any] = Depends(get_current_org_member),
) -> dict[str, Any]:
    """Powers the "Why LexProof?" executive dashboard (hardening item #9):
    the current portfolio-wide snapshot (contracts/findings/proposals/
    evidence/scores, same aggregation `compute_portfolio_metrics()` already
    does for the trend snapshots) plus the funnel/KPI-shaped extras
    (redlines reviewed, versions published, evidence anchored, average real
    AI analysis time, contracts requiring attention) that only this
    dashboard needs. Any active org member can read it -- same access level
    as the Portfolio Trends endpoints above."""
    cached = _executive_summary_cache.get(org_id)
    if cached is not None and time.monotonic() - cached[0] < EXECUTIVE_SUMMARY_TTL_SECONDS:
        return cached[1]
    service = _service()
    base_metrics = compute_portfolio_metrics(
        org_id,
        contracts=service.contracts,
        findings=service.findings,
        proposals=service.proposals,
        passports=service.passports,
    )
    executive_metrics = compute_executive_metrics(
        org_id,
        contracts=service.contracts,
        versions=FirestoreRepository("contract_versions"),
        proposals=service.proposals,
        passports=service.passports,
        evidence_records=FirestoreRepository("evidence_records"),
        evidence_anchors=EvidenceAnchorRepository("evidence_anchors"),
    )
    result = {**base_metrics, **executive_metrics}
    _executive_summary_cache[org_id] = (time.monotonic(), result)
    return result
