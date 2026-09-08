from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.lexproof.api import redline_proposals as proposal_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.redline_proposals import ProposalService
from app.lexproof.services.workflow_engine import WorkflowEngine
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"


class FakeVersionAnalysisService:
    def __init__(self):
        self.calls = []

    async def analyze_version(self, contract_id, version_id, user_id, *, anchor_evidence):
        self.calls.append((contract_id, version_id, user_id, anchor_evidence))
        return {"analysis_status": "complete", "version_id": version_id}


def seed_data():
    FakeRepository.stores = {
        "contracts": {"contract-1": {"id": "contract-1", "owner_id": "owner-1", "org_id": ORG_ID, "current_version_id": "version-1"}},
        "contract_versions": {"version-1": {"id": "version-1", "contract_id": "contract-1", "owner_id": "owner-1", "version_number": 1, "content_hash": "hash-v1", "document_text": "Before clause. Exact clause text. After clause."}},
        "risk_findings": {"finding-1": {"id": "finding-1", "contract_id": "contract-1", "version_id": "version-1", "title": "Liability cap", "severity": "critical", "description": "The cap is too low.", "evidence": "Clause text", "evidence_quote": "Exact clause text", "recommendation": "Review the cap.", "created_at": datetime.now(timezone.utc)}},
        "redline_proposals": {},
        "redline_reviews": {},
        "redline_publication_audits": {},
        "organizations": {ORG_ID: {"org_id": ORG_ID, "name": "LexProof Demo", "status": "active"}},
        f"organizations/{ORG_ID}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": ORG_ID},
            "reviewer-1": {"user_id": "reviewer-1", "roles": ["reviewer"], "status": "active", "org_id": ORG_ID},
            "approver-1": {"user_id": "approver-1", "roles": ["approver"], "status": "active", "org_id": ORG_ID},
            "admin-1": {"user_id": "admin-1", "roles": ["admin"], "status": "active", "org_id": ORG_ID},
            "owner-approver": {"user_id": "owner-approver", "roles": ["contract_owner", "approver"], "status": "active", "org_id": ORG_ID},
        },
        "users": {},
        "organization_invites": {},
        "workflow_definitions": {},
        "workflow_instances": {},
    }


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


def make_service(analysis_service=None):
    return ProposalService(
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        findings=FakeRepository("risk_findings"),
        proposals=FakeRepository("redline_proposals"),
        reviews=FakeRepository("redline_reviews"),
        publication_audits=FakeRepository("redline_publication_audits"),
        analysis_service=analysis_service,
        organizations=make_orgs(),
        workflow=make_workflow(),
    )


def test_create_proposal_persists_finding_context_without_mutating_contract():
    seed_data()
    service = make_service()
    original_version = dict(FakeRepository.stores["contract_versions"]["version-1"])
    proposal = service.create("contract-1", "version-1", "finding-1", "Liability is capped at fees paid.", "owner-1")

    assert proposal["contract_id"] == "contract-1"
    assert proposal["source_version_id"] == "version-1"
    assert proposal["finding_id"] == "finding-1"
    assert proposal["original_text"] == "Exact clause text"
    assert proposal["proposed_text"] == "Liability is capped at fees paid."
    assert proposal["status"] == "PROPOSED"
    assert proposal["workflow_instance_id"]
    assert FakeRepository.stores["contract_versions"]["version-1"] == original_version
    assert FakeRepository.stores["contracts"]["contract-1"]["current_version_id"] == "version-1"
    assert len(FakeRepository.stores["contract_versions"]) == 1


def test_empty_proposed_text_is_draft_and_update_is_persisted():
    seed_data()
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "", "owner-1")
    assert proposal["status"] == "DRAFT"

    updated = service.update(proposal["proposal_id"], "Revised liability language.", "owner-1")

    assert updated["proposed_text"] == "Revised liability language."
    assert updated["status"] == "PROPOSED"
    assert FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]["proposed_text"] == "Revised liability language."


def test_service_rejects_cross_contract_finding_and_unauthorized_user():
    seed_data()
    FakeRepository.stores["risk_findings"]["other-finding"] = {"id": "other-finding", "contract_id": "other-contract", "version_id": "version-1"}
    service = make_service()

    try:
        service.create("contract-1", "version-1", "other-finding", "text", "owner-1")
        assert False
    except ValueError as error:
        assert "contract" in str(error)
    try:
        service.create("contract-1", "version-1", "finding-1", "text", "other-user")
        assert False
    except PermissionError:
        pass


def make_client(monkeypatch, uid: str):
    seed_data()
    service = make_service()
    monkeypatch.setattr(proposal_api, "_service", lambda: service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_api_create_get_filters_and_update(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    created = client.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1", "proposed_text": "Initial proposal"})
    assert created.status_code == 201
    proposal_id = created.json()["proposal_id"]

    listed = client.get("/api/contracts/contract-1/redline-proposals?version_id=version-1&finding_id=finding-1")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    updated = client.patch(f"/api/redline-proposals/{proposal_id}", json={"proposed_text": "Edited proposal"})
    assert updated.status_code == 200
    assert updated.json()["proposed_text"] == "Edited proposal"


def test_api_unauthorized_invalid_contract_and_invalid_version(monkeypatch):
    unauthorized = make_client(monkeypatch, "other-user")
    assert unauthorized.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1"}).status_code == 403
    owner = make_client(monkeypatch, "owner-1")
    assert owner.post("/api/contracts/missing/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1"}).status_code == 404
    assert owner.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "missing", "finding_id": "finding-1"}).status_code == 404


def test_approved_review_persists_and_does_not_create_version():
    seed_data()
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Revised clause", "owner-1")
    original_version = dict(FakeRepository.stores["contract_versions"]["version-1"])

    review = service.review(proposal["proposal_id"], "APPROVED", "reviewer-1", "Reviewed by counsel")

    assert review["decision"] == "APPROVED"
    assert review["reviewer_id"] == "reviewer-1"
    assert review["comment"] == "Reviewed by counsel"
    assert service.get(proposal["proposal_id"], "owner-1")["status"] == "APPROVED"
    assert service.get(proposal["proposal_id"], "owner-1")["review"]["review_id"] == review["review_id"]
    assert FakeRepository.stores["contract_versions"]["version-1"] == original_version
    assert FakeRepository.stores["contracts"]["contract-1"]["current_version_id"] == "version-1"
    assert len(FakeRepository.stores["contract_versions"]) == 1


def test_rejected_review_persists_and_final_decision_is_immutable():
    seed_data()
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Revised clause", "owner-1")
    review = service.review(proposal["proposal_id"], "REJECTED", "reviewer-1", "Needs negotiation")

    assert review["decision"] == "REJECTED"
    try:
        service.review(proposal["proposal_id"], "APPROVED", "reviewer-1", "Changed mind")
        assert False
    except ValueError as error:
        assert "final decision" in str(error)
    assert len(FakeRepository.stores["redline_reviews"]) == 1


def test_review_rejects_invalid_decision_and_unauthorized_user():
    seed_data()
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Revised clause", "owner-1")
    try:
        service.review(proposal["proposal_id"], "PENDING", "reviewer-1")
        assert False
    except ValueError as error:
        assert "APPROVED or REJECTED" in str(error)
    try:
        service.review(proposal["proposal_id"], "APPROVED", "other-user")
        assert False
    except PermissionError:
        pass


def test_review_api_and_get_return_persisted_review(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    created = client.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1", "proposed_text": "Revised clause"})
    proposal_id = created.json()["proposal_id"]
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    reviewed = client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED", "comment": "Looks good"})

    assert reviewed.status_code == 200
    assert reviewed.json()["decision"] == "APPROVED"
    fetched = client.get(f"/api/redline-proposals/{proposal_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "APPROVED"
    assert fetched.json()["review"]["comment"] == "Looks good"
    assert client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"}).status_code == 409


def approved_service():
    seed_data()
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    service.review(proposal["proposal_id"], "APPROVED", "reviewer-1", "Approved for publication")
    return service, proposal


def test_approved_proposal_publishes_v2_and_preserves_source_and_review():
    service, proposal = approved_service()
    source_before = dict(FakeRepository.stores["contract_versions"]["version-1"])
    contract_before = dict(FakeRepository.stores["contracts"]["contract-1"])
    review_before = dict(next(iter(FakeRepository.stores["redline_reviews"].values())))

    result = service.publish(proposal["proposal_id"], "approver-1")

    assert result["status"] == "PUBLISHED"
    assert result["source_version_id"] == "version-1"
    assert result["published_by"] == "approver-1"
    published = FakeRepository.stores["contract_versions"][result["published_version_id"]]
    assert published["version_number"] == 2
    assert published["parent_version_id"] == "version-1"
    assert published["contract_id"] == "contract-1"
    assert published["document_text"] == "Before clause. Replacement clause. After clause."
    assert FakeRepository.stores["contract_versions"]["version-1"] == source_before
    assert FakeRepository.stores["contracts"]["contract-1"]["current_version_id"] != contract_before["current_version_id"]
    assert next(iter(FakeRepository.stores["redline_reviews"].values())) == review_before
    stored_proposal = FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]
    assert stored_proposal["published_version_id"] == result["published_version_id"]
    assert stored_proposal["status"] == "PUBLISHED"
    assert len(FakeRepository.stores["redline_publication_audits"]) == 1


def test_publish_is_idempotent_and_does_not_create_v3():
    service, proposal = approved_service()
    first = service.publish(proposal["proposal_id"], "approver-1")
    second = service.publish(proposal["proposal_id"], "approver-1")

    assert second == first
    assert len(FakeRepository.stores["contract_versions"]) == 2
    assert len(FakeRepository.stores["redline_publication_audits"]) == 1


def test_publish_analyzes_new_version_and_preserves_source():
    seed_data()
    analysis_service = FakeVersionAnalysisService()
    service = make_service(analysis_service)
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    service.review(proposal["proposal_id"], "APPROVED", "reviewer-1")
    source_before = dict(FakeRepository.stores["contract_versions"]["version-1"])

    result = service.publish(proposal["proposal_id"], "approver-1")

    assert analysis_service.calls == [
        ("contract-1", result["published_version_id"], "approver-1", True)
    ]
    assert FakeRepository.stores["contract_versions"]["version-1"] == source_before
    assert FakeRepository.stores["contract_versions"][result["published_version_id"]]["analysis_status"] == "pending"


def test_publish_rejects_unapproved_missing_review_and_unsafe_content():
    seed_data()
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    for expected in ("APPROVED", "APPROVED"):
        try:
            service.publish(proposal["proposal_id"], "approver-1")
            assert False
        except ValueError as error:
            assert "APPROVED" in str(error)
    service.review(proposal["proposal_id"], "REJECTED", "reviewer-1")
    try:
        service.publish(proposal["proposal_id"], "approver-1")
        assert False
    except ValueError:
        pass
    assert len(FakeRepository.stores["contract_versions"]) == 1

    service, proposal = approved_service()
    FakeRepository.stores["contract_versions"]["version-1"]["document_text"] = "No matching clause"
    try:
        service.publish(proposal["proposal_id"], "approver-1")
        assert False
    except ValueError as error:
        assert "match exactly once" in str(error)
    assert len(FakeRepository.stores["contract_versions"]) == 1


def test_publish_rejects_unauthorized_and_invalid_proposal():
    service, proposal = approved_service()
    try:
        service.publish(proposal["proposal_id"], "other-user")
        assert False
    except PermissionError:
        pass
    try:
        service.publish("missing", "approver-1")
        assert False
    except ValueError as error:
        assert "not found" in str(error)


def test_publish_api_returns_explicit_publication_result(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    created = client.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1", "proposed_text": "Replacement clause"})
    proposal_id = created.json()["proposal_id"]
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    assert client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"}).status_code == 200
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "approver-1"}

    published = client.post(f"/api/redline-proposals/{proposal_id}/publish")

    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["source_version_id"] == "version-1"
    assert published.json()["published_version_id"] in FakeRepository.stores["contract_versions"]


def test_reviewer_cannot_publish():
    service, proposal = approved_service()
    try:
        service.publish(proposal["proposal_id"], "reviewer-1")
        assert False
    except PermissionError:
        pass
    assert "PUBLISHED" not in {
        item.get("status") for item in FakeRepository.stores["redline_proposals"].values()
    }


def test_owner_with_approver_role_cannot_approve_own_submission():
    seed_data()
    FakeRepository.stores["contracts"]["contract-1"]["owner_id"] = "owner-approver"
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-approver")
    try:
        service.review(proposal["proposal_id"], "APPROVED", "owner-approver")
        assert False
    except PermissionError:
        pass
    assert service.get(proposal["proposal_id"], "owner-approver")["status"] == "PROPOSED"
