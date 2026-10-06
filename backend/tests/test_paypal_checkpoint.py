import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.lexproof.api.payments import create_contract_payment_checkpoint
from app.lexproof.services.paypal.checkpoint import CHAIN_VERSION, chain_head, coverage, order_receipts
from app.lexproof.services.paypal.checkpoint_service import create_payment_checkpoint
from app.lexproof.services.paypal.obligations import PaymentError
from app.lexproof.services.paypal.public_chain import public_payment_chain, public_receipt_canonical
from app.lexproof.services.paypal.receipts import receipt_hash
from paypal_memory import MemoryRepository


def _receipt(receipt_id: str, created_at: str, receipt_hash: str) -> dict[str, str]:
    return {"id": receipt_id, "created_at": created_at, "receipt_hash": receipt_hash}


def test_chain_head_is_deterministic_and_orders_by_timestamp_then_id():
    receipts = [
        _receipt("b", "2026-10-01T00:00:00Z", "b" * 64),
        _receipt("a", "2026-10-01T00:00:00Z", "a" * 64),
    ]
    expected, count = chain_head("contract-1", order_receipts(receipts))
    assert chain_head("contract-1", list(reversed(receipts))) == (expected, 2)
    assert count == 2
    assert expected != chain_head("contract-2", receipts)[0]
    assert CHAIN_VERSION == "lexproof-payments-v1"


def test_chain_head_is_order_sensitive_and_changes_with_any_receipt():
    first = _receipt("a", "2026-10-01", "a" * 64)
    second = _receipt("b", "2026-10-02", "b" * 64)
    expected, _ = chain_head("contract-1", [first, second])
    changed_first, _ = chain_head("contract-1", [{**first, "receipt_hash": "c" * 64}, second])
    changed_hash, _ = chain_head("contract-1", [first, {**second, "receipt_hash": "c" * 64}])
    changed_order, _ = chain_head("contract-1", [{**second, "created_at": "2026-09-30"}, first])
    assert changed_first != expected
    assert changed_hash != expected
    assert changed_order != expected


def test_coverage_selects_first_anchored_checkpoint_that_covers_each_receipt():
    receipts = [_receipt(str(index), f"2026-10-0{index}", f"{index:x}" * 64) for index in range(1, 5)]
    checkpoints = [
        {"id": "cp-3", "count": 3, "transaction_hash": "0x3"},
        {"id": "cp-pending", "count": 4},
        {"id": "cp-5", "count": 5, "transaction_hash": "0x5"},
    ]
    covered = coverage(receipts, checkpoints)
    assert [covered[str(index)]["id"] for index in range(1, 4)] == ["cp-3"] * 3
    assert covered["4"]["id"] == "cp-5"


def test_checkpoint_writes_evidence_and_calls_existing_anchor_service_once():
    receipts = MemoryRepository()
    receipts.set("receipt-1", {
        "org_id": "org-1", "contract_id": "contract-1", "tool": "send_invoice",
        "decision": "allow", "actor": "owner@example.com", "created_at": "2026-10-01T00:00:00Z",
    })
    checkpoints = MemoryRepository()
    evidence = MemoryRepository()
    passports = MemoryRepository()
    calls = []

    class AnchorService:
        async def anchor_evidence(self, evidence_id, **kwargs):
            calls.append((evidence_id, kwargs))
            return {
                "transaction_hash": "0xconfirmed",
                "block_number": 123,
                "anchored_at": "2026-10-01T00:01:00+00:00",
            }

    result = asyncio.run(create_payment_checkpoint(
        contract_id="contract-1",
        org_id="org-1",
        actor_id="owner-1",
        receipts=receipts,
        checkpoints=checkpoints,
        evidence=evidence,
        passports=passports,
        anchor_service_factory=lambda **kwargs: AnchorService(),
        now=lambda: "2026-10-01T00:00:30+00:00",
    ))

    stored_evidence = evidence.get(result["evidence_id"])
    assert len(calls) == 1
    assert calls[0][0] == result["evidence_id"]
    assert len(evidence.docs) == 1
    assert json.loads(stored_evidence["content"]) == {
        "contract_id": "contract-1",
        "count": 1,
        "last_receipt_id": "receipt-1",
        "chain_head": result["chain_head"],
    }
    assert result["transaction_hash"] == "0xconfirmed"
    assert result["block_number"] == 123
    chain_receipt = {
        **receipts.stream()[0],
        "receipt_hash": receipt_hash(public_receipt_canonical(receipts.stream()[0])),
    }
    assert result["chain_head"] == chain_head("contract-1", [chain_receipt])[0]
    assert checkpoints.get(result["id"]) == result


def test_checkpoint_returns_conflict_when_latest_checkpoint_covers_all_receipts():
    receipts = MemoryRepository()
    receipts.set("receipt-1", {"org_id": "org-1", "contract_id": "contract-1"})
    checkpoints = MemoryRepository()
    checkpoints.set("cp-1", {"org_id": "org-1", "contract_id": "contract-1", "count": 1})
    evidence = MemoryRepository()
    passports = MemoryRepository()
    with pytest.raises(PaymentError) as error:
        asyncio.run(create_payment_checkpoint(
            contract_id="contract-1", org_id="org-1", actor_id="owner-1",
            receipts=receipts, checkpoints=checkpoints, evidence=evidence, passports=passports,
        ))
    assert error.value.status_code == 409


def test_checkpoint_route_returns_409_when_no_new_receipts():
    book = SimpleNamespace(
        obligations=SimpleNamespace(_require_roles=lambda *_: {"org_id": "org-1"}),
        receipts=MemoryRepository(),
        checkpoints=MemoryRepository(),
        settings=None,
    )
    book.obligations.evidence = MemoryRepository()
    book.obligations.passports = MemoryRepository()
    with pytest.raises(HTTPException) as error:
        asyncio.run(create_contract_payment_checkpoint("contract-1", {"uid": "owner-1"}, book))
    assert error.value.status_code == 409


def test_checkpoint_route_rejects_configured_read_only_user(monkeypatch):
    monkeypatch.setenv("LEXPROOF_READ_ONLY_UIDS", "demo-judge-1,demo-judge-2")
    with pytest.raises(HTTPException) as error:
        asyncio.run(create_contract_payment_checkpoint("contract-1", {"uid": "demo-judge-1"}, object()))
    assert error.value.status_code == 403


def test_public_chain_exposes_anchored_checkpoint_and_receipt_coverage():
    passports = MemoryRepository()
    passports.set("payment-contract-1", {"contract_id": "contract-1"})
    receipts = MemoryRepository()
    receipts.set("receipt-1", {
        "org_id": "org-1", "contract_id": "contract-1", "tool": "send_invoice",
        "decision": "allow", "created_at": "2026-10-01T00:00:00Z",
    })
    checkpoints = MemoryRepository()
    checkpoints.set("cp-1", {
        "org_id": "org-1", "contract_id": "contract-1", "count": 1,
        "chain_head": "a" * 64, "transaction_hash": "0xconfirmed", "block_number": 123,
        "anchored_at": "2026-10-01T00:01:00Z",
    })
    chain = public_payment_chain(
        "payment-contract-1", passports=passports, obligations=MemoryRepository(),
        receipts=receipts, settings=MemoryRepository(), checkpoints=checkpoints,
    )
    assert chain["chain_version"] == CHAIN_VERSION
    assert chain["checkpoints"][0]["etherscan_url"] == "https://sepolia.etherscan.io/tx/0xconfirmed"
    assert chain["receipts"][0]["anchor_status"] == "anchored"
    assert chain["receipts"][0]["checkpoint_id"] == "cp-1"
    assert chain["receipts"][0]["anchor_tx"] == "0xconfirmed"