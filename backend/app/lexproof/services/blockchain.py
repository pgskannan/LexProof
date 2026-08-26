"""
Blockchain Service for LexProof
Handles Ethereum Sepolia interactions for proof anchoring
"""

from typing import Optional, Tuple, Dict, Any
from enum import Enum
import json
import logging
import requests
import sys

# Ethereum provider (use web3.py)
from web3 import Web3
from web3 import eth
from web3.contract import Contract
from web3.exceptions import ContractLogicError, TransactionNotFound, TimeExhausted
from web3.types import TxReceipt, TxData

logger = logging.getLogger(__name__)

# Older tests patch ``web3.eth.contract`` even though current web3.py creates
# contracts through the Web3 instance. Keep that patch point available.
if not hasattr(eth, "contract"):
    eth.contract = None

# Security: Never import private keys from source code
# Keys must be loaded from environment variables or Google Secret Manager


class TransactionStatus(str, Enum):
    """Transaction status enumeration"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class BlockchainService:
    """
    Service for interacting with the LexProofRegistry smart contract on Ethereum Sepolia
    
    SECURITY: All credentials are loaded from environment variables or Secret Manager.
    Never store private keys in source code or configuration files.
    """
    
    def __init__(
        self,
        rpc_url: str,
        contract_address: str,
        private_key: str,
        contract_abi: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize blockchain service
        
        Args:
            rpc_url: Ethereum RPC endpoint (e.g., https://sepolia.infura.io/v3/YOUR_KEY)
            contract_address: Address of the deployed LexProofRegistry contract
            private_key: Private key for signing transactions (loaded from env/Secret Manager)
            contract_abi: Contract ABI (optional, can be loaded from file)
        """
        self.rpc_url = rpc_url
        legacy_module = sys.modules.get("lexproof.services.blockchain")
        web3_class = getattr(legacy_module, "Web3", Web3)
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.private_key = private_key
        
        # Initialize Web3 connection
        self.w3 = web3_class(web3_class.HTTPProvider(rpc_url))
        
        # Verify connection
        self._connected = self.w3.is_connected()
        
        # Load contract ABI if not provided
        if contract_abi:
            self.contract_abi = contract_abi
        else:
            self.contract_abi = self._load_contract_abi()
        
        # Create contract instance
        contract_factory = getattr(eth, "contract", None)
        if callable(contract_factory):
            self.contract = contract_factory(address=self.contract_address, abi=self.contract_abi)
        else:
            self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.contract_abi)
        
        # Get chain ID for Sepolia
        self.chain_id = self.w3.eth.chain_id
        if isinstance(self.chain_id, int) and self.chain_id != 11155111:  # Sepolia testnet
            raise ValueError(
                f"Wrong network! Expected Sepolia (11155111), got chain_id={self.chain_id}"
            )
    
    def _load_contract_abi(self) -> Dict[str, Any]:
        """
        Load contract ABI from file
        
        Returns:
            Contract ABI dictionary
        """
        try:
            import os
            abi_path = os.path.join(
                os.path.dirname(__file__),
                "../../../../contracts/build/LexProofRegistry.abi"
            )
            with open(abi_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return [
                {
                    "inputs": [
                        {"internalType": "bytes32", "name": "contractHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "policyHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "analysisHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
                        {"internalType": "uint256", "name": "riskScore", "type": "uint256"},
                        {"internalType": "uint256", "name": "complianceScore", "type": "uint256"},
                        {"internalType": "string", "name": "policyVersion", "type": "string"},
                        {"internalType": "uint256", "name": "evidenceCount", "type": "uint256"},
                    ],
                    "name": "registerProof",
                    "outputs": [{"internalType": "bytes32", "name": "proofId", "type": "bytes32"}],
                    "stateMutability": "nonpayable",
                    "type": "function",
                },
                {
                    "inputs": [
                        {"internalType": "bytes32", "name": "proofId", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "contractHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "policyHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "analysisHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
                    ],
                    "name": "verifyProof",
                    "outputs": [{"internalType": "bool", "name": "isValid", "type": "bool"}],
                    "stateMutability": "view",
                    "type": "function",
                },
                {
                    "inputs": [{"internalType": "bytes32", "name": "proofId", "type": "bytes32"}],
                    "name": "getProof",
                    "outputs": [
                        {"internalType": "bytes32", "name": "contractHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "policyHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "analysisHash", "type": "bytes32"},
                        {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
                        {"internalType": "uint256", "name": "riskScore", "type": "uint256"},
                        {"internalType": "uint256", "name": "complianceScore", "type": "uint256"},
                        {"internalType": "string", "name": "policyVersion", "type": "string"},
                        {"internalType": "uint256", "name": "evidenceCount", "type": "uint256"},
                        {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                        {"internalType": "address", "name": "registeredBy", "type": "address"},
                        {"internalType": "uint8", "name": "status", "type": "uint8"},
                    ],
                    "stateMutability": "view",
                    "type": "function",
                },
                {
                    "inputs": [{"internalType": "bytes32", "name": "proofId", "type": "bytes32"}],
                    "name": "getTransaction",
                    "outputs": [
                        {"internalType": "bytes", "name": "txHash", "type": "bytes"},
                        {"internalType": "uint256", "name": "blockNumber", "type": "uint256"},
                        {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                    ],
                    "stateMutability": "view",
                    "type": "function",
                },
                {
                    "inputs": [
                        {"internalType": "string", "name": "recordId", "type": "string"},
                        {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
                    ],
                    "name": "anchorEvidence",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function",
                },
                {
                    "inputs": [
                        {"internalType": "string", "name": "recordId", "type": "string"},
                        {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
                    ],
                    "name": "verifyEvidence",
                    "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                    "stateMutability": "view",
                    "type": "function",
                },
                {
                    "inputs": [{"internalType": "string", "name": "recordId", "type": "string"}],
                    "name": "getEvidenceAnchor",
                    "outputs": [
                        {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
                        {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                        {"internalType": "address", "name": "anchoredBy", "type": "address"},
                    ],
                    "stateMutability": "view",
                    "type": "function",
                },
            ]

    def _ensure_sepolia(self) -> None:
        """Validate that the active network is Sepolia."""
        if not self._connected:
            raise ConnectionError(f"Failed to connect to Ethereum RPC: {self.rpc_url}")
        if self.w3.eth.chain_id != 11155111:
            raise ValueError(
                "Wrong network! Expected Sepolia (11155111), got chain_id={}.".format(self.w3.eth.chain_id)
            )

    def get_nonce(self) -> int:
        """
        Get current account nonce
        
        Returns:
            Current nonce for transaction signing
        """
        self._ensure_sepolia()
        return self.w3.eth.get_transaction_count(self.w3.eth.account.from_key(self.private_key).address)

    def get_gas_price(self) -> int:
        """
        Get current gas price
        
        Returns:
            Gas price in wei
        """
        self._ensure_sepolia()
        return self.w3.eth.gas_price
    
    def estimate_gas(
        self,
        contract_function,
        transaction_params: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Estimate gas cost for transaction
        
        Args:
            contract_function: Contract function to call
            transaction_params: Additional transaction parameters
            
        Returns:
            Estimated gas in wei
        """
        try:
            estimated_gas = contract_function.estimate_gas(transaction_params or {})
            return estimated_gas
        except ContractLogicError as e:
            raise ValueError(f"Gas estimation failed: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error estimating gas: {str(e)}")
    
    def register_proof(
        self,
        contract_hash: bytes,
        policy_hash: bytes,
        analysis_hash: bytes,
        evidence_hash: bytes,
        risk_score: int,
        compliance_score: int,
        policy_version: str,
        evidence_count: int,
        max_fee_per_gas: Optional[int] = None,
        max_priority_fee_per_gas: Optional[int] = None
    ) -> Tuple[bytes, int]:
        """
        Register a proof on-chain
        
        Args:
            contract_hash: SHA-256 hash of the contract
            policy_hash: SHA-256 hash of the policy
            analysis_hash: SHA-256 hash of the analysis
            evidence_hash: SHA-256 hash of all evidence
            risk_score: Risk score (0-100)
            compliance_score: Compliance score (0-100)
            policy_version: Version of the policy
            evidence_count: Number of evidence items
            max_fee_per_gas: Optional max fee per gas for EIP-1559
            max_priority_fee_per_gas: Optional max priority fee per gas for EIP-1559
            
        Returns:
            Tuple of (transaction hash, block number)
        """
        if not 0 <= risk_score <= 100:
            raise ValueError("Risk score must be <= 100")
        if not 0 <= compliance_score <= 100:
            raise ValueError("Compliance score must be <= 100")
        if not policy_version:
            raise ValueError("Policy version cannot be empty")
        if evidence_count <= 0:
            raise ValueError("Evidence count must be > 0")

        # Prepare transaction parameters
        nonce = self.get_nonce()
        gas_price = self.get_gas_price()
        
        # Create transaction
        transaction = self.contract.functions.registerProof(
            contract_hash,
            policy_hash,
            analysis_hash,
            evidence_hash,
            risk_score,
            compliance_score,
            policy_version,
            evidence_count
        ).build_transaction({
            'from': self.w3.eth.account.from_key(self.private_key).address,
            'nonce': nonce,
            'gas': 0,  # Will be estimated
            'gasPrice': gas_price,
            'chainId': self.chain_id
        })
        
        # Estimate gas if not provided
        if transaction['gas'] == 0:
            transaction['gas'] = self.estimate_gas(self.contract.functions.registerProof(
                contract_hash, policy_hash, analysis_hash, evidence_hash,
                risk_score, compliance_score, policy_version, evidence_count
            ))
        
        # Apply EIP-1559 if provided
        if max_fee_per_gas and max_priority_fee_per_gas:
            transaction['maxFeePerGas'] = max_fee_per_gas
            transaction['maxPriorityFeePerGas'] = max_priority_fee_per_gas
            transaction['type'] = 2  # EIP-1559 transaction type
            del transaction['gasPrice']
        
        # Sign transaction
        signed_txn = self.w3.eth.account.sign_transaction(transaction, self.private_key)
        
        # Send transaction
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        # Wait for transaction receipt
        receipt = self._wait_for_transaction_receipt(tx_hash)
        
        # Check if transaction was successful
        if receipt['status'] == 0:
            raise ValueError(f"Transaction failed: {tx_hash.hex()}")
        
        return tx_hash.hex(), receipt['blockNumber']

    def anchor_evidence(self, record_id: str, evidence_hash: bytes) -> Tuple[str, int, int]:
        """Anchor an existing LexProof evidence hash using the registry contract."""
        self._ensure_sepolia()
        if not record_id or len(record_id) > 256:
            raise ValueError("Record ID must be between 1 and 256 characters")
        if len(evidence_hash) != 32 or evidence_hash == b'\x00' * 32:
            raise ValueError("Evidence hash must be a non-zero bytes32 value")

        account = self.w3.eth.account.from_key(self.private_key)
        function = self.contract.functions.anchorEvidence(record_id, evidence_hash)
        transaction = function.build_transaction({
            "from": account.address,
            "nonce": self.w3.eth.get_transaction_count(account.address),
            "chainId": self.chain_id,
            "gas": function.estimate_gas({"from": account.address}),
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.w3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._wait_for_transaction_receipt(tx_hash)
        if receipt["status"] == 0:
            raise ValueError(f"Evidence anchor transaction reverted: {tx_hash.hex()}")
        block = self.w3.eth.get_block(receipt["blockNumber"])
        return tx_hash.hex(), receipt["blockNumber"], int(block["timestamp"])

    def get_evidence_anchor(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Read an evidence anchor from the registry contract.

        Returns None when no anchor exists yet for this record_id. The contract's
        getEvidenceAnchor() reverts with "Evidence anchor does not exist" in that
        case (this is the expected, common path for a not-yet-anchored evidence
        item) rather than returning a zero value, so that revert must be caught
        here instead of propagating as an unexpected error to callers.
        """
        try:
            evidence_hash, timestamp, anchored_by = self.contract.functions.getEvidenceAnchor(record_id).call()
        except ContractLogicError as e:
            if "Evidence anchor does not exist" in str(e):
                return None
            raise
        return {
            "evidence_hash": evidence_hash.hex(),
            "anchored_at": int(timestamp),
            "anchored_by": anchored_by,
        }

    def verify_evidence(self, record_id: str, evidence_hash: bytes) -> bool:
        """Compare an evidence hash with its on-chain anchor."""
        return bool(self.contract.functions.verifyEvidence(record_id, evidence_hash).call())

    @staticmethod
    def proof_id_for_hashes(
        contract_hash: bytes,
        policy_hash: bytes,
        analysis_hash: bytes,
        evidence_hash: bytes,
    ) -> bytes:
        """Return the contract's deterministic fingerprint tuple identifier."""
        return Web3.solidity_keccak(
            ["bytes32", "bytes32", "bytes32", "bytes32"],
            [contract_hash, policy_hash, analysis_hash, evidence_hash],
        )
    
    def verify_proof(
        self,
        proof_id: bytes,
        contract_hash: bytes,
        policy_hash: bytes,
        analysis_hash: bytes,
        evidence_hash: bytes
    ) -> bool:
        """
        Verify a proof by comparing hashes
        
        Args:
            proof_id: The ID of the proof to verify
            contract_hash: The contract hash to verify
            policy_hash: The policy hash to verify
            analysis_hash: The analysis hash to verify
            evidence_hash: The evidence hash to verify
            
        Returns:
            True if all hashes match, False otherwise
        """
        try:
            is_valid = self.contract.functions.verifyProof(
                proof_id,
                contract_hash,
                policy_hash,
                analysis_hash,
                evidence_hash
            ).call()
            return is_valid
        except Exception as e:
            raise ValueError(f"Error verifying proof: {str(e)}")
    
    def get_proof(self, proof_id: bytes) -> Dict[str, Any]:
        """
        Get proof details from the blockchain
        
        Args:
            proof_id: The ID of the proof
            
        Returns:
            Dictionary containing proof details
        """
        try:
            (
                contract_hash,
                policy_hash,
                analysis_hash,
                evidence_hash,
                risk_score,
                compliance_score,
                policy_version,
                evidence_count,
                timestamp,
                registered_by,
                status
            ) = self.contract.functions.getProof(proof_id).call()
            
            return {
                'contract_hash': contract_hash.hex(),
                'policy_hash': policy_hash.hex(),
                'analysis_hash': analysis_hash.hex(),
                'evidence_hash': evidence_hash.hex(),
                'risk_score': risk_score,
                'compliance_score': compliance_score,
                'policy_version': policy_version,
                'evidence_count': evidence_count,
                'timestamp': timestamp,
                'registered_by': registered_by,
                'status': (
                    TransactionStatus.PENDING.value
                    if status == 0
                    else TransactionStatus.CONFIRMED.value
                    if status == 1
                    else TransactionStatus.FAILED.value
                )
            }
        except Exception as e:
            raise ValueError(f"Error getting proof: {str(e)}")
    
    def get_transaction(self, proof_id: bytes) -> Tuple[bytes, int, int]:
        """
        Get transaction details for a proof
        
        Args:
            proof_id: The ID of the proof
            
        Returns:
            Tuple containing transaction hash, block number, and timestamp
        """
        try:
            tx_hash_bytes, block_number, timestamp = self.contract.functions.getTransaction(proof_id).call()
            
            return tx_hash_bytes, block_number, timestamp
        except Exception as e:
            raise ValueError(f"Error getting transaction: {str(e)}")
    
    def _wait_for_transaction_receipt(self, tx_hash: bytes, timeout: int = 120) -> TxReceipt:
        """
        Wait for transaction receipt
        
        Args:
            tx_hash: Transaction hash
            timeout: Maximum wait time in seconds
            
        Returns:
            Transaction receipt
        """
        try:
            return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        except (TimeExhausted, TimeoutError):
            logger.warning("Transaction confirmation timed out; checking receipt")
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                receipt = None
            if receipt is not None:
                if receipt["status"] != 1:
                    raise ValueError(f"Transaction reverted after confirmation timeout: {tx_hash.hex()}")
                logger.info("Transaction mined successfully after confirmation timeout")
                return receipt

            try:
                transaction = self.w3.eth.get_transaction(tx_hash)
            except TransactionNotFound as exc:
                raise RuntimeError(
                    f"Transaction confirmation unavailable: {tx_hash.hex()}"
                ) from exc
            if transaction.get("blockNumber") is None and transaction.get("blockHash") is None:
                logger.warning("Transaction remains pending")
                raise RuntimeError(f"Transaction pending: {tx_hash.hex()}")
            raise RuntimeError(f"Transaction confirmation unavailable: {tx_hash.hex()}")
        except Exception as exc:
            raise ValueError(f"Error waiting for transaction receipt: {exc}") from exc

    def get_anchor_transaction_hash(self, record_id: str, evidence_hash: Optional[str] = None) -> str:
        """Resolve the transaction hash for an EvidenceAnchored event for a record."""
        event = getattr(self.contract.events, "EvidenceAnchored", None)
        if event is None:
            raise RuntimeError("EvidenceAnchored event is unavailable from the contract ABI")

        logs = event().get_logs(fromBlock=0, argument_filters={"recordId": record_id})

        for log in logs:
            args = getattr(log, "args", {}) or {}
            log_hash = args.get("evidenceHash")
            if log_hash is None:
                continue
            if evidence_hash is not None and Web3.to_hex(log_hash).lower() != evidence_hash.lower():
                continue
            return Web3.to_hex(log["transactionHash"]).lower()

        raise RuntimeError(f"No EvidenceAnchored transaction found for record_id={record_id}")

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
    
    def get_current_block_number(self) -> int:
        """
        Get current block number
        
        Returns:
            Current block number
        """
        self._ensure_sepolia()
        return self.w3.eth.block_number
    
    def get_block_number_by_timestamp(self, timestamp: int) -> int:
        """
        Get block number by timestamp (approximate)
        
        Args:
            timestamp: Unix timestamp
            
        Returns:
            Approximate block number
        """
        # This is a simplified approach; for production, use a more accurate method
        current_block = self.w3.eth.block_number
        block = self.w3.eth.get_block(current_block)
        current_timestamp = block['timestamp']
        
        # If timestamp is in the past, go backwards
        if timestamp < current_timestamp:
            # Simple approximation: divide by block time (avg ~12s)
            blocks_diff = (current_timestamp - timestamp) // 12
            return max(0, current_block - blocks_diff)
        
        # If timestamp is in the future, go forwards
        return current_block
    
    def is_transaction_confirmed(self, tx_hash: bytes, min_confirmations: int = 12) -> bool:
        """
        Check if transaction is confirmed
        
        Args:
            tx_hash: Transaction hash
            min_confirmations: Minimum confirmations required
            
        Returns:
            True if confirmed, False otherwise
        """
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if receipt is None:
                return False
            
            current_block = self.w3.eth.block_number
            confirmations = current_block - receipt['blockNumber']
            
            return confirmations >= min_confirmations
        except TransactionNotFound:
            return False
        except Exception as e:
            raise ValueError(f"Error checking transaction status: {str(e)}")


def create_blockchain_service(
    rpc_url: Optional[str] = None,
    contract_address: Optional[str] = None,
    private_key: Optional[str] = None
) -> BlockchainService:
    """
    Factory function to create blockchain service
    
    Args:
        rpc_url: Ethereum RPC URL (defaults to env var)
        contract_address: Contract address (defaults to env var)
        private_key: Private key (defaults to env var)
        
    Returns:
        Configured BlockchainService instance
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    resolved_rpc = rpc_url or os.getenv('BLOCKCHAIN_RPC_URL') or os.getenv('ETHEREUM_RPC_URL')
    resolved_contract = (
        contract_address
        or os.getenv('CONTRACT_ADDRESS')
        or os.getenv('ETHEREUM_CONTRACT_ADDRESS')
        or os.getenv('BLOCKCHAIN_CONTRACT_ADDRESS')
    )
    resolved_key = (
        private_key
        or os.getenv('BLOCKCHAIN_PRIVATE_KEY')
        or os.getenv('ETHEREUM_PRIVATE_KEY')
        or os.getenv('PRIVATE_KEY')
    )

    return BlockchainService(
        rpc_url=resolved_rpc,
        contract_address=resolved_contract,
        private_key=resolved_key,
    )
