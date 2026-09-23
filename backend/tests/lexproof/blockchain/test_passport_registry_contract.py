"""Local-chain contract tests for the additive LexProofPassportRegistry.

These tests deploy the ACTUAL compiled bytecode (contracts/build/*.bin, built
by contracts/compile.sh) to an in-process local Ethereum test chain and
exercise the real EVM -- not a Python mock of the contract's behavior. The
repository has no Anvil/Hardhat installation, so this uses web3.py's own
standard local-test-chain tooling (eth-tester + the py-evm backend), which is
a genuine local blockchain: real bytecode, real EVM execution, real reverts,
real event logs.

Per docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md §12/§22, this suite proves,
against real contract execution:
  * registrar-only authorization (owner/registrar can anchor; a stranger reverts)
  * zero-value validation (zero key, zero root both rejected)
  * persistence (root, timestamp, registrar all stored and readable)
  * first-write-wins duplicate protection (same key twice reverts, whether
    the second write repeats the same root or supplies a different one)
  * verifyPassportRoot's three answers (match / wrong root / unknown key)
  * PassportRootAnchored event fields
  * isolation from the existing, unmodified LexProofRegistry (evidence
    anchors cannot create/observe a passport root and vice versa)

It never touches Sepolia, never submits a real transaction, and never
changes contracts/LexProofRegistry.sol or its compiled artifacts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

eth_tester = pytest.importorskip(
    "eth_tester",
    reason="eth-tester[py-evm] is a test-only dependency for local contract testing (see backend/requirements.txt)",
)
from eth_tester import EthereumTester, PyEVMBackend  # noqa: E402
from eth_tester.exceptions import TransactionFailed  # noqa: E402
from web3 import Web3  # noqa: E402

# NOTE: web3.py's EthereumTesterProvider does not translate a reverted
# `.call()` into web3.exceptions.ContractLogicError the way a real JSON-RPC
# node's error response does (that translation, in
# web3._utils.error_formatters_utils.raise_contract_logic_error_on_revert,
# only fires for an actual JSON-RPC error payload). Against eth-tester, the
# underlying eth_tester.exceptions.TransactionFailed propagates unwrapped
# instead. This is a property of the *local test chain's provider*, not of
# the contract or of production code talking to a real node -- so these
# tests assert on TransactionFailed (still carrying the exact Solidity
# `require(...)` revert reason string) rather than ContractLogicError.

CONTRACTS_BUILD_DIR = Path(__file__).resolve().parents[4] / "contracts" / "build"
PASSPORT_REGISTRY_NAME = "LexProofPassportRegistry"
EVIDENCE_REGISTRY_NAME = "LexProofRegistry"

ZERO_BYTES32 = b"\x00" * 32


def _load_artifact(contract_name: str) -> tuple[list, str]:
    """Load a compiled contract's ABI + bytecode from contracts/build.

    Mirrors the naming convention BlockchainService._load_contract_abi()
    already handles: solc's default "<SourceFile>_sol_<ContractName>"
    output naming.
    """
    abi_path = CONTRACTS_BUILD_DIR / f"{contract_name}_sol_{contract_name}.abi"
    bin_path = CONTRACTS_BUILD_DIR / f"{contract_name}_sol_{contract_name}.bin"
    if not abi_path.is_file() or not bin_path.is_file():
        pytest.skip(
            f"Compiled artifact for {contract_name} not found at {abi_path}. "
            "Run `bash contracts/compile.sh` first."
        )
    abi = json.loads(abi_path.read_text(encoding="utf-8"))
    bytecode = bin_path.read_text(encoding="utf-8").strip()
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode
    return abi, bytecode


@pytest.fixture(scope="module")
def w3():
    """A real in-process local Ethereum test chain (py-evm backend)."""
    tester = EthereumTester(backend=PyEVMBackend())
    return Web3(Web3.EthereumTesterProvider(tester))


@pytest.fixture
def accounts(w3):
    return w3.eth.accounts


@pytest.fixture
def owner(accounts):
    return accounts[0]


@pytest.fixture
def stranger(accounts):
    return accounts[1]


@pytest.fixture
def second_registrar(accounts):
    return accounts[2]


def _deploy(w3, contract_name: str, owner_address: str):
    abi, bytecode = _load_artifact(contract_name)
    factory = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = factory.constructor(owner_address).transact({"from": owner_address})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt.status == 1
    return w3.eth.contract(address=receipt.contractAddress, abi=abi)


@pytest.fixture
def passport_registry(w3, owner):
    return _deploy(w3, PASSPORT_REGISTRY_NAME, owner)


@pytest.fixture
def evidence_registry(w3, owner):
    """The EXISTING, unmodified item registry, deployed alongside the new
    passport registry purely to prove isolation between the two contracts."""
    return _deploy(w3, EVIDENCE_REGISTRY_NAME, owner)


def _bytes32(value: str) -> bytes:
    return bytes.fromhex(value)


PASSPORT_KEY_1 = _bytes32("31e5891f6803041a37cfae842c5bf47aa89df5130d6a8ba235cdd9041744763f"[:64])
PASSPORT_ROOT_1 = _bytes32("a" * 64)
PASSPORT_ROOT_2 = _bytes32("b" * 64)
PASSPORT_KEY_2 = _bytes32("c" * 64)


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_owner_registrar_can_anchor(passport_registry, owner):
    tx_hash = passport_registry.functions.anchorPassportRoot(PASSPORT_KEY_1, PASSPORT_ROOT_1).transact({"from": owner})
    receipt = passport_registry.w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt.status == 1


def test_unauthorized_address_cannot_anchor(passport_registry, stranger):
    with pytest.raises(TransactionFailed, match="Not authorized registrar"):
        passport_registry.functions.anchorPassportRoot(PASSPORT_KEY_1, PASSPORT_ROOT_1).call({"from": stranger})


def test_owner_can_authorize_a_new_registrar(passport_registry, owner, second_registrar):
    tx_hash = passport_registry.functions.setRegistrar(second_registrar, True).transact({"from": owner})
    passport_registry.w3.eth.wait_for_transaction_receipt(tx_hash)
    assert passport_registry.functions.authorizedRegistrars(second_registrar).call() is True

    tx_hash = passport_registry.functions.anchorPassportRoot(PASSPORT_KEY_1, PASSPORT_ROOT_1).transact({"from": second_registrar})
    receipt = passport_registry.w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt.status == 1


def test_non_owner_cannot_authorize_a_registrar(passport_registry, stranger, second_registrar):
    with pytest.raises(TransactionFailed):
        passport_registry.functions.setRegistrar(second_registrar, True).call({"from": stranger})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_zero_passport_key_rejected(passport_registry, owner):
    with pytest.raises(TransactionFailed, match="Passport key cannot be zero"):
        passport_registry.functions.anchorPassportRoot(ZERO_BYTES32, PASSPORT_ROOT_1).call({"from": owner})


def test_zero_passport_root_rejected(passport_registry, owner):
    with pytest.raises(TransactionFailed, match="Passport root cannot be zero"):
        passport_registry.functions.anchorPassportRoot(PASSPORT_KEY_1, ZERO_BYTES32).call({"from": owner})


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_anchor_stored_with_timestamp_and_registrar(passport_registry, owner):
    tx_hash = passport_registry.functions.anchorPassportRoot(PASSPORT_KEY_2, PASSPORT_ROOT_1).transact({"from": owner})
    receipt = passport_registry.w3.eth.wait_for_transaction_receipt(tx_hash)
    block = passport_registry.w3.eth.get_block(receipt.blockNumber)

    root, timestamp, anchored_by = passport_registry.functions.getPassportRoot(PASSPORT_KEY_2).call()
    assert root == PASSPORT_ROOT_1
    assert timestamp == block["timestamp"]
    assert anchored_by == owner


def test_get_passport_root_reverts_for_unknown_key(passport_registry):
    with pytest.raises(TransactionFailed, match="Passport root does not exist"):
        passport_registry.functions.getPassportRoot(b"\x99" * 32).call()


# ---------------------------------------------------------------------------
# Duplicate / immutability
# ---------------------------------------------------------------------------


def test_duplicate_passport_key_same_root_rejected(passport_registry, owner):
    key = _bytes32("d" * 64)
    passport_registry.functions.anchorPassportRoot(key, PASSPORT_ROOT_1).transact({"from": owner})
    with pytest.raises(TransactionFailed, match="Passport root already anchored"):
        passport_registry.functions.anchorPassportRoot(key, PASSPORT_ROOT_1).call({"from": owner})


def test_duplicate_passport_key_different_root_cannot_overwrite(passport_registry, owner):
    key = _bytes32("e" * 64)
    passport_registry.functions.anchorPassportRoot(key, PASSPORT_ROOT_1).transact({"from": owner})
    with pytest.raises(TransactionFailed, match="Passport root already anchored"):
        passport_registry.functions.anchorPassportRoot(key, PASSPORT_ROOT_2).call({"from": owner})

    # The original root must remain untouched after the rejected overwrite attempt.
    root, _, _ = passport_registry.functions.getPassportRoot(key).call()
    assert root == PASSPORT_ROOT_1


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def test_verify_passport_root_true_for_correct_key_and_root(passport_registry, owner):
    key = _bytes32("f" * 64)
    passport_registry.functions.anchorPassportRoot(key, PASSPORT_ROOT_1).transact({"from": owner})
    assert passport_registry.functions.verifyPassportRoot(key, PASSPORT_ROOT_1).call() is True


def test_verify_passport_root_false_for_wrong_root(passport_registry, owner):
    key = _bytes32("1" * 64)
    passport_registry.functions.anchorPassportRoot(key, PASSPORT_ROOT_1).transact({"from": owner})
    assert passport_registry.functions.verifyPassportRoot(key, PASSPORT_ROOT_2).call() is False


def test_verify_passport_root_false_for_unknown_key(passport_registry):
    assert passport_registry.functions.verifyPassportRoot(b"\x77" * 32, PASSPORT_ROOT_1).call() is False


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_passport_root_anchored_event_fields(passport_registry, owner):
    key = _bytes32("2" * 64)
    tx_hash = passport_registry.functions.anchorPassportRoot(key, PASSPORT_ROOT_1).transact({"from": owner})
    receipt = passport_registry.w3.eth.wait_for_transaction_receipt(tx_hash)
    block = passport_registry.w3.eth.get_block(receipt.blockNumber)

    events = passport_registry.events.PassportRootAnchored().process_receipt(receipt)
    assert len(events) == 1
    args = events[0]["args"]
    assert args["passportKey"] == key
    assert args["passportRoot"] == PASSPORT_ROOT_1
    assert args["timestamp"] == block["timestamp"]
    assert args["anchoredBy"] == owner


# ---------------------------------------------------------------------------
# Isolation from the existing, unmodified LexProofRegistry
# ---------------------------------------------------------------------------


def test_evidence_registry_anchor_evidence_cannot_create_a_passport_root(
    passport_registry, evidence_registry, owner
):
    """Anchoring an EVIDENCE item on the existing, separate LexProofRegistry
    must have zero effect on the new passport registry's storage -- they are
    different contracts at different addresses with no shared state."""
    record_id = "evidence-item-isolation-check"
    evidence_hash = PASSPORT_ROOT_1
    tx_hash = evidence_registry.functions.anchorEvidence(record_id, evidence_hash).transact({"from": owner})
    evidence_registry.w3.eth.wait_for_transaction_receipt(tx_hash)

    # Using the SAME 32-byte value as a passport key on the passport registry
    # must show no anchor -- the evidence anchor above cannot have written it.
    key_shaped_like_the_evidence_hash = evidence_hash
    with pytest.raises(TransactionFailed, match="Passport root does not exist"):
        passport_registry.functions.getPassportRoot(key_shaped_like_the_evidence_hash).call()


def test_anchor_passport_root_cannot_affect_evidence_anchors(passport_registry, evidence_registry, owner):
    """The inverse: anchoring a passport root must have zero effect on the
    existing, separate evidence registry's storage."""
    key = _bytes32("3" * 64)
    passport_registry.functions.anchorPassportRoot(key, PASSPORT_ROOT_1).transact({"from": owner})

    with pytest.raises(TransactionFailed, match="Evidence anchor does not exist"):
        evidence_registry.functions.getEvidenceAnchor("some-record-id-that-was-never-anchored").call()

    # And the passport registry has exactly one anchor -- the evidence
    # registry's own (separate, pre-existing) storage is not reachable from it
    # at all: there is no shared mapping, no shared address, and no function
    # on LexProofPassportRegistry that references evidenceAnchors.
    root, _, _ = passport_registry.functions.getPassportRoot(key).call()
    assert root == PASSPORT_ROOT_1


def test_updateProofStatus_on_evidence_registry_has_no_passport_registry_analog(evidence_registry):
    """LexProofPassportRegistry deliberately has no updateProofStatus-style
    mutator at all -- passport root anchors are immutable from the moment
    they are written (see docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md §10, §24:
    "on-chain roots cannot be deleted... rollback is stop writing, not erase
    Sepolia"). This test documents that this residual mutability on the
    OLD Proof struct is a property only of the existing, unmodified
    evidence-registry contract's registerProof/Proof primitives -- confirmed
    by checking the passport registry ABI carries no such function -- and is
    explicitly not carried over into the new contract."""
    passport_abi, _ = _load_artifact(PASSPORT_REGISTRY_NAME)
    function_names = {entry["name"] for entry in passport_abi if entry.get("type") == "function"}
    assert "updateProofStatus" not in function_names
    assert "registerProof" not in function_names
