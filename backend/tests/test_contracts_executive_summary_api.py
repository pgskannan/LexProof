"""API-level tests for the executive-summary endpoints on /api/contracts."""

from app.lexproof.api import contracts as contracts_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.executive_summary import ExecutiveSummaryService
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services import executive_summary as executive_summary_service
from fastapi.testclient import TestClient
from tests.fakes import FakeRepository


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def complete_json(self, prompt, schema, system_prompt=None):
        self.calls.append(prompt)
        return self.payload


def seed_data():
    FakeRepository.stores = {
        "contracts": {
            "contract-1": {"id": "contract-1", "owner_id": "owner-1", "org_id": "org-1", "current_version_id": "version-1", "name": "MSA with Acme"},
        },
        "contract_versions": {
            "version-1": {"id": "version-1", "contract_id": "contract-1", "passport_id": "passport-1"},
        },
        "legal_passports": {
            "passport-1": {"id": "passport-1", "risk_score": 78.5, "risk_level": "HIGH", "compliance_score": 42.0},
        },
        "risk_findings": {
            "finding-1": {
                "id": "finding-1",
                "contract_id": "contract-1",
                "version_id": "version-1",
                "title": "Liability cap too low",
                "severity": "critical",
                "description": "The cap does not cover realistic exposure.",
            },
        },
        "executive_summaries": {},
        "organizations": {"org-1": {"org_id": "org-1", "status": "active"}},
        "organizations/org-1/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": "org-1"},
            "admin-1": {"user_id": "admin-1", "roles": ["admin"], "status": "active", "org_id": "org-1"},
        },
        "users": {},
        "organization_invites": {},
    }


def make_service(llm=None) -> ExecutiveSummaryService:
    return ExecutiveSummaryService(
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        passports=FakeRepository("legal_passports"),
        findings=FakeRepository("risk_findings"),
        summaries=FakeRepository("executive_summaries"),
        llm=llm or FakeLLM({"summary": "Plain-English brief."}),
    )


def make_client(monkeypatch, service=None, uid: str = "owner-1"):
    monkeypatch.setattr(contracts_api, "get_executive_summary_service", lambda: service or make_service())
    monkeypatch.setattr(executive_summary_service, "get_organization_service", make_org_service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": f"{uid}@example.com"}
    return TestClient(app)


def make_org_service() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def test_get_executive_summary_returns_a_generated_summary(monkeypatch):
    seed_data()
    llm = FakeLLM({"summary": "This contract carries high liability exposure."})
    client = make_client(monkeypatch, make_service(llm))

    response = client.get("/api/contracts/contract-1/executive-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "This contract carries high liability exposure."
    assert body["risk_score"] == 78.5
    assert len(llm.calls) == 1


def test_get_executive_summary_requires_authentication():
    seed_data()
    response = TestClient(create_app()).get("/api/contracts/contract-1/executive-summary")
    assert response.status_code == 401


def test_get_executive_summary_rejects_a_non_owner(monkeypatch):
    seed_data()
    client = make_client(monkeypatch, uid="stranger-1")

    response = client.get("/api/contracts/contract-1/executive-summary")

    assert response.status_code == 403


def test_same_org_admin_can_retrieve_executive_summary(monkeypatch):
    seed_data()
    client = make_client(monkeypatch, uid="admin-1")
    response = client.get("/api/contracts/contract-1/executive-summary")
    assert response.status_code == 200


def test_nonmember_cannot_retrieve_executive_summary(monkeypatch):
    seed_data()
    client = make_client(monkeypatch, uid="stranger-1")
    response = client.get("/api/contracts/contract-1/executive-summary")
    assert response.status_code == 403


def test_get_executive_summary_404s_for_an_unanalyzed_contract(monkeypatch):
    seed_data()
    FakeRepository.stores["contracts"]["contract-2"] = {"id": "contract-2", "owner_id": "owner-1", "current_version_id": "version-2"}
    client = make_client(monkeypatch)

    response = client.get("/api/contracts/contract-2/executive-summary")

    assert response.status_code == 404


def test_regenerate_executive_summary_forces_a_fresh_call(monkeypatch):
    seed_data()
    llm = FakeLLM({"summary": "First."})
    service = make_service(llm)
    client = make_client(monkeypatch, service)

    first = client.get("/api/contracts/contract-1/executive-summary")
    assert first.json()["summary"] == "First."
    assert len(llm.calls) == 1

    llm.payload = {"summary": "Regenerated."}
    second = client.post("/api/contracts/contract-1/executive-summary/regenerate")
    assert second.status_code == 200
    assert second.json()["summary"] == "Regenerated."
    assert len(llm.calls) == 2

    # And the cache now reflects the regenerated summary on a plain GET.
    third = client.get("/api/contracts/contract-1/executive-summary")
    assert third.json()["summary"] == "Regenerated."
    assert len(llm.calls) == 2
