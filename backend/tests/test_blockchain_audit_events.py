"""Phase 3F: blockchain/evidence-anchoring lifecycle audit events.

Phase 3F audit finding: Ethereum anchoring (services/ethereum_anchor_service.py)
had zero representation in the cross-cutting, org-scoped audit_log
(services/audit.py) used by Phase 3E for the Reviewer/Approver workflow. An
auditor could see that a passport/version existed but had no way to answer,
from the audit trail alone: when anchoring was initiated, when a transaction
was submitted, what transaction, when it was confirmed, which evidence/
version/contract it belongs to, whether it failed, or whether an anchor was
recovered/reused rather than freshly submitted.

This file exercises EthereumAnchorService directly (same fixture style as
the existing tests/lexproof/test_ethereum_anchor_service.py: a MemoryRepository
standing in for Firestore, a FakeBlockchain standing in for the real Web3
client, and object.__new__() to build the service without touching real
settings/network) and proves, for every lifecycle branch Step 1 traced
through anchor_evidence():

  - a brand-new anchor (empty Firestore AND empty chain) emits
    anchor_initiated -> anchor_submitted -> anchor_confirmed, each carrying
    the real evidence_id/contract_id/version_id and (for submitted/confirmed)
    the real transaction_hash and block_number;
  - an anchor that already exists in Firestore (the idempotent early-return
    path) emits anchor_reused ONLY -- never a false anchor_submitted or
    anchor_confirmed, and never triggers a second on-chain transaction;
  - an anchor that already exists on-chain but not in Firestore (the
    distributed-failure recovery path) emits anchor_recovered ONLY -- again
    never a false anchor_submitted, and never triggers a new transaction;
  - a genuine submission failure (no anchor anywhere, chain re-check also
    empty) emits anchor_failed with sanitized error detail, and never a false
    anchor_confirmed, and leaves no anchor persisted.

Fixture note: FakeBlockchain(on_chain_hash=...) seeds the chain as if it
ALREADY has a matching anchor before anchor_evidence() is ever called --
that's what drives the chain-recovery tests. Tests exercising a genuinely
new submission must construct FakeBlockchain() with no seed hash, or they
would silently take the recovery path instead (a bug caught while writing
this file: an early draft accidentally re-seeded several "brand new anchor"
tests this way).

record_audit_event()'s default `repository_factory` parameter is bound to the
real FirestoreRepository at import time (see services/audit.py) -- patching
`ethereum_anchor_service.FirestoreRepository`-style aliases has no effect on
it, because Python binds default argument values once, at function-definition
time, not by name lookup on every call (the same gotcha Phase 3E's
test_redline_audit_events.py documents). So, as in that file, this module
replaces `ethereum_anchor_service.record_audit_event` itself with a thin
wrapper that calls the real function with `repository_factory=FakeRepository`
explicitly injected -- every real code path in services/audit.py still runs,
only the storage backend changes.
"""

from __future__ import annotations

import asyncio

import pytest

import app.lexproof.services.ethereum_anchor_service as ethereum_anchor_service
from app.lexproof.services.ethereum_anchor_service import EthereumAnchorService
from app.lexproof.services.audit import record_audit_event as real_record_audit_event
from app.lexproof.domains.passport.utils.hashing import hash_evidence_item
from tests.fakes import FakeRepository


class MemoryRepository:
    """Same minimal Firestore stand-in used by test_ethereum_anchor_service.py."""

    def __init__(self):
        self.data = {}

    def get(self, document_id):
        return self.data.get(document_id)

    def set(self, document_id, data, merge=False):
        self.data[document_id] = {**self.data.get(document_id, {}), **data} if merge else data

    def delete(self, document_id):
        self.data.pop(document_id, None)


class FakeBlockchain:
    """Same fixture shape as test_ethereum_anchor_service.py, reproduced here
    so this file has no import-order dependency on that module.

    on_chain_hash=None (the default) means the chain starts EMPTY -- a real
    anchor_evidence() call must go through the "submit a new transaction"
    path. Passing a hash simulates the chain already having a confirmed
    anchor for that hash before anchor_evidence() is ever called (used only
    by the chain-recovery test).
    """

    contract_address = "0x0000000000000000000000000000000000000001"

    def __init__(self, on_chain_hash=None):
        self.on_chain_hash = on_chain_hash
        self.anchor_evidence_calls = 0

    def get_anchor_transaction_hash(self, record_id, evidence_hash=None):
        return "0x" + "c" * 64

    def anchor_evidence(self, record_id, evidence_hash):
        self.anchor_evidence_calls += 1
        self.on_chain_hash = evidence_hash.hex()
        return "0x" + "a" * 64, 123, 1700000000

    def get_evidence_anchor(self, record_id):
        if self.on_chain_hash:
            return {
                "evidence_hash": self.on_chain_hash,
                "anchored_at": 1700000000,
                "anchored_by": self.contract_address,
            }
        return None

    def verify_evidence(self, record_id, evidence_hash):
        return self.on_chain_hash == evidence_hash.hex()

    def recover_confirmed_transaction(self, transaction_hash):
        return transaction_hash.lower(), 11566053, 1700000000


class FailingBlockchain(FakeBlockchain):
    """A blockchain client whose submission always fails and which never has
    (before or after) a matching on-chain anchor -- the genuine-failure path,
    as opposed to the transient-failure-then-recovered race handled
    separately by anchor_evidence()'s except block."""

    def anchor_evidence(self, record_id, evidence_hash):
        self.anchor_evidence_calls += 1
        raise RuntimeError("RPC error: nonce too low, sk-should-be-redacted-1234567890")


def make_service(repository, blockchain, evidence_repository=None):
    service = object.__new__(EthereumAnchorService)
    service.repository = repository
    service.evidence_repository = evidence_repository or MemoryRepository()
    service.blockchain = blockchain
    return service


def evidence_record(**overrides):
    record = {
        "evidence_id": "evidence-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Original content",
        "evidence_type": "contract_clause",
        "metadata": {},
        "contract_id": "contract-1",
        "contract_version": 1,
    }
    record.update(overrides)
    return record


@pytest.fixture(autouse=True)
def patch_audit(monkeypatch):
    FakeRepository.stores["audit_log"] = {}

    def fake_record_audit_event(**kwargs):
        return real_record_audit_event(FakeRepository, **kwargs)

    monkeypatch.setattr(ethereum_anchor_service, "record_audit_event", fake_record_audit_event)
    yield


def audit_events():
    return list(FakeRepository.stores.get("audit_log", {}).values())


def audit_actions():
    return [event["action"] for event in audit_events()]


# ---------------------------------------------------------------------------
# 1. Initiation
# ---------------------------------------------------------------------------

def test_anchor_emits_initiation_event_before_anything_else():
    evidence = evidence_record()
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain())
    service.evidence_repository.set("evidence-1", evidence)

    asyncio.run(
        service.anchor_evidence("evidence-1", actor_id="user-1", org_id="org-a", version_id="version-1")
    )

    actions = audit_actions()
    assert "blockchain.anchor_initiated" in actions
    # Initiation is recorded before the transaction is ever submitted.
    assert actions.index("blockchain.anchor_initiated") < actions.index("blockchain.anchor_submitted")


# ---------------------------------------------------------------------------
# 2. Transaction submission
# ---------------------------------------------------------------------------

def test_anchor_emits_submission_event_for_a_brand_new_anchor():
    evidence = evidence_record()
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain())
    service.evidence_repository.set("evidence-1", evidence)

    asyncio.run(service.anchor_evidence("evidence-1"))

    actions = audit_actions()
    assert actions.count("blockchain.anchor_submitted") == 1
    submitted = next(e for e in audit_events() if e["action"] == "blockchain.anchor_submitted")
    assert submitted["resource_id"] == "evidence-1"


# ---------------------------------------------------------------------------
# 3. Confirmation
# ---------------------------------------------------------------------------

def test_anchor_emits_confirmation_event_after_persisting():
    evidence = evidence_record()
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain())
    service.evidence_repository.set("evidence-1", evidence)

    result = asyncio.run(service.anchor_evidence("evidence-1"))

    actions = audit_actions()
    assert actions.count("blockchain.anchor_confirmed") == 1
    # Confirmation is only recorded once the anchor is actually persisted.
    assert repository.get("evidence-1") == result
    assert actions.index("blockchain.anchor_submitted") < actions.index("blockchain.anchor_confirmed")


# ---------------------------------------------------------------------------
# 4. Failure
# ---------------------------------------------------------------------------

def test_anchor_emits_failure_event_on_genuine_submission_failure():
    evidence = evidence_record()
    repository = MemoryRepository()
    service = make_service(repository, FailingBlockchain())
    service.evidence_repository.set("evidence-1", evidence)

    with pytest.raises(RuntimeError):
        asyncio.run(service.anchor_evidence("evidence-1"))

    actions = audit_actions()
    assert actions.count("blockchain.anchor_failed") == 1
    failure = next(e for e in audit_events() if e["action"] == "blockchain.anchor_failed")
    assert "error" in failure["metadata"]
    # sanitize_analysis_error must have redacted the secret-shaped token.
    assert "sk-should-be-redacted" not in failure["metadata"]["error"]
    assert repository.get("evidence-1") is None


# ---------------------------------------------------------------------------
# 5. Idempotency: existing Firestore anchor is reused
# ---------------------------------------------------------------------------

def test_anchor_existing_firestore_anchor_is_idempotent_and_reused():
    evidence = evidence_record()
    repository = MemoryRepository()
    blockchain = FakeBlockchain()
    service = make_service(repository, blockchain)
    service.evidence_repository.set("evidence-1", evidence)

    first = asyncio.run(service.anchor_evidence("evidence-1"))
    assert blockchain.anchor_evidence_calls == 1

    FakeRepository.stores["audit_log"] = {}
    second = asyncio.run(service.anchor_evidence("evidence-1"))

    assert second == first
    assert blockchain.anchor_evidence_calls == 1
    actions = audit_actions()
    assert actions.count("blockchain.anchor_reused") == 1
    assert "blockchain.anchor_submitted" not in actions
    assert "blockchain.anchor_confirmed" not in actions


# ---------------------------------------------------------------------------
# 6. Idempotency: chain-success / Firestore-missing recovery
# ---------------------------------------------------------------------------

def test_anchor_recovers_from_chain_without_resubmitting():
    evidence = evidence_record()
    computed_hash = hash_evidence_item(evidence)
    repository = MemoryRepository()
    # Chain already has the anchor (e.g. a prior submission's Firestore write
    # was lost); nothing has been written to Firestore yet.
    blockchain = FakeBlockchain(computed_hash)
    service = make_service(repository, blockchain)
    service.evidence_repository.set("evidence-1", evidence)

    result = asyncio.run(
        service.anchor_evidence("evidence-1", actor_id="user-1", org_id="org-a", version_id="version-1")
    )

    assert blockchain.anchor_evidence_calls == 0
    assert repository.get("evidence-1") == result
    actions = audit_actions()
    assert actions.count("blockchain.anchor_recovered") == 1
    assert "blockchain.anchor_submitted" not in actions
    recovered = next(e for e in audit_events() if e["action"] == "blockchain.anchor_recovered")
    assert recovered["org_id"] == "org-a"


# ---------------------------------------------------------------------------
# 7. Correct contract_id
# ---------------------------------------------------------------------------

def test_events_carry_correct_contract_id():
    evidence = evidence_record(contract_id="contract-xyz")
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain())
    service.evidence_repository.set("evidence-1", evidence)

    asyncio.run(service.anchor_evidence("evidence-1"))

    events = audit_events()
    assert len(events) > 0
    for event in events:
        assert event["contract_id"] == "contract-xyz"


# ---------------------------------------------------------------------------
# 8. Correct version_id
# ---------------------------------------------------------------------------

def test_events_carry_correct_version_id():
    evidence = evidence_record()
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain())
    service.evidence_repository.set("evidence-1", evidence)

    asyncio.run(service.anchor_evidence("evidence-1", version_id="version-abc"))

    events = audit_events()
    assert len(events) > 0
    for event in events:
        assert event["metadata"]["version_id"] == "version-abc"


# ---------------------------------------------------------------------------
# 9. Correct evidence_id (as resource_id)
# ---------------------------------------------------------------------------

def test_events_carry_correct_evidence_id_as_resource_id():
    evidence = evidence_record(evidence_id="evidence-999", passport_id="passport-999")
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain())
    service.evidence_repository.set("evidence-999", evidence)

    asyncio.run(service.anchor_evidence("evidence-999"))

    events = audit_events()
    assert len(events) > 0
    for event in events:
        assert event["resource_id"] == "evidence-999"
        assert event["resource_type"] == "evidence_anchor"


# ---------------------------------------------------------------------------
# 10. Transaction hash / block number present where available
# ---------------------------------------------------------------------------

def test_confirmed_event_carries_transaction_hash_and_block_number():
    evidence = evidence_record()
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain())
    service.evidence_repository.set("evidence-1", evidence)

    result = asyncio.run(service.anchor_evidence("evidence-1"))

    confirmed = next(e for e in audit_events() if e["action"] == "blockchain.anchor_confirmed")
    assert confirmed["metadata"]["transaction_hash"] == result["transaction_hash"]
    assert confirmed["metadata"]["block_number"] == result["block_number"]
    assert confirmed["metadata"]["transaction_hash"] == "0x" + "a" * 64
    assert confirmed["metadata"]["block_number"] == 123

    # And the initiation event, which precedes submission, correctly has no
    # transaction details yet (they don't exist at that point).
    initiated = next(e for e in audit_events() if e["action"] == "blockchain.anchor_initiated")
    assert "transaction_hash" not in initiated["metadata"]


# ---------------------------------------------------------------------------
# 11. No duplicate transaction submission
# ---------------------------------------------------------------------------

def test_reused_path_does_not_submit_duplicate_transaction():
    evidence = evidence_record()
    repository = MemoryRepository()
    blockchain = FakeBlockchain()
    service = make_service(repository, blockchain)
    service.evidence_repository.set("evidence-1", evidence)

    asyncio.run(service.anchor_evidence("evidence-1"))
    asyncio.run(service.anchor_evidence("evidence-1"))
    asyncio.run(service.anchor_evidence("evidence-1"))

    assert blockchain.anchor_evidence_calls == 1
    assert audit_actions().count("blockchain.anchor_submitted") == 1


# ---------------------------------------------------------------------------
# 12. No false confirmation after failure
# ---------------------------------------------------------------------------

def test_failure_path_does_not_emit_false_confirmation_and_leaves_existing_anchor_intact():
    evidence = evidence_record()
    repository = MemoryRepository()
    blockchain = FakeBlockchain()
    service = make_service(repository, blockchain)
    service.evidence_repository.set("evidence-1", evidence)

    # First anchor succeeds and is confirmed.
    confirmed_result = asyncio.run(service.anchor_evidence("evidence-1"))
    assert audit_actions().count("blockchain.anchor_confirmed") == 1

    # A second, DIFFERENT evidence record's submission then fails genuinely.
    other_evidence = evidence_record(evidence_id="evidence-2", passport_id="passport-2")
    service.evidence_repository.set("evidence-2", other_evidence)
    failing_blockchain = FailingBlockchain()
    service.blockchain = failing_blockchain

    FakeRepository.stores["audit_log"] = {}
    with pytest.raises(RuntimeError):
        asyncio.run(service.anchor_evidence("evidence-2"))

    actions = audit_actions()
    assert "blockchain.anchor_confirmed" not in actions
    assert actions.count("blockchain.anchor_failed") == 1
    # The first evidence's already-confirmed anchor is completely untouched.
    assert repository.get("evidence-1") == confirmed_result
    assert repository.get("evidence-2") is None
