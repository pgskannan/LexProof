"""Regulation mapping: per-finding regulatory_citations aggregated into a
portfolio-wide view of which regulations show up most, at what severity."""

from fastapi.testclient import TestClient

from app.lexproof.api import organizations as org_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.regulation_map import build_regulation_map
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"


def test_build_regulation_map_groups_by_citation_and_severity():
    findings = [
        {"contract_id": "c1", "severity": "critical", "regulatory_citations": ["GDPR Article 28"]},
        {"contract_id": "c1", "severity": "high", "regulatory_citations": ["GDPR Article 28", "GDPR"]},
        {"contract_id": "c2", "severity": "medium", "regulatory_citations": ["GDPR Article 28"]},
        {"contract_id": "c2", "severity": "high", "regulatory_citations": []},
        {"contract_id": "c3", "severity": "low", "regulatory_citations": None},
    ]
    names = {"c1": "Contract One", "c2": "Contract Two", "c3": "Contract Three"}
    result = build_regulation_map(findings, names)
    by_citation = {item["citation"]: item for item in result}

    assert by_citation["GDPR Article 28"]["count"] == 3
    assert by_citation["GDPR Article 28"]["severity_counts"] == {"CRITICAL": 1, "HIGH": 1, "MEDIUM": 1}
    contracts = {c["contract_id"]: c for c in by_citation["GDPR Article 28"]["contracts"]}
    assert contracts["c1"]["finding_count"] == 2
    assert contracts["c1"]["contract_name"] == "Contract One"
    assert contracts["c2"]["finding_count"] == 1

    assert by_citation["GDPR"]["count"] == 1

    # Findings with an empty or missing citations list contribute nothing, and
    # c3 (whose only finding has regulatory_citations=None) never appears.
    all_contract_ids = {c["contract_id"] for entry in result for c in entry["contracts"]}
    assert "c3" not in all_contract_ids
    assert sum(entry["count"] for entry in result) == 4  # 3 + 1, not 5


def test_build_regulation_map_sorts_by_count_descending():
    findings = [
        {"contract_id": "c1", "severity": "high", "regulatory_citations": ["CCPA"]},
        {"contract_id": "c1", "severity": "high", "regulatory_citations": ["GDPR"]},
        {"contract_id": "c2", "severity": "high", "regulatory_citations": ["GDPR"]},
    ]
    result = build_regulation_map(findings, {"c1": "C1", "c2": "C2"})
    assert [item["citation"] for item in result] == ["GDPR", "CCPA"]


def reset_stores():
    FakeRepository.stores = {
        "organizations": {},
        "users": {},
        "organization_invites": {},
        f"organizations/{ORG_ID}/members": {},
        "contracts": {
            "c1": {"id": "c1", "name": "Acme MSA", "org_id": ORG_ID},
            "c2": {"id": "c2", "name": "Beta NDA", "org_id": ORG_ID},
            "c3": {"id": "c3", "name": "Other Org Contract", "org_id": "someone-else"},
        },
        "risk_findings": {
            "f1": {"id": "f1", "contract_id": "c1", "severity": "critical", "regulatory_citations": ["GDPR Article 28"]},
            "f2": {"id": "f2", "contract_id": "c2", "severity": "high", "regulatory_citations": ["GDPR Article 28"]},
            "f3": {"id": "f3", "contract_id": "c1", "severity": "low", "regulatory_citations": []},
            "f-other-org": {"id": "f-other-org", "contract_id": "c3", "severity": "critical", "regulatory_citations": ["GDPR Article 28"]},
        },
    }


def make_org_service() -> OrganizationService:
    service = OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )
    service.create_org("LexProof Demo", "admin-1", org_id=ORG_ID, creator_email="admin@example.com")
    return service


def make_client(monkeypatch, uid: str):
    org_service = make_org_service()
    monkeypatch.setattr(org_api, "_orgs", lambda: org_service)
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: org_service)
    monkeypatch.setattr(org_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": "admin@example.com"}
    return TestClient(app)


def test_regulation_map_endpoint_scopes_to_org_and_excludes_other_orgs(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "admin-1")
    response = client.get(f"/api/orgs/{ORG_ID}/regulation-map")
    assert response.status_code == 200
    body = response.json()
    [entry] = body["regulations"]
    assert entry["citation"] == "GDPR Article 28"
    # f1 (c1, critical) + f2 (c2, high); f-other-org (different org) must be excluded.
    assert entry["count"] == 2
    assert entry["severity_counts"] == {"CRITICAL": 1, "HIGH": 1}
    contract_ids = {c["contract_id"] for c in entry["contracts"]}
    assert contract_ids == {"c1", "c2"}


def test_regulation_map_endpoint_requires_org_membership(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch, "stranger-1")
    response = client.get(f"/api/orgs/{ORG_ID}/regulation-map")
    assert response.status_code == 403
