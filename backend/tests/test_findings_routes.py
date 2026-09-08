from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.lexproof.api import findings as findings_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user


class FakeFindingsRepository:
    records = [
        {
            "id": "finding-1",
            "owner_id": "user-1",
            "contract_id": "contract-1",
            "version_id": "version-1",
            "title": "Liability cap",
            "severity": "critical",
            "description": "The cap is too low.",
            "risk_impact": 90,
            "compliance_impact": 20,
            "evidence": "Clause text",
            "evidence_quote": "Liability shall not exceed...",
            "source_section": "Section 12",
            "recommendation": "Review the cap.",
            "created_at": datetime.now(timezone.utc),
            "internal_value": "excluded",
        },
        {
            "id": "finding-2",
            "owner_id": "user-1",
            "contract_id": "contract-2",
            "version_id": "version-2",
            "title": "Notice period",
            "severity": "medium",
        },
        {
            "id": "finding-other-user",
            "owner_id": "user-2",
            "contract_id": "contract-1",
        },
    ]

    def __init__(self, collection: str):
        assert collection == "risk_findings"

    def stream(self):
        return iter(self.records)


def make_client(monkeypatch):
    monkeypatch.setattr(findings_api, "FirestoreRepository", FakeFindingsRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "user-1"}
    return TestClient(app)


def test_findings_require_authentication():
    response = TestClient(create_app()).get("/api/findings")
    assert response.status_code == 401


def test_findings_are_filtered_by_contract_and_version(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/findings?contract_id=contract-1&version_id=version-1")

    assert response.status_code == 200
    assert response.json() == [{
        "finding_id": "finding-1",
        "contract_id": "contract-1",
        "version_id": "version-1",
        "title": "Liability cap",
        "severity": "critical",
        "description": "The cap is too low.",
        "risk_impact": 90.0,
        "compliance_impact": 20.0,
        "evidence": "Clause text",
        "evidence_quote": "Liability shall not exceed...",
        "source_section": "Section 12",
        "recommendation": "Review the cap.",
        "created_at": response.json()[0]["created_at"],
    }]


def test_findings_return_empty_for_unknown_contract(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/findings?contract_id=missing")

    assert response.status_code == 200
    assert response.json() == []


def test_missing_optional_fields_remain_unavailable(monkeypatch):
    client = make_client(monkeypatch)
    response = client.get("/api/findings?contract_id=contract-2&version_id=version-2")

    assert response.status_code == 200
    finding = response.json()[0]
    assert finding["risk_impact"] is None
    assert finding["compliance_impact"] is None
    assert finding["evidence_quote"] is None
    assert finding["source_section"] is None