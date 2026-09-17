"""Security / adversarial test pass (hardening item #5).

LexProof's core claim is verifiability + trust: server-enforced access
control and separation of duties. This file proves those specific claims
with automated tests that deliberately try to break them, rather than only
exercising happy paths -- per the explicit ask in
claude/hardening-priority-review-2026-09-10.md item #5.

This file does NOT re-test ground already covered elsewhere in the suite.
In particular, at the time this file was written the following adversarial
scenarios from that review already had real, passing coverage and are
intentionally not duplicated here:

  - Modified/tampered evidence must never verify as VERIFIED:
    tests/lexproof/test_ethereum_anchor_service.py::test_different_hash_is_tampered
  - Untampered evidence must never show TAMPERED:
    tests/lexproof/test_ethereum_anchor_service.py::test_matching_hash_is_verified
  - Deleted/missing evidence must report EVIDENCE_NOT_FOUND, not a false VERIFIED:
    tests/test_public_verification.py (EVIDENCE_NOT_FOUND / ANCHOR_NOT_FOUND cases)
  - A stale/non-current contract version cannot be (re-)analyzed as if current:
    tests/test_explicit_version_analysis.py::test_explicit_analysis_rejects_non_current_version_without_creating_artifacts
  - Anchoring a second, different hash over an existing evidence anchor is rejected:
    tests/lexproof/test_ethereum_anchor_service.py::test_anchor_rejects_existing_evidence_with_different_hash

What follows is the coverage that did NOT already exist explicitly: IDOR/
cross-owner contract access, self-approval and self-publish (a reviewer or
approver acting on their own submission), a read-only role attempting a
write action, unauthenticated and expired-token access to a private
endpoint, and a non-member of an org attempting to act on that org's data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.lexproof.api import contracts as contracts_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.firebase_auth import FirebaseAuthenticationError
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.redline_proposals import ProposalService
from app.lexproof.services.workflow_engine import WorkflowEngine
from tests.fakes import FakeRepository

ORG_ID = "adversarial-org"


# ---------------------------------------------------------------------------
# 1. Cross-owner (IDOR) contract access
# ---------------------------------------------------------------------------

def test_cross_owner_cannot_read_another_users_contract(monkeypatch):
    """A non-member must not read an org-owned contract by guessing its ID."""
    FakeRepository.stores = {
        "contracts": {
            "contract-1": {"id": "contract-1", "owner_id": "owner-1", "org_id": ORG_ID, "current_version_id": "version-1"},
        },
        "contract_versions": {},
        "legal_passports": {},
        "evidence_records": {},
        "evidence_anchors": {},
        "organizations": {ORG_ID: {"org_id": ORG_ID, "status": "active"}},
        f"organizations/{ORG_ID}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": ORG_ID},
        },
        "users": {},
        "organization_invites": {},
    }
    monkeypatch.setattr(
        contracts_api, "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()),
    )
    # get_contract()'s legacy-passport fallback (reached whenever the primary
    # owner_id check denies access, exactly the path this test exercises)
    # constructs its own FirestoreRepository("legal_passports") directly
    # rather than through _repositories() -- patch the class itself so that
    # fallback also reads from FakeRepository.stores instead of trying a real
    # Firestore connection.
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "get_organization_service", make_orgs)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "attacker"}
    client = TestClient(app)

    response = client.get("/api/contracts/contract-1")

    assert response.status_code == 404
    assert "attacker" not in response.text


def test_owner_can_read_their_own_contract(monkeypatch):
    """The owner remains visible as an active member of the organization."""
    seed_contract_visibility()
    monkeypatch.setattr(contracts_api, "get_organization_service", make_orgs)
    monkeypatch.setattr(
        contracts_api, "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()),
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    client = TestClient(app)

    response = client.get("/api/contracts/contract-1")

    assert response.status_code == 200


def seed_contract_visibility():
    FakeRepository.stores = {
        "contracts": {
            "contract-1": {"id": "contract-1", "owner_id": "owner-1", "org_id": ORG_ID, "current_version_id": "version-1"},
        },
        "contract_versions": {},
        "legal_passports": {},
        "organizations": {ORG_ID: {"org_id": ORG_ID, "status": "active"}},
        f"organizations/{ORG_ID}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": ORG_ID},
            "admin-1": {"user_id": "admin-1", "roles": ["admin"], "status": "active", "org_id": ORG_ID},
            "reviewer-1": {"user_id": "reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": ORG_ID},
        },
        "users": {},
        "organization_invites": {},
    }


def make_contract_visibility_client(monkeypatch, uid: str):
    seed_contract_visibility()
    monkeypatch.setattr(
        contracts_api,
        "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()),
    )
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "get_organization_service", make_orgs)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_same_org_admin_can_read_another_users_contract(monkeypatch):
    response = make_contract_visibility_client(monkeypatch, "admin-1").get("/api/contracts/contract-1")
    assert response.status_code == 200


def test_same_org_member_can_read_another_users_contract(monkeypatch):
    response = make_contract_visibility_client(monkeypatch, "reviewer-1").get("/api/contracts/contract-1")
    assert response.status_code == 200


def test_legacy_contract_without_org_id_preserves_owner_only_visibility(monkeypatch):
    seed_contract_visibility()
    FakeRepository.stores["contracts"]["legacy-contract"] = {
        "id": "legacy-contract",
        "owner_id": "owner-1",
        "current_version_id": "version-1",
    }
    monkeypatch.setattr(
        contracts_api,
        "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()),
    )
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "admin-1"}
    response = TestClient(app).get("/api/contracts/legacy-contract")
    assert response.status_code == 404


def test_same_org_owner_can_read_contract_versions(monkeypatch):
    response = make_contract_visibility_client(monkeypatch, "owner-1").get("/api/contracts/contract-1/versions")
    assert response.status_code == 200


def test_same_org_admin_can_read_contract_versions(monkeypatch):
    response = make_contract_visibility_client(monkeypatch, "admin-1").get("/api/contracts/contract-1/versions")
    assert response.status_code == 200


def test_same_org_member_can_read_contract_versions(monkeypatch):
    response = make_contract_visibility_client(monkeypatch, "reviewer-1").get("/api/contracts/contract-1/versions")
    assert response.status_code == 200


def test_nonmember_cannot_read_contract_versions(monkeypatch):
    response = make_contract_visibility_client(monkeypatch, "attacker").get("/api/contracts/contract-1/versions")
    assert response.status_code == 404


def test_legacy_contract_versions_remain_owner_only(monkeypatch):
    seed_contract_visibility()
    FakeRepository.stores["contracts"]["legacy-contract"] = {
        "id": "legacy-contract",
        "owner_id": "owner-1",
        "current_version_id": "version-1",
    }
    monkeypatch.setattr(
        contracts_api,
        "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()),
    )
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "admin-1"}
    response = TestClient(app).get("/api/contracts/legacy-contract/versions")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 2. Self-approval / self-publish (separation of duties)
# ---------------------------------------------------------------------------

def make_orgs() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def make_workflow() -> WorkflowEngine:
    return WorkflowEngine(
        definitions=FakeRepository("workflow_definitions"),
        instances=FakeRepository("workflow_instances"),
        history_factory=lambda instance_id: FakeRepository(f"workflow_instances/{instance_id}/history"),
    )


def make_proposal_service() -> ProposalService:
    return ProposalService(
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        findings=FakeRepository("risk_findings"),
        proposals=FakeRepository("redline_proposals"),
        reviews=FakeRepository("redline_reviews"),
        publication_audits=FakeRepository("redline_publication_audits"),
        passports=FakeRepository("legal_passports"),
        evidence_records=FakeRepository("evidence_records"),
        evidence_anchors=FakeRepository("evidence_anchors"),
        analysis_service=None,
        organizations=make_orgs(),
        workflow=make_workflow(),
    )


def seed_proposal_fixture(extra_members: dict | None = None):
    FakeRepository.stores = {
        "contracts": {"contract-1": {"id": "contract-1", "owner_id": "owner-1", "org_id": ORG_ID, "current_version_id": "version-1"}},
        "contract_versions": {"version-1": {"id": "version-1", "contract_id": "contract-1", "owner_id": "owner-1", "version_number": 1, "content_hash": "hash-v1", "document_text": "Before clause. Exact clause text. After clause."}},
        "risk_findings": {"finding-1": {"id": "finding-1", "contract_id": "contract-1", "version_id": "version-1", "title": "Liability cap", "severity": "critical", "description": "The cap is too low.", "evidence": "Clause text", "evidence_quote": "Exact clause text", "recommendation": "Review the cap."}},
        "redline_proposals": {},
        "redline_reviews": {},
        "redline_publication_audits": {},
        "organizations": {ORG_ID: {"org_id": ORG_ID, "name": "Adversarial Org", "status": "active"}},
        f"organizations/{ORG_ID}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner", "reviewer", "approver"], "status": "active", "org_id": ORG_ID},
            "auditor-1": {"user_id": "auditor-1", "roles": ["auditor"], "status": "active", "org_id": ORG_ID},
            **(extra_members or {}),
        },
        "users": {},
        "organization_invites": {},
        "workflow_definitions": {},
        "workflow_instances": {},
    }


def test_creator_cannot_approve_their_own_proposal():
    """A user who both owns the contract and holds the reviewer role must
    still not be able to approve their own submission -- separation of
    duties is enforced by role membership alone, not by who drafted it."""
    seed_proposal_fixture()
    service = make_proposal_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")

    with pytest.raises(PermissionError):
        service.review(proposal["proposal_id"], "APPROVED", "owner-1")

    assert FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]["status"] != "APPROVED"


def test_creator_cannot_publish_their_own_approved_proposal():
    """Same guarantee at the publish step: the creator holding the approver
    role does not get to publish their own proposal."""
    seed_proposal_fixture(extra_members={
        "reviewer-1": {"user_id": "reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": ORG_ID},
    })
    service = make_proposal_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    service.review(proposal["proposal_id"], "APPROVED", "reviewer-1")

    with pytest.raises(PermissionError):
        service.publish(proposal["proposal_id"], "owner-1")

    stored = FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]
    assert stored.get("published_version_id") is None
    assert stored["status"] != "PUBLISHED"
    # Confirms this genuinely blocked publication rather than silently no-op'ing --
    # no second contract version was ever created.
    assert len(FakeRepository.stores["contract_versions"]) == 1


def test_auditor_read_only_role_cannot_review_or_publish():
    """A read-only role (this app's closest analogue to a "viewer") must be
    rejected by both the review and publish actions, not merely hidden from
    the UI."""
    seed_proposal_fixture()
    service = make_proposal_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")

    with pytest.raises(PermissionError):
        service.review(proposal["proposal_id"], "APPROVED", "auditor-1")

    # Force it into APPROVED via the real reviewer path so publish() has
    # something to reject on its own merits, not just "not approved yet".
    seed_proposal_fixture(extra_members={
        "reviewer-1": {"user_id": "reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": ORG_ID},
    })
    service = make_proposal_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    service.review(proposal["proposal_id"], "APPROVED", "reviewer-1")

    with pytest.raises(PermissionError):
        service.publish(proposal["proposal_id"], "auditor-1")


def test_non_member_cannot_act_on_a_foreign_orgs_proposal():
    """A real Firebase-authenticated user who simply has no membership record
    in this org must be rejected, not merely unauthorized by role."""
    seed_proposal_fixture()
    service = make_proposal_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")

    with pytest.raises(PermissionError):
        service.review(proposal["proposal_id"], "APPROVED", "total-stranger")


# ---------------------------------------------------------------------------
# 3. Unauthenticated and expired-token access to a private endpoint
# ---------------------------------------------------------------------------

def test_unauthenticated_request_to_private_endpoint_is_rejected():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/contracts/contract-1")

    assert response.status_code == 401


def test_expired_token_is_rejected_as_401_not_treated_as_valid(monkeypatch):
    """An expired Firebase ID token must fail closed (401), exercised through
    the exact code path a real expired token hits: firebase_auth.verify_firebase_token
    raising FirebaseAuthenticationError, caught by get_current_user."""
    import app.lexproof.services.auth as auth_module

    def _raise_expired(token):
        raise FirebaseAuthenticationError("Firebase ID token has expired")

    monkeypatch.setattr(auth_module, "verify_firebase_token", _raise_expired)
    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/contracts/contract-1",
        headers={"Authorization": "Bearer this-token-is-expired"},
    )

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()
