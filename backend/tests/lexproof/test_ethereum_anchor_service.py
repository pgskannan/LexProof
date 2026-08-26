from datetime import datetime, timezone

import pytest

from app.lexproof.services.ethereum_anchor_service import EthereumAnchorService
import app.lexproof.services.ethereum_anchor_service as ethereum_anchor_service
from app.lexproof.domains.passport.utils.hashing import hash_evidence_item
from app.lexproof.api import evidence_anchor as evidence_anchor_api


class MemoryRepository:
    def __init__(self):
        self.data = {}

    def get(self, document_id):
        return self.data.get(document_id)

    def set(self, document_id, data, merge=False):
        self.data[document_id] = {**self.data.get(document_id, {}), **data} if merge else data

    def delete(self, document_id):
        self.data.pop(document_id, None)


class FakeBlockchain:
    contract_address = "0x0000000000000000000000000000000000000001"

    def __init__(self, on_chain_hash):
        self.on_chain_hash = on_chain_hash

    def anchor_evidence(self, record_id, evidence_hash):
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


@pytest.fixture
def evidence_hash():
    return "a" * 64


def make_service(repository, blockchain):
    service = object.__new__(EthereumAnchorService)
    service.repository = repository
    service.evidence_repository = MemoryRepository()
    service.blockchain = blockchain
    return service


def evidence_record():
    return {
        "evidence_id": "evidence-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Original content",
        "evidence_type": "contract_clause",
        "metadata": {},
    }


def test_invalid_hash_rejected(evidence_hash):
    service = make_service(MemoryRepository(), FakeBlockchain(evidence_hash))
    with pytest.raises(ValueError):
        service._validate_evidence_hash("invalid")


def test_anchor_persists_metadata_and_duplicate_is_idempotent(evidence_hash):
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain(evidence_hash))
    evidence = evidence_record()
    service.evidence_repository.set("evidence-1", evidence)
    computed_hash = hash_evidence_item(evidence)
    service.blockchain = FakeBlockchain(computed_hash)

    result = __import__("asyncio").run(
        service.anchor_evidence("evidence-1")
    )

    assert repository.get("evidence-1")["transaction_hash"] == result["transaction_hash"]
    assert repository.get("evidence-1")["evidence_hash"] == computed_hash
    retry = __import__("asyncio").run(service.anchor_evidence("evidence-1"))
    assert retry == result


def test_anchor_rejects_existing_evidence_with_different_hash(evidence_hash):
    repository = MemoryRepository()
    service = make_service(repository, FakeBlockchain(evidence_hash))
    evidence = evidence_record()
    service.evidence_repository.set("evidence-1", evidence)
    service.blockchain = FakeBlockchain(hash_evidence_item(evidence))
    __import__("asyncio").run(service.anchor_evidence("evidence-1"))
    service.evidence_repository.set("evidence-1", {**evidence, "content": "Changed"})

    with pytest.raises(ValueError, match="different Ethereum anchor"):
        __import__("asyncio").run(service.anchor_evidence("evidence-1"))


def test_anchor_requires_existing_evidence(evidence_hash):
    service = make_service(MemoryRepository(), FakeBlockchain(evidence_hash))
    with pytest.raises(ValueError, match="Evidence record not found"):
        __import__("asyncio").run(service.anchor_evidence("evidence-1"))


def test_recover_confirmed_transaction_persists_without_resubmitting(evidence_hash):
    evidence = evidence_record()
    repository = MemoryRepository()
    computed_hash = hash_evidence_item(evidence)
    service = make_service(repository, FakeBlockchain(computed_hash))
    service.evidence_repository.set("evidence-1", evidence)
    transaction_hash = "0x" + "b" * 64

    result = service.recover_anchor_from_transaction("evidence-1", transaction_hash)

    assert result["evidence_id"] == "evidence-1"
    assert result["passport_id"] == "passport-1"
    assert result["transaction_hash"] == transaction_hash
    assert result["block_number"] == 11566053
    assert result["evidence_hash"] == hash_evidence_item(evidence)
    assert repository.get("evidence-1") == result


def test_recover_rejects_existing_anchor_with_different_hash(evidence_hash):
    evidence = evidence_record()
    repository = MemoryRepository()
    computed_hash = hash_evidence_item(evidence)
    service = make_service(repository, FakeBlockchain(computed_hash))
    service.evidence_repository.set("evidence-1", evidence)
    repository.set("evidence-1", {
        "evidence_hash": computed_hash,
        "transaction_hash": "0x" + "b" * 64,
    })
    service.evidence_repository.set("evidence-1", {**evidence, "content": "Changed"})

    with pytest.raises(ValueError, match="different Ethereum anchor"):
        service.recover_anchor_from_transaction("evidence-1", "0x" + "b" * 64)


def test_matching_hash_is_verified(evidence_hash):
    evidence = evidence_record()
    computed_hash = hash_evidence_item(evidence)
    service = make_service(MemoryRepository(), FakeBlockchain(computed_hash))
    service.evidence_repository.set("evidence-1", evidence)
    service.repository.set("evidence-1", {
        "evidence_hash": computed_hash,
        "blockchain_network": "ethereum-sepolia",
        "contract_address": service.blockchain.contract_address,
        "transaction_hash": "0x" + "a" * 64,
        "block_number": 123,
        "anchored_at": datetime.fromtimestamp(1700000000, timezone.utc).isoformat(),
    })

    result = service.verify_evidence("evidence-1")
    assert result["verified"] is True
    assert result["status"] == "VERIFIED"


def test_different_hash_is_tampered(evidence_hash):
    evidence = evidence_record()
    computed_hash = hash_evidence_item(evidence)
    service = make_service(MemoryRepository(), FakeBlockchain(computed_hash))
    service.evidence_repository.set("evidence-1", {**evidence, "content": "Changed content"})
    service.repository.set("evidence-1", {
        "evidence_hash": computed_hash,
        "blockchain_network": "ethereum-sepolia",
        "contract_address": service.blockchain.contract_address,
        "transaction_hash": "0x" + "a" * 64,
        "block_number": 123,
        "anchored_at": datetime.fromtimestamp(1700000000, timezone.utc).isoformat(),
    })

    result = service.verify_evidence("evidence-1")
    assert result["verified"] is False
    assert result["status"] == "TAMPERED"


def test_restored_evidence_is_verified(evidence_hash):
    evidence = evidence_record()
    computed_hash = hash_evidence_item(evidence)
    service = make_service(MemoryRepository(), FakeBlockchain(computed_hash))
    service.evidence_repository.set("evidence-1", evidence)
    service.repository.set("evidence-1", {
        "evidence_hash": computed_hash,
        "blockchain_network": "ethereum-sepolia",
        "contract_address": service.blockchain.contract_address,
        "transaction_hash": "0x" + "a" * 64,
        "block_number": 123,
        "anchored_at": datetime.fromtimestamp(1700000000, timezone.utc).isoformat(),
    })

    result = service.verify_evidence("evidence-1")
    assert result["verified"] is True
    assert result["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_anchor_api_uses_stored_evidence_and_shared_anchor_key(monkeypatch):
    evidence = evidence_record()
    anchor_repository = MemoryRepository()
    service = make_service(anchor_repository, FakeBlockchain(hash_evidence_item(evidence)))
    evidence_repository = MemoryRepository()
    evidence_repository.set("evidence-1", evidence)
    service.evidence_repository = evidence_repository
    monkeypatch.setattr(
        evidence_anchor_api,
        "get_ethereum_anchor_service",
        lambda **kwargs: service,
    )

    request = evidence_anchor_api.EvidenceAnchorRequest(evidence_id="evidence-1")
    result = await evidence_anchor_api.anchor_evidence_to_blockchain(
        "evidence-1", request, object(), anchor_repository, evidence_repository
    )

    assert result.evidence_hash == hash_evidence_item(evidence)
    assert anchor_repository.get("evidence-1")["passport_id"] == "passport-1"
    assert anchor_repository.get("evidence_anchor_evidence-1") is None

    retrieved = await evidence_anchor_api.get_evidence_anchor(
        "evidence-1", object(), anchor_repository
    )
    status = await evidence_anchor_api.get_evidence_anchor_status(
        "evidence-1", object(), anchor_repository
    )
    assert retrieved["evidence_id"] == "evidence-1"
    assert status["anchored"] is True


def test_anchor_request_rejects_client_hash():
    with pytest.raises(ValueError):
        evidence_anchor_api.EvidenceAnchorRequest(
            evidence_id="evidence-1", evidence_hash="a" * 64
        )


def test_cached_service_refreshes_repositories_for_request_order():
    original = ethereum_anchor_service._ethereum_anchor_service
    try:
        cached = make_service(MemoryRepository(), FakeBlockchain("a" * 64))
        ethereum_anchor_service._ethereum_anchor_service = cached
        anchor_repository = MemoryRepository()
        evidence_repository = MemoryRepository()
        result = ethereum_anchor_service.get_ethereum_anchor_service(
            repository=anchor_repository,
            evidence_repository=evidence_repository,
        )
        assert result is cached
        assert result.repository is anchor_repository
        assert result.evidence_repository is evidence_repository
    finally:
        ethereum_anchor_service._ethereum_anchor_service = original


@pytest.mark.asyncio
async def test_anchor_api_reports_missing_evidence(monkeypatch):
    service = make_service(MemoryRepository(), FakeBlockchain("a" * 64))
    monkeypatch.setattr(
        evidence_anchor_api,
        "get_ethereum_anchor_service",
        lambda **kwargs: service,
    )
    with pytest.raises(evidence_anchor_api.HTTPException) as error:
        await evidence_anchor_api.anchor_evidence_to_blockchain(
            "missing", evidence_anchor_api.EvidenceAnchorRequest(evidence_id="missing"),
            object(), service.repository, service.evidence_repository
        )
    assert error.value.status_code == 404


def test_anchor_evidence_recover_from_ethereum_when_firestore_missing(evidence_hash):
    """
    Test recovery when Ethereum anchor succeeds but Firestore persistence fails.
    
    Scenario:
    1. Ethereum anchor succeeds (transaction confirmed)
    2. Firestore persistence fails (simulated by clearing repository)
    3. Client retries anchor_evidence
    4. System discovers existing Ethereum anchor
    5. System recovers and persists metadata
    6. No second Ethereum transaction is submitted
    """
    evidence = evidence_record()
    repository = MemoryRepository()
    computed_hash = hash_evidence_item(evidence)
    
    # Create service with blockchain that will succeed
    blockchain = FakeBlockchain(computed_hash)
    service = make_service(repository, blockchain)
    service.evidence_repository.set("evidence-1", evidence)
    
    # First anchor succeeds on Ethereum
    result = __import__("asyncio").run(service.anchor_evidence("evidence-1"))
    assert result["evidence_hash"] == computed_hash
    assert result["transaction_hash"] == blockchain.on_chain_hash
    
    # Simulate Firestore persistence failure by clearing repository
    repository.data = {}
    
    # Retry anchor - should recover from Ethereum without submitting new transaction
    retry_result = __import__("asyncio").run(service.anchor_evidence("evidence-1"))
    
    # Verify recovery succeeded
    assert retry_result["evidence_id"] == "evidence-1"
    assert retry_result["evidence_hash"] == computed_hash
    assert retry_result["transaction_hash"] == result["transaction_hash"]
    assert retry_result["block_number"] == result["block_number"]
    
    # Verify Firestore was persisted
    assert repository.get("evidence-1") is not None
    assert repository.get("evidence-1")["evidence_hash"] == computed_hash


def test_anchor_evidence_recover_same_hash_from_ethereum(evidence_hash):
    """
    Test recovery when Ethereum contains same evidence ID + same hash.
    
    Scenario:
    1. Ethereum anchor already exists for evidence ID
    2. System attempts to anchor again
    3. System discovers existing Ethereum anchor
    4. System recovers and returns existing proof
    """
    evidence = evidence_record()
    repository = MemoryRepository()
    computed_hash = hash_evidence_item(evidence)
    
    # Create service with blockchain that already has the anchor
    blockchain = FakeBlockchain(computed_hash)
    service = make_service(repository, blockchain)
    service.evidence_repository.set("evidence-1", evidence)
    
    # Attempt to anchor - should recover from Ethereum
    result = __import__("asyncio").run(service.anchor_evidence("evidence-1"))
    
    # Verify recovery succeeded without new transaction
    assert result["evidence_id"] == "evidence-1"
    assert result["evidence_hash"] == computed_hash
    assert result["transaction_hash"] == blockchain.on_chain_hash
    
    # Verify no new transaction was submitted
    assert repository.get("evidence-1")["transaction_hash"] == blockchain.on_chain_hash


def test_anchor_evidence_rejects_conflicting_hash_from_ethereum(evidence_hash):
    """
    Test rejection when Ethereum contains same evidence ID + different hash.
    
    Scenario:
    1. Ethereum anchor exists for evidence ID with hash H1
    2. System attempts to anchor with different hash H2
    3. System discovers conflicting Ethereum anchor
    4. System rejects the operation
    """
    evidence = evidence_record()
    repository = MemoryRepository()
    computed_hash = hash_evidence_item(evidence)
    
    # Create service with blockchain that has different hash
    blockchain = FakeBlockchain("b" * 64)  # Different hash
    service = make_service(repository, blockchain)
    service.evidence_repository.set("evidence-1", evidence)
    
    # Attempt to anchor with different hash - should fail because hash doesn't match
    with pytest.raises(ValueError, match="different Ethereum anchor"):
        __import__("asyncio").run(service.anchor_evidence("evidence-1"))


def test_anchor_evidence_normal_new_anchor_when_no_ethereum_anchor(evidence_hash):
    """
    Test normal new anchor submission when no Ethereum anchor exists.
    
    Scenario:
    1. No Ethereum anchor exists for evidence ID
    2. System attempts to anchor
    3. System submits new Ethereum transaction
    4. System persists metadata
    """
    evidence = evidence_record()
    repository = MemoryRepository()
    computed_hash = hash_evidence_item(evidence)
    
    # Create service with blockchain that has no anchor yet
    blockchain = FakeBlockchain(computed_hash)  # Set initial hash
    service = make_service(repository, blockchain)
    service.evidence_repository.set("evidence-1", evidence)
    
    # Attempt to anchor - should submit new transaction
    result = __import__("asyncio").run(service.anchor_evidence("evidence-1"))
    
    # Verify new transaction was submitted
    assert result["evidence_hash"] == computed_hash
    assert result["transaction_hash"] == blockchain.on_chain_hash
    
    # Verify metadata was persisted
    assert repository.get("evidence-1") is not None
    assert repository.get("evidence-1")["evidence_hash"] == computed_hash
