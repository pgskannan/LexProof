"""Tests for human-approved AI remediation and re-proof."""

from datetime import datetime

import pytest

from app.lexproof.domains.compliance.models import AmendmentRequest
from app.lexproof.domains.compliance.remediation import RemediationService


@pytest.fixture
def request_data() -> AmendmentRequest:
    return AmendmentRequest(
        event_id="event-1",
        contract_id="contract-1",
        affected_clause="Data transfers",
        current_language="Transfers may occur to approved processors.",
        regulatory_requirement="Transfers require documented safeguards and notice.",
        jurisdiction="EU",
        amendment_reason="Regulatory update detected",
    )


def test_proposal_contains_required_before_context_and_is_not_published(request_data):
    service = RemediationService()

    proposal = service.request_amendment(request_data)

    assert proposal.current_language == request_data.current_language
    assert proposal.regulatory_requirement == request_data.regulatory_requirement
    assert proposal.proposed_amendment
    assert proposal.created_by == "gemini"
    assert proposal.id not in service._published_versions
    assert service.get_audit_trail(request_data.event_id)[0].action_type == "ai_recommendation"


def test_rejection_cannot_publish_contract(request_data):
    service = RemediationService()
    proposal = service.request_amendment(request_data)

    result = service.approve_and_reproof(
        proposal.id,
        approved=False,
        approved_by="counsel-1",
        rejection_reason="Needs negotiation",
    )

    assert result["published"] is False
    assert result["approval"].approved is False
    assert proposal.id not in service._published_versions
    assert len(service.get_audit_trail(request_data.event_id)) == 2


def test_approval_creates_new_version_and_preserves_previous_proof(request_data):
    service = RemediationService(proof_anchorer=lambda *_args: "tx-123")
    proposal = service.request_amendment(request_data)

    result = service.approve_and_reproof(
        proposal.id,
        approved=True,
        approved_by="counsel-1",
        approval_notes="Reviewed and approved",
    )

    assert result["published"] is True
    assert result["previous_proof_preserved"] is True
    assert result["passport"]["version"] == 2
    assert result["passport"]["proof_status"] == "verified"
    assert result["after"]["risk"] == "low"
    assert result["after"]["compliance"] == "passed"


def test_approval_audit_trail_has_complete_order(request_data):
    service = RemediationService()
    proposal = service.request_amendment(request_data)

    result = service.approve_and_reproof(proposal.id, approved=True, approved_by="counsel-1")
    actions = [entry.action_type for entry in result["audit_trail"]]

    assert actions == [
        "ai_recommendation",
        "human_approval",
        "amendment",
        "analysis",
        "policy_evaluation",
        "blockchain_proof",
    ]


def test_missing_proposal_is_rejected():
    service = RemediationService()

    with pytest.raises(ValueError, match="not found"):
        service.approve_and_reproof(
            "missing", approved=True, approved_by="counsel-1"
        )
