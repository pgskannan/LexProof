export type ChainCheckStatus = 'idle' | 'loading' | 'match' | 'mismatch' | 'not_anchored' | 'error'

export interface ChainCheckResult {
  status: ChainCheckStatus
  onChainHash: string | null
  onChainTimestamp: string | null
  anchoredBy: string | null
  message: string
}

export const SEPOLIA_RPC_URL =
  process.env.NEXT_PUBLIC_ETHEREUM_SEPOLIA_RPC_URL || 'https://ethereum-sepolia-rpc.publicnode.com'

export const REGISTRY_CONTRACT_ADDRESS = process.env.NEXT_PUBLIC_LEXPROOF_CONTRACT_ADDRESS || ''

export const REGISTRY_ABI = [
  'function getEvidenceAnchor(string) view returns (bytes32 evidenceHash, uint256 timestamp, address anchoredBy)',
]

/**
 * Independently verify an evidence hash directly against the LexProofRegistry
 * contract on Ethereum Sepolia, from the browser, using a public RPC endpoint.
 *
 * This does NOT go through the LexProof backend at all — it is a second,
 * independent path to the same on-chain fact, so a visitor doesn't have to
 * trust the backend's word for what is (or isn't) anchored on-chain.
 */
export async function verifyOnChainIndependently(
  evidenceId: string,
  expectedHash: string | null,
  options?: {
    rpcUrl?: string
    contractAddress?: string
  },
): Promise<ChainCheckResult> {
  const contractAddress = options?.contractAddress || REGISTRY_CONTRACT_ADDRESS
  const rpcUrl = options?.rpcUrl || SEPOLIA_RPC_URL

  if (!contractAddress) {
    return {
      status: 'error',
      onChainHash: null,
      onChainTimestamp: null,
      anchoredBy: null,
      message: 'Registry contract address is not configured on this deployment.',
    }
  }

  try {
    const { ethers } = await import('ethers')
    const provider = new ethers.JsonRpcProvider(rpcUrl)
    const contract = new ethers.Contract(contractAddress, REGISTRY_ABI, provider)

    const [evidenceHash, timestamp, anchoredBy] = await contract.getEvidenceAnchor(evidenceId)
    const onChainHash: string = evidenceHash.toString().toLowerCase()
    const zeroHash = '0x' + '0'.repeat(64)

    if (!onChainHash || onChainHash === zeroHash) {
      return {
        status: 'not_anchored',
        onChainHash: null,
        onChainTimestamp: null,
        anchoredBy: null,
        message: 'The contract has no anchor for this evidence ID.',
      }
    }

    const onChainTimestamp = new Date(Number(timestamp) * 1000).toLocaleString()
    const normalizedExpected = expectedHash ? `0x${expectedHash.replace(/^0x/i, '').toLowerCase()}` : null

    if (normalizedExpected && normalizedExpected === onChainHash) {
      return {
        status: 'match',
        onChainHash,
        onChainTimestamp,
        anchoredBy,
        message: 'The hash read directly from the smart contract matches the recomputed evidence hash.',
      }
    }

    return {
      status: 'mismatch',
      onChainHash,
      onChainTimestamp,
      anchoredBy,
      message: normalizedExpected
        ? 'The hash read directly from the smart contract does NOT match the recomputed evidence hash.'
        : 'Read an on-chain hash, but no recomputed hash was available to compare it against.',
    }
  } catch (err) {
    const reason =
      (err as { shortMessage?: string; reason?: string; message?: string })?.shortMessage ||
      (err as { reason?: string })?.reason ||
      (err instanceof Error ? err.message : String(err))

    if (typeof reason === 'string' && reason.toLowerCase().includes('evidence anchor does not exist')) {
      return {
        status: 'not_anchored',
        onChainHash: null,
        onChainTimestamp: null,
        anchoredBy: null,
        message: 'The contract has no anchor for this evidence ID.',
      }
    }

    return {
      status: 'error',
      onChainHash: null,
      onChainTimestamp: null,
      anchoredBy: null,
      message: `Could not reach Ethereum Sepolia directly from your browser: ${reason}`,
    }
  }
}
