from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.lexproof.api import redline_proposals as proposal_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from app.lexproof.services.redline_suggestions import RedlineSuggestionError, RedlineSuggestionService
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def complete_json(self, prompt, schema, system_prompt=None):
        self.calls.append({"prompt": prompt, "schema": schema, "system_prompt": system_prompt})
        return self.payload


def seed_data():
    FakeRepository.stores = {
        "contracts": {
            "contract-1": {"id": "contract-1", "owner_id": "owner-1", "org_id": ORG_ID},
            "contract-legacy": {"id": "contract-legacy", "owner_id": "owner-1"},
        },
        "risk_findings": {
            "finding-1": {
                "id": "finding-1",
                "contract_id": "contract-1",
                "title": "Liability cap too low",
                "severity": "critical",
                "description": "The cap is too low relative to contract value.",
                "reasoning": "A $10k cap does not match the $2M contract value.",
                "recommendation": "Raise the cap to at least contract value.",
                "evidence_quote": "Vendor's liability under this Agreement shall not exceed $10,000.",
                "clause_type": "Limitation of Liability",
                "created_at": datetime.now(timezone.utc),
            },
            "finding-no-quote": {
                "id": "finding-no-quote",
                "contract_id": "contract-1",
                "title": "Vague finding",
                "severity": "low",
                "description": "No clause text recorded.",
                "evidence_quote": None,
                "evidence": None,
            },
            "finding-other-contract": {
                "id": "finding-other-contract",
                "contract_id": "contract-legacy",
                "title": "Unrelated",
                "evidence_quote": "Some other clause.",
            },
        },
        "organizations": {ORG_ID: {"org_id": ORG_ID, "name": "LexProof Demo", "status": "active"}},
        f"organizations/{ORG_ID}/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": ORG_ID},
        },
        "users": {},
        "organization_invites": {},
    }


def make_orgs() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def make_service(llm=None) -> RedlineSuggestionService:
    return RedlineSuggestionService(
        contracts=FakeRepository("contracts"),
        findings=FakeRepository("risk_findings"),
        organizations=make_orgs(),
        llm=llm or FakeLLM({"suggested_text": "Vendor's liability shall not exceed the total fees paid.", "rationale": "Aligns cap with contract value."}),
    )


def run(coro):
    import asyncio

    return asyncio.run(coro)


def test_suggest_returns_drafted_replacement_with_playbook_context():
    seed_data()
    llm = FakeLLM({"suggested_text": "Replacement clause text.", "rationale": "Because reasons."})
    service = make_service(llm)
    result = run(service.suggest("contract-1", "finding-1", "owner-1"))
    assert result["suggested_text"] == "Replacement clause text."
    assert result["rationale"] == "Because reasons."
    assert result["original_text"] == "Vendor's liability under this Agreement shall not exceed $10,000."
    assert result["clause_type"] == "Limitation of Liability"
    # Default playbook seeds a Limitation of Liability standard position; the
    # prompt sent to the LLM should include it even though this org never
    # customized its playbook.
    assert result["playbook_standard_position"]
    assert result["playbook_standard_position"] in llm.calls[0]["prompt"]


def test_suggest_uses_org_customized_playbook_over_default():
    seed_data()
    orgs = make_orgs()
    orgs.update_playbook(
        ORG_ID,
        [{"clause_type": "Limitation of Liability", "standard_position": "Custom cap: 12 months of fees."}],
        "owner-1",
    )
    llm = FakeLLM({"suggested_text": "x", "rationale": "y"})
    service = RedlineSuggestionService(
        contracts=FakeRepository("contracts"),
        findings=FakeRepository("risk_findings"),
        organizations=orgs,
        llm=llm,
    )
    result = run(service.suggest("contract-1", "finding-1", "owner-1"))
    assert result["playbook_standard_position"] == "Custom cap: 12 months of fees."
    assert "Custom cap: 12 months of fees." in llm.calls[0]["prompt"]


def test_suggest_rejects_finding_with_no_recorded_clause_text():
    seed_data()
    service = make_service()
    try:
        run(service.suggest("contract-1", "finding-no-quote", "owner-1"))
        assert False, "expected RedlineSuggestionError"
    except RedlineSuggestionError:
        pass


def test_suggest_rejects_finding_belonging_to_a_different_contract():
    seed_data()
    service = make_service()
    try:
        run(service.suggest("contract-1", "finding-other-contract", "owner-1"))
        assert False, "expected RedlineSuggestionError"
    except RedlineSuggestionError:
        pass


def test_suggest_rejects_non_member():
    seed_data()
    service = make_service()
    try:
        run(service.suggest("contract-1", "finding-1", "stranger-1"))
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_suggest_endpoint_returns_ai_draft(monkeypatch):
    seed_data()
    llm = FakeLLM({"suggested_text": "Replacement clause text.", "rationale": "Because reasons."})
    monkeypatch.setattr(proposal_api, "_suggestion_service", lambda: make_service(llm))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1", "email": "owner@example.com"}
    client = TestClient(app)
    response = client.post("/api/contracts/contract-1/redline-proposals/suggest", json={"finding_id": "finding-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["suggested_text"] == "Replacement clause text."
    assert body["rationale"] == "Because reasons."
    assert body["original_text"] == "Vendor's liability under this Agreement shall not exceed $10,000."


def test_suggest_endpoint_requires_org_membership(monkeypatch):
    seed_data()
    monkeypatch.setattr(proposal_api, "_suggestion_service", lambda: make_service())
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "stranger-1", "email": "stranger@example.com"}
    client = TestClient(app)
    response = client.post("/api/contracts/contract-1/redline-proposals/suggest", json={"finding_id": "finding-1"})
    assert response.status_code == 403


def test_suggest_endpoint_404s_for_unknown_finding(monkeypatch):
    seed_data()
    monkeypatch.setattr(proposal_api, "_suggestion_service", lambda: make_service())
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1", "email": "owner@example.com"}
    client = TestClient(app)
    response = client.post("/api/contracts/contract-1/redline-proposals/suggest", json={"finding_id": "does-not-exist"})
    assert response.status_code == 404
