from datetime import date, timedelta

import pytest

from app.lexproof.services.paypal.obligations import assess_extracted_obligation
from scripts.seed_alexa_demo import (
    ORG_ID,
    apply_synthetic_removal,
    build_attach_plan,
    extract_verified_payment_candidates,
    plan_synthetic_removal,
    synthetic_record_ids,
)
from tests.fakes import FakeRepository


def _contract(contract_id: str, name: str, version_id: str) -> dict:
    return {"id": contract_id, "org_id": ORG_ID, "name": name, "current_version_id": version_id}


def test_attach_plan_picks_msa_by_name_and_quotes_real_document_verbatim():
    today = date(2026, 10, 12)
    acme = _contract("acme", "Acme Master Services Agreement", "v-acme")
    globex = _contract("globex", "Globex Services Agreement", "v-globex")
    versions = {
        "v-acme": {
            "id": "v-acme",
            "analysis_status": "complete",
            "content_hash": "acme-hash",
            "document_text": "MASTER SERVICES AGREEMENT. Monthly fee is USD 12,500, payable within thirty days. Support fee USD 4,000 is due quarterly.",
        },
        "v-globex": {
            "id": "v-globex",
            "analysis_status": "complete",
            "content_hash": "globex-hash",
            "document_text": "SUBSCRIPTION AGREEMENT. Renewal fee is USD 8,250 payable on the anniversary date.",
        },
    }

    plan = build_attach_plan([globex, acme], versions, "owner", "judge", today=today)

    assert plan["workflows"][0]["instance"]["entity_id"] == "acme"
    assert plan["workflows"][1]["instance"]["entity_id"] == "globex"
    assert len(plan["obligations"]) == 3
    for obligation in plan["obligations"]:
        text = versions[obligation["contract_version_id"]]["document_text"]
        assert obligation["clause_quote"] in text
        assessed = assess_extracted_obligation(text, {
            "label": obligation["label"],
            "amount": obligation["amount"],
            "currency": obligation["currency"],
            "clause_quote": obligation["clause_quote"],
        })
        assert assessed["needs_review_reason"] is None
    assert plan["obligations"][0]["due_date"] == (today - timedelta(days=2)).isoformat()
    assert all(workflow["instance"]["created_by"] == "judge" for workflow in plan["workflows"])


def test_attach_fails_clearly_with_fewer_than_two_analyzed_contracts():
    one_contract = _contract("acme", "Acme Master Services Agreement", "v-acme")
    with pytest.raises(ValueError, match="Upload and analyze contracts in LexProof Alexa Demo first"):
        build_attach_plan([one_contract], {"v-acme": {"analysis_status": "complete"}}, "owner", "judge")


def test_payment_candidate_amount_and_quote_are_extracted_from_source_text():
    contract = _contract("acme", "Acme Master Services Agreement", "v-acme")
    body = "Customer will pay USD 12,500 per month within thirty days of invoice."
    candidates = extract_verified_payment_candidates(
        [contract],
        {"v-acme": {"id": "v-acme", "document_text": body}},
    )
    assert len(candidates) == 1
    assert candidates[0]["amount"] == "12500"
    assert candidates[0]["quote"] in body


def test_remove_synthetic_only_targets_deterministic_ids_in_alexa_org():
    FakeRepository.stores = {}
    repos = {collection: FakeRepository(collection) for collection in synthetic_record_ids()}
    repos["workflow_history_factory"] = lambda instance_id: FakeRepository(f"workflow_instances/{instance_id}/history")
    contract_id = synthetic_record_ids()["contracts"][0]
    other_id = "ordinary-contract"
    repos["contracts"].set(contract_id, {"org_id": ORG_ID, "name": "old synthetic"})
    repos["contracts"].set(other_id, {"org_id": ORG_ID, "name": "keep this"})
    foreign_seed_id = synthetic_record_ids()["contract_versions"][0]
    repos["contract_versions"].set(foreign_seed_id, {"org_id": "another-org"})
    workflow_id = synthetic_record_ids()["workflow_instances"][0]
    repos["workflow_instances"].set(workflow_id, {"org_id": ORG_ID})
    repos["workflow_instances"].set("ordinary-workflow", {"org_id": ORG_ID})
    history = repos["workflow_history_factory"](workflow_id)
    history.set("event-1", {"action": "seed event"})
    anchors = FakeRepository("passport_anchors")
    passport_id = synthetic_record_ids()["legal_passports"][0]
    anchors.set(passport_id, {"org_id": ORG_ID, "transaction_hash": "0xkeep"})

    plan = plan_synthetic_removal(repos)
    assert plan["contracts"] == [contract_id]
    assert plan["contract_versions"] == []
    assert plan["workflow_instances"] == [workflow_id]

    removed = apply_synthetic_removal(repos, plan)

    assert removed["contracts"] == [contract_id]
    assert repos["contracts"].get(other_id) is not None
    assert repos["contract_versions"].get(foreign_seed_id) is not None
    assert repos["workflow_instances"].get("ordinary-workflow") is not None
    assert history.get("event-1") is None
    assert anchors.get(passport_id)["transaction_hash"] == "0xkeep"
