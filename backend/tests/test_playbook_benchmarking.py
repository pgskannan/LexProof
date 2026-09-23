"""Playbook / template benchmarking: prompt injection and finding persistence."""

import json

from fastapi.testclient import TestClient

from app.lexproof.api import contracts as contracts_api
from app.lexproof.api import findings as findings_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import DEFAULT_PLAYBOOK_CLAUSES
from tests.fakes import FakeRepository


ANALYSIS_WITH_PLAYBOOK_FIELDS = {
    "risk_score": 60,
    "risk_level": "HIGH",
    "compliance_score": 70,
    "findings": [{
        "title": "Below-standard liability cap",
        "severity": "high",
        "description": "The cap is set below the org's standard position.",
        "evidence": "Liability shall not exceed $5,000.",
        "recommendation": "Raise the cap to the standard position.",
        "risk_impact": 70,
        "compliance_impact": 40,
        "source_section": "Section 8",
        "evidence_quote": "Liability shall not exceed $5,000.",
        "reasoning": "The cap is far below typical exposure.",
        "confidence": 0.9,
        "clause_type": "Limitation of Liability",
        "playbook_alignment": "DEVIATION",
        "playbook_notes": "The $5,000 cap is well below the standard 12-months-of-fees position.",
    }],
    "key_clauses": [{"text": "Liability shall not exceed $5,000."}],
    "compliance_items": [],
}


class PromptCapturingProvider:
    last_prompt: str | None = None

    async def complete(self, request):
        PromptCapturingProvider.last_prompt = request.prompt
        return type("Response", (), {"content": json.dumps(ANALYSIS_WITH_PLAYBOOK_FIELDS)})()


def seed_data(*, org_id: str | None = None, org_playbook: list[dict] | None = None):
    PromptCapturingProvider.last_prompt = None
    contract = {"id": "contract-1", "owner_id": "owner-1", "current_version_id": "version-1"}
    if org_id:
        contract["org_id"] = org_id
    stores = {
        "contracts": {"contract-1": contract},
        "contract_versions": {
            "version-1": {
                "id": "version-1",
                "contract_id": "contract-1",
                "owner_id": "owner-1",
                "version_number": 1,
                "document_text": "Liability shall not exceed $5,000.",
            },
        },
        "legal_passports": {},
        "risk_findings": {},
        "evidence_records": {},
        "organizations": {},
    }
    if org_id and org_playbook is not None:
        stores["organizations"][org_id] = {"id": org_id, "playbook_clauses": org_playbook}
    FakeRepository.stores = stores


def make_client(monkeypatch, *, org_id: str | None = None, org_playbook: list[dict] | None = None):
    seed_data(org_id=org_id, org_playbook=org_playbook)
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(contracts_api, "_repositories", lambda: (FakeRepository("contracts"), FakeRepository("contract_versions"), object()))
    monkeypatch.setattr(contracts_api, "VertexGeminiProvider", PromptCapturingProvider)
    monkeypatch.setattr(findings_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}
    return TestClient(app)


def test_analysis_prompt_includes_default_playbook_when_no_org(monkeypatch):
    client = make_client(monkeypatch, org_id=None)
    response = client.post("/api/contracts/contract-1/analyze")

    assert response.status_code == 200
    assert PromptCapturingProvider.last_prompt is not None
    for clause in DEFAULT_PLAYBOOK_CLAUSES:
        assert clause["clause_type"] in PromptCapturingProvider.last_prompt


def test_analysis_prompt_uses_orgs_customized_playbook(monkeypatch):
    custom_playbook = [{"clause_type": "Data Privacy", "standard_position": "GDPR/CCPA-compliant processing only."}]
    client = make_client(monkeypatch, org_id="org-1", org_playbook=custom_playbook)
    response = client.post("/api/contracts/contract-1/analyze")

    assert response.status_code == 200
    assert "Data Privacy" in PromptCapturingProvider.last_prompt
    assert "GDPR/CCPA-compliant processing only." in PromptCapturingProvider.last_prompt
    # The org's customization replaces the default seed, it doesn't merge with it.
    assert "Limitation of Liability" not in PromptCapturingProvider.last_prompt


def test_analysis_prompt_falls_back_to_default_when_org_has_no_custom_playbook(monkeypatch):
    client = make_client(monkeypatch, org_id="org-1", org_playbook=None)
    response = client.post("/api/contracts/contract-1/analyze")

    assert response.status_code == 200
    assert "Limitation of Liability" in PromptCapturingProvider.last_prompt


def test_findings_persist_playbook_alignment_fields(monkeypatch):
    client = make_client(monkeypatch, org_id=None)
    response = client.post("/api/contracts/contract-1/analyze")

    assert response.status_code == 200
    [finding] = list(FakeRepository.stores["risk_findings"].values())
    assert finding["clause_type"] == "Limitation of Liability"
    assert finding["playbook_alignment"] == "DEVIATION"
    assert finding["playbook_notes"] == "The $5,000 cap is well below the standard 12-months-of-fees position."


def test_findings_api_surfaces_playbook_alignment(monkeypatch):
    client = make_client(monkeypatch, org_id=None)
    client.post("/api/contracts/contract-1/analyze")

    response = client.get("/api/findings?contract_id=contract-1&version_id=version-1")
    assert response.status_code == 200
    [finding] = response.json()
    assert finding["clause_type"] == "Limitation of Liability"
    assert finding["playbook_alignment"] == "DEVIATION"
