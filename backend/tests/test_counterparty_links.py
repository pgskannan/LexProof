from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient

from app.lexproof.api import counterparty as counterparty_api
from app.lexproof.domains.passport.evidence_service import EvidenceService
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.counterparty_links import (
    ATTESTATION_STATEMENT,
    CounterpartyLinkService,
    TokenRateLimiter,
    token_document_id,
)
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"


def seed_data():
    now = datetime.now(timezone.utc).isoformat()
    FakeRepository.stores = {
        "contracts": {
            "contract-1": {
                "id": "contract-1",
                "name": "Vendor MSA",
                "owner_id": "owner-1",
                "org_id": ORG_ID,
                "version": 1,
                "current_version_id": "version-1",
            }
        },
        "contract_versions": {
            "version-1": {
                "id": "version-1",
                "contract_id": "contract-1",
                "owner_id": "owner-1",
                "version_number": 1,
                "passport_id": "passport-1",
                "document_text": "Exact clause text",
            }
        },
        "redline_proposals": {
            "proposal-1": {
                "proposal_id": "proposal-1",
                "org_id": ORG_ID,
                "contract_id": "contract-1",
                "source_version_id": "version-1",
                "finding_id": "finding-1",
                "title": "Liability cap",
                "original_text": "Exact clause text",
                "proposed_text": "Liability is capped at fees paid.",
                "recommendation": "Cap liability at fees.",
                "reason": "The cap is too low.",
                "status": "APPROVED",
                "created_by": "owner-1",
                "workflow_instance_id": "wf-1",
            }
        },
        "legal_passports": {
            "passport-1": {
                "passport_id": "passport-1",
                "contract_id": "contract-1",
                "contract_version": 1,
                "owner_id": "owner-1",
            }
        },
        "evidence_records": {},
        "evidence_anchors": {},
        "external_access_links": {},
        "organizations": {ORG_ID: {"org_id": ORG_ID, "name": "LexProof Demo", "status": "active"}},
        f"organizations/{ORG_ID}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": ORG_ID},
            "admin-1": {"user_id": "admin-1", "roles": ["admin"], "status": "active", "org_id": ORG_ID},
            "reviewer-1": {"user_id": "reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": ORG_ID},
        },
        "users": {},
        "organization_invites": {},
        "workflow_instances": {
            "wf-1": {
                "instance_id": "wf-1",
                "org_id": ORG_ID,
                "definition_id": f"{ORG_ID}_contract_redline_approval",
                "entity_type": "redline_proposal",
                "entity_id": "proposal-1",
                "current_state": "approved",
                "status": "in_progress",
                "created_by": "owner-1",
                "updated_at": now,
            }
        },
        "workflow_instances/wf-1/history": {
            "evt-1": {
                "event_id": "evt-1",
                "instance_id": "wf-1",
                "transition_id": "approve",
                "from_state": "in_review",
                "to_state": "approved",
                "actor_id": "reviewer-1",
                "occurred_at": now,
            }
        },
    }


def make_orgs() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def make_service() -> CounterpartyLinkService:
    orgs = make_orgs()

    def evidence_factory(owner_id: str) -> EvidenceService:
        return EvidenceService(
            FakeRepository("evidence_records"),
            owner_id=owner_id,
            passport_repository=FakeRepository("legal_passports"),
            anchor_repository=FakeRepository("evidence_anchors"),
        )

    return CounterpartyLinkService(
        links=FakeRepository("external_access_links"),
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        proposals=FakeRepository("redline_proposals"),
        passports=FakeRepository("legal_passports"),
        evidence_records=FakeRepository("evidence_records"),
        organizations=orgs,
        evidence_service_factory=evidence_factory,
        limiter=TokenRateLimiter(),
    )


def make_client(monkeypatch, uid: str = "owner-1"):
    seed_data()
    service = make_service()
    monkeypatch.setattr(counterparty_api, "_service", lambda: service)
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: service.organizations)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": f"{uid}@example.com"}
    return TestClient(app), service


def _create_link(client, **overrides):
    body = {
        "redline_proposal_id": "proposal-1",
        "counterparty_name": "Jordan Chen",
        "counterparty_email": "jordan@counterparty.example",
        **overrides,
    }
    return client.post(f"/api/orgs/{ORG_ID}/contracts/contract-1/counterparty-links", json=body)


def test_owner_can_create_link_and_token_is_returned_once(monkeypatch):
    client, _service = make_client(monkeypatch, "owner-1")
    created = _create_link(client)
    assert created.status_code == 201
    payload = created.json()
    assert payload["token"]
    assert len(payload["token"]) >= 32
    assert payload["share_path"] == f"/counterparty/{payload['token']}"
    assert payload["share_url"].endswith(payload["share_path"])
    assert payload["share_url"].startswith("http")
    assert payload["counterparty_name"] == "Jordan Chen"
    assert "view" in payload["permissions"]
    listed = client.get(
        f"/api/orgs/{ORG_ID}/contracts/contract-1/counterparty-links?redline_proposal_id=proposal-1"
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    listed_item = listed.json()[0]
    assert "token" not in listed_item
    assert "share_path" not in listed_item
    assert "share_url" not in listed_item
    assert payload["token"] not in json.dumps(listed_item)
    assert listed_item["countersigned"] is False


def test_reviewer_cannot_create_or_list_links(monkeypatch):
    client, _service = make_client(monkeypatch, "reviewer-1")
    created = _create_link(client)
    assert created.status_code == 403
    listed = client.get(f"/api/orgs/{ORG_ID}/contracts/contract-1/counterparty-links")
    assert listed.status_code == 403


def test_external_get_requires_no_auth_and_returns_redline_diff(monkeypatch):
    authed, _service = make_client(monkeypatch, "owner-1")
    token = _create_link(authed).json()["token"]
    public = TestClient(create_app())
    # Rebind the same service onto a fresh app so the unauthenticated client
    # hits the in-memory link store rather than a real Firestore collection.
    monkeypatch.setattr(counterparty_api, "_service", lambda: _service)
    public_app = create_app()
    public = TestClient(public_app)
    response = public.get(f"/api/external/{token}")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_name"] == "Vendor MSA"
    assert body["original_text"] == "Exact clause text"
    assert body["proposed_text"] == "Liability is capped at fees paid."
    assert body["proposal_status"] == "APPROVED"
    assert body["already_countersigned"] is False
    assert body["attestation_statement"] == ATTESTATION_STATEMENT


def test_comment_is_tied_to_the_link_and_capped(monkeypatch):
    client, service = make_client(monkeypatch)
    token = _create_link(client).json()["token"]
    added = client.post(f"/api/external/{token}/comment", json={"body": "Please confirm the cap amount."})
    assert added.status_code == 201
    assert added.json()["author_name"] == "Jordan Chen"
    viewed = client.get(f"/api/external/{token}").json()
    assert len(viewed["comments"]) == 1
    document_id = token_document_id(token)
    FakeRepository.stores["external_access_links"][document_id]["comments"] = [
        {"comment_id": f"c-{index}", "author_name": "Jordan Chen", "body": "x", "created_at": "t"}
        for index in range(25)
    ]
    blocked = client.post(f"/api/external/{token}/comment", json={"body": "one more"})
    assert blocked.status_code == 429


def test_countersign_creates_exactly_one_evidence_item_and_is_idempotent(monkeypatch):
    client, service = make_client(monkeypatch)
    token = _create_link(client).json()["token"]
    workflow_before = dict(FakeRepository.stores["workflow_instances"]["wf-1"])
    history_before = dict(FakeRepository.stores["workflow_instances/wf-1/history"])
    proposal_before = dict(FakeRepository.stores["redline_proposals"]["proposal-1"])

    first = client.post(
        f"/api/external/{token}/countersign",
        json={"typed_name": "Jordan Chen", "attestation_accepted": True, "attestation": ATTESTATION_STATEMENT},
    )
    assert first.status_code == 200
    evidence_id = first.json()["evidence_id"]
    assert evidence_id
    records = list(FakeRepository.stores["evidence_records"].values())
    assert len(records) == 1
    evidence = records[0]
    assert evidence["evidence_type"] == "counterparty_countersignature"
    assert evidence["passport_id"] == "passport-1"
    assert token not in (evidence.get("content") or "")
    assert token not in json.dumps(evidence.get("metadata") or {})
    assert evidence["metadata"]["token_id"]
    assert ATTESTATION_STATEMENT in (evidence.get("content") or "")

    second = client.post(
        f"/api/external/{token}/countersign",
        json={"typed_name": "Jordan Chen", "attestation_accepted": True},
    )
    assert second.status_code == 409
    assert len(FakeRepository.stores["evidence_records"]) == 1

    viewed = client.get(f"/api/external/{token}").json()
    assert viewed["already_countersigned"] is True
    assert viewed["countersign_evidence_id"] == evidence_id

    assert FakeRepository.stores["workflow_instances"]["wf-1"] == workflow_before
    assert FakeRepository.stores["workflow_instances/wf-1/history"] == history_before
    assert FakeRepository.stores["redline_proposals"]["proposal-1"]["status"] == proposal_before["status"]
    assert FakeRepository.stores["redline_proposals"]["proposal-1"]["workflow_instance_id"] == "wf-1"


def test_expired_and_revoked_tokens_are_rejected(monkeypatch):
    client, _service = make_client(monkeypatch)
    token = _create_link(client, expires_in_days=1).json()["token"]
    document_id = token_document_id(token)
    FakeRepository.stores["external_access_links"][document_id]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    expired = client.get(f"/api/external/{token}")
    assert expired.status_code == 410
    assert "expired" in expired.json()["detail"].lower()

    token2 = _create_link(client).json()["token"]
    document_id2 = token_document_id(token2)
    FakeRepository.stores["external_access_links"][document_id2]["revoked"] = True
    revoked = client.get(f"/api/external/{token2}")
    assert revoked.status_code == 403
    assert "revoked" in revoked.json()["detail"].lower()

    missing = client.get("/api/external/this-token-does-not-exist-at-all-0000")
    assert missing.status_code == 404


def test_countersign_requires_matching_name_and_attestation(monkeypatch):
    client, _service = make_client(monkeypatch)
    token = _create_link(client).json()["token"]
    wrong_name = client.post(
        f"/api/external/{token}/countersign",
        json={"typed_name": "Someone Else", "attestation_accepted": True},
    )
    assert wrong_name.status_code == 400
    no_check = client.post(
        f"/api/external/{token}/countersign",
        json={"typed_name": "Jordan Chen", "attestation_accepted": False},
    )
    assert no_check.status_code == 400
    assert FakeRepository.stores["evidence_records"] == {}


def test_countersign_blocked_when_proposal_not_approved(monkeypatch):
    client, _service = make_client(monkeypatch)
    FakeRepository.stores["redline_proposals"]["proposal-1"]["status"] = "PROPOSED"
    token = _create_link(client).json()["token"]
    response = client.post(
        f"/api/external/{token}/countersign",
        json={"typed_name": "Jordan Chen", "attestation_accepted": True},
    )
    assert response.status_code == 409
    assert FakeRepository.stores["evidence_records"] == {}
    assert FakeRepository.stores["workflow_instances"]["wf-1"]["current_state"] == "approved"


def test_external_endpoints_do_not_require_firebase_auth(monkeypatch):
    authed, service = make_client(monkeypatch, "admin-1")
    token = _create_link(authed).json()["token"]
    monkeypatch.setattr(counterparty_api, "_service", lambda: service)
    public = TestClient(create_app())
    viewed = public.get(f"/api/external/{token}")
    assert viewed.status_code == 200
    commented = public.post(f"/api/external/{token}/comment", json={"body": "Looks good."})
    assert commented.status_code == 201


def test_link_expiry_defaults_to_org_setting_when_not_specified(monkeypatch):
    client, service = make_client(monkeypatch, "owner-1")
    service.organizations.update_org_settings(ORG_ID, {"default_link_expiry_days": 5}, "admin-1")
    created = _create_link(client)
    assert created.status_code == 201
    expires_at = datetime.fromisoformat(created.json()["expires_at"])
    created_at = datetime.fromisoformat(created.json()["created_at"])
    assert (expires_at - created_at).days == 5


def test_link_expiry_explicit_value_overrides_org_setting(monkeypatch):
    client, service = make_client(monkeypatch, "owner-1")
    service.organizations.update_org_settings(ORG_ID, {"default_link_expiry_days": 5}, "admin-1")
    created = _create_link(client, expires_in_days=21)
    assert created.status_code == 201
    expires_at = datetime.fromisoformat(created.json()["expires_at"])
    created_at = datetime.fromisoformat(created.json()["created_at"])
    assert (expires_at - created_at).days == 21
