import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.lexproof.api import contracts as contracts_api
from app.lexproof.config import LexProofSettings, get_settings
from app.lexproof.main import create_app
from app.lexproof.services import health as health_module
from app.lexproof.services.ask_contracts import AskContractsService
from app.lexproof.services.auth import enforce_read_only, get_current_user
from app.lexproof.services.paypal.rate_limit import (
    JUDGE_DEMO_LIMIT_DETAIL,
    check_judge_analysis_rate,
    check_judge_interaction_rate,
)
from app.lexproof.services.translation import TranslationService


class MemoryRepository:
    stores: dict[str, dict[str, dict]] = {}

    def __init__(self, collection: str):
        self.collection = collection
        self.stores.setdefault(collection, {})

    def get(self, document_id: str):
        return self.stores[self.collection].get(document_id)

    def set(self, document_id: str, data: dict, merge: bool = False):
        bucket = self.stores[self.collection]
        if merge and document_id in bucket:
            bucket[document_id].update(data)
        else:
            bucket[document_id] = dict(data)

    def stream(self):
        return iter({"id": key, **value} for key, value in self.stores[self.collection].items())


class MemoryStorage:
    def upload(self, path: str, content: bytes, content_type: str) -> str:
        return f"gs://judge-test/{path}"


@pytest.fixture(autouse=True)
def judge_environment(monkeypatch):
    monkeypatch.setenv("LEXPROOF_READ_ONLY_UIDS", "demo-judge-1")
    monkeypatch.setenv("LEXPROOF_JUDGE_CAN_ANALYZE", "true")
    get_settings.cache_clear()
    MemoryRepository.stores = {}
    yield
    get_settings.cache_clear()


def _client(monkeypatch):
    monkeypatch.setattr(contracts_api, "_repositories", lambda: (
        MemoryRepository("contracts"),
        MemoryRepository("contract_versions"),
        MemoryStorage(),
    ))
    monkeypatch.setattr(contracts_api, "record_audit_event", lambda **kwargs: None)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "demo-judge-1", "email": "judge@example.test"}
    return TestClient(app)


def test_read_only_judge_can_upload_and_analyze_their_own_contract(monkeypatch):
    enforce_read_only("demo-judge-1", "POST", "/api/contracts")
    enforce_read_only("demo-judge-1", "POST", "/api/contracts/new-contract/analyze")

    class FakeAnalysisService:
        async def analyze_version(self, contract_id, version_id, user_id, **kwargs):
            assert user_id == "demo-judge-1"
            assert kwargs["anchor_evidence"] is False
            return {"passport": {"passport_id": "judge-passport"}}

    monkeypatch.setattr(contracts_api, "_version_analysis_service", lambda contracts, versions: FakeAnalysisService())
    client = _client(monkeypatch)

    uploaded = client.post(
        "/api/contracts",
        files={"file": ("judge-contract.txt", b"A small contract for the Nebius judge demo.", "text/plain")},
    )
    assert uploaded.status_code == 201
    contract_id = uploaded.json()["contract_id"]
    assert MemoryRepository.stores["contracts"][contract_id]["owner_id"] == "demo-judge-1"

    analyzed = client.post(f"/api/contracts/{contract_id}/analyze")
    assert analyzed.status_code == 200
    assert analyzed.json()["passport_id"] == "judge-passport"


def test_read_only_judge_upload_restrictions_are_enforced(monkeypatch):
    client = _client(monkeypatch)
    too_large = client.post(
        "/api/contracts",
        files={"file": ("large.txt", b"x" * (2 * 1024 * 1024 + 1), "text/plain")},
    )
    assert too_large.status_code == 413
    assert too_large.json()["detail"] == "Judge demo uploads are limited to 2 MB."

    unsupported = client.post(
        "/api/contracts",
        files={"file": ("scan.png", b"image", "image/png")},
    )
    assert unsupported.status_code == 415


def test_read_only_judge_cannot_analyze_another_users_contract(monkeypatch):
    monkeypatch.setattr(contracts_api, "_repositories", lambda: (
        MemoryRepository("contracts"), MemoryRepository("contract_versions"), MemoryStorage()
    ))
    MemoryRepository.stores.setdefault("contracts", {})["other-contract"] = {
        "id": "other-contract",
        "owner_id": "another-user",
        "current_version_id": "other-version",
    }
    client = _client(monkeypatch)

    response = client.post("/api/contracts/other-contract/analyze")

    assert response.status_code == 404


def test_judge_ask_scope_includes_only_their_org_contracts():
    contracts = MemoryRepository("contracts")
    contracts.set("judge-contract", {"owner_id": "demo-judge-1", "org_id": "org-demo", "name": "Judge NDA"})
    contracts.set("other-contract", {"owner_id": "another-user", "org_id": "org-demo", "name": "Other NDA"})
    service = AskContractsService(contracts=contracts)

    owned = service.org_contracts("org-demo", "demo-judge-1", owner_only=True)

    assert [contract["contract_id"] for contract in owned] == ["judge-contract"]


@pytest.mark.asyncio
async def test_judge_translation_scope_excludes_findings_from_other_owned_contracts():
    findings = MemoryRepository("risk_findings")
    translations = MemoryRepository("finding_translations")
    findings.set("judge-finding", {
        "owner_id": "demo-judge-1",
        "contract_id": "judge-contract",
        "title": "Own finding",
    })
    findings.set("foreign-finding", {
        "owner_id": "demo-judge-1",
        "contract_id": "other-contract",
        "title": "Foreign contract finding",
    })

    class FakeTranslator:
        name = "fake"

        async def translate_texts(self, texts, target_language):
            return [f"translated:{text}" for text in texts]

    service = TranslationService(findings=findings, translations=translations, provider=FakeTranslator())
    result = await service.translate_findings(
        ["judge-finding", "foreign-finding"],
        "fr",
        "demo-judge-1",
        owned_contract_ids={"judge-contract"},
    )

    assert list(result) == ["judge-finding"]


def test_judge_write_allowlist_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("LEXPROOF_JUDGE_CAN_ANALYZE", "false")
    get_settings.cache_clear()
    for path in ("/api/contracts", "/api/contracts/owned-contract/analyze"):
        with pytest.raises(HTTPException) as error:
            enforce_read_only("demo-judge-1", "POST", path)
        assert error.value.status_code == 403


def test_all_other_judge_writes_remain_blocked_when_analysis_is_enabled():
    blocked_writes = (
        ("POST", "/api/contracts/bulk"),
        ("POST", "/api/contracts/c1/versions/v1/analyze"),
        ("POST", "/api/contracts/c1/redline-proposals/p1/publish"),
        ("POST", "/api/passports/p1/anchor-root"),
        ("POST", "/api/evidence/e1/anchor"),
        ("POST", "/api/orgs/o1/workflow-instances/i1/transition"),
        ("POST", "/api/payment-actions/a1:execute"),
        ("PATCH", "/api/orgs/o1/settings"),
        ("DELETE", "/api/contracts/c1"),
    )
    for method, path in blocked_writes:
        with pytest.raises(HTTPException) as error:
            enforce_read_only("demo-judge-1", method, path)
        assert error.value.status_code == 403, (method, path)


def test_judge_limits_return_the_documented_429():
    analysis_uid = "analysis-limit-test-judge"
    for _ in range(10):
        check_judge_analysis_rate(analysis_uid)
    with pytest.raises(HTTPException) as analysis_error:
        check_judge_analysis_rate(analysis_uid)
    assert analysis_error.value.status_code == 429
    assert analysis_error.value.detail == JUDGE_DEMO_LIMIT_DETAIL

    interaction_uid = "interaction-limit-test-judge"
    for _ in range(30):
        check_judge_interaction_rate(interaction_uid)
    with pytest.raises(HTTPException) as interaction_error:
        check_judge_interaction_rate(interaction_uid)
    assert interaction_error.value.status_code == 429
    assert interaction_error.value.detail == JUDGE_DEMO_LIMIT_DETAIL


@pytest.mark.asyncio
async def test_health_reports_provider_models_and_no_secret(monkeypatch):
    settings = LexProofSettings(
        llm_provider="nebius",
        nebius_api_key=SecretStr("never-return-this-key"),
        llm_fallback_to_vertex=True,
    )
    monkeypatch.setattr(health_module, "get_settings", lambda: settings)

    response = await health_module.health()

    assert response["ai"] == {
        "provider": "nebius",
        "analysis_model": "nvidia/Nemotron-3-Ultra-550b-a55b",
        "fast_model": "nvidia/nemotron-3-super-120b-a12b",
        "fallback_to_vertex": True,
        "nebius_configured": True,
    }
    assert "never-return-this-key" not in json.dumps(response)
