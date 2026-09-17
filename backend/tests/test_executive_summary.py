from datetime import datetime, timezone

from app.lexproof.services.executive_summary import ExecutiveSummaryError, ExecutiveSummaryService
from tests.fakes import FakeRepository


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
            "contract-1": {"id": "contract-1", "owner_id": "owner-1", "current_version_id": "version-1", "name": "MSA with Acme"},
            "contract-unanalyzed": {"id": "contract-unanalyzed", "owner_id": "owner-1", "current_version_id": "version-2"},
            "contract-no-version": {"id": "contract-no-version", "owner_id": "owner-1", "current_version_id": None},
            "contract-legacy": {"id": "contract-legacy", "current_version_id": "version-3"},
        },
        "contract_versions": {
            "version-1": {"id": "version-1", "contract_id": "contract-1", "passport_id": "passport-1"},
            "version-3": {"id": "version-3", "contract_id": "contract-legacy", "passport_id": "passport-3"},
        },
        "legal_passports": {
            "passport-1": {"id": "passport-1", "risk_score": 78.5, "risk_level": "HIGH", "compliance_score": 42.0},
            "passport-3": {"id": "passport-3", "risk_score": 10.0, "risk_level": "LOW", "compliance_score": 90.0},
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
            "finding-2": {
                "id": "finding-2",
                "contract_id": "contract-1",
                "version_id": "version-1",
                "title": "Missing indemnity",
                "severity": "medium",
                "description": "No mutual indemnification clause.",
            },
            "finding-legacy": {
                "id": "finding-legacy",
                "contract_id": "contract-legacy",
                "version_id": "version-3",
                "title": "Minor notice period issue",
                "severity": "low",
                "description": "Notice period is short.",
            },
        },
        "executive_summaries": {},
    }


def make_service(llm=None) -> ExecutiveSummaryService:
    return ExecutiveSummaryService(
        contracts=FakeRepository("contracts"),
        versions=FakeRepository("contract_versions"),
        passports=FakeRepository("legal_passports"),
        findings=FakeRepository("risk_findings"),
        summaries=FakeRepository("executive_summaries"),
        llm=llm or FakeLLM({"summary": "Plain-English brief of the contract's risk."}),
    )


def run(coro):
    import asyncio

    return asyncio.run(coro)


def test_get_summary_generates_and_persists_a_summary():
    seed_data()
    llm = FakeLLM({"summary": "This contract carries high liability exposure -- needs legal review before signing."})
    service = make_service(llm)
    result = run(service.get_summary("contract-1", "owner-1"))
    assert result["summary"] == "This contract carries high liability exposure -- needs legal review before signing."
    assert result["risk_score"] == 78.5
    assert result["risk_level"] == "HIGH"
    assert result["compliance_score"] == 42.0
    assert result["findings_by_severity"] == {"critical": 1, "high": 0, "medium": 1, "low": 0}
    assert len(llm.calls) == 1
    assert "Liability cap too low" in llm.calls[0]["prompt"]


def test_get_summary_returns_cached_result_without_recalling_llm():
    seed_data()
    llm = FakeLLM({"summary": "Original summary."})
    service = make_service(llm)
    run(service.get_summary("contract-1", "owner-1"))
    assert len(llm.calls) == 1

    result = run(service.get_summary("contract-1", "owner-1"))
    assert len(llm.calls) == 1  # cache hit, no second call
    assert result["summary"] == "Original summary."


def test_get_summary_force_regenerates_even_when_cached():
    seed_data()
    llm = FakeLLM({"summary": "First version."})
    service = make_service(llm)
    run(service.get_summary("contract-1", "owner-1"))

    llm.payload = {"summary": "Updated version."}
    result = run(service.get_summary("contract-1", "owner-1", force=True))
    assert len(llm.calls) == 2
    assert result["summary"] == "Updated version."


def test_get_summary_rejects_an_unknown_contract():
    seed_data()
    service = make_service()
    try:
        run(service.get_summary("does-not-exist", "owner-1"))
        assert False, "expected ExecutiveSummaryError"
    except ExecutiveSummaryError:
        pass


def test_get_summary_rejects_a_contract_owned_by_someone_else():
    seed_data()
    service = make_service()
    try:
        run(service.get_summary("contract-1", "stranger-1"))
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_get_summary_allows_a_legacy_contract_with_no_owner():
    seed_data()
    service = make_service()
    result = run(service.get_summary("contract-legacy", "anyone-at-all"))
    assert result["risk_score"] == 10.0


def test_get_summary_rejects_a_contract_with_no_current_version():
    seed_data()
    service = make_service()
    try:
        run(service.get_summary("contract-no-version", "owner-1"))
        assert False, "expected ExecutiveSummaryError"
    except ExecutiveSummaryError:
        pass


def test_get_summary_rejects_a_contract_not_yet_analyzed():
    seed_data()
    service = make_service()
    try:
        run(service.get_summary("contract-unanalyzed", "owner-1"))
        assert False, "expected ExecutiveSummaryError"
    except ExecutiveSummaryError:
        pass


def test_get_summary_rejects_an_empty_llm_response():
    seed_data()
    service = make_service(FakeLLM({"summary": "   "}))
    try:
        run(service.get_summary("contract-1", "owner-1"))
        assert False, "expected ExecutiveSummaryError"
    except ExecutiveSummaryError:
        pass
