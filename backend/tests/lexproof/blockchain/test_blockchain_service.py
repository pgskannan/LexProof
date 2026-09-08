"""
Blockchain Service Integration Tests for LexProof
Tests Ethereum Sepolia interactions and transaction handling
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from app.lexproof.services.blockchain import BlockchainService, TransactionStatus, create_blockchain_service
from web3.exceptions import TimeExhausted, TransactionNotFound


def configure_contract_mock(contract_mock):
    """Configure the contract calls exercised by the service tests."""
    contract_mock.functions.registerProof.return_value.build_transaction.return_value = {
        "gas": 21000,
        "gasPrice": 20000000000,
    }
    contract_mock.functions.registerProof.return_value.estimate_gas.return_value = 21000
    contract_mock.functions.verifyProof.return_value.call.return_value = True
    contract_mock.functions.getProof.return_value.call.return_value = (
        b"\x01" * 32,
        b"\x02" * 32,
        b"\x03" * 32,
        b"\x04" * 32,
        75,
        85,
        "1.0.0",
        3,
        1700000000,
        "0x1234567890123456789012345678901234567890",
        1,
    )
    contract_mock.functions.getTransaction.return_value.call.return_value = (
        b"\x01" * 32,
        5000001,
        1700000000,
    )
    return contract_mock


class TestBlockchainService:
    """Test suite for BlockchainService"""

    @pytest.fixture
    def mock_web3(self):
        """Mock Web3 instance"""
        web3_mock = Mock()
        web3_mock.is_connected.return_value = True
        web3_mock.eth.chain_id = 11155111  # Sepolia
        web3_mock.eth.get_transaction_count.return_value = 0
        web3_mock.eth.gas_price = 20000000000  # 20 Gwei
        web3_mock.eth.block_number = 5000000
        web3_mock.eth.account.from_key.return_value.address = "0x1234567890123456789012345678901234567890"
        return web3_mock

    @pytest.fixture
    def mock_contract(self):
        """Mock contract instance"""
        contract_mock = Mock()
        contract_mock.address = "0x1234567890123456789012345678901234567890"
        return contract_mock

    @pytest.fixture
    def blockchain_service(
        self,
        mock_web3,
        mock_contract,
        tmp_path
    ):
        """Create BlockchainService instance with mocked dependencies"""
        # Create temporary ABI file
        abi_path = tmp_path / "LexProofRegistry.abi"
        abi_path.write_text('[{"name":"registerProof","type":"function"}]')

        # Mock Web3
        with patch('lexproof.services.blockchain.Web3', return_value=mock_web3) as mock_web3_class:
            # Web3.to_checksum_address is a classmethod call the real service now
            # makes on the address it's given (see blockchain.py __init__); the
            # patched Web3 class needs it stubbed too, or it returns an
            # unconfigured MagicMock instead of the (already-checksummed) test
            # address.
            mock_web3_class.to_checksum_address.side_effect = lambda address: address
            with patch('lexproof.services.blockchain.eth.contract', return_value=mock_contract):
                with patch('lexproof.services.blockchain.requests.get'):
                    service = BlockchainService(
                        rpc_url="https://sepolia.infura.io/v3/test",
                        contract_address="0x1234567890123456789012345678901234567890",
                        private_key="test_private_key",
                        contract_abi=None
                    )
                    return service

    def test_initialization(self, blockchain_service):
        """Test BlockchainService initialization"""
        assert blockchain_service.rpc_url == "https://sepolia.infura.io/v3/test"

    def test_wait_for_receipt_success(self, blockchain_service):
        receipt = {"status": 1, "blockNumber": 12}
        blockchain_service.w3.eth.wait_for_transaction_receipt.return_value = receipt

        assert blockchain_service._wait_for_transaction_receipt(b"\x01" * 32) == receipt

    def test_wait_for_receipt_reverted(self, blockchain_service):
        blockchain_service.w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "blockNumber": 12,
        }

        receipt = blockchain_service._wait_for_transaction_receipt(b"\x01" * 32)
        assert receipt["status"] == 0

    def test_anchor_evidence_reverted_receipt_raises(self, blockchain_service):
        tx_hash = b"\x01" * 32
        function = blockchain_service.contract.functions.anchorEvidence.return_value
        function.estimate_gas.return_value = 21000
        function.build_transaction.return_value = {"gas": 21000, "gasPrice": 1}
        blockchain_service.w3.eth.account.sign_transaction.return_value.raw_transaction = b"signed"
        blockchain_service.w3.eth.send_raw_transaction.return_value = tx_hash
        blockchain_service.w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "blockNumber": 12,
        }

        with pytest.raises(ValueError, match="reverted"):
            blockchain_service.anchor_evidence("evidence-1", b"\x01" * 32)
        blockchain_service.w3.eth.send_raw_transaction.assert_called_once()

    def test_anchor_evidence_timeout_recovery_sends_once(self, blockchain_service):
        tx_hash = b"\x01" * 32
        function = blockchain_service.contract.functions.anchorEvidence.return_value
        function.estimate_gas.return_value = 21000
        function.build_transaction.return_value = {"gas": 21000, "gasPrice": 1}
        blockchain_service.w3.eth.account.sign_transaction.return_value.raw_transaction = b"signed"
        blockchain_service.w3.eth.send_raw_transaction.return_value = tx_hash
        blockchain_service.w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted()
        blockchain_service.w3.eth.get_transaction_receipt.return_value = {
            "status": 1,
            "blockNumber": 12,
        }
        blockchain_service.w3.eth.get_block.return_value = {"timestamp": 1700000000}

        result = blockchain_service.anchor_evidence("evidence-1", b"\x01" * 32)

        assert result == (tx_hash.hex(), 12, 1700000000)
        blockchain_service.w3.eth.send_raw_transaction.assert_called_once()

    def test_wait_timeout_recovers_mined_receipt(self, blockchain_service):
        tx_hash = b"\x01" * 32
        receipt = {"status": 1, "blockNumber": 12}
        blockchain_service.w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted()
        blockchain_service.w3.eth.get_transaction_receipt.return_value = receipt

        assert blockchain_service._wait_for_transaction_receipt(tx_hash) == receipt
        blockchain_service.w3.eth.get_transaction_receipt.assert_called_once_with(tx_hash)

    def test_wait_timeout_reports_pending_transaction(self, blockchain_service):
        tx_hash = b"\x01" * 32
        blockchain_service.w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted()
        blockchain_service.w3.eth.get_transaction_receipt.side_effect = TransactionNotFound("not found")
        blockchain_service.w3.eth.get_transaction.return_value = {
            "blockNumber": None,
            "blockHash": None,
        }

        with pytest.raises(RuntimeError, match="Transaction pending"):
            blockchain_service._wait_for_transaction_receipt(tx_hash)

    def test_wait_timeout_reports_unavailable_transaction(self, blockchain_service):
        tx_hash = b"\x01" * 32
        blockchain_service.w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted()
        blockchain_service.w3.eth.get_transaction_receipt.side_effect = TransactionNotFound("not found")
        blockchain_service.w3.eth.get_transaction.side_effect = TransactionNotFound("not found")

        with pytest.raises(RuntimeError, match="confirmation unavailable"):
            blockchain_service._wait_for_transaction_receipt(tx_hash)
        assert blockchain_service.contract_address == "0x1234567890123456789012345678901234567890"
        assert blockchain_service.chain_id == 11155111
        assert blockchain_service.contract == blockchain_service.contract

    def test_get_nonce(self, blockchain_service):
        """Test getting current nonce"""
        nonce = blockchain_service.get_nonce()
        assert nonce == 0

    def test_get_gas_price(self, blockchain_service):
        """Test getting gas price"""
        gas_price = blockchain_service.get_gas_price()
        assert gas_price == 20000000000

    def test_get_current_block_number(self, blockchain_service):
        """Test getting current block number"""
        block_number = blockchain_service.get_current_block_number()
        assert block_number == 5000000

    def test_get_anchor_transaction_hash_returns_matching_event_hash(self, blockchain_service):
        # get_anchor_transaction_hash fetches raw logs via w3.eth.get_logs (chunked,
        # provider-safe block ranges) and decodes each one with the contract event's own
        # process_log - not ContractEvent.get_logs(argument_filters=...), which Alchemy
        # rejected for this event with a JSON-RPC "Invalid params" error when tried
        # against the real chain. Mock at that same level.
        class DecodedLog:
            def __init__(self, evidence_hash):
                self.args = {"evidenceHash": evidence_hash}

        tx_hash = b"\xCC" * 32
        evidence_hash = b"\xAA" * 32
        raw_log = {"transactionHash": tx_hash}
        blockchain_service.w3.eth.get_logs.return_value = [raw_log]
        blockchain_service.contract.events.EvidenceAnchored.return_value.process_log.return_value = DecodedLog(evidence_hash)
        # get_anchor_transaction_hash first reads the anchor's on-chain timestamp so it
        # can jump straight to the right block window instead of brute-force-scanning
        # from the chain tip; mock that lookup and the binary search it feeds directly
        # rather than the whole chain of w3.eth.get_block calls behind it.
        blockchain_service.get_evidence_anchor = Mock(return_value={"anchored_at": 1700000000})
        blockchain_service._estimate_block_for_timestamp = Mock(return_value=4999990)

        assert blockchain_service.get_anchor_transaction_hash("evidence-1", "0x" + "aa" * 32) == "0x" + "cc" * 32
        # Should stop at the first (most recent) chunk once a match is found, not scan
        # the whole configured lookback window.
        assert blockchain_service.w3.eth.get_logs.call_count == 1

    def test_get_anchor_transaction_hash_raises_on_unmatched_event_hash(self, blockchain_service):
        class DecodedLog:
            def __init__(self, evidence_hash):
                self.args = {"evidenceHash": evidence_hash}

        raw_log = {"transactionHash": b"\x22" * 32}
        blockchain_service.w3.eth.get_logs.return_value = [raw_log]
        blockchain_service.contract.events.EvidenceAnchored.return_value.process_log.return_value = DecodedLog(b"\x11" * 32)
        # No on-chain anchor at all (the common case for this error): falls back to the
        # bounded recent-lookback scan from the chain tip.
        blockchain_service.get_evidence_anchor = Mock(return_value=None)
        # Bound the lookback so a genuinely-unmatched search terminates quickly in the test.
        blockchain_service._LOG_SCAN_MAX_LOOKBACK_BLOCKS = 20

        with pytest.raises(RuntimeError, match="No EvidenceAnchored transaction found"):
            blockchain_service.get_anchor_transaction_hash("evidence-1", "0x" + "aa" * 32)

    def test_create_blockchain_service_factory(self, tmp_path):
        """Test factory function to create BlockchainService"""
        # Create temporary ABI file
        abi_path = tmp_path / "LexProofRegistry.abi"
        abi_path.write_text('[{"name":"registerProof","type":"function"}]')

        with patch('lexproof.services.blockchain.Web3') as mock_web3_class:
            mock_web3_class.to_checksum_address.side_effect = lambda address: address
            with patch('lexproof.services.blockchain.requests.get'):
                with patch.dict('os.environ', {
                    'ETHEREUM_RPC_URL': 'https://sepolia.infura.io/v3/test',
                    'CONTRACT_ADDRESS': '0x1234567890123456789012345678901234567890',
                    'BLOCKCHAIN_PRIVATE_KEY': 'test_key'
                }):
                    service = create_blockchain_service()
                    assert service.rpc_url == "https://sepolia.infura.io/v3/test"
                    assert service.contract_address == "0x1234567890123456789012345678901234567890"


class TestBlockchainTransactionHandling:
    """Test suite for blockchain transaction handling"""

    @pytest.fixture
    def mock_web3_with_receipt(self):
        """Mock Web3 with transaction receipt"""
        web3_mock = Mock()
        web3_mock.is_connected.return_value = True
        web3_mock.eth.chain_id = 11155111
        web3_mock.eth.get_transaction_count.return_value = 0
        web3_mock.eth.gas_price = 20000000000
        web3_mock.eth.block_number = 5000000
        web3_mock.eth.account.from_key.return_value.address = "0x1234567890123456789012345678901234567890"

        # Mock transaction receipt
        receipt = {
            'status': 1,
            'blockNumber': 5000001,
            'transactionHash': b'\x01' * 32
        }
        web3_mock.eth.wait_for_transaction_receipt.return_value = receipt
        web3_mock.eth.send_raw_transaction.return_value = b'\x01' * 32

        return web3_mock

    @pytest.fixture
    def blockchain_service_with_receipt(self, mock_web3_with_receipt, tmp_path):
        """Create BlockchainService with mocked receipt"""
        abi_path = tmp_path / "LexProofRegistry.abi"
        abi_path.write_text('[{"name":"registerProof","type":"function"}]')

        with patch('lexproof.services.blockchain.Web3', return_value=mock_web3_with_receipt):
            with patch('lexproof.services.blockchain.eth.contract') as contract_factory:
                contract_factory.return_value = configure_contract_mock(MagicMock())
                with patch('lexproof.services.blockchain.requests.get'):
                    return BlockchainService(
                        rpc_url="https://sepolia.infura.io/v3/test",
                        contract_address="0x1234567890123456789012345678901234567890",
                        private_key="test_private_key"
                    )

    def test_register_proof_success(self, blockchain_service_with_receipt):
        """Test successful proof registration"""
        contract_hash = b'\x01' * 32
        policy_hash = b'\x02' * 32
        analysis_hash = b'\x03' * 32
        evidence_hash = b'\x04' * 32

        tx_hash, block_number = blockchain_service_with_receipt.register_proof(
            contract_hash=contract_hash,
            policy_hash=policy_hash,
            analysis_hash=analysis_hash,
            evidence_hash=evidence_hash,
            risk_score=75,
            compliance_score=85,
            policy_version="1.0.0",
            evidence_count=3
        )

        assert tx_hash is not None
        assert block_number == 5000001

    def test_register_proof_validation(self, blockchain_service_with_receipt):
        """Test proof registration validation"""
        # Test with invalid risk score
        with pytest.raises(ValueError, match="Risk score must be <= 100"):
            blockchain_service_with_receipt.register_proof(
                contract_hash=b'\x01' * 32,
                policy_hash=b'\x02' * 32,
                analysis_hash=b'\x03' * 32,
                evidence_hash=b'\x04' * 32,
                risk_score=101,  # Invalid
                compliance_score=85,
                policy_version="1.0.0",
                evidence_count=3
            )

        # Test with invalid compliance score
        with pytest.raises(ValueError, match="Compliance score must be <= 100"):
            blockchain_service_with_receipt.register_proof(
                contract_hash=b'\x01' * 32,
                policy_hash=b'\x02' * 32,
                analysis_hash=b'\x03' * 32,
                evidence_hash=b'\x04' * 32,
                risk_score=75,
                compliance_score=101,  # Invalid
                policy_version="1.0.0",
                evidence_count=3
            )

    def test_verify_proof(self, blockchain_service_with_receipt):
        """Test proof verification"""
        proof_id = b'\x01' * 32
        contract_hash = b'\x01' * 32
        policy_hash = b'\x02' * 32
        analysis_hash = b'\x03' * 32
        evidence_hash = b'\x04' * 32

        is_valid = blockchain_service_with_receipt.verify_proof(
            proof_id,
            contract_hash,
            policy_hash,
            analysis_hash,
            evidence_hash
        )

        assert is_valid is True

    def test_get_proof(self, blockchain_service_with_receipt):
        """Test getting proof details"""
        proof_id = b'\x01' * 32

        proof = blockchain_service_with_receipt.get_proof(proof_id)

        assert proof['contract_hash'] == (b'\x01' * 32).hex()
        assert proof['policy_hash'] == (b'\x02' * 32).hex()
        assert proof['risk_score'] == 75
        assert proof['compliance_score'] == 85
        assert proof['policy_version'] == "1.0.0"
        assert proof['evidence_count'] == 3
        assert proof['status'] == "confirmed"


class TestTransactionStatus:
    """Test suite for transaction status tracking"""

    @pytest.fixture
    def mock_web3_with_receipt(self):
        """Mock Web3 with transaction receipt"""
        web3_mock = Mock()
        web3_mock.is_connected.return_value = True
        web3_mock.eth.chain_id = 11155111
        web3_mock.eth.get_transaction_count.return_value = 0
        web3_mock.eth.gas_price = 20000000000
        web3_mock.eth.block_number = 5000001
        web3_mock.eth.account.from_key.return_value.address = "0x1234567890123456789012345678901234567890"

        receipt = {
            'status': 1,
            'blockNumber': 5000001,
            'transactionHash': b'\x01' * 32
        }
        web3_mock.eth.wait_for_transaction_receipt.return_value = receipt
        web3_mock.eth.send_raw_transaction.return_value = b'\x01' * 32

        return web3_mock

    @pytest.fixture
    def blockchain_service(self, mock_web3_with_receipt, tmp_path):
        """Create BlockchainService instance"""
        abi_path = tmp_path / "LexProofRegistry.abi"
        abi_path.write_text('[{"name":"registerProof","type":"function"}]')

        with patch('lexproof.services.blockchain.Web3', return_value=mock_web3_with_receipt):
            with patch('lexproof.services.blockchain.eth.contract') as contract_factory:
                contract_factory.return_value = configure_contract_mock(MagicMock())
                with patch('lexproof.services.blockchain.requests.get'):
                    return BlockchainService(
                        rpc_url="https://sepolia.infura.io/v3/test",
                        contract_address="0x1234567890123456789012345678901234567890",
                        private_key="test_private_key"
                    )

    def test_get_transaction(self, blockchain_service):
        """Test getting transaction details"""
        proof_id = b'\x01' * 32

        tx_hash_bytes, block_number, timestamp = blockchain_service.get_transaction(proof_id)

        assert tx_hash_bytes == b'\x01' * 32
        assert block_number == 5000001
        assert timestamp > 0


class TestEIP1559Transactions:
    """Test suite for EIP-1559 transaction support"""

    @pytest.fixture
    def mock_web3_eip1559(self):
        """Mock Web3 with EIP-1559 support"""
        web3_mock = Mock()
        web3_mock.is_connected.return_value = True
        web3_mock.eth.chain_id = 11155111
        web3_mock.eth.get_transaction_count.return_value = 0
        web3_mock.eth.gas_price = 20000000000  # Legacy gas price
        web3_mock.eth.block_number = 5000000
        web3_mock.eth.account.from_key.return_value.address = "0x1234567890123456789012345678901234567890"

        receipt = {
            'status': 1,
            'blockNumber': 5000001,
            'transactionHash': b'\x01' * 32
        }
        web3_mock.eth.wait_for_transaction_receipt.return_value = receipt
        web3_mock.eth.send_raw_transaction.return_value = b'\x01' * 32

        return web3_mock

    @pytest.fixture
    def blockchain_service_eip1559(self, mock_web3_eip1559, tmp_path):
        """Create BlockchainService with EIP-1559 support"""
        abi_path = tmp_path / "LexProofRegistry.abi"
        abi_path.write_text('[{"name":"registerProof","type":"function"}]')

        with patch('lexproof.services.blockchain.Web3', return_value=mock_web3_eip1559):
            with patch('lexproof.services.blockchain.eth.contract') as contract_factory:
                contract_factory.return_value = configure_contract_mock(MagicMock())
                with patch('lexproof.services.blockchain.requests.get'):
                    return BlockchainService(
                        rpc_url="https://sepolia.infura.io/v3/test",
                        contract_address="0x1234567890123456789012345678901234567890",
                        private_key="test_private_key"
                    )

    def test_register_proof_with_eip1559(self, blockchain_service_eip1559):
        """Test proof registration with EIP-1559 parameters"""
        contract_hash = b'\x01' * 32
        policy_hash = b'\x02' * 32
        analysis_hash = b'\x03' * 32
        evidence_hash = b'\x04' * 32

        tx_hash, block_number = blockchain_service_eip1559.register_proof(
            contract_hash=contract_hash,
            policy_hash=policy_hash,
            analysis_hash=analysis_hash,
            evidence_hash=evidence_hash,
            risk_score=75,
            compliance_score=85,
            policy_version="1.0.0",
            evidence_count=3,
            max_fee_per_gas=50000000000,  # 50 Gwei
            max_priority_fee_per_gas=2000000000  # 2 Gwei
        )

        assert tx_hash is not None
        assert block_number == 5000001


class TestBlockchainServiceErrorHandling:
    """Test suite for blockchain service error handling"""

    @pytest.fixture
    def mock_web3_error(self):
        """Mock Web3 with error conditions"""
        web3_mock = Mock()
        web3_mock.is_connected.return_value = False
        return web3_mock

    @pytest.fixture
    def blockchain_service_error(self, mock_web3_error, tmp_path):
        """Create BlockchainService with error conditions"""
        abi_path = tmp_path / "LexProofRegistry.abi"
        abi_path.write_text('[{"name":"registerProof","type":"function"}]')

        with patch('lexproof.services.blockchain.Web3', return_value=mock_web3_error):
            with patch('lexproof.services.blockchain.eth.contract'):
                with patch('lexproof.services.blockchain.requests.get'):
                    return BlockchainService(
                        rpc_url="https://sepolia.infura.io/v3/test",
                        contract_address="0x1234567890123456789012345678901234567890",
                        private_key="test_private_key"
                    )

    def test_connection_error(self, blockchain_service_error):
        """Test handling of connection errors"""
        with pytest.raises(ConnectionError):
            blockchain_service_error.get_nonce()

    def test_invalid_chain_id(self, tmp_path):
        """Test handling of invalid chain ID"""
        abi_path = tmp_path / "LexProofRegistry.abi"
        abi_path.write_text('[{"name":"registerProof","type":"function"}]')

        with patch('lexproof.services.blockchain.Web3'):
            with patch('lexproof.services.blockchain.eth.contract'):
                with patch('lexproof.services.blockchain.requests.get'):
                    service = BlockchainService(
                        rpc_url="https://sepolia.infura.io/v3/test",
                        contract_address="0x1234567890123456789012345678901234567890",
                        private_key="test_private_key"
                    )
                    service.w3.eth.chain_id = 1  # Mainnet instead of Sepolia
                    with pytest.raises(ValueError, match="Wrong network"):
                        service.get_current_block_number()
