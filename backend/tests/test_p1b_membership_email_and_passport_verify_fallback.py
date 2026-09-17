"""Phase 3H.5: regression tests for two confirmed, narrow authorization/data
fixes.

1. P1-B (membership document email inconsistency): OrganizationService.
   list_members() used to prefer a membership document's own, possibly
   stale, `email` field over the live `users/{user_id}.email` record that
   sync_signed_in_user() keeps current on every sign-in. A membership
   created directly (e.g. by a seed/demo script) rather than through
   invite_member() has no matching organization_invites record, so
   sync_signed_in_user()'s invite-acceptance reconciliation loop never
   touches its stored email -- it could go stale forever. The fix flips
   list_members()'s precedence to prefer the live user email, falling back
   to the membership doc's own email only when no live user record (or no
   email on it) exists yet. This is purely a read-side join change: no
   Firestore writes, no duplicate memberships, no change to roles/status,
   and no change to authorization (get_member/get_active_member, which
   auth.py's load_org_member uses for roles/status only, are untouched).

2. Passport verify fallback (`_scan_evidence_for_passport`, inside
   POST /passports/{id}/verify): this fallback -- reached only when the
   primary in-process `PassportService.get_evidence()` snapshot is empty,
   which is the common case for any passport not created in this exact
   process's memory -- used to gate on a bare `owner_id` comparison,
   independent of the org-aware `is_visible_via_contract` visibility rule
   the sibling read endpoints (GET /evidence/{id}, GET
   /passports/{id}/evidence) already use. A legitimate non-owner org member
   who could read a passport's evidence through those endpoints was
   silently denied evidence in the /verify fallback specifically. The fix
   reuses EvidenceService._is_visible (the exact mechanism those read
   endpoints already use) instead of inventing a second, inconsistent
   check. Legacy/orgless records keep the original strict owner-only rule.
"""

from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.lexproof.domains.passport.evidence_service import EvidenceService
from app.lexproof.domains.passport.models import EvidenceItemUpdate
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

passport_router = importlib.import_module("app.lexproof.domains.passport.api.router")

ORG_ID = "lexproof-demo-fixture"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reset_stores() -> None:
    FakeRepository.stores = {
        "organizations": {},
        "users": {},
        "organization_invites": {},
        f"organizations/{ORG_ID}/members": {},
    }


def make_service() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Section 1: P1-B membership email consistency (OrganizationService.list_members)
# ---------------------------------------------------------------------------


def test_list_members_prefers_current_user_email_over_stale_membership_email():
    """The literal reported bug: a directly-seeded membership doc still has
    its original placeholder email, but the user has since signed in for
    real and their global users/{id}.email record is current."""
    reset_stores()
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    service.ensure_member(ORG_ID, "seed-admin-1", ["admin"], email="seed-admin-1@lexproof.local")
    # Simulate a real sign-in updating the global user record, with no
    # matching organization_invites entry (this membership was never
    # created via invite_member()).
    service.upsert_user("seed-admin-1", email="realuser@example.com")

    members = service.list_members(ORG_ID)
    seed_admin = next(m for m in members if m["user_id"] == "seed-admin-1")
    assert seed_admin["email"] == "realuser@example.com"


def test_list_members_falls_back_to_membership_email_when_no_user_record():
    """A membership document can exist with a stored email before any
    users/{id} record exists for that user at all (every service-layer
    helper that creates a membership -- ensure_member, invite_member's
    resolved-user branch, _upsert_member -- also upserts a users/{id}
    record in the same call, so this state is modeled by seeding the
    membership doc directly, the same way tests/test_p1a_..._visibility.py's
    seed_everything() seeds FakeRepository.stores directly). list_members
    must still surface the membership's own stored email rather than
    showing blank/None when there is truly no live user record to prefer."""
    reset_stores()
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    FakeRepository.stores[f"organizations/{ORG_ID}/members"]["not-signed-in-yet"] = {
        "user_id": "not-signed-in-yet",
        "org_id": ORG_ID,
        "roles": ["auditor"],
        "status": "invited",
        "email": "not-signed-in-yet@example.com",
    }
    assert "not-signed-in-yet" not in FakeRepository.stores["users"]

    members = service.list_members(ORG_ID)
    invited = next(m for m in members if m["user_id"] == "not-signed-in-yet")
    assert invited["email"] == "not-signed-in-yet@example.com"


def test_list_members_unchanged_when_membership_email_matches_current():
    """No behavior change in the common, already-correct case: membership
    email and live user email already agree."""
    reset_stores()
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    service.ensure_member(ORG_ID, "member-1", ["reviewer"], email="member1@example.com")
    service.upsert_user("member-1", email="member1@example.com")

    members = service.list_members(ORG_ID)
    member = next(m for m in members if m["user_id"] == "member-1")
    assert member["email"] == "member1@example.com"


def test_list_members_falls_back_when_user_record_has_no_email():
    """A users/{id} record exists (e.g. created via upsert_user with only a
    display_name) but carries no email -- list_members must not regress to
    showing an empty email when the membership doc has a real one."""
    reset_stores()
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    service.ensure_member(ORG_ID, "member-2", ["reviewer"], email="member2@example.com")
    # A users record with no email at all (upsert_user with email=None keeps
    # any prior email, so seed a blank one directly to model a genuinely
    # email-less user record).
    FakeRepository.stores["users"]["member-2"] = {"user_id": "member-2", "email": "", "display_name": "No Email Yet"}

    members = service.list_members(ORG_ID)
    member = next(m for m in members if m["user_id"] == "member-2")
    assert member["email"] == "member2@example.com"


def test_multi_org_user_email_not_leaked_across_orgs():
    """A user who belongs to two orgs, each with its own (differently
    stale) stored membership email, must see the SAME authoritative live
    email in both listings -- never one org's stored membership email
    bleeding into the other org's listing."""
    reset_stores()
    other_org = "lexproof-demo-fixture-2"
    FakeRepository.stores[f"organizations/{other_org}/members"] = {}
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    service.create_org("Second Org", "creator-2", org_id=other_org, creator_email="creator2@example.com")
    service.ensure_member(ORG_ID, "multi-1", ["reviewer"], email="stale-org-a@example.com")
    service.ensure_member(other_org, "multi-1", ["auditor"], email="stale-org-b@example.com")
    service.upsert_user("multi-1", email="live-current@example.com")

    org_a_email = next(m for m in service.list_members(ORG_ID) if m["user_id"] == "multi-1")["email"]
    org_b_email = next(m for m in service.list_members(other_org) if m["user_id"] == "multi-1")["email"]
    assert org_a_email == "live-current@example.com"
    assert org_b_email == "live-current@example.com"


def test_get_active_member_email_behavior_unchanged():
    """get_active_member/get_member are the authorization-relevant reads
    (auth.py's load_org_member uses them for roles/status) and must be
    completely untouched by this read-only listing fix: they still return
    whatever raw email happens to be stored on the membership doc, with no
    join against users/{id}."""
    reset_stores()
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    service.ensure_member(ORG_ID, "seed-admin-2", ["admin"], email="seed-admin-2@lexproof.local")
    service.upsert_user("seed-admin-2", email="realuser2@example.com")

    active = service.get_active_member(ORG_ID, "seed-admin-2")
    assert active is not None
    assert active["roles"] == ["admin"]
    assert active["status"] == "active"
    # Unchanged: get_active_member/get_member never joined against users and
    # still don't -- this fix only touches list_members().
    assert active.get("email") == "seed-admin-2@lexproof.local"


def test_list_members_still_returns_all_valid_members():
    """Sanity: the fix doesn't drop, duplicate, or otherwise corrupt the
    member list itself -- same members, same roles/status as before."""
    reset_stores()
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    service.ensure_member(ORG_ID, "member-a", ["reviewer"], email="a@example.com")
    service.ensure_member(ORG_ID, "member-b", ["approver"], email="b@example.com")
    service.ensure_member(ORG_ID, "member-c", ["auditor"], email="c@example.com")

    members = service.list_members(ORG_ID)
    user_ids = {m["user_id"] for m in members}
    assert user_ids == {"creator-1", "member-a", "member-b", "member-c"}
    by_id = {m["user_id"]: m for m in members}
    assert by_id["member-a"]["roles"] == ["reviewer"]
    assert by_id["member-b"]["roles"] == ["approver"]
    assert by_id["member-c"]["roles"] == ["auditor"]
    assert all(m["status"] == "active" for m in members)


def test_invite_created_membership_continues_to_work_after_acceptance():
    """Regression: the already-working invite -> sync_signed_in_user()
    acceptance path (which DOES reconcile membership email today) must
    keep working unchanged after this fix."""
    reset_stores()
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    service.invite_member(ORG_ID, "invitee@example.com", ["approver"], "creator-1")
    accepted = service.sync_signed_in_user("invitee-uid", "invitee@example.com", "Invitee")
    assert any(org["org_id"] == ORG_ID for org in accepted["orgs"])

    members = service.list_members(ORG_ID)
    invitee = next(m for m in members if m["user_id"] == "invitee-uid")
    assert invitee["email"] == "invitee@example.com"
    assert invitee["status"] == "active"
    assert invitee["roles"] == ["approver"]


def test_seed_or_directly_created_membership_no_longer_permanently_stale():
    """End-to-end reproduction of the confirmed P1-B root cause, mirroring
    the real Firestore data: a directly-seeded membership document (no
    organization_invites record at all) whose email must reflect the
    user's current, live sign-in email rather than staying stuck on its
    original placeholder forever."""
    reset_stores()
    service = make_service()
    service.create_org("Demo Org", "creator-1", org_id=ORG_ID, creator_email="creator@example.com")
    service.ensure_member(ORG_ID, "demo-admin-1", ["admin"], email="demo-admin-1@placeholder.local")
    assert FakeRepository.stores["organization_invites"] == {}

    # Real sign-in happens later, with no invite in play.
    service.sync_signed_in_user("demo-admin-1", "realuser@example.com", "Real User")

    members = service.list_members(ORG_ID)
    demo_admin = next(m for m in members if m["user_id"] == "demo-admin-1")
    assert demo_admin["email"] == "realuser@example.com", (
        "membership email must no longer be permanently stuck on the seed placeholder"
    )
    # Authorization itself was never broken and must remain correct.
    active = service.get_active_member(ORG_ID, "demo-admin-1")
    assert active is not None
    assert active["roles"] == ["admin"]
    assert active["status"] == "active"


# ---------------------------------------------------------------------------
# Section 2: Passport verify fallback authorization (_scan_evidence_for_passport)
# ---------------------------------------------------------------------------

VERIFY_ORG = "verify-org-fixture"
VERIFY_FOREIGN_ORG = "verify-org-foreign-fixture"


def make_orgs() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def passport_record(passport_id: str, contract_id: str, owner_id: str) -> dict:
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


def evidence_record(evidence_id: str, passport_id: str, contract_id: str, owner_id: str) -> dict:
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


@pytest.fixture
def verify_fixture(monkeypatch):
    """Seeds one org-scoped contract/passport/evidence triple (owned by
    'owner-1', in VERIFY_ORG) and one legacy/orgless triple (owned by
    'legacy-owner'), plus a membership roster covering an authorized
    non-owner org member, a foreign-org member, and (implicitly, by
    omission) a non-member. Fresh, uuid4-derived passport/evidence ids each
    call so PassportService's in-process `_evidence_by_passport` snapshot
    (populated only by create_passport, never by this fixture) is
    guaranteed empty -- which is exactly what forces the real endpoint to
    take the `_scan_evidence_for_passport` fallback branch being tested,
    the same way it does for any passport not created in-process (the
    documented common case, e.g. after a server restart or for seeded
    data)."""
    passport_id = str(uuid4())
    evidence_id = str(uuid4())
    contract_id = str(uuid4())

    legacy_passport_id = str(uuid4())
    legacy_evidence_id = str(uuid4())
    legacy_contract_id = str(uuid4())

    FakeRepository.stores = {
        "organizations": {
            VERIFY_ORG: {"org_id": VERIFY_ORG, "status": "active"},
            VERIFY_FOREIGN_ORG: {"org_id": VERIFY_FOREIGN_ORG, "status": "active"},
        },
        f"organizations/{VERIFY_ORG}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": VERIFY_ORG},
            "admin-1": {"user_id": "admin-1", "roles": ["admin"], "status": "active", "org_id": VERIFY_ORG},
        },
        f"organizations/{VERIFY_FOREIGN_ORG}/members": {
            "foreign-admin-1": {
                "user_id": "foreign-admin-1",
                "roles": ["admin"],
                "status": "active",
                "org_id": VERIFY_FOREIGN_ORG,
            },
        },
        "users": {},
        "organization_invites": {},
        "contracts": {
            contract_id: {"id": contract_id, "owner_id": "owner-1", "org_id": VERIFY_ORG},
            legacy_contract_id: {"id": legacy_contract_id, "owner_id": "legacy-owner"},
        },
        "legal_passports": {
            passport_id: passport_record(passport_id, contract_id, "owner-1"),
            legacy_passport_id: passport_record(legacy_passport_id, legacy_contract_id, "legacy-owner"),
        },
        "evidence_records": {
            evidence_id: evidence_record(evidence_id, passport_id, contract_id, "owner-1"),
            legacy_evidence_id: evidence_record(legacy_evidence_id, legacy_passport_id, legacy_contract_id, "legacy-owner"),
        },
    }

    monkeypatch.setattr(
        "app.lexproof.services.organizations.get_organization_service", make_orgs
    )
    from app.lexproof.domains.passport import authorization as authorization_module

    monkeypatch.setattr(authorization_module, "get_organization_service", make_orgs)

    return {
        "passport_id": passport_id,
        "evidence_id": evidence_id,
        "contract_id": contract_id,
        "legacy_passport_id": legacy_passport_id,
        "legacy_evidence_id": legacy_evidence_id,
        "legacy_contract_id": legacy_contract_id,
    }


def _passport_service_for(uid: str) -> PassportService:
    return PassportService(
        analysis_engine=lambda *_: None,
        user_id=uid,
        tenant_id=uid,
        repository=FakeRepository("legal_passports"),
        contracts_repository=FakeRepository("contracts"),
    )


def _evidence_service_for(uid: str) -> EvidenceService:
    return EvidenceService(
        FakeRepository("evidence_records"),
        owner_id=uid,
        passport_repository=FakeRepository("legal_passports"),
        anchor_repository=FakeRepository("evidence_anchors"),
        contracts_repository=FakeRepository("contracts"),
    )


def _client_and_capture(monkeypatch, uid: str):
    """Builds a TestClient wired to fixture-backed services (mirroring
    tests/test_p1a_passport_evidence_visibility.py's _client_for pattern),
    plus a `captured` dict that records exactly which evidence_items
    verify_passport_integrity() was called with -- so assertions below
    prove what the fallback branch itself returned, not just the HTTP
    status code."""
    monkeypatch.setattr(passport_router, "get_read_passport_service", lambda user: _passport_service_for(str(user["uid"])))
    monkeypatch.setattr(passport_router, "get_evidence_service", _make_get_evidence_service(uid))
    # verify_passport_integrity_endpoint has its own pre-existing (not part
    # of this fix) legacy fallback for an invisible passport that builds a
    # *raw* FirestoreRepository directly rather than reusing the
    # already-patchable passport_service.repository -- patch the name the
    # same way FakeRepository stands in everywhere else in this test file,
    # so a genuinely-blocked read hits FakeRepository's in-memory
    # "legal_passports" store instead of trying to reach real Firestore.
    monkeypatch.setattr(passport_router, "FirestoreRepository", FakeRepository)

    captured: dict = {}

    def _spy_verify(passport_data, evidence_items=None):
        captured["evidence_ids"] = sorted(
            (item.get("evidence_id") or item.get("id")) for item in (evidence_items or [])
        )
        return {"verified": True, "spy": True}

    monkeypatch.setattr(passport_router, "verify_passport_integrity", _spy_verify)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app), captured


def _make_get_evidence_service(uid: str):
    async def _get_evidence_service(user):
        return _evidence_service_for(str(user["uid"]))

    return _get_evidence_service


def test_owner_can_verify_via_fallback(verify_fixture, monkeypatch):
    client, captured = _client_and_capture(monkeypatch, "owner-1")
    response = client.post(f"/api/passports/{verify_fixture['passport_id']}/verify", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert captured["evidence_ids"] == [verify_fixture["evidence_id"]]


def test_authorized_non_owner_org_member_can_verify_via_fallback(verify_fixture, monkeypatch):
    """The fix under test: admin-1 never uploaded this contract/passport,
    but is an active member of its organization -- the same visibility
    rule the sibling GET /evidence endpoints already grant this member
    must now also apply inside the /verify fallback."""
    client, captured = _client_and_capture(monkeypatch, "admin-1")
    response = client.post(f"/api/passports/{verify_fixture['passport_id']}/verify", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert captured["evidence_ids"] == [verify_fixture["evidence_id"]], (
        "authorized non-owner org member must receive evidence via the fallback branch"
    )


def test_foreign_org_member_cannot_gain_evidence_via_fallback(verify_fixture, monkeypatch):
    client, captured = _client_and_capture(monkeypatch, "foreign-admin-1")
    response = client.post(f"/api/passports/{verify_fixture['passport_id']}/verify", headers={"Authorization": "Bearer test"})
    assert response.status_code == 404, "a foreign-org member cannot even see the passport itself"


def test_non_member_cannot_gain_evidence_via_fallback(verify_fixture, monkeypatch):
    client, captured = _client_and_capture(monkeypatch, "complete-stranger-1")
    response = client.post(f"/api/passports/{verify_fixture['passport_id']}/verify", headers={"Authorization": "Bearer test"})
    assert response.status_code == 404, "a non-member cannot even see the passport itself"


def test_legacy_orgless_passport_owner_still_verifies_via_fallback(verify_fixture, monkeypatch):
    """Legacy/orgless behavior must remain owner-only: the actual owner
    still gets their evidence through the fallback."""
    client, captured = _client_and_capture(monkeypatch, "legacy-owner")
    response = client.post(f"/api/passports/{verify_fixture['legacy_passport_id']}/verify", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert captured["evidence_ids"] == [verify_fixture["legacy_evidence_id"]]


def test_legacy_orgless_passport_non_owner_blocked_via_fallback(verify_fixture, monkeypatch):
    """Legacy/orgless behavior must remain owner-only: a non-owner, even one
    who is an active admin of a real organization, must NOT gain access to
    a legacy/orgless record just because is_visible_via_contract cannot
    resolve an org_id for it."""
    client, captured = _client_and_capture(monkeypatch, "admin-1")
    response = client.post(f"/api/passports/{verify_fixture['legacy_passport_id']}/verify", headers={"Authorization": "Bearer test"})
    assert response.status_code == 404, (
        "a non-owner must not see a legacy/orgless passport at all (owner-only, unchanged)"
    )


def test_fallback_not_reached_when_primary_path_has_evidence(verify_fixture, monkeypatch):
    """Sanity check on the test technique itself: when the primary
    PassportService.get_evidence() snapshot is non-empty, the endpoint must
    use THAT list and never call the fallback scan at all. This proves the
    other tests above are actually exercising the fallback branch, not
    merely riding on primary-path behavior that would pass regardless of
    this fix."""
    from app.lexproof.domains.passport import service as service_module

    passport_id = verify_fixture["passport_id"]
    primary_item = {"evidence_id": "primary-only-item", "id": "primary-only-item"}
    service_module._evidence_by_passport[passport_id] = [primary_item]
    try:
        client, captured = _client_and_capture(monkeypatch, "owner-1")
        response = client.post(f"/api/passports/{passport_id}/verify", headers={"Authorization": "Bearer test"})
        assert response.status_code == 200
        assert captured["evidence_ids"] == ["primary-only-item"], (
            "primary in-process snapshot must take precedence over the fallback scan"
        )
    finally:
        service_module._evidence_by_passport.pop(passport_id, None)


def test_non_owner_org_member_still_cannot_mutate_evidence_seen_via_fallback(verify_fixture, monkeypatch):
    """Existing mutation authorization must be completely unaffected by
    this read-only fallback fix: admin-1 can now read/verify evidence-a via
    the fallback, but update/delete/verify-evidence mutation paths remain
    strictly owner-scoped, exactly as before."""
    service = _evidence_service_for("admin-1")
    evidence_id = verify_fixture["evidence_id"]
    assert _run(service.get_evidence_item(evidence_id)) is not None

    updated = _run(service.update_evidence_item(evidence_id, EvidenceItemUpdate(evidence_status="suspicious")))
    assert updated is None
    deleted = _run(service.delete_evidence_item(evidence_id))
    assert deleted is False
    verified = _run(service.verify_evidence_item(evidence_id))
    assert verified is None
    assert FakeRepository.stores["evidence_records"][evidence_id]["evidence_status"] == "valid"
