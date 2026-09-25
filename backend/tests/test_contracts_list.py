from fastapi.testclient import TestClient

import app.lexproof.api.contracts as contracts_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.organizations import OrganizationService
from tests.fakes import FakeRepository


class CountingRepository(FakeRepository):
    """Records whether list_contracts streamed whole collections.

    GET /api/contracts used to stream contracts, versions, passports, and
    proposals on every findings-page picker open. That left the golden-path
    E2E staring at "No contracts match" for 15s+. An org-scoped list must
    query by org_id and get_many current versions instead.
    """

    stream_collections: list[str] = []
    query_equals: list[tuple[str, dict]] = []
    get_many_collections: list[str] = []

    def stream(self):
        type(self).stream_collections.append(self.collection)
        return super().stream()

    def query(self, *, equal=None, **kwargs):
        type(self).query_equals.append((self.collection, dict(equal or {})))
        return super().query(equal=equal, **kwargs)

    def get_many(self, document_ids):
        type(self).get_many_collections.append(self.collection)
        return super().get_many(document_ids)


def make_org_service() -> OrganizationService:
    return OrganizationService(
        orgs=FakeRepository("organizations"),
        users=FakeRepository("users"),
        invites=FakeRepository("organization_invites"),
        member_factory=lambda org_id: FakeRepository(f"organizations/{org_id}/members"),
        claims_refresher=lambda *args, **kwargs: None,
    )


def seed_list_stores() -> None:
    FakeRepository.stores = {
        "organizations": {"org-1": {"org_id": "org-1", "status": "active"}},
        "users": {},
        "organization_invites": {},
        "organizations/org-1/members": {
            "owner-1": {"user_id": "owner-1", "roles": ["contract_owner"], "status": "active", "org_id": "org-1"},
        },
        "contracts": {
            "demo-golden-path-master-services-agreement": {
                "id": "demo-golden-path-master-services-agreement",
                "name": "Demo Golden Path Master Services Agreement",
                "org_id": "org-1",
                "owner_id": "owner-1",
                "current_version_id": "version-1",
            },
            "other-org-contract": {
                "id": "other-org-contract",
                "name": "Other Org Contract",
                "org_id": "org-2",
                "owner_id": "owner-1",
                "current_version_id": "version-other",
            },
        },
        "contract_versions": {
            "version-1": {
                "id": "version-1",
                "passport_id": "passport-1",
                "version_number": 1,
                "analysis_status": "complete",
            },
        },
        "legal_passports": {
            "passport-1": {
                "id": "passport-1",
                "org_id": "org-1",
                "contract_id": "demo-golden-path-master-services-agreement",
            },
        },
        "redline_proposals": {},
        "evidence_records": {},
        "evidence_anchors": {},
        "risk_findings": {},
    }


def make_client(monkeypatch, uid: str = "owner-1"):
    seed_list_stores()
    CountingRepository.stream_collections = []
    CountingRepository.query_equals = []
    CountingRepository.get_many_collections = []
    monkeypatch.setattr(contracts_api, "FirestoreRepository", CountingRepository)
    monkeypatch.setattr(contracts_api, "EvidenceAnchorRepository", CountingRepository)
    monkeypatch.setattr(contracts_api, "get_organization_service", make_org_service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_org_header_lists_only_that_orgs_contracts(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/api/contracts", headers={"X-Org-Id": "org-1"})

    assert response.status_code == 200
    assert [item["contract_id"] for item in response.json()] == [
        "demo-golden-path-master-services-agreement"
    ]
    assert response.json()[0]["name"] == "Demo Golden Path Master Services Agreement"


def test_org_header_does_not_stream_workspace_collections(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/api/contracts", headers={"X-Org-Id": "org-1"})

    assert response.status_code == 200
    assert ("contracts", {"org_id": "org-1"}) in CountingRepository.query_equals
    assert ("legal_passports", {"org_id": "org-1"}) in CountingRepository.query_equals
    assert ("redline_proposals", {"org_id": "org-1"}) in CountingRepository.query_equals
    assert "contract_versions" in CountingRepository.get_many_collections
    assert "contracts" not in CountingRepository.stream_collections
    assert "contract_versions" not in CountingRepository.stream_collections
    assert "legal_passports" not in CountingRepository.stream_collections
    assert "redline_proposals" not in CountingRepository.stream_collections


def test_non_member_cannot_list_org_contracts(monkeypatch):
    response = make_client(monkeypatch, uid="outside-1").get(
        "/api/contracts", headers={"X-Org-Id": "org-1"}
    )
    assert response.status_code == 403


def test_unscoped_list_keeps_legacy_owner_visibility(monkeypatch):
    FakeRepository.stores = {
        "contracts": {
            "legacy-1": {"id": "legacy-1", "name": "Legacy", "owner_id": "owner-1"},
            "someone-else": {"id": "someone-else", "name": "Hidden", "owner_id": "other-1"},
        },
        "contract_versions": {},
        "legal_passports": {},
        "redline_proposals": {},
        "evidence_records": {},
        "evidence_anchors": {},
        "risk_findings": {},
        "organizations": {},
        "users": {},
        "organization_invites": {},
    }
    CountingRepository.stream_collections = []
    CountingRepository.query_equals = []
    CountingRepository.get_many_collections = []
    monkeypatch.setattr(contracts_api, "FirestoreRepository", CountingRepository)
    monkeypatch.setattr(contracts_api, "EvidenceAnchorRepository", CountingRepository)
    monkeypatch.setattr(contracts_api, "get_organization_service", make_org_service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}

    response = TestClient(app).get("/api/contracts")

    assert response.status_code == 200
    assert [item["contract_id"] for item in response.json()] == ["legacy-1"]
    assert "contracts" in CountingRepository.stream_collections
    assert "contract_versions" not in CountingRepository.stream_collections


def test_org_list_finds_published_version_passport_without_org_id(monkeypatch):
    """CONTRACT_04 regression: list said "Failed — retry", detail said Confirmed.

    The published version's passport predates org scoping (no org_id), so the
    org-scoped passport query missed it; the list then saw no passport and no
    evidence. The list must resolve it by contract, like the detail page does.
    """
    from app.lexproof.domains.passport.utils.hashing import hash_evidence_item

    client = make_client(monkeypatch)
    stores = FakeRepository.stores
    stores["contracts"]["demo-golden-path-master-services-agreement"]["current_version_id"] = "version-2"
    stores["contract_versions"]["version-2"] = {
        "id": "version-2",
        "contract_id": "demo-golden-path-master-services-agreement",
        "version_number": 2,
        "analysis_status": "failed",
    }
    stores["legal_passports"]["passport-2"] = {
        "id": "passport-2",
        "passport_id": "passport-2",
        "contract_id": "demo-golden-path-master-services-agreement",
        "contract_version": 2,
        "version_id": "version-2",
    }
    stores["redline_proposals"]["proposal-1"] = {
        "id": "proposal-1",
        "org_id": "org-1",
        "contract_id": "demo-golden-path-master-services-agreement",
        "published_version_id": "version-2",
        "analysis_status": "failed",
    }
    evidence = {
        "id": "evidence-1",
        "evidence_id": "evidence-1",
        "passport_id": "passport-2",
        "evidence_type": "clause",
        "title": "Termination",
    }
    stores["evidence_records"]["evidence-1"] = evidence
    stores["evidence_anchors"]["evidence-1"] = {
        "id": "evidence-1",
        "evidence_id": "evidence-1",
        "evidence_hash": hash_evidence_item(evidence),
    }

    response = client.get("/api/contracts", headers={"X-Org-Id": "org-1"})

    assert response.status_code == 200
    row = response.json()[0]
    assert row["passport_id"] == "passport-2"
    assert row["proof_status"] == "confirmed"
    assert row["analysis_status"] == "complete"
