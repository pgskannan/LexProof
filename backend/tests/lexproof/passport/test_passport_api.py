"""Integration tests for Legal Passport HTTP endpoints."""

from fastapi.testclient import TestClient

from app.lexproof.main import create_app
from app.lexproof.domains.passport.api.router import configure_passport_service
from app.lexproof.domains.passport.service import PassportService
from app.lexproof.services.auth import get_current_user


async def existing_contractriskedge_engine(document: str, policy: str) -> dict:
    """Test adapter representing the existing ContractRiskEdge engine."""
    return {
        "risk_score": 24.0,
        "risk_level": "low",
        "compliance_score": 91.0,
        "findings": [
            {
                "id": "finding-1",
                "title": "Notice",
                "severity": "low",
                "description": "Notice period requirement",
                "evidence": "Clause 5.2 requires 30-day notice",
                "recommendation": "Ensure notice clause is clear",
                "risk_impact": 10.0,
                "compliance_impact": 5.0,
                "source_section": "Clause 5.2",
                "evidence_quote": "30-day notice required",
            },
            {
                "id": "finding-2",
                "title": "Termination Rights",
                "severity": "medium",
                "description": "Termination clause flexibility",
                "evidence": "Clause 12.3 provides 60-day termination notice",
                "recommendation": "Review termination flexibility",
                "risk_impact": 15.0,
                "compliance_impact": 10.0,
                "source_section": "Clause 12.3",
                "evidence_quote": "60-day termination notice",
            }
        ],
        "key_clauses": ["Clause 5", "Clause 12"],
        "compliance_items": ["Notice Period", "Termination Rights"],
    }


def test_create_and_get_passport():
    """The API creates an immutable snapshot and reads it by ID and contract."""
    configure_passport_service(PassportService(
        analysis_engine=existing_contractriskedge_engine,
        user_id="integration-user",
        tenant_id="integration-tenant",
    ))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "integration-user"}
    client = TestClient(app)
    payload = {
        "contract_id": "contract-123",
        "contract_version": 1,
        "policy_version": "policy-1",
        "created_by": "integration-user",
        "document_content": "The contract text.",
        "normalized_document": "the contract text",
        "policy_content": "Required notice period.",
    }

    created = client.post("/api/passports", json=payload)
    assert created.status_code == 200
    passport = created.json()
    assert passport["risk_score"] == 24.0
    assert passport["evidence_count"] == 2
    assert len(passport["analysis_hash"]) == 64

    by_id = client.get(f"/api/passports/{passport['passport_id']}")
    assert by_id.status_code == 200
    by_contract = client.get("/api/contracts/contract-123/passport?contract_version=1")
    assert by_contract.status_code == 200
    assert by_contract.json()["passport_id"] == passport["passport_id"]
