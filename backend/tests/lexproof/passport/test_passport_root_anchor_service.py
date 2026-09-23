"""Unit tests for PassportRootAnchorService (docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md §27).

These mirror the existing fake-object pattern used by
``tests/lexproof/test_ethereum_anchor_service.py`` for the per-evidence-item
anchor service: an in-memory Firestore-shaped repository plus a fake
blockchain client, with the real service constructed via ``object.__new__``
so no real network/Firestore access is required.

Covered per the spec:
  * compute_passport_key golden vectors (independently cross-checked against
    a direct Web3.keccak call, not just against the function under test)
  * passport_root_bytes32 formatting/validation
  * eligibility (PASS/FAIL/UNVERIFIABLE combinations)
  * server authority: only integrity["recomputed_passport_hash"] is ever
    anchored, regardless of anything else the caller-supplied passport_doc
    contains
  * idempotency (Firestore already anchored / chain already anchored, same
    root -> reused, no new transaction)
  * conflict (Firestore or chain already anchored with a DIFFERENT root ->
    hard failure, never silently overwritten)
  * recovery playbook (submission races with a concurrent winner; receipt
    succeeds but enrichment/lookup fails; genuine failure still propagates)
  * verify_passport_root_status's full anchor_status state machine (PASS,
    FAIL, UNVERIFIABLE, NOT_ANCHORED, INVALID_PROOF, NETWORK_ERROR,
    CHAIN_MISMATCH) and that local integrity is NEVER promoted by chain state
  * public_root_existence (existence-only, no confidential snapshot)
  * configuration failure (missing ETHEREUM_PASSPORT_REGISTRY_ADDRESS)
"""

from __future__ import annotations

import asyncio

import pytest
from web3 import Web3

import app.lexproof.services.passport_root_anchor_service as passport_root_anchor_service
from app.lexproof.domains.passport.integrity import FAIL, PASS, UNVERIFIABLE
from app.lexproof.domains.passport.utils.hashing import (
    compute_passport_key,
    passport_root_bytes32,
)
from app.lexproof.services.passport_blockchain import create_passport_blockchain_service
from app.lexproof.services.passport_root_anchor_service import (
    PassportEligibilityError,
    PassportRootAnchorService,
    PassportRootConflictError,
    get_passport_root_anchor_service,
    passport_root_eligibility,
)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Golden vectors: compute_passport_key
# ---------------------------------------------------------------------------

GOLDEN_VECTORS = {
    "11111111-1111-4111-8111-111111111111": "31e5891f6803041a37cfae842c5bf47aa89df5130d6a8ba235cdd9041744763f",
    "a1b2c3d4-e5f6-4789-9abc-def012345678": "e74ec87633f8add186ec9c983897f821c715d43c910151b367e8329964fe43e4"[:64],
}


@pytest.mark.parametrize("passport_id, expected", GOLDEN_VECTORS.items())
def test_compute_passport_key_golden_vector(passport_id, expected):
    key = compute_passport_key(passport_id)
    assert key == expected
    assert len(key) == 64
    # Independently cross-checked against a direct keccak256(UTF-8(...)) call
    # made in this test, not routed back through compute_passport_key itself.
    assert key == Web3.keccak(text=passport_id).hex().removeprefix("0x").lower()


def test_compute_passport_key_rejects_empty_or_non_string():
    with pytest.raises(ValueError):
        compute_passport_key("")
    with pytest.raises(ValueError):
        compute_passport_key(None)  # type: ignore[arg-type]


def test_passport_root_bytes32_round_trips_and_validates_length():
    passport_hash = "ab" * 32
    root = passport_root_bytes32(passport_hash)
    assert root == bytes.fromhex(passport_hash)
    assert passport_root_bytes32("0x" + passport_hash) == root

    with pytest.raises(ValueError):
        passport_root_bytes32("not-hex-and-too-short")


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def integrity(
    *,
    document_status=PASS,
    policy_status=PASS,
    analysis_status=PASS,
    evidence_status=PASS,
    passport_hash_status=PASS,
    recomputed_passport_hash="a" * 64,
):
    return {
        "document_status": document_status,
        "policy_status": policy_status,
        "analysis_status": analysis_status,
        "evidence_status": evidence_status,
        "passport_hash_status": passport_hash_status,
        "recomputed_passport_hash": recomputed_passport_hash,
    }


def test_eligibility_all_pass():
    eligible, reasons = passport_root_eligibility(integrity())
    assert eligible is True
    assert reasons == []


def test_eligibility_fails_on_single_unverifiable_component():
    eligible, reasons = passport_root_eligibility(integrity(evidence_status=UNVERIFIABLE))
    assert eligible is False
    assert reasons == ["evidence_status=UNVERIFIABLE"]


def test_eligibility_fails_on_single_fail_component():
    eligible, reasons = passport_root_eligibility(integrity(analysis_status=FAIL))
    assert eligible is False
    assert reasons == ["analysis_status=FAIL"]


def test_eligibility_reports_every_failing_component():
    eligible, reasons = passport_root_eligibility(
        integrity(document_status=FAIL, policy_status=UNVERIFIABLE)
    )
    assert eligible is False
    assert reasons == ["document_status=FAIL", "policy_status=UNVERIFIABLE"]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class MemoryAnchorRepository:
    """Mirrors PassportAnchorRepository's create-once semantics in-memory."""

    def __init__(self):
        self.data = {}

    def get(self, document_id):
        return self.data.get(document_id)

    def set(self, document_id, data, merge=False):
        if self.get(document_id):
            raise ValueError(f"Passport root anchor already exists: {document_id}")
        self.data[document_id] = data

    def delete(self, document_id):
        raise ValueError("Passport root anchors cannot be deleted")


class FakePassportBlockchain:
    contract_address = "0x0000000000000000000000000000000000000002"
    chain_id = 11155111

    def __init__(self, on_chain=None):
        # on_chain: None, or {"passport_root": <hex, no 0x>, "anchored_at": int, "anchored_by": addr}
        self.on_chain = on_chain
        self.anchor_calls = 0

    def anchor_passport_root(self, passport_key, passport_root):
        self.anchor_calls += 1
        self.on_chain = {
            "passport_root": passport_root.hex(),
            "anchored_at": 1700000000,
            "anchored_by": self.contract_address,
        }
        return "0x" + "a" * 64, 555, 1700000000

    def get_passport_root(self, passport_key):
        return dict(self.on_chain) if self.on_chain else None

    def verify_passport_root(self, passport_key, passport_root):
        if not self.on_chain:
            return False
        return self.on_chain["passport_root"] == passport_root.hex()

    def get_anchor_transaction_hash(self, passport_key, passport_root_hex=None):
        return "0x" + "c" * 64

    def recover_confirmed_transaction(self, transaction_hash):
        return transaction_hash.lower(), 777, 1700000111


def make_service(repository, blockchain):
    service = object.__new__(PassportRootAnchorService)
    service.settings = None
    service.repository = repository
    service._blockchain = blockchain
    return service


PASSPORT_ID = "passport-1"
PASSPORT_HASH = "aa" * 32


def passport_doc(**overrides):
    doc = {
        "contract_id": "contract-1",
        # A client-controlled document may contain ANY hash-shaped field here
        # (e.g. a stale/legacy or outright spoofed one) -- the service must
        # never read it; only integrity["recomputed_passport_hash"] governs
        # what gets anchored.
        "metadata": {"passport_hash": "ff" * 32},
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# anchor_passport_root: eligibility gating
# ---------------------------------------------------------------------------


def test_anchor_rejects_ineligible_passport_without_touching_chain_or_repository():
    repository = MemoryAnchorRepository()
    blockchain = FakePassportBlockchain()
    service = make_service(repository, blockchain)

    with pytest.raises(PassportEligibilityError):
        run(
            service.anchor_passport_root(
                PASSPORT_ID, passport_doc(), integrity(evidence_status=UNVERIFIABLE)
            )
        )

    assert repository.data == {}
    assert blockchain.anchor_calls == 0


def test_anchor_rejects_invalid_passport_id():
    repository = MemoryAnchorRepository()
    blockchain = FakePassportBlockchain()
    service = make_service(repository, blockchain)

    with pytest.raises(ValueError):
        run(service.anchor_passport_root("", passport_doc(), integrity()))
    with pytest.raises(ValueError):
        run(service.anchor_passport_root("x" * 257, passport_doc(), integrity()))

    assert repository.data == {}
    assert blockchain.anchor_calls == 0


# ---------------------------------------------------------------------------
# anchor_passport_root: server authority (never trust client-supplied hash)
# ---------------------------------------------------------------------------


def test_anchor_uses_only_server_recomputed_hash_never_client_document_fields():
    repository = MemoryAnchorRepository()
    blockchain = FakePassportBlockchain()
    service = make_service(repository, blockchain)

    result = run(
        service.anchor_passport_root(
            PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )

    assert result["passport_hash"] == PASSPORT_HASH
    # The spoofed "ff"*32 hash living on passport_doc["metadata"] must never
    # reach the chain or Firestore.
    assert blockchain.on_chain["passport_root"] == PASSPORT_HASH
    assert repository.get(PASSPORT_ID)["passport_hash"] == PASSPORT_HASH


# ---------------------------------------------------------------------------
# anchor_passport_root: idempotency / conflict
# ---------------------------------------------------------------------------


def test_anchor_is_idempotent_when_firestore_already_has_matching_anchor():
    repository = MemoryAnchorRepository()
    existing = {
        "passport_id": PASSPORT_ID,
        "passport_hash": PASSPORT_HASH,
        "transaction_hash": "0x" + "b" * 64,
        "block_number": 42,
    }
    repository.data[PASSPORT_ID] = existing
    blockchain = FakePassportBlockchain()
    service = make_service(repository, blockchain)

    result = run(
        service.anchor_passport_root(
            PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )

    assert result == existing
    assert blockchain.anchor_calls == 0


def test_anchor_conflicts_when_firestore_has_a_different_anchored_root():
    repository = MemoryAnchorRepository()
    repository.data[PASSPORT_ID] = {
        "passport_id": PASSPORT_ID,
        "passport_hash": "bb" * 32,
    }
    blockchain = FakePassportBlockchain()
    service = make_service(repository, blockchain)

    with pytest.raises(PassportRootConflictError):
        run(
            service.anchor_passport_root(
                PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
            )
        )
    assert blockchain.anchor_calls == 0


def test_anchor_recovers_from_chain_when_matching_root_already_anchored_onchain():
    repository = MemoryAnchorRepository()
    key_bytes = bytes.fromhex(compute_passport_key(PASSPORT_ID))
    blockchain = FakePassportBlockchain(
        on_chain={"passport_root": PASSPORT_HASH, "anchored_at": 1700000000, "anchored_by": "0xabc"}
    )
    service = make_service(repository, blockchain)

    result = run(
        service.anchor_passport_root(
            PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )

    assert blockchain.anchor_calls == 0  # no new transaction submitted
    assert result["passport_hash"] == PASSPORT_HASH
    assert result["transaction_hash"] == "0x" + "c" * 64  # from get_anchor_transaction_hash/recover
    assert result["block_number"] == 777
    assert repository.get(PASSPORT_ID) == result
    del key_bytes  # only used to document what key would be looked up


def test_anchor_conflicts_when_chain_already_has_a_different_root():
    repository = MemoryAnchorRepository()
    blockchain = FakePassportBlockchain(
        on_chain={"passport_root": "bb" * 32, "anchored_at": 1700000000, "anchored_by": "0xabc"}
    )
    service = make_service(repository, blockchain)

    with pytest.raises(PassportRootConflictError):
        run(
            service.anchor_passport_root(
                PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
            )
        )
    assert blockchain.anchor_calls == 0
    assert repository.data == {}


def test_anchor_recovery_persists_even_when_enrichment_lookup_fails():
    """Receipt-equivalent on-chain data exists, but resolving the exact
    transaction hash/block via event-log lookup fails -- the anchor must
    still be recorded (with transaction_hash/block_number left None) rather
    than the whole recovery failing."""
    repository = MemoryAnchorRepository()

    class NoEventLogBlockchain(FakePassportBlockchain):
        def get_anchor_transaction_hash(self, passport_key, passport_root_hex=None):
            raise RuntimeError("No PassportRootAnchored transaction found")

    blockchain = NoEventLogBlockchain(
        on_chain={"passport_root": PASSPORT_HASH, "anchored_at": 1700000000, "anchored_by": "0xabc"}
    )
    service = make_service(repository, blockchain)

    result = run(
        service.anchor_passport_root(
            PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )

    assert result["transaction_hash"] is None
    assert result["block_number"] is None
    assert repository.get(PASSPORT_ID)["passport_hash"] == PASSPORT_HASH


# ---------------------------------------------------------------------------
# anchor_passport_root: new anchor + race recovery
# ---------------------------------------------------------------------------


def test_anchor_submits_new_transaction_and_persists_full_record_when_nothing_exists():
    repository = MemoryAnchorRepository()
    blockchain = FakePassportBlockchain()
    service = make_service(repository, blockchain)

    result = run(
        service.anchor_passport_root(
            PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )

    assert blockchain.anchor_calls == 1
    assert result["passport_id"] == PASSPORT_ID
    assert result["passport_hash"] == PASSPORT_HASH
    assert result["passport_key"] == compute_passport_key(PASSPORT_ID)
    assert result["transaction_hash"] == "0x" + "a" * 64
    assert result["block_number"] == 555
    assert result["blockchain_network"] == "ethereum-sepolia"
    assert result["contract_address"] == blockchain.contract_address
    assert result["chain_id"] == 11155111
    assert result["canonicalization_version"] == 1
    assert result["hash_algorithm"] == "sha256"
    assert repository.get(PASSPORT_ID) == result


class RacingPassportBlockchain(FakePassportBlockchain):
    """A concurrent caller's anchor for the SAME passport_key lands first;
    our own submission reverts, but the anchor is recoverable afterward."""

    def anchor_passport_root(self, passport_key, passport_root):
        self.on_chain = {
            "passport_root": passport_root.hex(),
            "anchored_at": 1700000000,
            "anchored_by": "0xconcurrent",
        }
        raise ValueError("Passport root anchor transaction reverted: 0x" + "d" * 64)


def test_anchor_recovers_from_concurrent_race_on_submit_failure():
    repository = MemoryAnchorRepository()
    blockchain = RacingPassportBlockchain()
    service = make_service(repository, blockchain)

    result = run(
        service.anchor_passport_root(
            PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )

    assert result["passport_hash"] == PASSPORT_HASH
    assert repository.get(PASSPORT_ID)["passport_hash"] == PASSPORT_HASH


class AlwaysFailingPassportBlockchain(FakePassportBlockchain):
    def anchor_passport_root(self, passport_key, passport_root):
        raise ValueError("Passport root anchor transaction reverted: 0x" + "d" * 64)


def test_anchor_still_raises_when_submit_fails_and_nothing_recoverable():
    repository = MemoryAnchorRepository()
    blockchain = AlwaysFailingPassportBlockchain()
    service = make_service(repository, blockchain)

    with pytest.raises(ValueError, match="reverted"):
        run(
            service.anchor_passport_root(
                PASSPORT_ID, passport_doc(), integrity(recomputed_passport_hash=PASSPORT_HASH)
            )
        )
    assert repository.data == {}


# ---------------------------------------------------------------------------
# verify_passport_root_status: local-integrity-first state machine
# ---------------------------------------------------------------------------


def test_verify_status_reports_fail_when_any_component_failed():
    service = make_service(MemoryAnchorRepository(), FakePassportBlockchain())
    result = run(
        service.verify_passport_root_status(PASSPORT_ID, integrity(document_status=FAIL))
    )
    assert result["anchor_status"] == FAIL
    assert result["anchor_ineligible_reasons"] == ["document_status=FAIL"]


def test_verify_status_reports_unverifiable_when_no_component_failed_but_one_unverifiable():
    service = make_service(MemoryAnchorRepository(), FakePassportBlockchain())
    result = run(
        service.verify_passport_root_status(PASSPORT_ID, integrity(evidence_status=UNVERIFIABLE))
    )
    assert result["anchor_status"] == UNVERIFIABLE


def test_verify_status_unverifiable_is_never_promoted_to_pass_by_chain_state():
    """Even if a root happens to exist on-chain for this passport_key, an
    UNVERIFIABLE local integrity result must never become PASS."""
    blockchain = FakePassportBlockchain(
        on_chain={"passport_root": PASSPORT_HASH, "anchored_at": 1700000000, "anchored_by": "0xabc"}
    )
    service = make_service(MemoryAnchorRepository(), blockchain)
    result = run(
        service.verify_passport_root_status(
            PASSPORT_ID, integrity(evidence_status=UNVERIFIABLE, recomputed_passport_hash=PASSPORT_HASH)
        )
    )
    assert result["anchor_status"] == UNVERIFIABLE


def test_verify_status_not_anchored_when_eligible_but_nothing_onchain():
    service = make_service(MemoryAnchorRepository(), FakePassportBlockchain(on_chain=None))
    result = run(
        service.verify_passport_root_status(
            PASSPORT_ID, integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )
    assert result["anchor_status"] == "NOT_ANCHORED"


def test_verify_status_pass_when_onchain_root_matches_and_fills_persisted_tx_metadata():
    repository = MemoryAnchorRepository()
    repository.data[PASSPORT_ID] = {
        "transaction_hash": "0x" + "e" * 64,
        "block_number": 321,
    }
    blockchain = FakePassportBlockchain(
        on_chain={"passport_root": PASSPORT_HASH, "anchored_at": 1700000000, "anchored_by": "0xabc"}
    )
    service = make_service(repository, blockchain)

    result = run(
        service.verify_passport_root_status(
            PASSPORT_ID, integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )

    assert result["anchor_status"] == PASS
    assert result["on_chain_root"] == PASSPORT_HASH
    assert result["blockchain_network"] == "ethereum-sepolia"
    assert result["contract_address"] == blockchain.contract_address
    assert result["chain_id"] == 11155111
    assert result["transaction_hash"] == "0x" + "e" * 64
    assert result["block_number"] == 321


def test_verify_status_invalid_proof_when_onchain_root_does_not_match():
    blockchain = FakePassportBlockchain(
        on_chain={"passport_root": "bb" * 32, "anchored_at": 1700000000, "anchored_by": "0xabc"}
    )
    service = make_service(MemoryAnchorRepository(), blockchain)

    result = run(
        service.verify_passport_root_status(
            PASSPORT_ID, integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )
    assert result["anchor_status"] == "INVALID_PROOF"


def test_verify_status_network_error_when_blockchain_unavailable(monkeypatch):
    def failing_factory():
        raise ValueError("ETHEREUM_PASSPORT_REGISTRY_ADDRESS is not configured")

    monkeypatch.setattr(passport_root_anchor_service, "create_passport_blockchain_service", failing_factory)
    service = make_service(MemoryAnchorRepository(), None)

    result = run(
        service.verify_passport_root_status(
            PASSPORT_ID, integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )
    assert result["anchor_status"] == "NETWORK_ERROR"
    assert "anchor_error" in result


def test_verify_status_network_error_on_connection_error():
    class UnreachableBlockchain(FakePassportBlockchain):
        def get_passport_root(self, passport_key):
            raise ConnectionError("Failed to connect to Ethereum RPC")

    service = make_service(MemoryAnchorRepository(), UnreachableBlockchain())
    result = run(
        service.verify_passport_root_status(
            PASSPORT_ID, integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )
    assert result["anchor_status"] == "NETWORK_ERROR"


def test_verify_status_chain_mismatch_on_wrong_network_error():
    class WrongNetworkBlockchain(FakePassportBlockchain):
        def get_passport_root(self, passport_key):
            raise ValueError("Wrong network! Expected Sepolia (11155111), got chain_id=1")

    service = make_service(MemoryAnchorRepository(), WrongNetworkBlockchain())
    result = run(
        service.verify_passport_root_status(
            PASSPORT_ID, integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )
    assert result["anchor_status"] == "CHAIN_MISMATCH"


def test_verify_status_network_error_on_generic_value_error():
    class OddErrorBlockchain(FakePassportBlockchain):
        def get_passport_root(self, passport_key):
            raise ValueError("some other RPC problem")

    service = make_service(MemoryAnchorRepository(), OddErrorBlockchain())
    result = run(
        service.verify_passport_root_status(
            PASSPORT_ID, integrity(recomputed_passport_hash=PASSPORT_HASH)
        )
    )
    assert result["anchor_status"] == "NETWORK_ERROR"


# ---------------------------------------------------------------------------
# public_root_existence: existence-only, unauthenticated-safe
# ---------------------------------------------------------------------------


def test_public_root_existence_invalid_hash_format():
    service = make_service(MemoryAnchorRepository(), FakePassportBlockchain())
    result = run(service.public_root_existence(PASSPORT_ID, "not-a-valid-hash"))
    assert result["exists"] is False
    assert result["status"] == "INVALID_INPUT"
    # No blockchain fields leak through on a pure input-validation failure.
    assert "blockchain_network" not in result


def test_public_root_existence_anchored_true():
    blockchain = FakePassportBlockchain(
        on_chain={"passport_root": PASSPORT_HASH, "anchored_at": 1700000000, "anchored_by": "0xabc"}
    )
    service = make_service(MemoryAnchorRepository(), blockchain)
    result = run(service.public_root_existence(PASSPORT_ID, PASSPORT_HASH))
    assert result["exists"] is True
    assert result["status"] == "ANCHORED"
    assert result["passport_key"] == compute_passport_key(PASSPORT_ID)


def test_public_root_existence_not_anchored_false():
    service = make_service(MemoryAnchorRepository(), FakePassportBlockchain(on_chain=None))
    result = run(service.public_root_existence(PASSPORT_ID, PASSPORT_HASH))
    assert result["exists"] is False
    assert result["status"] == "NOT_ANCHORED"


def test_public_root_existence_never_exposes_confidential_snapshot_fields():
    """The public endpoint's own service method must not be able to leak
    anything beyond existence + chain plumbing -- no document/analysis/
    evidence status fields of any kind."""
    blockchain = FakePassportBlockchain(
        on_chain={"passport_root": PASSPORT_HASH, "anchored_at": 1700000000, "anchored_by": "0xabc"}
    )
    service = make_service(MemoryAnchorRepository(), blockchain)
    result = run(service.public_root_existence(PASSPORT_ID, PASSPORT_HASH))
    forbidden_keys = {
        "document_status", "policy_status", "analysis_status",
        "evidence_status", "passport_hash_status", "recomputed_passport_hash",
    }
    assert forbidden_keys.isdisjoint(result.keys())


def test_public_root_existence_network_error_when_blockchain_unavailable(monkeypatch):
    def failing_factory():
        raise ValueError("ETHEREUM_PASSPORT_REGISTRY_ADDRESS is not configured")

    monkeypatch.setattr(passport_root_anchor_service, "create_passport_blockchain_service", failing_factory)
    service = make_service(MemoryAnchorRepository(), None)
    result = run(service.public_root_existence(PASSPORT_ID, PASSPORT_HASH))
    assert result["exists"] is False
    assert result["status"] == "NETWORK_ERROR"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_create_passport_blockchain_service_requires_registry_address(monkeypatch):
    # create_passport_blockchain_service() imports get_settings LOCALLY
    # (``from ..config import get_settings``) rather than at module scope, so
    # the patch target is the defining module, app.lexproof.config, not
    # app.lexproof.services.passport_blockchain.
    import app.lexproof.config as config_module

    class StubSettings:
        ethereum_rpc_url = "https://example-rpc.invalid"
        passport_registry_address = None

        class _Secret:
            def get_secret_value(self):
                return "0x" + "1" * 64

        blockchain_private_key = _Secret()

    monkeypatch.setattr(config_module, "get_settings", lambda: StubSettings())

    with pytest.raises(ValueError, match="ETHEREUM_PASSPORT_REGISTRY_ADDRESS"):
        create_passport_blockchain_service()


# ---------------------------------------------------------------------------
# Lazy blockchain construction + singleton accessor
# ---------------------------------------------------------------------------


def test_blockchain_is_not_constructed_eagerly_for_an_ineligible_passport(monkeypatch):
    """Checking eligibility for an UNVERIFIABLE/FAIL passport must never
    require a working chain connection -- the blockchain client is built
    lazily and only on first real chain use."""

    def explode():
        raise AssertionError("blockchain must not be constructed for an ineligible passport")

    monkeypatch.setattr(passport_root_anchor_service, "create_passport_blockchain_service", explode)
    service = make_service(MemoryAnchorRepository(), None)

    with pytest.raises(PassportEligibilityError):
        run(
            service.anchor_passport_root(
                PASSPORT_ID, passport_doc(), integrity(evidence_status=UNVERIFIABLE)
            )
        )


def test_get_passport_root_anchor_service_singleton_refreshes_repository():
    original = passport_root_anchor_service._passport_root_anchor_service
    try:
        cached = make_service(MemoryAnchorRepository(), FakePassportBlockchain())
        passport_root_anchor_service._passport_root_anchor_service = cached
        new_repository = MemoryAnchorRepository()
        result = get_passport_root_anchor_service(repository=new_repository)
        assert result is cached
        assert result.repository is new_repository
    finally:
        passport_root_anchor_service._passport_root_anchor_service = original
