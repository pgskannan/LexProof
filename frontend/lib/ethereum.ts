'use client'

/**
 * Client-side Ethereum operations using ethers.js with dynamic imports.
 * This module ensures ethers is only loaded in the browser, never during SSR.
 *
 * All functions in this module are async and use dynamic imports to avoid
 * Next.js chunk loading issues.
 */

export interface EthereumAnchorRead {
  evidenceHash: string | null
  timestamp: number | null
  anchoredBy: string | null
  transactionHash: string | null
  blockNumber: number | null
}

const ETHEREUM_SEPOLIA_RPC_URL = process.env.NEXT_PUBLIC_ETHEREUM_SEPOLIA_RPC_URL ?? 'https://ethereum-sepolia-rpc.publicnode.com'
const LEXPROOF_CONTRACT_ADDRESS = process.env.NEXT_PUBLIC_LEXPROOF_CONTRACT_ADDRESS ?? '0x0000000000000000000000000000000000000000'
const ETHEREUM_SEPOLIA_EXPLORER = 'https://sepolia.etherscan.io'

const EVIDENCE_ANCHOR_ABI = [
  'function getEvidenceAnchor(string) view returns (bytes32 evidenceHash, uint256 timestamp, address anchoredBy)',
  'event EvidenceAnchored(string indexed recordId, bytes32 indexed evidenceHash, uint256 timestamp, address anchoredBy)',
]

/**
 * Read an evidence anchor directly from the LexProofRegistry contract on Ethereum Sepolia.
 * Uses dynamic import to ensure ethers is only loaded in the browser.
 */
export async function readEvidenceAnchorFromEthereum(evidenceId: string): Promise<EthereumAnchorRead | null> {
  try {
    // Dynamic import ensures ethers is only loaded when this function runs (browser only)
    const { ethers } = await import('ethers')

    const provider = new ethers.JsonRpcProvider(ETHEREUM_SEPOLIA_RPC_URL)
    const contract = new ethers.Contract(LEXPROOF_CONTRACT_ADDRESS, EVIDENCE_ANCHOR_ABI, provider)

    const [onChainHash, timestamp, anchoredBy] = await contract.getEvidenceAnchor(evidenceId)
    if (!onChainHash || onChainHash === '0x0000000000000000000000000000000000000000000000000000000000000000') {
      return null
    }

    // The transaction hash/block number are a display-only nicety (Etherscan link, block).
    // Public RPC providers cap eth_getLogs to a bounded block range (e.g. 50k blocks), so
    // this lookup is scoped to recent history and allowed to fail independently: a failure
    // here must never turn a genuinely verified on-chain hash into a false "not found".
    let matchingLog: { transactionHash: string; blockNumber: number } | null = null
    try {
      const latestBlock = await provider.getBlockNumber()
      const fromBlock = Math.max(latestBlock - 45000, 0)
      const logs = await contract.queryFilter(contract.filters.EvidenceAnchored(evidenceId), fromBlock, latestBlock)
      const found = logs.find((log) => {
        const args = (log as any).args as { evidenceHash?: string } | undefined
        return args?.evidenceHash && ethers.hexlify(args.evidenceHash).toLowerCase() === ethers.hexlify(onChainHash).toLowerCase()
      })
      if (found) {
        matchingLog = { transactionHash: found.transactionHash, blockNumber: Number(found.blockNumber) }
      }
    } catch (logError) {
      console.warn('Unable to fetch anchoring transaction log for evidence', evidenceId, logError)
    }

    return {
      evidenceHash: ethers.hexlify(onChainHash),
      timestamp: Number(timestamp),
      anchoredBy: anchoredBy ?? null,
      transactionHash: matchingLog ? matchingLog.transactionHash : null,
      blockNumber: matchingLog ? matchingLog.blockNumber : null,
    }
  } catch (error) {
    console.warn('Unable to read Ethereum anchor for evidence', evidenceId, error)
    return null
  }
}

/**
 * Get a URL to view a transaction on Sepolia Etherscan.
 */
export function getEtherscanTransactionUrl(txHash: string): string {
  return `${ETHEREUM_SEPOLIA_EXPLORER}/tx/${txHash}`
}

/**
 * Get a URL to view an address on Sepolia Etherscan.
 */
export function getEtherscanAddressUrl(address: string): string {
  return `${ETHEREUM_SEPOLIA_EXPLORER}/address/${address}`
}
