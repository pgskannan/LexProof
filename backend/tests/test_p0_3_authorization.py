"""P0.3 Authorization tests for evidence anchoring.

Tests critical IDOR vulnerability: User A should NOT be able to anchor User B's evidence.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.lexproof.api import evidence_anchor
from app.lexproof.api.evidence_anchor import (
    get_evidence_records_repository as original_get_evidence_records_repository,
    get_evidence_repository as original_get_evidence_repository,
)
from app.lexproof.api.auth import get_current_user
from app.lexproof.main import create_app


def evidence_record(owner_id="user-1", evidence_id="evidence-1", passport_id="ac2ad6e6-d8d7-4408-be19-dcef069fa4df"):
    """Create a fake evidence record."""
    return {
        "evidence_id": evidence_id,
        "passport_id": passport_id,
        "owner_id": owner_id,
        "evidence_type": "clause",
        "title": "Risk finding",
        "description": "A finding",
        "content": "Evidence",
        "content_type": "text/plain",
        "risk_impact": 10,
        "compliance_impact": 0,
        "evidence_status": "valid",
        "contract_reference": None,
        "policy_reference": None,
        "analysis_reference": "finding-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "verified_at": None,
        "source": "ai_analysis",
        "source_id": "finding_1",
        "hash": "a" * 64,
        "metadata": {},
    }


def test_no_authentication_returns_401():
    """Test that anchor endpoint requires authentication."""
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/evidence/evidence-1/anchor",
        json={"evidence_id": "evidence-1"},
    )
    # The endpoint should fail authentication (401)
    assert response.status_code == 401
    assert "Bearer token is required" in response.json()["detail"]


def test_authenticated_user_can_anchor_own_evidence():
    """Test that a user CAN anchor their own evidence."""
    app = create_app()

    # Setup: User 1 owns evidence-1
    with patch('app.lexproof.api.evidence_anchor.get_current_user', return_value={"uid": "user-1"}):
        with patch('app.lexproof.api.evidence_anchor.get_evidence_repository') as mock_repo:
            with patch('app.lexproof.api.evidence_anchor.get_evidence_records_repository') as mock_evidence_repo:
                with patch('app.lexproof.api.evidence_anchor.get_ethereum_anchor_service') as mock_anchor_service:
                    # Setup mocks
                    mock_evidence_repo.return_value.get.return_value = evidence_record(owner_id="user-1", evidence_id="evidence-1")
                    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
                    app.dependency_overrides[original_get_evidence_repository] = lambda: mock_repo.return_value
                    app.dependency_overrides[original_get_evidence_records_repository] = lambda: mock_evidence_repo.return_value
                    mock_anchor_service.return_value.anchor_evidence = AsyncMock(return_value={
                        "blockchain_network": "ethereum-sepolia",
                        "contract_address": "0x123...",
                        "transaction_hash": "0xabc...",
                        "block_number": 12345,
                        "anchored_at": "2026-08-25T00:00:00",
                        "evidence_hash": "a" * 64,
                    })

                    client = TestClient(app)
                    response = client.post(
                        "/api/evidence/evidence-1/anchor",
                        json={"evidence_id": "evidence-1"},
                        headers={"Authorization": "Bearer valid-token"}
                    )

                    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.json()}"
                    assert response.json()["evidence_id"] == "evidence-1"


def test_user_cannot_anchor_another_users_evidence_idor():
    """CRITICAL P0.3 TEST: User A cannot anchor User B's evidence."""
    app = create_app()

    # Setup: User 1 owns evidence-1, User 2 wants to anchor it
    with patch('app.lexproof.api.evidence_anchor.get_current_user', return_value={"uid": "user-2"}):
        with patch('app.lexproof.api.evidence_anchor.get_evidence_repository') as mock_repo:
            with patch('app.lexproof.api.evidence_anchor.get_evidence_records_repository') as mock_evidence_repo:
                with patch('app.lexproof.api.evidence_anchor.get_ethereum_anchor_service') as mock_anchor_service:
                    # Setup mocks
                    mock_evidence_repo.return_value.get.return_value = evidence_record(owner_id="user-1", evidence_id="evidence-1")
                    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-2"}
                    app.dependency_overrides[original_get_evidence_repository] = lambda: mock_repo.return_value
                    app.dependency_overrides[original_get_evidence_records_repository] = lambda: mock_evidence_repo.return_value

                    client = TestClient(app)
                    response = client.post(
                        "/api/evidence/evidence-1/anchor",
                        json={"evidence_id": "evidence-1"},
                        headers={"Authorization": "Bearer valid-token"}
                    )

                    # CRITICAL: Should be 403 Forbidden, not 202
                    assert response.status_code == 403, f"Expected 403 IDOR protection, got {response.status_code}: {response.json()}"
                    assert "not authorized to anchor" in response.json()["detail"].lower()

                    # CRITICAL: EthereumAnchorService should NOT be called
                    mock_anchor_service.assert_not_called()


def test_user_cannot_anchor_nonexistent_evidence():
    """Test that anchoring nonexistent evidence returns 404."""
    app = create_app()

    # Setup: User 2 tries to anchor evidence that doesn't exist
    with patch('app.lexproof.api.evidence_anchor.get_current_user', return_value={"uid": "user-2"}):
        with patch('app.lexproof.api.evidence_anchor.get_evidence_repository') as mock_repo:
            with patch('app.lexproof.api.evidence_anchor.get_evidence_records_repository') as mock_evidence_repo:
                with patch('app.lexproof.api.evidence_anchor.get_ethereum_anchor_service') as mock_anchor_service:
                    # Setup mocks
                    mock_evidence_repo.return_value.get.return_value = None
                    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-2"}
                    app.dependency_overrides[original_get_evidence_repository] = lambda: mock_repo.return_value
                    app.dependency_overrides[original_get_evidence_records_repository] = lambda: mock_evidence_repo.return_value

                    client = TestClient(app)
                    response = client.post(
                        "/api/evidence/nonexistent-evidence/anchor",
                        json={"evidence_id": "nonexistent-evidence"},
                        headers={"Authorization": "Bearer valid-token"}
                    )

                    # Should be 404 (evidence not found), not 403 (ownership) or 202
                    assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.json()}"
                    assert "not found" in response.json()["detail"].lower()


def test_unauthorized_evidence_prevents_ethereum_anchor():
    """Verify that evidence without proper ownership never reaches blockchain."""
    app = create_app()

    # Setup: User 1 owns evidence, User 2 tries to anchor
    with patch('app.lexproof.api.evidence_anchor.get_current_user', return_value={"uid": "user-2"}):
        with patch('app.lexproof.api.evidence_anchor.get_evidence_repository') as mock_repo:
            with patch('app.lexproof.api.evidence_anchor.get_evidence_records_repository') as mock_evidence_repo:
                with patch('app.lexproof.api.evidence_anchor.get_ethereum_anchor_service') as mock_anchor_service:
                    # Setup mocks
                    mock_evidence_repo.return_value.get.return_value = evidence_record(owner_id="user-1", evidence_id="evidence-1")
                    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-2"}
                    app.dependency_overrides[original_get_evidence_repository] = lambda: mock_repo.return_value
                    app.dependency_overrides[original_get_evidence_records_repository] = lambda: mock_evidence_repo.return_value

                    client = TestClient(app)
                    response = client.post(
                        "/api/evidence/evidence-1/anchor",
                        json={"evidence_id": "evidence-1"},
                        headers={"Authorization": "Bearer valid-token"}
                    )

                    # Should fail authorization before any blockchain interaction
                    assert response.status_code == 403
                    mock_anchor_service.assert_not_called(), "EthereumAnchorService should NOT be called for unauthorized evidence"


def test_blockchain_pending_transaction_returns_503():
    """Transient blockchain submission failures should surface as a retryable 503."""
    app = create_app()

    with patch('app.lexproof.api.evidence_anchor.get_current_user', return_value={"uid": "user-1"}):
        with patch('app.lexproof.api.evidence_anchor.get_evidence_repository') as mock_repo:
            with patch('app.lexproof.api.evidence_anchor.get_evidence_records_repository') as mock_evidence_repo:
                with patch('app.lexproof.api.evidence_anchor.get_ethereum_anchor_service') as mock_anchor_service:
                    mock_evidence_repo.return_value.get.return_value = evidence_record(owner_id="user-1", evidence_id="evidence-1")
                    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
                    app.dependency_overrides[original_get_evidence_repository] = lambda: mock_repo.return_value
                    app.dependency_overrides[original_get_evidence_records_repository] = lambda: mock_evidence_repo.return_value
                    mock_anchor_service.return_value.anchor_evidence = AsyncMock(
                        side_effect=RuntimeError("Transaction pending: 0xabc")
                    )

                    client = TestClient(app)
                    response = client.post(
                        "/api/evidence/evidence-1/anchor",
                        json={"evidence_id": "evidence-1"},
                        headers={"Authorization": "Bearer valid-token"}
                    )

                    assert response.status_code == 503, f"Expected 503, got {response.status_code}: {response.json()}"
                    assert "temporarily unavailable" in response.json()["detail"].lower()


def test_authorized_evidence_calls_anchor_service():
    """Verify that authorized evidence DOES call the anchor service."""
    app = create_app()

    # Setup: User 1 owns evidence, tries to anchor it
    with patch('app.lexproof.api.evidence_anchor.get_current_user', return_value={"uid": "user-1"}):
        with patch('app.lexproof.api.evidence_anchor.get_evidence_repository') as mock_repo:
            with patch('app.lexproof.api.evidence_anchor.get_evidence_records_repository') as mock_evidence_repo:
                with patch('app.lexproof.api.evidence_anchor.get_ethereum_anchor_service') as mock_anchor_service:
                    # Setup mocks
                    mock_evidence_repo.return_value.get.return_value = evidence_record(owner_id="user-1", evidence_id="evidence-1")
                    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
                    app.dependency_overrides[original_get_evidence_repository] = lambda: mock_repo.return_value
                    app.dependency_overrides[original_get_evidence_records_repository] = lambda: mock_evidence_repo.return_value
                    mock_anchor_service.return_value.anchor_evidence = AsyncMock(return_value={
                        "blockchain_network": "ethereum-sepolia",
                        "contract_address": "0x123...",
                        "transaction_hash": "0xabc...",
                        "block_number": 12345,
                        "anchored_at": "2026-08-25T00:00:00",
                        "evidence_hash": "a" * 64,
                    })

                    client = TestClient(app)
                    response = client.post(
                        "/api/evidence/evidence-1/anchor",
                        json={"evidence_id": "evidence-1"},
                        headers={"Authorization": "Bearer valid-token"}
                    )

                    # Should succeed and anchor service should be called
                    assert response.status_code == 202
                    mock_anchor_service.return_value.anchor_evidence.assert_called_once_with(evidence_id="evidence-1")


def test_evidence_owner_id_authoritative_boundary():
    """Test that owner_id in Firestore is the authoritative security boundary."""
    app = create_app()

    # Setup: Multiple users, different evidence ownership
    with patch('app.lexproof.api.evidence_anchor.get_current_user', return_value={"uid": "user-3"}):
        with patch('app.lexproof.api.evidence_anchor.get_evidence_repository') as mock_repo:
            with patch('app.lexproof.api.evidence_anchor.get_evidence_records_repository') as mock_evidence_repo:
                with patch('app.lexproof.api.evidence_anchor.get_ethereum_anchor_service') as mock_anchor_service:
                    # Setup mocks
                    mock_evidence_repo.return_value.get.side_effect = [
                        evidence_record(owner_id="user-1", evidence_id="evidence-1"),
                        evidence_record(owner_id="user-2", evidence_id="evidence-2"),
                    ]
                    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-3"}
                    app.dependency_overrides[original_get_evidence_repository] = lambda: mock_repo.return_value
                    app.dependency_overrides[original_get_evidence_records_repository] = lambda: mock_evidence_repo.return_value

                    client = TestClient(app)

                    # User 3 tries to anchor User 1's evidence
                    response1 = client.post(
                        "/api/evidence/evidence-1/anchor",
                        json={"evidence_id": "evidence-1"},
                        headers={"Authorization": "Bearer valid-token"}
                    )
                    assert response1.status_code == 403

                    # User 3 tries to anchor User 2's evidence
                    response2 = client.post(
                        "/api/evidence/evidence-2/anchor",
                        json={"evidence_id": "evidence-2"},
                        headers={"Authorization": "Bearer valid-token"}
                    )
                    assert response2.status_code == 403

                    # No anchor writes should occur for either
                    mock_anchor_service.assert_not_called(), "No anchor service calls for any unauthorized evidence"


def legacy_test_no_authentication_returns_401():
    """Test that anchor endpoint requires authentication."""
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/evidence/evidence-1/anchor",
        json={"evidence_id": "evidence-1"},
        headers={"Authorization": "Bearer test"}
    )
    # The endpoint should fail authentication (401)
    assert response.status_code == 401
    assert "Bearer token is required" in response.json()["detail"]


def legacy_test_authenticated_user_can_anchor_own_evidence():
    """Test that a user CAN anchor their own evidence."""
    app = create_app()

    # Setup: User 1 owns evidence-1
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}

    # Create fake evidence repository
    fake_repo = FakeEvidenceRepository([evidence_record(owner_id="user-1", evidence_id="evidence-1")])

    client = TestClient(app)
    response = client.post(
        "/api/evidence/evidence-1/anchor",
        json={"evidence_id": "evidence-1"},
        headers={"Authorization": "Bearer valid-token"}
    )

    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.json()}"
    assert response.json()["evidence_id"] == "evidence-1"


def legacy_test_user_cannot_anchor_another_users_evidence_idor():
    """CRITICAL P0.3 TEST: User A cannot anchor User B's evidence."""
    app = create_app()

    # Setup: User 1 owns evidence-1, User 2 wants to anchor it
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-2"}

    # Create fake evidence repository with User 1's evidence
    fake_repo = FakeEvidenceRepository([evidence_record(owner_id="user-1", evidence_id="evidence-1")])

    client = TestClient(app)
    response = client.post(
        "/api/evidence/evidence-1/anchor",
        json={"evidence_id": "evidence-1"},
        headers={"Authorization": "Bearer valid-token"}
    )

    # CRITICAL: Should be 403 Forbidden, not 202
    assert response.status_code == 403, f"Expected 403 IDOR protection, got {response.status_code}: {response.json()}"
    assert "not authorized to anchor" in response.json()["detail"].lower()

    # CRITICAL: EthereumAnchorService should NOT be called
    # Verify no anchor writes occurred
    assert len(fake_repo.anchor_writes) == 0, "Anchor service should NOT be called for unauthorized evidence"


def legacy_test_user_cannot_anchor_nonexistent_evidence():
    """Test that anchoring nonexistent evidence returns 404."""
    app = create_app()

    # Setup: User 2 tries to anchor evidence that doesn't exist
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-2"}

    fake_repo = FakeEvidenceRepository([])

    client = TestClient(app)
    response = client.post(
        "/api/evidence/nonexistent-evidence/anchor",
        json={"evidence_id": "nonexistent-evidence"},
        headers={"Authorization": "Bearer valid-token"}
    )

    # Should be 404 (evidence not found), not 403 (ownership) or 202
    assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.json()}"
    assert "not found" in response.json()["detail"].lower()


def legacy_test_unauthorized_evidence_prevents_ethereum_anchor():
    """Verify that evidence without proper ownership never reaches blockchain."""
    app = create_app()

    # Setup: User 1 owns evidence, User 2 tries to anchor
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-2"}

    fake_repo = FakeEvidenceRepository([evidence_record(owner_id="user-1", evidence_id="evidence-1")])

    client = TestClient(app)
    response = client.post(
        "/api/evidence/evidence-1/anchor",
        json={"evidence_id": "evidence-1"},
        headers={"Authorization": "Bearer valid-token"}
    )

    # Should fail authorization before any blockchain interaction
    assert response.status_code == 403
    assert len(fake_repo.anchor_writes) == 0, "No anchor writes should occur for unauthorized evidence"


def legacy_test_authorized_evidence_calls_anchor_service():
    """Verify that authorized evidence DOES call the anchor service."""
    app = create_app()

    # Setup: User 1 owns evidence, tries to anchor it
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}

    fake_repo = FakeEvidenceRepository([evidence_record(owner_id="user-1", evidence_id="evidence-1")])

    client = TestClient(app)
    response = client.post(
        "/api/evidence/evidence-1/anchor",
        json={"evidence_id": "evidence-1"},
        headers={"Authorization": "Bearer valid-token"}
    )

    # Should succeed and anchor service should be called
    assert response.status_code == 202
    assert len(fake_repo.anchor_writes) == 1, "Anchor service SHOULD be called for authorized evidence"


def legacy_test_evidence_owner_id_authoritative_boundary():
    """Test that owner_id in Firestore is the authoritative security boundary."""
    app = create_app()

    # Setup: Multiple users, different evidence ownership
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-3"}

    # User 1 evidence
    fake_repo = FakeEvidenceRepository([
        evidence_record(owner_id="user-1", evidence_id="evidence-1"),
        evidence_record(owner_id="user-2", evidence_id="evidence-2"),
    ])

    client = TestClient(app)

    # User 3 tries to anchor User 1's evidence
    response1 = client.post(
        "/api/evidence/evidence-1/anchor",
        json={"evidence_id": "evidence-1"},
        headers={"Authorization": "Bearer valid-token"}
    )
    assert response1.status_code == 403

    # User 3 tries to anchor User 2's evidence
    response2 = client.post(
        "/api/evidence/evidence-2/anchor",
        json={"evidence_id": "evidence-2"},
        headers={"Authorization": "Bearer valid-token"}
    )
    assert response2.status_code == 403

    # No anchor writes should occur for either
    assert len(fake_repo.anchor_writes) == 0, "No anchor writes for any unauthorized evidence"
