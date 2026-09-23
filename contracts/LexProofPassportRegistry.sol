// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title LexProofPassportRegistry
 * @dev Additive smart contract for anchoring LexProof Legal Passport ROOT commitments
 * (`metadata.passport_hash`, canonicalization v1) on Ethereum Sepolia.
 *
 * This contract is deliberately separate from `LexProofRegistry`, which continues to
 * anchor per-evidence-item hashes via `anchorEvidence` at its own, unchanged address.
 * Deploying/using this contract must never require any change to `LexProofRegistry`,
 * its storage, or its historical `evidenceAnchors`/`proofs` state.
 *
 * SECURITY: Only a 32-byte passport root commitment, a 32-byte passport identity key,
 * a timestamp, and the anchoring registrar address are stored on-chain. This contract
 * never stores contract text, evidence content, analysis JSON, supplier names, tenant
 * IDs, user IDs, email addresses, filenames, raw document bytes, risk scores, compliance
 * scores, or policy content.
 *
 * Identity model:
 *   passportKey  = keccak256(bytes(passport_id))   -- computed off-chain by the backend;
 *                  the passport_id UUID itself is never sent as plaintext calldata.
 *   passportRoot = bytes32 decode of the existing v1 `metadata.passport_hash` SHA-256
 *                  hex digest (`bytes.fromhex(passport_hash)`), unchanged from today's
 *                  off-chain algorithm.
 *
 * Immutability model: first-write-wins. A given `passportKey` may be anchored exactly
 * once; any second `anchorPassportRoot` call for the same key reverts, whether the
 * caller supplies the same root (already anchored -- callers should recover the
 * existing anchor off-chain instead of resubmitting) or a different root (hard failure
 * -- this contract never overwrites, updates, or silently replaces a passport's root).
 */
contract LexProofPassportRegistry is Ownable, ReentrancyGuard {
    mapping(address => bool) public authorizedRegistrars;

    struct PassportRootAnchor {
        bytes32 passportRoot; // SHA-256 metadata.passport_hash, decoded to bytes32
        uint256 timestamp;    // block.timestamp at anchoring
        address anchoredBy;   // registrar address that submitted the anchor
    }

    mapping(bytes32 => PassportRootAnchor) public passportRoots;

    event PassportRootAnchored(
        bytes32 indexed passportKey,
        bytes32 indexed passportRoot,
        uint256 timestamp,
        address indexed anchoredBy
    );

    event RegistrarAuthorizationChanged(address indexed registrar, bool authorized);

    modifier onlyRegistrar() {
        require(authorizedRegistrars[msg.sender], "Not authorized registrar");
        _;
    }

    /**
     * @dev Constructor. Mirrors LexProofRegistry's registrar bootstrap model:
     * the initial owner is authorized as a registrar so the existing, already-funded
     * and already-authorized registrar signer can be granted access on this new
     * contract the same way it was granted on the item registry.
     * @param initialOwner Address of the initial owner (deployer / existing registrar)
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
     * @dev Anchor a Legal Passport root commitment. First-write-wins: reverts if this
     * passportKey already has an anchor, regardless of whether the supplied root matches
     * the existing one. Callers (the backend service) must check for an existing anchor
     * off-chain first and treat a matching existing anchor as an idempotent success
     * without calling this function again.
     * @param passportKey keccak256(bytes(passport_id)), computed off-chain
     * @param passportRoot bytes32 decode of the existing v1 metadata.passport_hash
     */
    function anchorPassportRoot(bytes32 passportKey, bytes32 passportRoot)
        external
        onlyRegistrar
        nonReentrant
    {
        require(passportKey != bytes32(0), "Passport key cannot be zero");
        require(passportRoot != bytes32(0), "Passport root cannot be zero");
        require(
            passportRoots[passportKey].passportRoot == bytes32(0),
            "Passport root already anchored"
        );

        passportRoots[passportKey] = PassportRootAnchor({
            passportRoot: passportRoot,
            timestamp: block.timestamp,
            anchoredBy: msg.sender
        });

        emit PassportRootAnchored(passportKey, passportRoot, block.timestamp, msg.sender);
    }

    /**
     * @dev Compare a candidate root against the anchored root for a passport key.
     * @return true only if an anchor exists for passportKey and its root matches exactly.
     */
    function verifyPassportRoot(bytes32 passportKey, bytes32 passportRoot)
        external
        view
        returns (bool)
    {
        PassportRootAnchor memory anchor = passportRoots[passportKey];
        return anchor.passportRoot != bytes32(0) && anchor.passportRoot == passportRoot;
    }

    /**
     * @dev Read the anchor for a passport key. Reverts if no anchor exists yet -- callers
     * (the backend service) should treat that revert as "not anchored" rather than an
     * unexpected error, matching LexProofRegistry.getEvidenceAnchor's convention.
     */
    function getPassportRoot(bytes32 passportKey)
        external
        view
        returns (bytes32 passportRoot, uint256 timestamp, address anchoredBy)
    {
        PassportRootAnchor memory anchor = passportRoots[passportKey];
        require(anchor.passportRoot != bytes32(0), "Passport root does not exist");
        return (anchor.passportRoot, anchor.timestamp, anchor.anchoredBy);
    }
}
