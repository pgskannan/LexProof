"""Phase 3D: contract-action authorization consistency (Phase 1/2 audit P1).

Prior to this fix, POST /contracts/{id}/analyze, POST /contracts/{id}/versions,
and the shared VersionAnalysisService.analyze_version() that backs both that
endpoint and POST /contracts/{id}/versions/{version_id}/analyze all used a bare
`contract.get("owner_id") == uid` check -- independent of the organization/role
model already enforced for read endpoints (api/contracts.py::_is_visible_to_user,
api/findings.py::_visible) and for redline-proposal actions
(services/redline_proposals.py's owner-or-admin rule). A legitimate org Admin
could see a contract (via the org-aware read endpoints) but not act on it if
they had not personally uploaded it.

The fix reuses the exact owner-or-admin rule already established in
services/redline_proposals.py (see its create()/update() methods), factored
out as services/organizations.py::contract_owner_or_org_admin, rather than
introducing a new authorization mechanism or weakening anything: only the
real owner or an active org Admin may act; Reviewer/Approver/Auditor and a
Contract-Owner-*role* member who does not actually own the contract remain
blocked; a member of a different org and a non-member are both blocked
(tenant isolation preserved); and a legacy contract with no org_id keeps its
original, strict owner-only behavior.

This file covers:
  1. Unit-level coverage of the authorization predicate itself (the matrix).
  2. Integration coverage (real FastAPI endpoints) proving the fix actually
     takes effect for POST /contracts/{id}/versions and
     POST /contracts/{id}/analyze, including the explicit-version-analyze
     endpoint that previously had *no* API-layer check at all.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.lexproof.api import contracts as contracts_api
from app.lexproof.main import create_app
from app.lexproof.services import organizations as organizations_module
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import (
    OrganizationService,
    contract_owner_or_org_admin,
)
from tests.fakes import FakeRepository

ORG_A = "org-a"
ORG_B = "org-b"


def make_orgs() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def seed_orgs_and_members() -> None:
    FakeRepository.stores = {
        "organizations": {
            ORG_A: {"org_id": ORG_A, "status": "active"},
            ORG_B: {"org_id": ORG_B, "status": "active"},
        },
        f"organizations/{ORG_A}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": ORG_A},
            "admin-1": {"user_id": "admin-1", "roles": ["admin"], "status": "active", "org_id": ORG_A},
            "reviewer-1": {"user_id": "reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": ORG_A},
            "approver-1": {"user_id": "approver-1", "roles": ["approver"], "status": "active", "org_id": ORG_A},
            "auditor-1": {"user_id": "auditor-1", "roles": ["auditor"], "status": "active", "org_id": ORG_A},
            # Holds the contract_owner role in this org, but does not own
            # contract-1 below -- role membership alone must not be enough.
            "other-owner-2": {"user_id": "other-owner-2", "roles": ["contract_owner"], "status": "active", "org_id": ORG_A},
            "deactivated-1": {"user_id": "deactivated-1", "roles": ["admin"], "status": "deactivated", "org_id": ORG_A},
        },
        f"organizations/{ORG_B}/members": {
            "foreign-admin-1": {"user_id": "foreign-admin-1", "roles": ["admin"], "status": "active", "org_id": ORG_B},
        },
        "users": {},
        "organization_invites": {},
    }


# ---------------------------------------------------------------------------
# 1. Authorization matrix (unit-level, on contract_owner_or_org_admin itself)
# ---------------------------------------------------------------------------

CONTRACT_A = {"id": "authz-contract-1", "owner_id": "owner-1", "org_id": ORG_A}
LEGACY_CONTRACT = {"id": "legacy-1", "owner_id": "owner-1"}


@pytest.fixture(autouse=True)
def _patch_org_service(monkeypatch):
    seed_orgs_and_members()
    monkeypatch.setattr(organizations_module, "get_organization_service", make_orgs)
    monkeypatch.setattr(contracts_api, "get_organization_service", make_orgs)


def test_owner_is_authorized():
    assert contract_owner_or_org_admin(CONTRACT_A, "owner-1") is True


def test_same_org_admin_is_authorized_even_though_not_owner():
    assert contract_owner_or_org_admin(CONTRACT_A, "admin-1") is True


def test_reviewer_is_not_authorized():
    assert contract_owner_or_org_admin(CONTRACT_A, "reviewer-1") is False


def test_approver_is_not_authorized():
    assert contract_owner_or_org_admin(CONTRACT_A, "approver-1") is False


def test_auditor_is_not_authorized():
    assert contract_owner_or_org_admin(CONTRACT_A, "auditor-1") is False


def test_contract_owner_role_without_actual_ownership_is_not_authorized():
    """Holding the contract_owner role in the org is not the same as owning
    this particular contract -- ownership must remain meaningful."""
    assert contract_owner_or_org_admin(CONTRACT_A, "other-owner-2") is False


def test_deactivated_admin_is_not_authorized():
    assert contract_owner_or_org_admin(CONTRACT_A, "deactivated-1") is False


def test_member_of_a_different_org_is_not_authorized():
    """Tenant isolation: an Admin of ORG_B has no standing over an ORG_A contract."""
    assert contract_owner_or_org_admin(CONTRACT_A, "foreign-admin-1") is False


def test_non_member_is_not_authorized():
    assert contract_owner_or_org_admin(CONTRACT_A, "complete-stranger") is False


def test_legacy_contract_without_org_id_keeps_strict_owner_only_behavior():
    assert contract_owner_or_org_admin(LEGACY_CONTRACT, "owner-1") is True
    assert contract_owner_or_org_admin(LEGACY_CONTRACT, "admin-1") is False


# ---------------------------------------------------------------------------
# 2. Integration: POST /contracts/{id}/versions
# ---------------------------------------------------------------------------

def seed_contract_with_version() -> None:
    seed_orgs_and_members()
    FakeRepository.stores["contracts"] = {
        "authz-contract-1": {"id": "authz-contract-1", "owner_id": "owner-1", "org_id": ORG_A, "current_version_id": "authz-version-1"},
    }
    FakeRepository.stores["contract_versions"] = {
        "authz-version-1": {
            "id": "authz-version-1",
            "owner_id": "owner-1",
            "org_id": ORG_A,
            "contract_id": "authz-contract-1",
            "version_number": 1,
            "storage_path": "gs://bucket/v1.txt",
            "content_hash": "hash-v1",
            "document_text": "Original contract",
            "analysis_status": "complete",
        },
    }


def make_client(monkeypatch, uid: str) -> TestClient:
    seed_contract_with_version()
    monkeypatch.setattr(
        contracts_api,
        "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()),
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_owner_can_create_version(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    response = client.post("/api/contracts/authz-contract-1/versions", json={"source_version_id": "authz-version-1"})
    assert response.status_code == 201


def test_same_org_admin_can_create_version(monkeypatch):
    """The exact P1 fixed: an org Admin who did not upload the contract can
    now perform the owner-gated action their role should permit."""
    client = make_client(monkeypatch, "admin-1")
    response = client.post("/api/contracts/authz-contract-1/versions", json={"source_version_id": "authz-version-1"})
    assert response.status_code == 201


def test_reviewer_cannot_create_version(monkeypatch):
    client = make_client(monkeypatch, "reviewer-1")
    response = client.post("/api/contracts/authz-contract-1/versions", json={"source_version_id": "authz-version-1"})
    assert response.status_code == 403


def test_auditor_cannot_create_version(monkeypatch):
    client = make_client(monkeypatch, "auditor-1")
    response = client.post("/api/contracts/authz-contract-1/versions", json={"source_version_id": "authz-version-1"})
    assert response.status_code == 403


def test_contract_owner_role_without_ownership_cannot_create_version(monkeypatch):
    client = make_client(monkeypatch, "other-owner-2")
    response = client.post("/api/contracts/authz-contract-1/versions", json={"source_version_id": "authz-version-1"})
    assert response.status_code == 403


def test_member_of_foreign_org_cannot_create_version(monkeypatch):
    client = make_client(monkeypatch, "foreign-admin-1")
    response = client.post("/api/contracts/authz-contract-1/versions", json={"source_version_id": "authz-version-1"})
    assert response.status_code == 403


def test_nonmember_cannot_create_version(monkeypatch):
    client = make_client(monkeypatch, "complete-stranger")
    response = client.post("/api/contracts/authz-contract-1/versions", json={"source_version_id": "authz-version-1"})
    assert response.status_code == 403


def test_missing_contract_still_404s_for_create_version(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    response = client.post("/api/contracts/missing/versions", json={"source_version_id": "authz-version-1"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 3. Integration: POST /contracts/{id}/analyze and the explicit-version
#    analyze endpoint (which previously had *no* API-layer authorization at
#    all -- it relied solely on VersionAnalysisService's own now-fixed check).
# ---------------------------------------------------------------------------

ANALYSIS = {
    "risk_score": 20,
    "risk_level": "LOW",
    "compliance_score": 90,
    "findings": [{
        "title": "Standard clause",
        "severity": "low",
        "description": "Nothing notable.",
        "evidence": "Original contract",
        "recommendation": "No action needed.",
        "risk_impact": 10,
        "compliance_impact": 10,
        "source_section": "Section 1",
        "evidence_quote": "Original contract",
    }],
    "key_clauses": [{"text": "Original contract"}],
    "compliance_items": [],
}


class FakeProvider:
    async def complete(self, request):
        return type("Response", (), {"content": json.dumps(ANALYSIS)})()


class FakeAnchorService:
    def __init__(self, repository, evidence_repository):
        self.repository = repository
        self.evidence_repository = evidence_repository

    async def anchor_evidence(self, evidence_id, **kwargs):
        existing = self.repository.get(evidence_id)
        if existing:
            return existing
        proof = {"evidence_id": evidence_id, "evidence_hash": "hash", "transaction_hash": "fake-tx", "block_number": 1}
        self.repository.set(evidence_id, proof)
        return proof


def make_analysis_client(monkeypatch, uid: str) -> TestClient:
    seed_contract_with_version()
    FakeRepository.stores["legal_passports"] = {}
    FakeRepository.stores["risk_findings"] = {}
    FakeRepository.stores["evidence_records"] = {}
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(
        contracts_api,
        "_repositories",
        lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()),
    )
    monkeypatch.setattr(contracts_api, "VertexGeminiProvider", FakeProvider)
    monkeypatch.setattr(contracts_api, "EvidenceAnchorRepository", FakeRepository)
    monkeypatch.setattr(
        contracts_api,
        "get_ethereum_anchor_service",
        lambda **kwargs: FakeAnchorService(kwargs["repository"], kwargs["evidence_repository"]),
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_owner_can_analyze_contract(monkeypatch):
    client = make_analysis_client(monkeypatch, "owner-1")
    response = client.post("/api/contracts/authz-contract-1/analyze")
    assert response.status_code == 200


def test_same_org_admin_can_analyze_contract(monkeypatch):
    """The exact P1 fixed on the /analyze endpoint."""
    client = make_analysis_client(monkeypatch, "admin-1")
    response = client.post("/api/contracts/authz-contract-1/analyze")
    assert response.status_code == 200


def test_reviewer_cannot_analyze_contract(monkeypatch):
    client = make_analysis_client(monkeypatch, "reviewer-1")
    response = client.post("/api/contracts/authz-contract-1/analyze")
    assert response.status_code == 404  # analyze_contract masks denial as not-found, unchanged behavior


def test_member_of_foreign_org_cannot_analyze_contract(monkeypatch):
    client = make_analysis_client(monkeypatch, "foreign-admin-1")
    response = client.post("/api/contracts/authz-contract-1/analyze")
    assert response.status_code == 404


def test_nonmember_cannot_analyze_contract(monkeypatch):
    client = make_analysis_client(monkeypatch, "complete-stranger")
    response = client.post("/api/contracts/authz-contract-1/analyze")
    assert response.status_code == 404


def test_same_org_admin_can_use_explicit_version_analyze_endpoint(monkeypatch):
    """Regression + fix: POST /contracts/{id}/versions/{version_id}/analyze had
    *no* authorization check of its own at the API layer -- it relied entirely
    on VersionAnalysisService.analyze_version()'s internal owner_id check,
    which is what this phase fixed. This proves an org Admin can now use this
    endpoint too, not just /analyze."""
    client = make_analysis_client(monkeypatch, "admin-1")
    response = client.post("/api/contracts/authz-contract-1/versions/authz-version-1/analyze")
    assert response.status_code == 200


def test_reviewer_cannot_use_explicit_version_analyze_endpoint(monkeypatch):
    client = make_analysis_client(monkeypatch, "reviewer-1")
    response = client.post("/api/contracts/authz-contract-1/versions/authz-version-1/analyze")
    assert response.status_code == 403


def test_nonmember_cannot_use_explicit_version_analyze_endpoint(monkeypatch):
    """Without this phase's fix, a non-member firebase user was still blocked
    here too (owner_id-only check happened to reject everyone but the real
    owner) -- this locks in that the fix did not accidentally loosen it."""
    client = make_analysis_client(monkeypatch, "complete-stranger")
    response = client.post("/api/contracts/authz-contract-1/versions/authz-version-1/analyze")
    assert response.status_code == 403


def test_member_of_foreign_org_cannot_use_explicit_version_analyze_endpoint(monkeypatch):
    client = make_analysis_client(monkeypatch, "foreign-admin-1")
    response = client.post("/api/contracts/authz-contract-1/versions/authz-version-1/analyze")
    assert response.status_code == 403
