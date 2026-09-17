import asyncio
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
    def __init__(self, fail_with: Exception | None = None):
        self.calls = []
        self.fail_with = fail_with

    async def analyze_version(self, contract_id, version_id, user_id, *, anchor_evidence):
        self.calls.append((contract_id, version_id, user_id, anchor_evidence))
        if self.fail_with is not None:
            raise self.fail_with
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
        passports=FakeRepository("legal_passports"),
        evidence_records=FakeRepository("evidence_records"),
        evidence_anchors=FakeRepository("evidence_anchors"),
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


def test_valid_finding_remains_redline_eligible():
    """Finding Evidence Integrity (status doc §45): the new
    evidence_validation/evidence_match_count fields on a finding are
    metadata only in this pass -- they must not introduce any new blocking
    behavior at proposal-creation time for a finding whose AI-generated
    evidence_quote does validate against the source. This is a regression
    guard for the additive change, not new enforcement -- the user
    explicitly deferred a remediation_eligibility gate to a later step."""
    seed_data()
    FakeRepository.stores["risk_findings"]["finding-1"]["evidence_validation"] = "VALID"
    FakeRepository.stores["risk_findings"]["finding-1"]["evidence_match_count"] = 1
    service = make_service()

    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")

    assert proposal["status"] == "PROPOSED"
    assert proposal["original_text"] == "Exact clause text"


def test_create_proposal_surfaces_sla_due_date_for_in_review_state():
    seed_data()
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "Liability is capped at fees paid.", "owner-1")

    assert proposal["status"] == "PROPOSED"
    assert proposal.get("sla_due_at") is not None
    assert proposal.get("is_overdue") is False


def test_draft_proposal_has_no_sla_due_date():
    seed_data()
    service = make_service()
    proposal = service.create("contract-1", "version-1", "finding-1", "", "owner-1")

    assert proposal["status"] == "DRAFT"
    assert proposal.get("sla_due_at") is None
    assert proposal.get("is_overdue") is False


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
    assert result["contract_id"] == "contract-1"
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


def test_publish_defers_analysis_and_returns_immediately_as_pending():
    """publish() must never block its caller on the slow Gemini analysis +
    Ethereum anchoring call (hardening item #1: publish success/error
    semantic separation). It commits the new version and returns with
    analysis_status "pending" -- without invoking analyze_version at all --
    leaving that slow work for run_post_publish_analysis() to run afterward,
    e.g. scheduled as a FastAPI background task by the API layer once this
    response has already been sent."""
    seed_data()
    analysis_service = FakeVersionAnalysisService()
    service = make_service(analysis_service)
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    service.review(proposal["proposal_id"], "APPROVED", "reviewer-1")
    source_before = dict(FakeRepository.stores["contract_versions"]["version-1"])

    result = service.publish(proposal["proposal_id"], "approver-1")

    assert analysis_service.calls == []
    assert result["analysis_status"] == "pending"
    assert FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]["analysis_status"] == "pending"
    assert FakeRepository.stores["contract_versions"]["version-1"] == source_before
    assert FakeRepository.stores["contract_versions"][result["published_version_id"]]["analysis_status"] == "pending"


def test_run_post_publish_analysis_marks_complete_on_success():
    seed_data()
    analysis_service = FakeVersionAnalysisService()
    service = make_service(analysis_service)
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    service.review(proposal["proposal_id"], "APPROVED", "reviewer-1")
    result = service.publish(proposal["proposal_id"], "approver-1")

    asyncio.run(service.run_post_publish_analysis(
        proposal["proposal_id"], "contract-1", result["published_version_id"], "approver-1",
    ))

    assert analysis_service.calls == [
        ("contract-1", result["published_version_id"], "approver-1", True)
    ]
    assert FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]["analysis_status"] == "complete"


def test_run_post_publish_analysis_marks_failed_without_undoing_publish():
    """A failing post-publish analysis/anchoring run must only degrade
    analysis_status to "failed" -- the publish itself (status PUBLISHED,
    published_version_id, the new contract version) must stay untouched, so
    the UI can offer a retry instead of ever implying the publish failed."""
    seed_data()
    analysis_service = FakeVersionAnalysisService(fail_with=RuntimeError("Sepolia RPC timeout"))
    service = make_service(analysis_service)
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    service.review(proposal["proposal_id"], "APPROVED", "reviewer-1")
    result = service.publish(proposal["proposal_id"], "approver-1")

    asyncio.run(service.run_post_publish_analysis(
        proposal["proposal_id"], "contract-1", result["published_version_id"], "approver-1",
    ))

    stored_proposal = FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]
    assert stored_proposal["analysis_status"] == "failed"
    assert stored_proposal["status"] == "PUBLISHED"
    assert stored_proposal["published_version_id"] == result["published_version_id"]


def test_run_post_publish_analysis_leaves_status_alone_on_409():
    """analyze_version()'s own idempotency guard raises a 409 if analysis for
    this exact version is already in progress or already complete -- that is
    not a real failure (e.g. this being scheduled a second time for the same
    version), so it must not downgrade an in-flight/completed run to
    "failed"."""
    from fastapi import HTTPException

    seed_data()
    analysis_service = FakeVersionAnalysisService(fail_with=HTTPException(status_code=409, detail="already in progress"))
    service = make_service(analysis_service)
    proposal = service.create("contract-1", "version-1", "finding-1", "Replacement clause", "owner-1")
    service.review(proposal["proposal_id"], "APPROVED", "reviewer-1")
    result = service.publish(proposal["proposal_id"], "approver-1")
    service.proposals.set(proposal["proposal_id"], {"analysis_status": "processing"}, merge=True)

    asyncio.run(service.run_post_publish_analysis(
        proposal["proposal_id"], "contract-1", result["published_version_id"], "approver-1",
    ))

    assert FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]["analysis_status"] == "processing"


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


def test_publish_rejects_when_original_text_matches_multiple_times():
    """Finding Evidence Integrity (status doc §45): a source text that
    contains the proposal's original_text more than once is exactly as
    unpublishable as one that contains it zero times (tested just above) --
    the exact-match guard can't safely guess which occurrence to replace, so
    this must also fail rather than silently editing the first match."""
    service, proposal = approved_service()
    FakeRepository.stores["contract_versions"]["version-1"]["document_text"] = (
        "Exact clause text. Middle text. Exact clause text."
    )
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
    assert published.json()["contract_id"] == "contract-1"
    assert published.json()["source_version_id"] == "version-1"
    assert published.json()["published_version_id"] in FakeRepository.stores["contract_versions"]


def test_publish_api_records_audit_event_with_contract_id(monkeypatch):
    client = make_client(monkeypatch, "owner-1")
    created = client.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1", "proposed_text": "Replacement clause"})
    proposal_id = created.json()["proposal_id"]
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    assert client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"}).status_code == 200
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "approver-1"}

    captured = {}

    def fake_record_audit_event(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(proposal_api, "record_audit_event", fake_record_audit_event)

    published = client.post(f"/api/redline-proposals/{proposal_id}/publish")

    assert published.status_code == 200
    assert published.json()["contract_id"] == "contract-1"
    assert captured["contract_id"] == "contract-1"
    assert captured["resource_type"] == "redline_proposal"


def test_publish_api_returns_409_when_original_text_not_found_in_source(monkeypatch):
    """Permanent regression test for the real failure this session's live
    browser Publish smoke test reproduced twice against the actual running
    app (status doc §45): a finding whose AI-generated evidence_quote does
    not literally occur in the source version's document_text must fail
    publish through the real HTTP endpoint with a genuine 409, leaving the
    proposal APPROVED and unpublished -- not a generic 500, and not a
    silent success. Finding Evidence Integrity's new analysis-time
    evidence_validation field (see test_finding_evidence_validation_* in
    test_explicit_version_analysis.py) only surfaces this earlier; this
    publish-time guard is unchanged and remains the last line of defense."""
    client = make_client(monkeypatch, "owner-1")
    created = client.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1", "proposed_text": "Replacement clause"})
    proposal_id = created.json()["proposal_id"]
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    assert client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"}).status_code == 200
    client.app.dependency_overrides[get_current_user] = lambda: {"uid": "approver-1"}
    FakeRepository.stores["contract_versions"]["version-1"]["document_text"] = "No matching clause here at all."

    published = client.post(f"/api/redline-proposals/{proposal_id}/publish")

    assert published.status_code == 409
    assert published.json()["detail"] == "Original text must match exactly once in the source version"
    stored_proposal = FakeRepository.stores["redline_proposals"][proposal_id]
    assert stored_proposal["status"] == "APPROVED"
    assert stored_proposal.get("published_version_id") is None
    assert len(FakeRepository.stores["contract_versions"]) == 1


def test_publish_api_schedules_post_publish_analysis_as_background_task(monkeypatch):
    """End-to-end: the /publish endpoint must not block on analysis (the
    endpoint's own commit work returns immediately), and the analysis it
    schedules as a FastAPI background task must actually run and land as
    "complete" by the time the request finishes -- TestClient executes
    background tasks synchronously as part of handling the request, so both
    effects are observable from a single call here."""
    seed_data()
    analysis_service = FakeVersionAnalysisService()
    service = make_service(analysis_service)
    monkeypatch.setattr(proposal_api, "_service", lambda: service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    client = TestClient(app)

    created = client.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1", "proposed_text": "Replacement clause"})
    proposal_id = created.json()["proposal_id"]
    app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    assert client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"}).status_code == 200
    app.dependency_overrides[get_current_user] = lambda: {"uid": "approver-1"}

    published = client.post(f"/api/redline-proposals/{proposal_id}/publish")

    assert published.status_code == 200
    # The endpoint's own response reflects the fast commit, not the slow
    # analysis it just scheduled -- confirming publish() truly returns before
    # analysis runs, not merely that analysis eventually completes.
    assert published.json()["analysis_status"] == "pending"
    published_version_id = published.json()["published_version_id"]
    assert analysis_service.calls == [("contract-1", published_version_id, "approver-1", True)]
    assert FakeRepository.stores["redline_proposals"][proposal_id]["analysis_status"] == "complete"

def test_publish_with_no_analysis_service_returns_not_attempted():
    """When no analysis_service is configured at all (distinct from one that
    is configured but fails), publish() must report analysis_status
    "not_attempted" rather than "pending" -- a caller polling for completion
    should not wait forever for work that was never going to run. Closes a
    gap in existing coverage: every other publish test constructs the
    service with a FakeVersionAnalysisService, so this specific branch
    (make_service() with analysis_service=None, as make_service()'s own
    default) had no direct test."""
    service, proposal = approved_service()

    result = service.publish(proposal["proposal_id"], "approver-1")

    assert result["analysis_status"] == "not_attempted"
    assert FakeRepository.stores["redline_proposals"][proposal["proposal_id"]]["analysis_status"] == "not_attempted"
    # The API layer's background-task scheduling condition is
    # `analysis_status in ("pending", "failed")` -- "not_attempted" must not
    # match it, i.e. nothing should ever be scheduled for this proposal.
    assert result["analysis_status"] not in ("pending", "failed")
    # KNOWN INCONSISTENCY (not fixed here -- unreachable in production today,
    # see note below): create_contract_version() hardcodes the new version
    # document's own analysis_status to "pending" unconditionally, so it does
    # NOT pick up "not_attempted" the way the proposal document does above.
    # If analysis_service is ever None in a real deployment, the published
    # version would show a permanently-stuck "pending" to anything reading
    # api/contracts.py's version detail/list endpoints or
    # portfolio_analytics.py's dashboard rollups, since nothing will ever
    # advance it. In the actual running app this branch is currently dead:
    # api/redline_proposals.py's _service() always constructs a real
    # VersionAnalysisService, so analysis_service is never None outside of
    # a test explicitly passing analysis_service=None as this one does. This
    # assertion documents current, verified behavior (not desired behavior)
    # so a future change to when/whether analysis_service can be None does
    # not silently reintroduce this without a test noticing.
    assert FakeRepository.stores["contract_versions"][result["published_version_id"]]["analysis_status"] == "pending"


def test_publish_api_get_reflects_failed_analysis_status(monkeypatch):
    """Closes a gap in existing coverage: test_run_post_publish_analysis_
    marks_failed_without_undoing_publish only asserts against the internal
    FakeRepository store, never against what a client actually receives back
    from a GET request. This is the end-to-end version -- through the real
    /publish and /redline-proposals/{id} API routes, with the background
    task (TestClient runs it synchronously) driving analysis_status to
    "failed" -- confirming the UI's polling endpoint genuinely surfaces the
    failure instead of leaving the client to infer it from internal state
    that isn't visible to it."""
    seed_data()
    analysis_service = FakeVersionAnalysisService(fail_with=RuntimeError("Sepolia RPC timeout"))
    service = make_service(analysis_service)
    monkeypatch.setattr(proposal_api, "_service", lambda: service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    client = TestClient(app)

    created = client.post("/api/contracts/contract-1/redline-proposals", json={"source_version_id": "version-1", "finding_id": "finding-1", "proposed_text": "Replacement clause"})
    proposal_id = created.json()["proposal_id"]
    app.dependency_overrides[get_current_user] = lambda: {"uid": "reviewer-1"}
    assert client.post(f"/api/redline-proposals/{proposal_id}/review", json={"decision": "APPROVED"}).status_code == 200
    app.dependency_overrides[get_current_user] = lambda: {"uid": "approver-1"}

    published = client.post(f"/api/redline-proposals/{proposal_id}/publish")
    assert published.status_code == 200
    # The publish response itself reflects the fast commit (background task
    # hasn't run yet from the caller's perspective at the moment the service
    # returns), so the failure only shows up on a subsequent GET.
    assert published.json()["status"] == "PUBLISHED"

    fetched = client.get(f"/api/redline-proposals/{proposal_id}")

    assert fetched.status_code == 200
    body = fetched.json()
    assert body["analysis_status"] == "failed"
    # The publish itself must remain untouched by the downstream analysis
    # failure -- this is the crux of hardening item #1's acceptance test,
    # verified here through the same GET response a real client would poll.
    assert body["status"] == "PUBLISHED"
    assert body["published_version_id"] is not None


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
