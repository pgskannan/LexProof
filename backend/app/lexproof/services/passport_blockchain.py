"""Low-level Ethereum client for the additive LexProofPassportRegistry contract.

This is a deliberately SEPARATE, self-contained class from
``services/blockchain.py``'s ``BlockchainService`` -- it never imports or
mutates that class, targets a different contract address
(``ETHEREUM_PASSPORT_REGISTRY_ADDRESS``) and a different ABI
(``LexProofPassportRegistry``), and exists purely to anchor and read Legal
Passport ROOT commitments (``metadata.passport_hash``). It shares the same
RPC endpoint, chain, and registrar signer as evidence anchoring (the same
funded, already-authorized account is authorized as a registrar on this new
contract too), but nothing about the existing per-evidence-item
``LexProofRegistry`` flow is touched by this module.

SECURITY: Only a 32-byte passport root, a 32-byte passport identity key, a
timestamp, and the registrar address ever cross this boundary. No contract
text, evidence content, analysis JSON, scores, tenant IDs, or PII.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted, TransactionNotFound

from .blockchain_fees import anchoring_fee_params

logger = logging.getLogger(__name__)

SEPOLIA_CHAIN_ID = 11155111
_PASSPORT_ROOT_ANCHORED_SIGNATURE = "PassportRootAnchored(bytes32,bytes32,uint256,address)"


class PassportBlockchainService:
    """Client for LexProofPassportRegistry (additive passport-root contract)."""

    def __init__(
        self,
        rpc_url: str,
        contract_address: str,
        private_key: str,
        contract_abi: Optional[Any] = None,
    ):
        self.rpc_url = rpc_url
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.private_key = private_key

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self._connected = self.w3.is_connected()

        self.contract_abi = contract_abi if contract_abi else self._load_contract_abi()
        self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.contract_abi)

        self.chain_id = self.w3.eth.chain_id
        if isinstance(self.chain_id, int) and self.chain_id != SEPOLIA_CHAIN_ID:
            raise ValueError(
                f"Wrong network! Expected Sepolia ({SEPOLIA_CHAIN_ID}), got chain_id={self.chain_id}"
            )

    def _load_contract_abi(self) -> Any:
        """Load the compiled LexProofPassportRegistry ABI from contracts/build.

        Mirrors BlockchainService._load_contract_abi's candidate-path search
        (solc's default "<SourceFile>_sol_<ContractName>.abi" naming first,
        then a glob fallback), plus a last-resort hardcoded ABI covering
        exactly this contract's public interface so a build-tool naming
        change can't silently regress anchor/verify/get-root calls the way an
        event-less stub previously did for the evidence registry.
        """
        import glob
        import os

        build_dir = os.path.join(os.path.dirname(__file__), "../../../../contracts/build")
        candidates = [
            os.path.join(build_dir, "LexProofPassportRegistry.abi"),
            os.path.join(build_dir, "LexProofPassportRegistry_sol_LexProofPassportRegistry.abi"),
        ]
        candidates.extend(sorted(glob.glob(os.path.join(build_dir, "*LexProofPassportRegistry.abi"))))
        for abi_path in candidates:
            try:
                with open(abi_path, "r") as handle:
                    return json.load(handle)
            except (FileNotFoundError, json.JSONDecodeError):
                continue

        return [
            {
                "inputs": [
                    {"internalType": "bytes32", "name": "passportKey", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "passportRoot", "type": "bytes32"},
                ],
                "name": "anchorPassportRoot",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            },
            {
                "inputs": [
                    {"internalType": "bytes32", "name": "passportKey", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "passportRoot", "type": "bytes32"},
                ],
                "name": "verifyPassportRoot",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [{"internalType": "bytes32", "name": "passportKey", "type": "bytes32"}],
                "name": "getPassportRoot",
                "outputs": [
                    {"internalType": "bytes32", "name": "passportRoot", "type": "bytes32"},
                    {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                    {"internalType": "address", "name": "anchoredBy", "type": "address"},
                ],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "internalType": "bytes32", "name": "passportKey", "type": "bytes32"},
                    {"indexed": True, "internalType": "bytes32", "name": "passportRoot", "type": "bytes32"},
                    {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
                    {"indexed": True, "internalType": "address", "name": "anchoredBy", "type": "address"},
                ],
                "name": "PassportRootAnchored",
                "type": "event",
            },
        ]

    def _ensure_sepolia(self) -> None:
        if not self._connected:
            raise ConnectionError(f"Failed to connect to Ethereum RPC: {self.rpc_url}")
        if self.w3.eth.chain_id != SEPOLIA_CHAIN_ID:
            raise ValueError(
                f"Wrong network! Expected Sepolia ({SEPOLIA_CHAIN_ID}), got chain_id={self.w3.eth.chain_id}."
            )

    def anchor_passport_root(self, passport_key: bytes, passport_root: bytes) -> Tuple[str, int, int]:
        """Submit anchorPassportRoot(passportKey, passportRoot) and wait for the receipt."""
        self._ensure_sepolia()
        if len(passport_key) != 32 or passport_key == b"\x00" * 32:
            raise ValueError("Passport key must be a non-zero bytes32 value")
        if len(passport_root) != 32 or passport_root == b"\x00" * 32:
            raise ValueError("Passport root must be a non-zero bytes32 value")

        account = self.w3.eth.account.from_key(self.private_key)
        function = self.contract.functions.anchorPassportRoot(passport_key, passport_root)
        transaction = function.build_transaction({
            "from": account.address,
            "nonce": self.w3.eth.get_transaction_count(account.address),
            "chainId": self.chain_id,
            "gas": function.estimate_gas({"from": account.address}),
            **anchoring_fee_params(self.w3),
        })
        signed = self.w3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._wait_for_transaction_receipt(tx_hash)
        if receipt["status"] == 0:
            raise ValueError(f"Passport root anchor transaction reverted: {tx_hash.hex()}")
        block = self.w3.eth.get_block(receipt["blockNumber"])
        return tx_hash.hex(), receipt["blockNumber"], int(block["timestamp"])

    def get_passport_root(self, passport_key: bytes) -> Optional[Dict[str, Any]]:
        """Read a passport root anchor. Returns None if no anchor exists yet.

        getPassportRoot() reverts with "Passport root does not exist" for an
        unanchored key (the common not-yet-anchored path) rather than
        returning a zero value -- that revert is caught here, matching
        BlockchainService.get_evidence_anchor's convention.
        """
        try:
            passport_root, timestamp, anchored_by = self.contract.functions.getPassportRoot(passport_key).call()
        except ContractLogicError as exc:
            if "Passport root does not exist" in str(exc):
                return None
            raise
        return {
            "passport_root": passport_root.hex(),
            "anchored_at": int(timestamp),
            "anchored_by": anchored_by,
        }

    def verify_passport_root(self, passport_key: bytes, passport_root: bytes) -> bool:
        return bool(self.contract.functions.verifyPassportRoot(passport_key, passport_root).call())

    # Same provider-safe chunked backward log scan as BlockchainService's
    # get_anchor_transaction_hash, for the same reason (small-range eth_getLogs
    # caps and per-second rate limits on typical free-tier RPC providers).
    _LOG_SCAN_CHUNK_SIZE = 10
    _LOG_SCAN_MAX_LOOKBACK_BLOCKS = 500
    _LOG_SCAN_REQUEST_DELAY_SECONDS = 0.25
    _LOG_SCAN_MAX_RETRIES_PER_CHUNK = 5

    def _estimate_block_for_timestamp(self, target_timestamp: int) -> int:
        low = 0
        high = self.w3.eth.block_number
        latest_ts = int(self.w3.eth.get_block(high)["timestamp"])
        if target_timestamp >= latest_ts:
            return high
        while low < high:
            mid = (low + high + 1) // 2
            mid_ts = int(self.w3.eth.get_block(mid)["timestamp"])
            if mid_ts <= target_timestamp:
                low = mid
            else:
                high = mid - 1
        return low

    def get_anchor_transaction_hash(self, passport_key: bytes, passport_root_hex: Optional[str] = None) -> str:
        """Resolve the transaction hash for a PassportRootAnchored event."""
        event = getattr(self.contract.events, "PassportRootAnchored", None)
        if event is None:
            raise RuntimeError("PassportRootAnchored event is unavailable from the contract ABI")

        topic0 = Web3.keccak(text=_PASSPORT_ROOT_ANCHORED_SIGNATURE)
        topic1 = Web3.to_hex(passport_key)

        chunk_size = self._LOG_SCAN_CHUNK_SIZE
        max_lookback_blocks = self._LOG_SCAN_MAX_LOOKBACK_BLOCKS
        chain_tip = self.w3.eth.block_number

        anchor_window_blocks = 50
        anchor_info = self.get_passport_root(passport_key)
        if anchor_info is not None:
            approx_block = self._estimate_block_for_timestamp(anchor_info["anchored_at"])
            latest_block = min(chain_tip, approx_block + anchor_window_blocks)
            earliest_block = max(0, approx_block - anchor_window_blocks)
        else:
            latest_block = chain_tip
            earliest_block = max(0, latest_block - max_lookback_blocks)

        to_block = latest_block
        while to_block >= earliest_block:
            from_block = max(earliest_block, to_block - chunk_size + 1)

            raw_logs = None
            last_exc: Optional[Exception] = None
            for attempt in range(self._LOG_SCAN_MAX_RETRIES_PER_CHUNK):
                try:
                    raw_logs = self.w3.eth.get_logs({
                        "address": self.contract_address,
                        "topics": [topic0, topic1],
                        "fromBlock": from_block,
                        "toBlock": to_block,
                    })
                    break
                except Exception as exc:  # noqa: BLE001 - provider-shaped errors vary
                    last_exc = exc
                    is_rate_limited = "429" in str(exc) or "Too Many Requests" in str(exc)
                    if not is_rate_limited or attempt == self._LOG_SCAN_MAX_RETRIES_PER_CHUNK - 1:
                        raise
                    time.sleep(self._LOG_SCAN_REQUEST_DELAY_SECONDS * (2 ** attempt))
            if raw_logs is None:
                raise last_exc

            time.sleep(self._LOG_SCAN_REQUEST_DELAY_SECONDS)

            for raw_log in raw_logs:
                decoded = event().process_log(raw_log)
                args = getattr(decoded, "args", {}) or {}
                log_root = args.get("passportRoot")
                if log_root is None:
                    continue
                if passport_root_hex is not None:
                    expected = passport_root_hex.lower().removeprefix("0x")
                    actual = Web3.to_hex(log_root).lower().removeprefix("0x")
                    if actual != expected:
                        continue
                return Web3.to_hex(raw_log["transactionHash"]).lower()
            if from_block == earliest_block:
                break
            to_block = from_block - 1

        raise RuntimeError(
            f"No PassportRootAnchored transaction found for passport_key={Web3.to_hex(passport_key)} "
            f"in blocks {earliest_block}-{latest_block}"
        )

    def recover_confirmed_transaction(self, transaction_hash: str) -> Tuple[str, int, int]:
        """Read a confirmed transaction receipt without submitting a transaction."""
        tx_hash = Web3.to_bytes(hexstr=transaction_hash)
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound as exc:
            raise RuntimeError(f"Transaction confirmation unavailable: {transaction_hash}") from exc
        if receipt["status"] != 1:
            raise ValueError(f"Transaction reverted: {transaction_hash}")
        block = self.w3.eth.get_block(receipt["blockNumber"])
        return transaction_hash.lower(), receipt["blockNumber"], int(block["timestamp"])

    def _wait_for_transaction_receipt(self, tx_hash: bytes, timeout: int = 120) -> Dict[str, Any]:
        try:
            return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        except (TimeExhausted, TimeoutError):
            logger.warning("Passport root anchor confirmation timed out; checking receipt")
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                receipt = None
            if receipt is not None:
                if receipt["status"] != 1:
                    raise ValueError(f"Transaction reverted after confirmation timeout: {tx_hash.hex()}")
                return receipt
            raise RuntimeError(f"Transaction confirmation unavailable: {tx_hash.hex()}")
        except Exception as exc:
            raise ValueError(f"Error waiting for transaction receipt: {exc}") from exc


def create_passport_blockchain_service(
    rpc_url: Optional[str] = None,
    contract_address: Optional[str] = None,
    private_key: Optional[str] = None,
) -> PassportBlockchainService:
    """Factory mirroring create_blockchain_service(), pointed at the additive
    passport-root registry instead of the item registry.
    """
    from ..config import get_settings

    settings = get_settings()
    resolved_rpc = rpc_url or settings.ethereum_rpc_url
    resolved_contract = contract_address or settings.passport_registry_address
    resolved_key = private_key or settings.blockchain_private_key.get_secret_value()

    if not resolved_contract:
        raise ValueError(
            "ETHEREUM_PASSPORT_REGISTRY_ADDRESS is not configured; the additive "
            "passport-root registry has not been deployed/configured for this environment"
        )

    return PassportBlockchainService(
        rpc_url=resolved_rpc,
        contract_address=resolved_contract,
        private_key=resolved_key,
    )
