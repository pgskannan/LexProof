"""Tests for canonical legal evidence finding helpers."""

from app.lexproof.domains.passport.utils.evidence import (
    count_legal_evidence_findings,
    filter_legal_evidence_findings,
    is_legal_evidence_finding,
)


def test_is_legal_evidence_finding_excludes_metadata():
    assert is_legal_evidence_finding({"evidence_type": "clause", "title": "Finding"}) is True
    assert is_legal_evidence_finding({"evidence_type": "metadata", "title": "Risk and Compliance Scores"}) is False


def test_count_legal_evidence_findings_excludes_metadata():
    items = [
        {"evidence_type": "clause", "title": "Finding 1"},
        {"evidence_type": "clause", "title": "Finding 2"},
        {"evidence_type": "metadata", "title": "Risk and Compliance Scores"},
    ]
    assert count_legal_evidence_findings(items) == 2
    assert len(filter_legal_evidence_findings(items)) == 2
