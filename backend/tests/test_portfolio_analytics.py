"""Portfolio-wide trend analytics: aggregation correctness, org-scoping, and
per-day snapshot idempotency."""

from datetime import datetime, timezone

from app.lexproof.services.portfolio_analytics import (
    PortfolioAnalyticsService,
    compute_executive_metrics,
    compute_portfolio_metrics,
)
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"


def reset_stores():
    FakeRepository.stores = {
        "portfolio_snapshots": {},
        "contracts": {
            "c1": {"id": "c1", "name": "Acme MSA", "org_id": ORG_ID},
            "c2": {"id": "c2", "name": "Beta NDA", "org_id": ORG_ID},
            "c3": {"id": "c3", "name": "Other Org Contract", "org_id": "someone-else"},
        },
        "risk_findings": {
            "f1": {"id": "f1", "contract_id": "c1", "severity": "critical"},
            "f2": {"id": "f2", "contract_id": "c1", "severity": "high"},
            "f3": {"id": "f3", "contract_id": "c2", "severity": "high"},
            "f-other-org": {"id": "f-other-org", "contract_id": "c3", "severity": "critical"},
        },
        "redline_proposals": {
            "p1": {"id": "p1", "contract_id": "c1", "status": "PROPOSED"},
            "p2": {"id": "p2", "contract_id": "c1", "status": "PUBLISHED"},
            "p3": {"id": "p3", "contract_id": "c2", "status": "PROPOSED"},
            "p-other-org": {"id": "p-other-org", "contract_id": "c3", "status": "PROPOSED"},
        },
        "legal_passports": {
            "pp1": {"id": "pp1", "contract_id": "c1", "risk_score": 40.0, "compliance_score": 80.0, "evidence_count": 3},
            "pp2": {"id": "pp2", "contract_id": "c2", "risk_score": 60.0, "compliance_score": 70.0, "evidence_count": 2},
            "pp-other-org": {"id": "pp-other-org", "contract_id": "c3", "risk_score": 10.0, "compliance_score": 90.0, "evidence_count": 5},
        },
    }


def reset_executive_stores():
    """Fixture shape for compute_executive_metrics -- deliberately distinct
    from reset_stores() above (which lacks current_version_id / versions /
    evidence_records / evidence_anchors) so each test file's fixtures stay
    self-contained and easy to reason about independently."""
    FakeRepository.stores = {
        "contracts": {
            "c1": {"id": "c1", "name": "Acme MSA", "org_id": ORG_ID, "current_version_id": "v1"},
            "c2": {"id": "c2", "name": "Beta NDA", "org_id": ORG_ID, "current_version_id": "v2"},
            "c3": {"id": "c3", "name": "Gamma SOW", "org_id": ORG_ID, "current_version_id": "v3"},
            "c-other-org": {"id": "c-other-org", "name": "Other Org", "org_id": "someone-else", "current_version_id": "v-other"},
        },
        "contract_versions": {
            "v1": {"id": "v1", "contract_id": "c1", "analysis_status": "complete"},
            "v2": {"id": "v2", "contract_id": "c2", "analysis_status": "failed"},
            "v3": {"id": "v3", "contract_id": "c3", "analysis_status": "complete"},
            "v-other": {"id": "v-other", "contract_id": "c-other-org", "analysis_status": "failed"},
        },
        "redline_proposals": {
            "p1": {"id": "p1", "contract_id": "c1", "status": "PUBLISHED"},
            "p2": {"id": "p2", "contract_id": "c1", "status": "REJECTED"},
            "p3": {"id": "p3", "contract_id": "c3", "status": "PROPOSED"},
            "p-other-org": {"id": "p-other-org", "contract_id": "c-other-org", "status": "PUBLISHED"},
        },
        "legal_passports": {
            # c1: published redline already addresses it -- not flagged even
            # though nothing here actually drives risk for c1.
            "pp1": {"id": "pp1", "contract_id": "c1", "contract_version": 2, "risk_score": 30.0, "ai_analysis_duration_ms": 4000.0},
            # c2: current version's analysis failed -- flagged for that reason
            # regardless of risk score.
            "pp2": {"id": "pp2", "contract_id": "c2", "contract_version": 1, "risk_score": 20.0, "ai_analysis_duration_ms": 6000.0},
            # c3: high risk (>= 70), no published proposal -- flagged.
            "pp3": {"id": "pp3", "contract_id": "c3", "contract_version": 1, "risk_score": 85.0},
            "pp-other-org": {"id": "pp-other-org", "contract_id": "c-other-org", "contract_version": 1, "risk_score": 95.0, "ai_analysis_duration_ms": 999.0},
        },
        "evidence_records": {
            "e1": {"evidence_id": "e1", "contract_id": "c1"},
            "e2": {"evidence_id": "e2", "contract_id": "c1"},
            "e3": {"evidence_id": "e3", "contract_id": "c3"},
            "e-other-org": {"evidence_id": "e-other-org", "contract_id": "c-other-org"},
        },
        "evidence_anchors": {
            "e1": {"evidence_id": "e1", "transaction_hash": "0xabc"},
            "e-other-org": {"evidence_id": "e-other-org", "transaction_hash": "0xdef"},
            # e2 and e3 deliberately unanchored.
        },
    }


def test_compute_executive_metrics_scopes_to_org_and_aggregates_correctly():
    reset_executive_stores()
    metrics = compute_executive_metrics(
        ORG_ID,
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        proposals=FakeRepository("redline_proposals"),
        passports=FakeRepository("legal_passports"),
        evidence_records=FakeRepository("evidence_records"),
        evidence_anchors=FakeRepository("evidence_anchors"),
    )
    assert metrics["redlines_reviewed_total"] == 2  # p1 (PUBLISHED) + p2 (REJECTED) -- p3 PROPOSED excluded, other-org excluded
    assert metrics["versions_published_total"] == 1  # p1 only
    assert metrics["evidence_records_total"] == 3  # e1, e2, e3 -- other-org excluded
    assert metrics["evidence_anchored_total"] == 1  # e1 only (e2/e3 unanchored)
    assert metrics["avg_ai_analysis_duration_ms"] == 5000.0  # (4000 + 6000) / 2 -- pp3 has no measurement, other-org excluded
    assert metrics["ai_analysis_measurement_count"] == 2
    assert metrics["contracts_requiring_attention_count"] == 2  # c2 (failed analysis), c3 (high risk, unpublished)
    flagged_ids = {item["contract_id"] for item in metrics["contracts_requiring_attention"]}
    assert flagged_ids == {"c2", "c3"}
    reasons = {item["contract_id"]: item["reason"] for item in metrics["contracts_requiring_attention"]}
    assert reasons["c2"] == "AI analysis failed"
    assert "High risk" in reasons["c3"]


def test_compute_executive_metrics_handles_empty_org_cleanly():
    reset_executive_stores()
    metrics = compute_executive_metrics(
        "empty-org",
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        proposals=FakeRepository("redline_proposals"),
        passports=FakeRepository("legal_passports"),
        evidence_records=FakeRepository("evidence_records"),
        evidence_anchors=FakeRepository("evidence_anchors"),
    )
    assert metrics["redlines_reviewed_total"] == 0
    assert metrics["versions_published_total"] == 0
    assert metrics["evidence_records_total"] == 0
    assert metrics["evidence_anchored_total"] == 0
    assert metrics["avg_ai_analysis_duration_ms"] is None
    assert metrics["contracts_requiring_attention_count"] == 0
    assert metrics["contracts_requiring_attention"] == []


def make_service() -> PortfolioAnalyticsService:
    return PortfolioAnalyticsService(
        snapshots=FakeRepository("portfolio_snapshots"),
        contracts=FakeRepository("contracts"),
        findings=FakeRepository("risk_findings"),
        proposals=FakeRepository("redline_proposals"),
        passports=FakeRepository("legal_passports"),
    )


def test_compute_portfolio_metrics_scopes_to_org_and_aggregates_correctly():
    reset_stores()
    metrics = compute_portfolio_metrics(
        ORG_ID,
        contracts=FakeRepository("contracts"),
        findings=FakeRepository("risk_findings"),
        proposals=FakeRepository("redline_proposals"),
        passports=FakeRepository("legal_passports"),
    )
    assert metrics["contract_count"] == 2
    assert metrics["findings_total"] == 3  # f1, f2, f3 -- f-other-org excluded
    assert metrics["findings_by_severity"] == {"CRITICAL": 1, "HIGH": 2}
    assert metrics["proposals_total"] == 3  # p1, p2, p3 -- p-other-org excluded
    assert metrics["proposals_by_status"] == {"PROPOSED": 2, "PUBLISHED": 1}
    assert metrics["passport_count"] == 2
    assert metrics["evidence_total"] == 5  # 3 + 2, not +5 from the other org
    assert metrics["avg_risk_score"] == 50.0  # (40 + 60) / 2
    assert metrics["avg_compliance_score"] == 75.0  # (80 + 70) / 2


def test_compute_portfolio_metrics_handles_empty_org_cleanly():
    reset_stores()
    metrics = compute_portfolio_metrics(
        "empty-org",
        contracts=FakeRepository("contracts"),
        findings=FakeRepository("risk_findings"),
        proposals=FakeRepository("redline_proposals"),
        passports=FakeRepository("legal_passports"),
    )
    assert metrics["contract_count"] == 0
    assert metrics["findings_total"] == 0
    assert metrics["findings_by_severity"] == {}
    assert metrics["avg_risk_score"] is None
    assert metrics["avg_compliance_score"] is None


def test_capture_snapshot_persists_one_row_keyed_by_org_and_day():
    reset_stores()
    service = make_service()
    moment = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    snapshot = service.capture_snapshot(ORG_ID, now=moment)

    assert snapshot["org_id"] == ORG_ID
    assert snapshot["snapshot_date"] == "2026-09-10"
    assert snapshot["contract_count"] == 2
    assert snapshot["findings_total"] == 3
    stored = FakeRepository("portfolio_snapshots").get(f"{ORG_ID}_2026-09-10")
    assert stored is not None
    assert stored["findings_total"] == 3


def test_capture_snapshot_is_idempotent_per_calendar_day():
    reset_stores()
    service = make_service()
    first_moment = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)
    first = service.capture_snapshot(ORG_ID, now=first_moment)

    # A finding gets added later the same day (e.g. a new analysis completes),
    # then the page is loaded again -- the snapshot for that day should update
    # in place, not create a second row.
    FakeRepository.stores["risk_findings"]["f4"] = {"id": "f4", "contract_id": "c1", "severity": "low"}
    second_moment = datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc)
    second = service.capture_snapshot(ORG_ID, now=second_moment)

    assert first["snapshot_id"] == second["snapshot_id"]
    assert second["findings_total"] == 4
    assert second["first_captured_at"] == first["captured_at"]
    assert second["captured_at"] != first["captured_at"]
    all_rows = [row for row in FakeRepository("portfolio_snapshots").stream() if row.get("org_id") == ORG_ID]
    assert len(all_rows) == 1


def test_capture_snapshot_on_a_new_day_creates_a_second_row():
    reset_stores()
    service = make_service()
    service.capture_snapshot(ORG_ID, now=datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc))
    service.capture_snapshot(ORG_ID, now=datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc))

    rows = service.list_snapshots(ORG_ID)
    assert [row["snapshot_date"] for row in rows] == ["2026-09-10", "2026-09-11"]


def test_list_snapshots_scopes_to_org_sorts_ascending_and_respects_limit():
    reset_stores()
    service = make_service()
    for day in (10, 11, 12):
        service.capture_snapshot(ORG_ID, now=datetime(2026, 9, day, 9, 0, tzinfo=timezone.utc))
    other_service = PortfolioAnalyticsService(
        snapshots=FakeRepository("portfolio_snapshots"),
        contracts=FakeRepository("contracts"),
        findings=FakeRepository("risk_findings"),
        proposals=FakeRepository("redline_proposals"),
        passports=FakeRepository("legal_passports"),
    )
    other_service.capture_snapshot("someone-else", now=datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc))

    rows = service.list_snapshots(ORG_ID)
    assert [row["snapshot_date"] for row in rows] == ["2026-09-10", "2026-09-11", "2026-09-12"]
    assert all(row["org_id"] == ORG_ID for row in rows)

    limited = service.list_snapshots(ORG_ID, limit=2)
    assert [row["snapshot_date"] for row in limited] == ["2026-09-11", "2026-09-12"]
