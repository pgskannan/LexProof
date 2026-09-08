"""Regression tests for the generic tamper demonstration scripts."""

from __future__ import annotations

import sys

import pytest

from app.lexproof.domains.passport.utils.hashing import hash_evidence_item
from scripts import restore_demo_evidence, tamper_demo


class FakeRepository:
    records = {}
    anchors = {}
    set_calls = []

    def __init__(self, collection, settings=None):
        self.collection = collection

    def get(self, document_id):
        store = self.anchors if self.collection == "evidence_anchors" else self.records
        value = store.get(document_id)
        return dict(value) if value else None

    def set(self, document_id, data, merge=False):
        FakeRepository.set_calls.append((self.collection, document_id, dict(data), merge))
        store = self.anchors if self.collection == "evidence_anchors" else self.records
        store[document_id] = {**store[document_id], **data} if merge else dict(data)


class FakeVerifier:
    anchor_calls = 0

    def __init__(self, repository, evidence_repository):
        self.repository = repository
        self.evidence_repository = evidence_repository

    async def verify_evidence(self, evidence_id):
        evidence = self.evidence_repository.get(evidence_id)
        anchor = self.repository.get(evidence_id)
        computed = hash_evidence_item(evidence)
        on_chain = anchor["evidence_hash"] if anchor else None
        verified = bool(on_chain and computed == on_chain)
        return {
            "status": "VERIFIED" if verified else "TAMPERED",
            "computed_hash": computed,
            "evidence_hash_on_chain": on_chain,
        }

    def anchor_evidence(self, evidence_id):
        FakeVerifier.anchor_calls += 1
        raise AssertionError("demo scripts must not anchor evidence")


def seed(value):
    record = {
        "evidence_id": "evd-demo",
        "passport_id": "passport-demo",
        "evidence_type": "clause",
        "title": "Liability cap",
        "content": "The liability cap applies to sensitive health data.",
        "risk_impact": value,
    }
    FakeRepository.records = {"evd-demo": record}
    FakeRepository.anchors = {"evd-demo": {
        "evidence_id": "evd-demo",
        "evidence_hash": hash_evidence_item(record),
        "transaction_hash": "0xtx-demo",
        "block_number": 123,
    }}
    FakeRepository.set_calls = []
    FakeVerifier.anchor_calls = 0


def patch_scripts(monkeypatch):
    monkeypatch.setattr(tamper_demo, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(tamper_demo, "EvidenceAnchorRepository", FakeRepository)
    monkeypatch.setattr(tamper_demo, "get_ethereum_anchor_service", lambda **kwargs: FakeVerifier(kwargs["repository"], kwargs["evidence_repository"]))
    monkeypatch.setattr(restore_demo_evidence, "FirestoreRepository", FakeRepository)
    monkeypatch.setattr(restore_demo_evidence, "EvidenceAnchorRepository", FakeRepository)
    monkeypatch.setattr(
        restore_demo_evidence,
        "get_ethereum_anchor_service",
        lambda **kwargs: FakeVerifier(kwargs["repository"], kwargs["evidence_repository"]),
    )


@pytest.mark.parametrize("original", (90, 95, 40))
def test_tamper_and_restore_support_all_original_values(monkeypatch, capsys, original):
    patch_scripts(monkeypatch)
    seed(original)
    anchor_before = dict(FakeRepository.anchors["evd-demo"])
    monkeypatch.setattr(sys, "argv", ["tamper_demo.py", "evd-demo"])
    tamper_demo.main()
    tamper_output = capsys.readouterr().out
    assert FakeRepository.records["evd-demo"]["risk_impact"] == 5
    assert f"original risk_impact: {original}" in tamper_output
    assert "hashes match: False" in tamper_output
    tampered_hash = hash_evidence_item(FakeRepository.records["evd-demo"])
    monkeypatch.setattr(sys, "argv", ["restore_demo_evidence.py", "evd-demo"])
    restore_demo_evidence.main()
    restore_output = capsys.readouterr().out
    assert FakeRepository.records["evd-demo"]["risk_impact"] == original
    assert "VERIFIED" in restore_output
    assert "ON-CHAIN HASH MATCH" in restore_output
    assert hash_evidence_item(FakeRepository.records["evd-demo"]) == anchor_before["evidence_hash"]
    assert tampered_hash != anchor_before["evidence_hash"]
    assert FakeRepository.anchors["evd-demo"] == anchor_before


def test_repeated_tamper_is_safe(monkeypatch, capsys):
    patch_scripts(monkeypatch)
    seed(95)
    monkeypatch.setattr(sys, "argv", ["tamper_demo.py", "evd-demo"])
    tamper_demo.main()
    FakeRepository.set_calls = []
    tamper_demo.main()
    assert "ALREADY TAMPERED" in capsys.readouterr().out
    assert FakeRepository.set_calls == []


def test_tamper_refuses_unverified_evidence(monkeypatch):
    patch_scripts(monkeypatch)
    seed(40)
    FakeRepository.records["evd-demo"]["title"] = "Changed"
    monkeypatch.setattr(sys, "argv", ["tamper_demo.py", "evd-demo"])
    tamper_demo.main()
    assert FakeRepository.records["evd-demo"]["title"] == "Changed"
    assert FakeRepository.set_calls == []


def test_tamper_writes_only_risk_field(monkeypatch):
    patch_scripts(monkeypatch)
    seed(40)
    monkeypatch.setattr(sys, "argv", ["tamper_demo.py", "evd-demo"])
    tamper_demo.main()
    assert FakeRepository.set_calls == [("evidence_records", "evd-demo", {"risk_impact": 5}, True)]
    assert FakeVerifier.anchor_calls == 0


def test_restore_rejects_wrong_supplied_value(monkeypatch):
    patch_scripts(monkeypatch)
    seed(95)
    monkeypatch.setattr(sys, "argv", ["tamper_demo.py", "evd-demo"])
    tamper_demo.main()
    FakeRepository.set_calls = []
    monkeypatch.setattr(sys, "argv", ["restore_demo_evidence.py", "evd-demo", "90"])
    with pytest.raises(SystemExit, match="does not match"):
        restore_demo_evidence.main()
    assert FakeRepository.set_calls == []


def test_restore_requires_tampered_state(monkeypatch):
    patch_scripts(monkeypatch)
    seed(95)
    monkeypatch.setattr(sys, "argv", ["restore_demo_evidence.py", "evd-demo"])
    with pytest.raises(SystemExit, match="not currently tampered"):
        restore_demo_evidence.main()
    assert FakeRepository.set_calls == []


def test_restore_never_anchors(monkeypatch):
    patch_scripts(monkeypatch)
    seed(95)
    monkeypatch.setattr(sys, "argv", ["tamper_demo.py", "evd-demo"])
    tamper_demo.main()
    monkeypatch.setattr(sys, "argv", ["restore_demo_evidence.py", "evd-demo"])
    restore_demo_evidence.main()
    assert FakeVerifier.anchor_calls == 0


def test_restore_refuses_hash_mismatch_without_writing(monkeypatch):
    patch_scripts(monkeypatch)
    seed(5)
    FakeRepository.anchors["evd-demo"]["evidence_hash"] = "0" * 64
    monkeypatch.setattr(sys, "argv", ["restore_demo_evidence.py", "evd-demo"])
    try:
        restore_demo_evidence.main()
    except SystemExit as error:
        assert "Unable to determine" in str(error)
    else:
        raise AssertionError("restore should refuse an unmatched anchor")
    assert FakeRepository.set_calls == []
