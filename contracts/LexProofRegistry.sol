// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title LexProofRegistry
 * @dev Smart contract for anchoring LexProof legal evidence fingerprints on Ethereum Sepolia
 * 
 * SECURITY: Only stores hashes and non-sensitive metadata. Never stores contract content,
 * PII, contract text, or AI findings directly on-chain.
 * 
 * Features:
 * - Immutable proof registration with SHA-256 hash verification
 * - Access control for proof registration
 * - Prevention of accidental overwrite
 * - Event logging for audit trail
 */
contract LexProofRegistry is Ownable, ReentrancyGuard {
    mapping(address => bool) public authorizedRegistrars;
    
    // Status constants
    enum ProofStatus {
        PENDING,
        CONFIRMED,
        FAILED
    }
    
    // Proof structure
    struct Proof {
        bytes32 contractHash;      // SHA-256 hash of the contract
        bytes32 policyHash;        // SHA-256 hash of the policy
        bytes32 analysisHash;      // SHA-256 hash of the analysis
        bytes32 evidenceHash;      // SHA-256 hash of all evidence
        uint256 riskScore;         // Risk score (0-100)
        uint256 complianceScore;   // Compliance score (0-100)
        string policyVersion;      // Policy version
        uint256 evidenceCount;     // Number of evidence items
        uint256 timestamp;         // Registration timestamp
        address registeredBy;      // Address that registered the proof
        ProofStatus status;        // Proof status
    }
    
    // Transaction structure
    struct Transaction {
        bytes32 proofId;           // Associated proof ID
        bytes transactionHash;     // Ethereum transaction hash
        uint256 blockNumber;       // Block number
        uint256 timestamp;         // Transaction timestamp
    }
    
    // Counters
    uint256 private proofCounter;
    
    // State variables
    mapping(bytes32 => Proof) public proofs;
    mapping(bytes32 => Transaction) public transactions;
    bytes32[] public proofIds;

    struct EvidenceAnchor {
        bytes32 evidenceHash;
        uint256 timestamp;
        address anchoredBy;
    }

    mapping(bytes32 => EvidenceAnchor) public evidenceAnchors;
    
    // Events
    event ProofRegistered(
        bytes32 indexed proofId,
        bytes32 contractHash,
        bytes32 policyHash,
        bytes32 analysisHash,
        bytes32 evidenceHash,
        uint256 riskScore,
        uint256 complianceScore,
        string policyVersion,
        uint256 evidenceCount,
        uint256 timestamp,
        address indexed registeredBy
    );
    
    event ProofUpdated(
        bytes32 indexed proofId,
        uint256 newStatus,
        bytes transactionHash,
        uint256 blockNumber
    );
    
    event ProofVerified(
        bytes32 indexed proofId,
        bool isValid,
        uint256 timestamp
    );

    event RegistrarAuthorizationChanged(address indexed registrar, bool authorized);

    event EvidenceAnchored(
        string indexed recordId,
        bytes32 indexed evidenceHash,
        uint256 timestamp,
        address indexed anchoredBy
    );

    modifier onlyRegistrar() {
        require(authorizedRegistrars[msg.sender], "Not authorized registrar");
        _;
    }

    function anchorEvidence(string calldata recordId, bytes32 evidenceHash)
        external
        onlyRegistrar
        nonReentrant
    {
        require(bytes(recordId).length > 0, "Record ID cannot be empty");
        require(evidenceHash != bytes32(0), "Evidence hash cannot be zero");
        bytes32 recordKey = keccak256(bytes(recordId));
        require(evidenceAnchors[recordKey].evidenceHash == bytes32(0), "Evidence already anchored");

        evidenceAnchors[recordKey] = EvidenceAnchor({
            evidenceHash: evidenceHash,
            timestamp: block.timestamp,
            anchoredBy: msg.sender
        });

        emit EvidenceAnchored(recordId, evidenceHash, block.timestamp, msg.sender);
    }

    function verifyEvidence(string calldata recordId, bytes32 evidenceHash)
        external
        view
        returns (bool)
    {
        bytes32 recordKey = keccak256(bytes(recordId));
        EvidenceAnchor memory anchor = evidenceAnchors[recordKey];
        return anchor.evidenceHash != bytes32(0) && anchor.evidenceHash == evidenceHash;
    }

    function getEvidenceAnchor(string calldata recordId)
        external
        view
        returns (bytes32 evidenceHash, uint256 timestamp, address anchoredBy)
    {
        EvidenceAnchor memory anchor = evidenceAnchors[keccak256(bytes(recordId))];
        require(anchor.evidenceHash != bytes32(0), "Evidence anchor does not exist");
        return (anchor.evidenceHash, anchor.timestamp, anchor.anchoredBy);
    }
    
    /**
     * @dev Constructor
     * @param initialOwner Address of the initial owner (deployer)
     */
    constructor(address initialOwner) Ownable(initialOwner) {
        require(initialOwner != address(0), "Invalid owner address");
        authorizedRegistrars[initialOwner] = true;
    }

    function setRegistrar(address registrar, bool authorized) external onlyOwner {
        require(registrar != address(0), "Invalid registrar address");
        authorizedRegistrars[registrar] = authorized;
        emit RegistrarAuthorizationChanged(registrar, authorized);
    }
    
    /**
     * @dev Register a new proof on-chain
     * @param contractHash SHA-256 hash of the contract document
     * @param policyHash SHA-256 hash of the policy
     * @param analysisHash SHA-256 hash of the AI analysis
     * @param evidenceHash SHA-256 hash of all evidence items
     * @param riskScore Risk score (0-100)
     * @param complianceScore Compliance score (0-100)
     * @param policyVersion Version of the policy
     * @param evidenceCount Number of evidence items
     * @return proofId The ID of the registered proof
     */
    function registerProof(
        bytes32 contractHash,
        bytes32 policyHash,
        bytes32 analysisHash,
        bytes32 evidenceHash,
        uint256 riskScore,
        uint256 complianceScore,
        string memory policyVersion,
        uint256 evidenceCount
    ) external onlyRegistrar nonReentrant returns (bytes32 proofId) {
        require(contractHash != bytes32(0), "Contract hash cannot be zero");
        require(policyHash != bytes32(0), "Policy hash cannot be zero");
        require(analysisHash != bytes32(0), "Analysis hash cannot be zero");
        require(evidenceHash != bytes32(0), "Evidence hash cannot be zero");
        require(riskScore <= 100, "Risk score must be <= 100");
        require(complianceScore <= 100, "Compliance score must be <= 100");
        require(bytes(policyVersion).length > 0, "Policy version cannot be empty");
        require(evidenceCount > 0, "Evidence count must be > 0");
        
        proofId = keccak256(abi.encode(contractHash, policyHash, analysisHash, evidenceHash));
        if (proofs[proofId].contractHash != bytes32(0)) {
            return proofId;
        }
        proofCounter += 1;
        
        // Create proof entry
        proofs[proofId] = Proof({
            contractHash: contractHash,
            policyHash: policyHash,
            analysisHash: analysisHash,
            evidenceHash: evidenceHash,
            riskScore: riskScore,
            complianceScore: complianceScore,
            policyVersion: policyVersion,
            evidenceCount: evidenceCount,
            timestamp: block.timestamp,
            registeredBy: msg.sender,
            status: ProofStatus.CONFIRMED
        });
        
        proofIds.push(proofId);
        
        // Emit event
        emit ProofRegistered(
            proofId,
            contractHash,
            policyHash,
            analysisHash,
            evidenceHash,
            riskScore,
            complianceScore,
            policyVersion,
            evidenceCount,
            block.timestamp,
            msg.sender
        );
    }
    
    /**
     * @dev Verify a proof by comparing hashes
     * @param proofId The ID of the proof to verify
     * @param contractHash The contract hash to verify
     * @param policyHash The policy hash to verify
     * @param analysisHash The analysis hash to verify
     * @param evidenceHash The evidence hash to verify
     * @return isValid True if all hashes match, false otherwise
     */
    function verifyProof(
        bytes32 proofId,
        bytes32 contractHash,
        bytes32 policyHash,
        bytes32 analysisHash,
        bytes32 evidenceHash
    ) external view returns (bool isValid) {
        require(proofId != bytes32(0), "Proof ID cannot be zero");
        require(proofs[proofId].status == ProofStatus.CONFIRMED, "Proof is not confirmed");
        
        isValid = (
            proofs[proofId].contractHash == contractHash &&
            proofs[proofId].policyHash == policyHash &&
            proofs[proofId].analysisHash == analysisHash &&
            proofs[proofId].evidenceHash == evidenceHash
        );
        
        // Verification is deliberately a read-only operation; no event is emitted.
    }
    
    /**
     * @dev Get proof details
     * @param proofId The ID of the proof
     * @return contractHash Contract hash
     * @return policyHash Policy hash
     * @return analysisHash Analysis hash
     * @return evidenceHash Evidence hash
     * @return riskScore Risk score
     * @return complianceScore Compliance score
     * @return policyVersion Policy version
     * @return evidenceCount Evidence count
     * @return timestamp Timestamp
     * @return registeredBy Address that registered the proof
     * @return status Proof status
     */
    function getProof(bytes32 proofId) 
        external 
        view 
        returns (
            bytes32 contractHash,
            bytes32 policyHash,
            bytes32 analysisHash,
            bytes32 evidenceHash,
            uint256 riskScore,
            uint256 complianceScore,
            string memory policyVersion,
            uint256 evidenceCount,
            uint256 timestamp,
            address registeredBy,
            ProofStatus status
        ) 
    {
        require(proofId != bytes32(0), "Proof ID cannot be zero");
        require(proofs[proofId].contractHash != bytes32(0), "Proof does not exist");
        
        Proof memory proof = proofs[proofId];
        return (
            proof.contractHash,
            proof.policyHash,
            proof.analysisHash,
            proof.evidenceHash,
            proof.riskScore,
            proof.complianceScore,
            proof.policyVersion,
            proof.evidenceCount,
            proof.timestamp,
            proof.registeredBy,
            proof.status
        );
    }
    
    /**
     * @dev Get transaction details for a proof
     * @param proofId The ID of the proof
     * @return transactionHash Transaction hash
     * @return blockNumber Block number
     * @return timestamp Transaction timestamp
     */
    function getTransaction(bytes32 proofId) 
        external 
        view 
        returns (bytes memory transactionHash, uint256 blockNumber, uint256 timestamp)
    {
        require(proofId != bytes32(0), "Proof ID cannot be zero");
        require(transactions[proofId].proofId != bytes32(0), "Transaction does not exist");
        
        Transaction memory transactionRecord = transactions[proofId];
        return (
            transactionRecord.transactionHash,
            transactionRecord.blockNumber,
            transactionRecord.timestamp
        );
    }
    
    /**
     * @dev Get all proof IDs
     * @return Array of proof IDs
     */
    function getAllProofIds() external view returns (bytes32[] memory) {
        return proofIds;
    }
    
    /**
     * @dev Get proof count
     * @return Number of proofs
     */
    function getProofCount() external view returns (uint256) {
        return proofCounter;
    }
    
    /**
     * @dev Update proof status (only owner)
     * @param proofId The ID of the proof
     * @param status New status
     * @param transactionHash Optional transaction hash for update
     * @param blockNumber Optional block number for update
     */
    function updateProofStatus(
        bytes32 proofId,
        ProofStatus status,
        bytes memory transactionHash,
        uint256 blockNumber
    ) external onlyOwner {
        require(proofId != bytes32(0), "Proof ID cannot be zero");
        require(proofs[proofId].contractHash != bytes32(0), "Proof does not exist");
        
        proofs[proofId].status = status;
        
        if (transactions[proofId].proofId == bytes32(0)) {
            transactions[proofId] = Transaction({
                proofId: proofId,
                transactionHash: transactionHash,
                blockNumber: blockNumber,
                timestamp: block.timestamp
            });
        }
        
        emit ProofUpdated(proofId, uint256(status), transactionHash, blockNumber);
    }
}
