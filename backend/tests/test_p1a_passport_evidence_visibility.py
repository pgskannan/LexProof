"""Phase 3H.2: Passport/Evidence visibility must match Contract's own policy (P1-A).

CONFIRMED ROOT CAUSE (Phase 3H.1): Contract Detail reaches Evidence/Anchor data
through:

    GET /api/passports?contract_id={contract_id}
        -> PassportService.list_passports() (filtered by passport.created_by ==
           current_user.uid)
        -> GET /api/passports/{passport_id}/evidence
        -> EvidenceService (filtered by evidence.owner_id == current_user.uid)
        -> GET /api/evidence/{evidence_id}/anchor

The Contract domain (api/contracts.py::_is_visible_to_user) had already moved to
organization-scoped read visibility: any ACTIVE member of the contract's
organization can see it (membership alone, no role check); a contract with no
org_id (legacy/orphan data) keeps strict owner-only visibility. Passport/Evidence
still used a bare owner_id/created_by match, so a legitimate non-owner org member
(an Admin, Reviewer, Approver, Auditor, or any other active member) who could see
a Contract got an empty Passport -> no Evidence -> no Anchor requests -> the
Contract Detail page showed 0/0 anchored for anyone but the uploader.

The fix (domains/passport/authorization.py::is_visible_via_contract, reused by
both PassportService._is_visible and EvidenceService._is_visible) resolves the
record's associated Contract and asks the *same* organization-membership
question api/contracts.py already asks for the Contract itself -- it does not
invent a new, broader, or role-restricted policy. This file proves the fix
directly against the production service methods that sit in the confirmed
root-cause call chain (PassportService.get_passport/get_passport_by_contract/
list_passports, EvidenceService.get_evidence_item/get_evidence_by_passport/
passport_exists), plus two HTTP-level integration checks proving the real
endpoints are wired to the fix.

Scope note: only READ/visibility paths are changed. Evidence mutation paths
(update/delete/verify, via EvidenceService._get_owned_evidence) are deliberately
left untouched and remain strictly owner-scoped -- broadening those was not part
of the confirmed root cause. TEST 11-equivalent coverage of that boundary is
below (test_non_owner_org_member_cannot_mutate_evidence and friends).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import importlib

from app.lexproof.domains.passport.evidence_service import EvidenceService
from app.lexproof.domains.passport.models import EvidenceItemUpdate
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.main import create_app
from app.lexproof.services import organizations as organizations_module
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

# api/__init__.py does `from .router import contract_router, router`, which
# binds the *attribute* app.lexproof.domains.passport.api.router to the
# APIRouter instance, shadowing the submodule of the same name -- so
# `from ...api import router as passport_router` would silently hand us the
# APIRouter, not the module with get_read_passport_service/get_evidence_service
# on it. importlib.import_module (same technique test_passport_retrieval.py
# uses) always resolves the real submodule.
passport_router = importlib.import_module("app.lexproof.domains.passport.api.router")

ORG_A = "org-a"
ORG_B = "org-b"

CONTRACT_A_ID = "contract-a"
LEGACY_CONTRACT_ID = "legacy-contract"

PASSPORT_A_ID = "11111111-1111-1111-1111-111111111111"
PASSPORT_LEGACY_ID = "22222222-2222-2222-2222-222222222222"

EVIDENCE_A_ID = "evidence-a"
EVIDENCE_LEGACY_ID = "evidence-legacy"


def make_orgs() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def passport_record(passport_id: str, contract_id: str, owner_id: str = "owner-1") -> dict:
    return {
        "id": passport_id,
        "passport_id": passport_id,
        "owner_id": owner_id,
        "contract_id": contract_id,
        "contract_version": 1,
        "document_hash": "a" * 64,
        "policy_hash": "b" * 64,
        "analysis_hash": "c" * 64,
        "evidence_hash": "d" * 64,
        "risk_score": 70,
        "compliance_score": 80,
        "policy_version": "default",
        "evidence_count": 1,
        "created_at": _now(),
        "created_by": owner_id,
        "status": "created",
        "audit_events": [],
        "metadata": {},
    }


def evidence_record(evidence_id: str, passport_id: str, contract_id: str, owner_id: str = "owner-1") -> dict:
    return {
        "evidence_id": evidence_id,
        "id": evidence_id,
        "passport_id": passport_id,
        "contract_id": contract_id,
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
        "created_at": _now(),
        "verified_at": None,
        "source": "ai_analysis",
        "source_id": "finding_1",
        "hash": "a" * 64,
        "metadata": {},
    }


def seed_everything() -> None:
    """Contract A (org-scoped) + a legacy/orgless contract, each with one
    Passport and one Evidence item, plus a full org membership matrix mirroring
    test_contract_action_authorization.py's roster."""
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
            # Holds the contract_owner ROLE in this org, but does not own
            # contract-a -- the Contract read policy this reuses only checks
            # active membership, not role, so this member IS expected to see
            # the passport/evidence below (unlike the stricter owner-or-admin
            # *action* policy tested in test_contract_action_authorization.py).
            "other-owner-2": {"user_id": "other-owner-2", "roles": ["contract_owner"], "status": "active", "org_id": ORG_A},
            # Holds admin, but deactivated -- get_active_member() must reject
            # this the same way it already does for Contract reads.
            "deactivated-1": {"user_id": "deactivated-1", "roles": ["admin"], "status": "deactivated", "org_id": ORG_A},
        },
        f"organizations/{ORG_B}/members": {
            "foreign-admin-1": {"user_id": "foreign-admin-1", "roles": ["admin"], "status": "active", "org_id": ORG_B},
        },
        "users": {},
        "organization_invites": {},
        "contracts": {
            CONTRACT_A_ID: {"id": CONTRACT_A_ID, "owner_id": "owner-1", "org_id": ORG_A},
            LEGACY_CONTRACT_ID: {"id": LEGACY_CONTRACT_ID, "owner_id": "owner-1"},
        },
        "legal_passports": {
            PASSPORT_A_ID: passport_record(PASSPORT_A_ID, CONTRACT_A_ID),
            PASSPORT_LEGACY_ID: passport_record(PASSPORT_LEGACY_ID, LEGACY_CONTRACT_ID),
        },
        "evidence_records": {
            EVIDENCE_A_ID: evidence_record(EVIDENCE_A_ID, PASSPORT_A_ID, CONTRACT_A_ID),
            EVIDENCE_LEGACY_ID: evidence_record(EVIDENCE_LEGACY_ID, PASSPORT_LEGACY_ID, LEGACY_CONTRACT_ID),
        },
    }


@pytest.fixture(autouse=True)
def _patch_org_service(monkeypatch):
    seed_everything()
    monkeypatch.setattr(organizations_module, "get_organization_service", make_orgs)
    # The authorization module imports get_organization_service directly into
    # its own namespace (`from ...services.organizations import
    # get_organization_service`), so it must be patched there too.
    from app.lexproof.domains.passport import authorization as authorization_module
    monkeypatch.setattr(authorization_module, "get_organization_service", make_orgs)
    yield


def passport_service(tenant_id: str) -> PassportService:
    return PassportService(
        analysis_engine=lambda *_: None,
        user_id=tenant_id,
        tenant_id=tenant_id,
        repository=FakeRepository("legal_passports"),
        contracts_repository=FakeRepository("contracts"),
    )


def evidence_service(owner_id: str) -> EvidenceService:
    return EvidenceService(
        FakeRepository("evidence_records"),
        owner_id=owner_id,
        passport_repository=FakeRepository("legal_passports"),
        anchor_repository=FakeRepository("evidence_anchors"),
        contracts_repository=FakeRepository("contracts"),
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TEST 1 / TEST 2: contract owner can read Passport and Evidence
# ---------------------------------------------------------------------------

def test_owner_can_read_passport():
    passport = _run(passport_service("owner-1").get_passport(PASSPORT_A_ID))
    assert passport is not None
    assert passport.passport_id == PASSPORT_A_ID


def test_owner_can_read_evidence():
    evidence = _run(evidence_service("owner-1").get_evidence_item(EVIDENCE_A_ID))
    assert evidence is not None
    assert evidence.evidence_id == EVIDENCE_A_ID
    items = _run(evidence_service("owner-1").get_evidence_by_passport(PASSPORT_A_ID))
    assert [item.evidence_id for item in items] == [EVIDENCE_A_ID]
    assert evidence_service("owner-1").passport_exists(PASSPORT_A_ID) is True


# ---------------------------------------------------------------------------
# TEST 3 / TEST 4: authorized non-owner org members can read Passport/Evidence
# ---------------------------------------------------------------------------

NON_OWNER_ORG_MEMBERS = ["admin-1", "reviewer-1", "approver-1", "auditor-1", "other-owner-2"]


@pytest.mark.parametrize("uid", NON_OWNER_ORG_MEMBERS)
def test_authorized_non_owner_can_read_passport(uid):
    """The exact bug fixed: none of these members uploaded contract-a, but
    all are active members of its organization, matching the Contract read
    policy this fix reuses."""
    passport = _run(passport_service(uid).get_passport(PASSPORT_A_ID))
    assert passport is not None, f"{uid} should see the passport (active org member)"

    by_contract = _run(passport_service(uid).get_passport_by_contract(CONTRACT_A_ID, 1))
    assert by_contract is not None

    listed = _run(passport_service(uid).list_passports(contract_id=CONTRACT_A_ID))
    assert [item.passport_id for item in listed] == [PASSPORT_A_ID]


@pytest.mark.parametrize("uid", NON_OWNER_ORG_MEMBERS)
def test_authorized_non_owner_can_read_evidence(uid):
    """The other half of the same bug: 0/0 anchored for any non-uploader."""
    assert evidence_service(uid).passport_exists(PASSPORT_A_ID) is True

    evidence = _run(evidence_service(uid).get_evidence_item(EVIDENCE_A_ID))
    assert evidence is not None

    items = _run(evidence_service(uid).get_evidence_by_passport(PASSPORT_A_ID))
    assert [item.evidence_id for item in items] == [EVIDENCE_A_ID]


# ---------------------------------------------------------------------------
# TEST 5 / TEST 6: foreign-org member cannot read Passport/Evidence
# ---------------------------------------------------------------------------

def test_foreign_org_member_cannot_read_passport():
    assert _run(passport_service("foreign-admin-1").get_passport(PASSPORT_A_ID)) is None
    assert _run(passport_service("foreign-admin-1").get_passport_by_contract(CONTRACT_A_ID, 1)) is None
    assert _run(passport_service("foreign-admin-1").list_passports(contract_id=CONTRACT_A_ID)) == []


def test_foreign_org_member_cannot_read_evidence():
    assert evidence_service("foreign-admin-1").passport_exists(PASSPORT_A_ID) is False
    assert _run(evidence_service("foreign-admin-1").get_evidence_item(EVIDENCE_A_ID)) is None
    assert _run(evidence_service("foreign-admin-1").get_evidence_by_passport(PASSPORT_A_ID)) == []


# ---------------------------------------------------------------------------
# TEST 7 / TEST 8: non-member cannot read Passport/Evidence
# ---------------------------------------------------------------------------

def test_non_member_cannot_read_passport():
    assert _run(passport_service("complete-stranger").get_passport(PASSPORT_A_ID)) is None
    assert _run(passport_service("complete-stranger").list_passports(contract_id=CONTRACT_A_ID)) == []


def test_non_member_cannot_read_evidence():
    assert evidence_service("complete-stranger").passport_exists(PASSPORT_A_ID) is False
    assert _run(evidence_service("complete-stranger").get_evidence_item(EVIDENCE_A_ID)) is None


# ---------------------------------------------------------------------------
# TEST 9: legacy/orgless contract preserves strict owner-only behavior
# ---------------------------------------------------------------------------

def test_legacy_orgless_record_preserves_owner_only_behavior():
    # The real owner still sees it.
    assert _run(passport_service("owner-1").get_passport(PASSPORT_LEGACY_ID)) is not None
    assert evidence_service("owner-1").passport_exists(PASSPORT_LEGACY_ID) is True
    assert _run(evidence_service("owner-1").get_evidence_item(EVIDENCE_LEGACY_ID)) is not None

    # An active org Admin -- who WOULD see an org-scoped contract's passport --
    # must NOT gain access just because a legacy record has no org_id. This is
    # the "do not automatically assign it to an organization" requirement.
    assert _run(passport_service("admin-1").get_passport(PASSPORT_LEGACY_ID)) is None
    assert evidence_service("admin-1").passport_exists(PASSPORT_LEGACY_ID) is False
    assert _run(evidence_service("admin-1").get_evidence_item(EVIDENCE_LEGACY_ID)) is None


# ---------------------------------------------------------------------------
# TEST 10: a caller who fails the Contract's own visibility policy (here: a
# deactivated member -- get_active_member() rejects them exactly as it does
# for Contract reads) remains blocked despite nominally holding a role.
# ---------------------------------------------------------------------------

def test_deactivated_member_remains_blocked_despite_holding_a_role():
    assert _run(passport_service("deactivated-1").get_passport(PASSPORT_A_ID)) is None
    assert evidence_service("deactivated-1").passport_exists(PASSPORT_A_ID) is False
    assert _run(evidence_service("deactivated-1").get_evidence_item(EVIDENCE_A_ID)) is None


# ---------------------------------------------------------------------------
# TEST 11 (equivalent): existing owner / security boundaries continue to pass.
# In particular, this fix must NOT broaden evidence *mutation* (update/
# delete/verify) beyond the owner -- only read visibility changed.
# ---------------------------------------------------------------------------

def test_non_owner_org_member_cannot_mutate_evidence():
    service = evidence_service("admin-1")  # active org member, can now READ evidence-a
    assert _run(service.get_evidence_item(EVIDENCE_A_ID)) is not None

    updated = _run(service.update_evidence_item(EVIDENCE_A_ID, EvidenceItemUpdate(evidence_status="suspicious")))
    assert updated is None, "mutation paths must remain strictly owner-scoped"

    deleted = _run(service.delete_evidence_item(EVIDENCE_A_ID))
    assert deleted is False

    verified = _run(service.verify_evidence_item(EVIDENCE_A_ID))
    assert verified is None

    # The record itself must be untouched.
    assert FakeRepository.stores["evidence_records"][EVIDENCE_A_ID]["evidence_status"] == "valid"


def test_owner_can_still_mutate_their_own_evidence():
    service = evidence_service("owner-1")
    updated = _run(service.update_evidence_item(EVIDENCE_A_ID, EvidenceItemUpdate(evidence_status="suspicious")))
    assert updated is not None
    assert updated.evidence_status.value == "suspicious"


# ---------------------------------------------------------------------------
# Integration: the real HTTP endpoints named in the confirmed root cause are
# actually wired to the fixed services.
# ---------------------------------------------------------------------------

def _client_for(monkeypatch, uid: str) -> TestClient:
    monkeypatch.setattr(
        passport_router,
        "get_read_passport_service",
        lambda user: passport_service(str(user["uid"])),
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    app.dependency_overrides[passport_router.get_evidence_service] = lambda: evidence_service(uid)
    return TestClient(app)


def test_http_list_passports_by_contract_owner(monkeypatch):
    client = _client_for(monkeypatch, "owner-1")
    response = client.get(f"/api/passports?contract_id={CONTRACT_A_ID}", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert [item["passport_id"] for item in response.json()] == [PASSPORT_A_ID]


def test_http_list_passports_by_contract_non_owner_admin(monkeypatch):
    """The literal bug report: GET /api/passports?contract_id=... must no
    longer come back empty for a non-uploader org member."""
    client = _client_for(monkeypatch, "admin-1")
    response = client.get(f"/api/passports?contract_id={CONTRACT_A_ID}", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert [item["passport_id"] for item in response.json()] == [PASSPORT_A_ID]


def test_http_list_passports_by_contract_foreign_member_is_empty(monkeypatch):
    client = _client_for(monkeypatch, "foreign-admin-1")
    response = client.get(f"/api/passports?contract_id={CONTRACT_A_ID}", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert response.json() == []


def test_http_get_evidence_by_passport_non_owner_admin(monkeypatch):
    """The other literal bug report: evidence (and therefore the anchor
    lookups the frontend fires per evidence item) must no longer come back
    empty for a non-uploader org member -- no more 0/0 anchored."""
    client = _client_for(monkeypatch, "admin-1")
    response = client.get(f"/api/passports/{PASSPORT_A_ID}/evidence", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert [item["evidence_id"] for item in response.json()] == [EVIDENCE_A_ID]


def test_http_get_evidence_by_passport_foreign_member_is_404(monkeypatch):
    client = _client_for(monkeypatch, "foreign-admin-1")
    response = client.get(f"/api/passports/{PASSPORT_A_ID}/evidence", headers={"Authorization": "Bearer test"})
    assert response.status_code == 404
