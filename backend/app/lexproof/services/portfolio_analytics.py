"""Portfolio-wide trend analytics.

Every other metrics view in this app (Reports' "Metrics that Matter",
Compliance's Command Center, the Regulation Map) answers "what does the data
look like right now" for one contract or one cross-section. None of them
answer "is this organization's risk posture getting better or worse over
time" -- that needs the same aggregate metrics captured at multiple points in
time, not just computed live on every page load.

This module adds that: `compute_portfolio_metrics()` aggregates an org's
current contracts/findings/proposals/passports into one snapshot of
portfolio-wide numbers (mirroring the org-scoping approach already used by
`api/organizations.py`'s regulation-map endpoint -- contracts filtered by
`org_id`, then findings/proposals/passports filtered by membership in that
contract set), and `PortfolioAnalyticsService.capture_snapshot()` persists one
of those per organization per UTC calendar day, so `list_snapshots()` returns
a real time series that gets more useful the longer the app is used.

There is no cron/scheduler process in this app (see workflow_escalation.py's
docstring for the same constraint), so snapshots are captured
opportunistically -- the Portfolio Trends page calls the capture endpoint on
load, best-effort. Capture is idempotent per (org, day): a second capture on
the same UTC day overwrites that day's snapshot in place rather than creating
a duplicate, so loading the page many times in one day never distorts the
trend. Nothing here is a fabricated or backfilled data point -- a fresh
deployment starts with zero snapshots and the trend fills in for real as the
app gets used, the same "measured, not invented" standard the Reports page
already holds itself to.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..repositories.firestore import FirestoreRepository


def _org_contracts(contracts_repo: FirestoreRepository, org_id: str) -> list[dict[str, Any]]:
    """The org's contracts via an org_id equality query (not a full scan)."""
    if hasattr(contracts_repo, "query"):
        return [contract for contract in contracts_repo.query(equal={"org_id": org_id}) if contract.get("org_id") == org_id]
    return [contract for contract in contracts_repo.stream() if contract.get("org_id") == org_id]


def _org_contract_ids(contracts_repo: FirestoreRepository, org_id: str) -> set[str]:
    ids: set[str] = set()
    for contract in _org_contracts(contracts_repo, org_id):
        contract_id = str(contract.get("id") or contract.get("contract_id") or "")
        if contract_id:
            ids.add(contract_id)
    return ids


def _records_for_contracts(repository: Any, contract_ids: set[str]) -> list[dict[str, Any]]:
    """Records whose contract_id is one of ``contract_ids``.

    Uses batched ``contract_id in [...]`` queries when the repository supports
    them, so the executive summary no longer streams whole collections
    (evidence_records alone carries every evidence payload); falls back to a
    filtered stream for repositories without query_in.
    """
    if not contract_ids:
        return []
    if hasattr(repository, "query_in"):
        return [
            record
            for record in repository.query_in("contract_id", sorted(contract_ids))
            if str(record.get("contract_id") or "") in contract_ids
        ]
    return [record for record in repository.stream() if str(record.get("contract_id") or "") in contract_ids]


def compute_portfolio_metrics(
    org_id: str,
    *,
    contracts: FirestoreRepository,
    findings: FirestoreRepository,
    proposals: FirestoreRepository,
    passports: FirestoreRepository,
) -> dict[str, Any]:
    """Aggregate one organization's current portfolio-wide metrics. Pure
    aggregation over already-persisted data -- no writes, no side effects."""
    contract_ids = _org_contract_ids(contracts, org_id)

    findings_total = 0
    severity_counts: dict[str, int] = {}
    for finding in _records_for_contracts(findings, contract_ids):
        if str(finding.get("contract_id") or "") not in contract_ids:
            continue
        findings_total += 1
        severity = str(finding.get("severity") or "UNKNOWN").upper()
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    proposals_total = 0
    status_counts: dict[str, int] = {}
    for proposal in _records_for_contracts(proposals, contract_ids):
        if str(proposal.get("contract_id") or "") not in contract_ids:
            continue
        proposals_total += 1
        proposal_status = str(proposal.get("status") or "UNKNOWN").upper()
        status_counts[proposal_status] = status_counts.get(proposal_status, 0) + 1

    passport_count = 0
    evidence_total = 0
    risk_scores: list[float] = []
    compliance_scores: list[float] = []
    for passport in _records_for_contracts(passports, contract_ids):
        if str(passport.get("contract_id") or "") not in contract_ids:
            continue
        passport_count += 1
        evidence_total += int(passport.get("evidence_count") or 0)
        risk_score = passport.get("risk_score")
        if isinstance(risk_score, (int, float)):
            risk_scores.append(float(risk_score))
        compliance_score = passport.get("compliance_score")
        if isinstance(compliance_score, (int, float)):
            compliance_scores.append(float(compliance_score))

    return {
        "contract_count": len(contract_ids),
        "findings_total": findings_total,
        "findings_by_severity": severity_counts,
        "proposals_total": proposals_total,
        "proposals_by_status": status_counts,
        "passport_count": passport_count,
        "evidence_total": evidence_total,
        "avg_risk_score": round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else None,
        "avg_compliance_score": (
            round(sum(compliance_scores) / len(compliance_scores), 2) if compliance_scores else None
        ),
    }


def compute_executive_metrics(
    org_id: str,
    *,
    contracts: FirestoreRepository,
    versions: FirestoreRepository,
    proposals: FirestoreRepository,
    passports: FirestoreRepository,
    evidence_records: FirestoreRepository,
    evidence_anchors: FirestoreRepository,
) -> dict[str, Any]:
    """Aggregate the extra, funnel/KPI-shaped numbers behind the "Why
    LexProof?" executive dashboard (hardening item #9) -- things
    `compute_portfolio_metrics()` above doesn't already answer: how many
    redlines were actually reviewed and published (not just proposed), how
    much evidence is anchored (not just how much exists), the real measured
    average AI analysis time across the portfolio (reusing the
    `ai_analysis_duration_ms` instrumentation from hardening item #3), and
    which specific contracts need a human's attention right now.

    Every number here is derived from already-persisted records, the same
    "measured, not invented" standard the rest of this module and the
    Reports page hold themselves to -- nothing is a fixed or sample value.

    A contract is flagged as "requiring attention" for one of two concrete,
    checkable reasons: its current version's AI analysis failed outright, or
    its latest Legal Passport shows high risk (score >= 70) with no redline
    for that contract published yet to address it. Capped at 20 contracts in
    the returned list to keep the payload small; `contracts_requiring_attention_count`
    is always the true, uncapped total.
    """
    contract_ids = _org_contract_ids(contracts, org_id)

    # Latest passport per contract (highest contract_version), and every
    # real ai_analysis_duration_ms measurement across the org's passports.
    latest_passport_by_contract: dict[str, dict[str, Any]] = {}
    ai_durations_ms: list[float] = []
    for passport in _records_for_contracts(passports, contract_ids):
        contract_id = str(passport.get("contract_id") or "")
        if contract_id not in contract_ids:
            continue
        current = latest_passport_by_contract.get(contract_id)
        if current is None or (passport.get("contract_version") or 0) > (current.get("contract_version") or 0):
            latest_passport_by_contract[contract_id] = passport
        duration = passport.get("ai_analysis_duration_ms")
        if isinstance(duration, (int, float)):
            ai_durations_ms.append(float(duration))

    # Redline funnel: reviewed = reached a final decision (APPROVED/REJECTED/
    # PUBLISHED); published is the subset that actually shipped a new version.
    reviewed_total = 0
    published_total = 0
    published_contract_ids: set[str] = set()
    for proposal in _records_for_contracts(proposals, contract_ids):
        contract_id = str(proposal.get("contract_id") or "")
        if contract_id not in contract_ids:
            continue
        proposal_status = str(proposal.get("status") or "").upper()
        if proposal_status in {"APPROVED", "REJECTED", "PUBLISHED"}:
            reviewed_total += 1
        if proposal_status == "PUBLISHED":
            published_total += 1
            published_contract_ids.add(contract_id)

    # Evidence anchored: every evidence record tied to one of this org's
    # contracts, cross-referenced against the create-once evidence_anchors
    # collection (the same source of truth AnchorProofButton's
    # /api/evidence/{id}/status endpoint reads).
    # One batched read for all anchors instead of one get() per evidence
    # record: the per-record lookups were ~200 sequential Firestore round
    # trips and made this endpoint take 13-15s, leaving the "Why LexProof?"
    # page on skeletons.
    org_evidence_ids: list[str] = []
    for record in _records_for_contracts(evidence_records, contract_ids):
        contract_id = str(record.get("contract_id") or "")
        if contract_id not in contract_ids:
            continue
        org_evidence_ids.append(str(record.get("evidence_id") or record.get("id") or ""))
    evidence_records_total = len(org_evidence_ids)
    anchors_by_id = evidence_anchors.get_many([evidence_id for evidence_id in org_evidence_ids if evidence_id])
    evidence_anchored_total = sum(
        1 for evidence_id in org_evidence_ids if evidence_id and anchors_by_id.get(evidence_id)
    )

    # Contracts requiring attention.
    attention: list[dict[str, Any]] = []
    org_contracts = [
        contract
        for contract in _org_contracts(contracts, org_id)
        if str(contract.get("id") or contract.get("contract_id") or "") in contract_ids
    ]
    # Batched, like the anchors above (was one versions.get() per contract).
    versions_by_id = versions.get_many(
        [str(contract["current_version_id"]) for contract in org_contracts if contract.get("current_version_id")]
    )
    for contract in org_contracts:
        contract_id = str(contract.get("id") or contract.get("contract_id") or "")
        current_version_id = contract.get("current_version_id")
        current_version = versions_by_id.get(str(current_version_id)) if current_version_id else None
        analysis_status = current_version.get("analysis_status") if current_version else None
        latest_passport = latest_passport_by_contract.get(contract_id)
        risk_score = latest_passport.get("risk_score") if latest_passport else None

        reason: str | None = None
        if analysis_status == "failed":
            reason = "AI analysis failed"
        elif isinstance(risk_score, (int, float)) and risk_score >= 70 and contract_id not in published_contract_ids:
            reason = f"High risk ({risk_score:.0f}/100) with no published redline yet"

        if reason:
            attention.append(
                {
                    "contract_id": contract_id,
                    "name": contract.get("name") or contract.get("contract_name") or contract_id,
                    "reason": reason,
                }
            )

    return {
        "redlines_reviewed_total": reviewed_total,
        "versions_published_total": published_total,
        "evidence_records_total": evidence_records_total,
        "evidence_anchored_total": evidence_anchored_total,
        "avg_ai_analysis_duration_ms": (
            round(sum(ai_durations_ms) / len(ai_durations_ms), 1) if ai_durations_ms else None
        ),
        "ai_analysis_measurement_count": len(ai_durations_ms),
        "contracts_requiring_attention_count": len(attention),
        "contracts_requiring_attention": attention[:20],
    }


class PortfolioAnalyticsService:
    def __init__(
        self,
        snapshots: FirestoreRepository | None = None,
        contracts: FirestoreRepository | None = None,
        findings: FirestoreRepository | None = None,
        proposals: FirestoreRepository | None = None,
        passports: FirestoreRepository | None = None,
    ) -> None:
        self.snapshots = snapshots or FirestoreRepository("portfolio_snapshots")
        self.contracts = contracts or FirestoreRepository("contracts")
        self.findings = findings or FirestoreRepository("risk_findings")
        self.proposals = proposals or FirestoreRepository("redline_proposals")
        self.passports = passports or FirestoreRepository("legal_passports")

    @staticmethod
    def _snapshot_id(org_id: str, day: str) -> str:
        return f"{org_id}_{day}"

    def capture_snapshot(self, org_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        moment = now or datetime.now(timezone.utc)
        day = moment.date().isoformat()
        metrics = compute_portfolio_metrics(
            org_id,
            contracts=self.contracts,
            findings=self.findings,
            proposals=self.proposals,
            passports=self.passports,
        )
        snapshot_id = self._snapshot_id(org_id, day)
        existing = self.snapshots.get(snapshot_id)
        snapshot = {
            "snapshot_id": snapshot_id,
            "org_id": org_id,
            "snapshot_date": day,
            "captured_at": moment.isoformat(),
            "first_captured_at": (existing or {}).get("first_captured_at") or moment.isoformat(),
            **metrics,
        }
        self.snapshots.set(snapshot_id, snapshot)
        return snapshot

    def list_snapshots(self, org_id: str, limit: int = 180) -> list[dict[str, Any]]:
        rows = [row for row in self.snapshots.stream() if row.get("org_id") == org_id]
        rows.sort(key=lambda row: row.get("snapshot_date") or "")
        if limit and len(rows) > limit:
            rows = rows[-limit:]
        return rows
