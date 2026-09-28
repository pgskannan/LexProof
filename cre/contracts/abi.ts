// Minimal read-only ABIs for the two LexProof registries on Ethereum Sepolia.
// Both use the contracts' public mapping getters, which return zero values for
// a missing key instead of reverting (unlike getEvidenceAnchor/getPassportRoot).

// LexProofRegistry (contracts/LexProofRegistry.sol):
//   mapping(bytes32 => EvidenceAnchor) public evidenceAnchors;  key = keccak256(bytes(evidenceId))
export const LexProofRegistry = [
  {
    type: 'function',
    name: 'evidenceAnchors',
    stateMutability: 'view',
    inputs: [{ name: 'recordKey', type: 'bytes32' }],
    outputs: [
      { name: 'evidenceHash', type: 'bytes32' },
      { name: 'timestamp', type: 'uint256' },
      { name: 'anchoredBy', type: 'address' },
    ],
  },
] as const

// LexProofPassportRegistry (contracts/LexProofPassportRegistry.sol):
//   mapping(bytes32 => PassportRootAnchor) public passportRoots;  key = keccak256(UTF-8(passportId))
export const LexProofPassportRegistry = [
  {
    type: 'function',
    name: 'passportRoots',
    stateMutability: 'view',
    inputs: [{ name: 'passportKey', type: 'bytes32' }],
    outputs: [
      { name: 'passportRoot', type: 'bytes32' },
      { name: 'timestamp', type: 'uint256' },
      { name: 'anchoredBy', type: 'address' },
    ],
  },
] as const
