from fastapi.testclient import TestClient

from app.lexproof.api import ask as ask_api
from app.lexproof.api import organizations as org_api
from app.lexproof.main import create_app
from app.lexproof.services.ask_contracts import (
    AskContractsService,
    UNGROUNDED_MESSAGE,
    named_contracts,
    validate_citations,
)
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository

ORG_ID = "lexproof-demo"


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def complete_json(self, prompt, schema, system_prompt=None):
        self.calls.append({"prompt": prompt, "schema": schema, "system_prompt": system_prompt})
        return self.payload


def reset_stores():
    FakeRepository.stores = {
        "organizations": {},
        "users": {},
        "organization_invites": {},
        f"organizations/{ORG_ID}/members": {},
        "contracts": {
            "acme-msa": {
                "id": "acme-msa",
                "name": "Acme Master Services Agreement",
                "org_id": ORG_ID,
            },
            "beta-nda": {
                "id": "beta-nda",
                "name": "Beta NDA",
                "org_id": ORG_ID,
            },
            "other-org": {
                "id": "other-org",
                "name": "Other Org Contract",
                "org_id": "someone-else",
            },
        },
        "risk_findings": {
            "finding-gov": {
                "id": "finding-gov",
                "contract_id": "acme-msa",
                "title": "Unfavorable governing law",
                "severity": "high",
                "description": "Governing law is Delaware with no negotiation right.",
                "evidence_quote": "This Agreement is governed by the laws of Delaware.",
                "source_section": "Section 18",
            },
            "finding-liability": {
                "id": "finding-liability",
                "contract_id": "beta-nda",
                "title": "Unlimited liability",
                "severity": "critical",
                "description": "No liability cap.",
                "evidence_quote": "Vendor's liability shall be unlimited.",
            },
        },
        "evidence_records": {
            "ev-gov": {
                "evidence_id": "ev-gov",
                "contract_id": "acme-msa",
                "title": "Risk Finding 1: Unfavorable governing law",
                "analysis_reference": "finding-gov",
            },
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


def make_ask_service(llm=None) -> AskContractsService:
    return AskContractsService(
        contracts=FakeRepository("contracts"),
        findings=FakeRepository("risk_findings"),
        evidence=FakeRepository("evidence_records"),
        llm=llm or FakeLLM({"answer": "unused", "citations": []}),
    )


def test_named_contract_scopes_retrieval():
    reset_stores()
    service = make_ask_service()
    retrieved = service.retrieve(ORG_ID, "Which governing law issues are in the Acme Master Services Agreement?", "admin-1")
    assert [item["finding_id"] for item in retrieved] == ["finding-gov"]
    assert retrieved[0]["evidence_id"] == "ev-gov"


def test_broad_question_returns_cross_portfolio_findings():
    reset_stores()
    service = make_ask_service()
    retrieved = service.retrieve(ORG_ID, "Which contracts have unfavorable liability or governing law clauses?", "admin-1")
    ids = {item["finding_id"] for item in retrieved}
    assert ids == {"finding-gov", "finding-liability"}


def test_unrelated_question_is_not_grounded():
    reset_stores()
    llm = FakeLLM({"answer": "should not be called", "citations": []})
    service = make_ask_service(llm)

    async def run():
        return await service.ask(ORG_ID, "What is the weather in Lisbon tomorrow?", "admin-1")

    import asyncio

    result = asyncio.run(run())
    assert result["grounded"] is False
    assert result["answer"] == UNGROUNDED_MESSAGE
    assert llm.calls == []


def test_validate_citations_drops_hallucinated_ids():
    retrieved = [
        {
            "finding_id": "finding-gov",
            "evidence_id": "ev-gov",
            "contract_id": "acme-msa",
            "contract_name": "Acme MSA",
        }
    ]
    validated = validate_citations(
        [
            {"finding_id": "finding-gov", "evidence_id": "ev-gov"},
            {"finding_id": "hallucinated-99", "evidence_id": "nope"},
        ],
        retrieved,
    )
    assert [item["finding_id"] for item in validated] == ["finding-gov"]
    assert validated[0]["contract_name"] == "Acme MSA"


def test_named_contracts_matches_by_name():
    contracts = [{"contract_id": "acme-msa", "name": "Acme Master Services Agreement"}]
    matches = named_contracts("issues in the Acme Master Services Agreement", contracts)
    assert matches[0]["contract_id"] == "acme-msa"


def test_ask_endpoint_requires_org_membership(monkeypatch):
    reset_stores()
    org_service = make_org_service()
    monkeypatch.setattr(org_api, "_orgs", lambda: org_service)
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: org_service)
    monkeypatch.setattr(ask_api, "_service", lambda: make_ask_service())
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "stranger-1", "email": "stranger@example.com"}
    client = TestClient(app)
    response = client.post(f"/api/orgs/{ORG_ID}/ask", json={"question": "Any liability issues?"})
    assert response.status_code == 403


def test_ask_endpoint_returns_validated_citations(monkeypatch):
    reset_stores()
    org_service = make_org_service()
    llm = FakeLLM(
        {
            "answer": "The Acme MSA has an unfavorable governing law clause.",
            "citations": [
                {"finding_id": "finding-gov", "evidence_id": "ev-gov"},
                {"finding_id": "not-real", "evidence_id": "x"},
            ],
        }
    )
    ask_service = make_ask_service(llm)
    monkeypatch.setattr(org_api, "_orgs", lambda: org_service)
    monkeypatch.setattr("app.lexproof.services.organizations.get_organization_service", lambda: org_service)
    monkeypatch.setattr(ask_api, "_service", lambda: ask_service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "admin-1", "email": "admin@example.com"}
    client = TestClient(app)
    response = client.post(
        f"/api/orgs/{ORG_ID}/ask",
        json={"question": "Which governing law issues are in the Acme Master Services Agreement?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert [item["finding_id"] for item in body["citations"]] == ["finding-gov"]
    assert body["citations"][0]["evidence_id"] == "ev-gov"
