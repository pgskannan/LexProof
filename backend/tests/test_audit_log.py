"""Unit tests for the cross-cutting audit log: the write helper and the
org-scoped, Admin/Auditor-gated read endpoint."""

import logging

from fastapi.testclient import TestClient

from app.lexproof.api import audit_log as audit_log_api
from app.lexproof.main import create_app
from app.lexproof.services.audit import record_audit_event
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

ORG_A = "org-a"
ORG_B = "org-b"


def reset_stores():
    FakeRepository.stores = {
        "organizations": {},
        "users": {},
        "organization_invites": {},
        f"organizations/{ORG_A}/members": {},
        f"organizations/{ORG_B}/members": {},
        "audit_log": {},
    }


def make_org_service() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def make_client(monkeypatch, uid: str):
    org_service = make_org_service()
    org_service.create_org("Org A", "admin-1", org_id=ORG_A, creator_email="admin@example.com")
    org_service.ensure_member(ORG_A, "auditor-1", ["auditor"], email="auditor@example.com")
    org_service.ensure_member(ORG_A, "reviewer-1", ["reviewer"], email="reviewer@example.com")
    org_service.create_org("Org B", "admin-2", org_id=ORG_B, creator_email="admin2@example.com")
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: org_service)
    monkeypatch.setattr(audit_log_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def seed_entries():
    entries = FakeRepository("audit_log")
    entries.set("e1", {
        "id": "e1", "actor_id": "admin-1", "action": "contract.uploaded", "resource_type": "contract",
        "resource_id": "c1", "summary": "Uploaded contract \"NDA.pdf\"", "org_id": ORG_A,
        "created_at": "2026-09-01T00:00:00+00:00",
    })
    entries.set("e2", {
        "id": "e2", "actor_id": "admin-1", "action": "redline.approved", "resource_type": "redline_proposal",
        "resource_id": "p1", "summary": "Approved redline proposal for contract c1", "org_id": ORG_A,
        "created_at": "2026-09-02T00:00:00+00:00",
    })
    entries.set("e3", {
        "id": "e3", "actor_id": "admin-2", "action": "contract.uploaded", "resource_type": "contract",
        "resource_id": "c9", "summary": "Uploaded contract \"MSA.pdf\"", "org_id": ORG_B,
        "created_at": "2026-09-03T00:00:00+00:00",
    })


def test_audit_log_requires_authentication():
    response = TestClient(create_app()).get("/api/audit-log", headers={"X-Org-Id": ORG_A})
    assert response.status_code == 401


def test_audit_log_requires_org_membership(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "stranger-1")
    response = client.get("/api/audit-log", headers={"X-Org-Id": ORG_A})
    assert response.status_code == 403


def test_audit_log_rejects_non_admin_non_auditor_roles(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "reviewer-1")
    response = client.get("/api/audit-log", headers={"X-Org-Id": ORG_A})
    assert response.status_code == 403


def test_admin_sees_org_scoped_entries_newest_first(monkeypatch):
    reset_stores()
    seed_entries()
    client = make_client(monkeypatch, "admin-1")
    response = client.get("/api/audit-log", headers={"X-Org-Id": ORG_A})
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == ["e2", "e1"]
    assert all(item["org_id"] == ORG_A for item in body)


def test_auditor_role_can_also_read(monkeypatch):
    reset_stores()
    seed_entries()
    client = make_client(monkeypatch, "auditor-1")
    response = client.get("/api/audit-log", headers={"X-Org-Id": ORG_A})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_contract_id_filter_returns_only_matching_entries(monkeypatch):
    reset_stores()
    seed_entries()
    entries = FakeRepository("audit_log")
    entries.set("e4", {
        "id": "e4",
        "actor_id": "admin-1",
        "action": "redline.published",
        "resource_type": "redline_proposal",
        "resource_id": "p2",
        "contract_id": "c1",
        "summary": "Published redline for contract c1",
        "org_id": ORG_A,
        "created_at": "2026-09-04T00:00:00+00:00",
    })
    client = make_client(monkeypatch, "admin-1")

    matching = client.get("/api/audit-log?contract_id=c1", headers={"X-Org-Id": ORG_A})
    assert matching.status_code == 200
    assert [item["id"] for item in matching.json()] == ["e4", "e1"]

    missing = client.get("/api/audit-log?contract_id=c2", headers={"X-Org-Id": ORG_A})
    assert missing.status_code == 200
    assert [item["id"] for item in missing.json()] == []


def test_other_org_entries_are_not_visible(monkeypatch):
    reset_stores()
    seed_entries()
    client = make_client(monkeypatch, "admin-1")
    response = client.get("/api/audit-log", headers={"X-Org-Id": ORG_A})
    ids = [item["id"] for item in response.json()]
    assert "e3" not in ids


def test_filters_by_action_and_resource_type(monkeypatch):
    reset_stores()
    seed_entries()
    client = make_client(monkeypatch, "admin-1")
    response = client.get("/api/audit-log?action=redline.approved", headers={"X-Org-Id": ORG_A})
    assert [item["id"] for item in response.json()] == ["e2"]
    response = client.get("/api/audit-log?resource_type=contract", headers={"X-Org-Id": ORG_A})
    assert [item["id"] for item in response.json()] == ["e1"]


def test_record_audit_event_writes_expected_shape():
    FakeRepository.stores = {"audit_log": {}}
    record_audit_event(
        FakeRepository,
        actor_id="user-1",
        actor_email="user@example.com",
        action="contract.uploaded",
        resource_type="contract",
        resource_id="c1",
        resource_name="NDA.pdf",
        summary='Uploaded contract "NDA.pdf"',
        org_id="org-a",
        metadata={"filename": "NDA.pdf"},
    )
    records = list(FakeRepository("audit_log").stream())
    assert len(records) == 1
    record = records[0]
    assert record["actor_id"] == "user-1"
    assert record["action"] == "contract.uploaded"
    assert record["resource_type"] == "contract"
    assert record["org_id"] == "org-a"
    assert record["metadata"] == {"filename": "NDA.pdf"}
    assert "created_at" in record


def test_record_audit_event_never_raises():
    def broken_factory(collection: str):
        raise RuntimeError("Firestore is down")

    # Must not raise -- the calling endpoint's real work must never fail
    # because the audit write failed.
    record_audit_event(
        broken_factory,
        actor_id="user-1",
        action="contract.uploaded",
        resource_type="contract",
        summary="Uploaded contract",
    )


# ---------------------------------------------------------------------------
# Phase 3G: audit-write failures must be observable, not silently swallowed.
# ---------------------------------------------------------------------------

AUDIT_LOGGER_NAME = "app.lexproof.services.audit"


def test_record_audit_event_success_logs_nothing(caplog):
    """1. Normal audit write still succeeds, and produces no warning log --
    logging must only ever fire on the failure path."""
    FakeRepository.stores = {"audit_log": {}}
    with caplog.at_level(logging.WARNING, logger=AUDIT_LOGGER_NAME):
        record_audit_event(
            FakeRepository,
            actor_id="user-1",
            action="contract.uploaded",
            resource_type="contract",
            resource_id="c1",
            summary="Uploaded contract",
            org_id="org-a",
        )
    assert caplog.records == []
    assert len(list(FakeRepository("audit_log").stream())) == 1


def test_record_audit_event_failure_does_not_raise_to_caller():
    """2. A simulated audit-write failure must not raise -- the calling
    business operation continues exactly as before Phase 3G."""

    def broken_factory(collection: str):
        raise RuntimeError("Firestore is down")

    record_audit_event(
        broken_factory,
        actor_id="user-1",
        action="redline.approved",
        resource_type="redline_proposal",
        resource_id="proposal-1",
        summary="Approved redline proposal",
        org_id="org-a",
    )


def test_record_audit_event_failure_produces_a_log_entry(caplog):
    """3. A simulated audit-write failure now produces exactly one log
    entry, at WARNING (the same level the codebase already uses for this
    best-effort pattern -- see _create_notification / chat notifications),
    where it was previously silently swallowed."""

    def broken_factory(collection: str):
        raise RuntimeError("Firestore is down")

    with caplog.at_level(logging.WARNING, logger=AUDIT_LOGGER_NAME):
        record_audit_event(
            broken_factory,
            actor_id="user-1",
            action="redline.approved",
            resource_type="redline_proposal",
            resource_id="proposal-1",
            summary="Approved redline proposal",
            org_id="org-a",
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING


def test_audit_failure_log_identifies_the_failure_sufficiently(caplog):
    """4. The log entry carries enough safe context (action, resource type/
    id, org id, and the real exception) to diagnose which audit write
    failed and why, without dumping the audit payload itself."""

    def broken_factory(collection: str):
        raise RuntimeError("Firestore is down")

    with caplog.at_level(logging.WARNING, logger=AUDIT_LOGGER_NAME):
        record_audit_event(
            broken_factory,
            actor_id="user-1",
            action="redline.approved",
            resource_type="redline_proposal",
            resource_id="proposal-42",
            summary="Approved redline proposal for contract c1",
            org_id="org-a",
        )

    message = caplog.records[0].getMessage()
    assert "redline.approved" in message
    assert "redline_proposal" in message
    assert "proposal-42" in message
    assert "org-a" in message
    assert "Firestore is down" in message


def test_audit_failure_log_does_not_expose_sensitive_payload(caplog):
    """5. Sensitive values (summary text, metadata) are never logged -- only
    the safe identifiers above and the exception itself."""

    def broken_factory(collection: str):
        raise RuntimeError("Firestore is down")

    sensitive_summary = "Reviewed contract clause: SSN 123-45-6789, wire routing 021000021"
    sensitive_metadata = {
        "api_key": "sk-super-secret-token-abcdef",
        "clause_text": "Confidential payment terms: $1,000,000 due net 10",
    }

    with caplog.at_level(logging.WARNING, logger=AUDIT_LOGGER_NAME):
        record_audit_event(
            broken_factory,
            actor_id="user-1",
            action="redline.approved",
            resource_type="redline_proposal",
            resource_id="proposal-42",
            summary=sensitive_summary,
            org_id="org-a",
            metadata=sensitive_metadata,
        )

    message = caplog.records[0].getMessage()
    assert "123-45-6789" not in message
    assert "021000021" not in message
    assert "sk-super-secret-token" not in message
    assert "Confidential payment terms" not in message
    assert sensitive_summary not in message


def test_existing_call_shapes_with_only_required_fields_still_succeed(caplog):
    """6. Existing callers remain unaffected: a call using only the required
    fields (several real call sites omit resource_id/contract_id/org_id/
    metadata) still succeeds and, on the success path, still logs nothing."""
    FakeRepository.stores = {"audit_log": {}}
    with caplog.at_level(logging.WARNING, logger=AUDIT_LOGGER_NAME):
        record_audit_event(
            FakeRepository,
            actor_id="user-1",
            action="passport.created",
            resource_type="legal_passport",
            summary="AI analysis complete",
        )
    assert caplog.records == []
    assert len(list(FakeRepository("audit_log").stream())) == 1
