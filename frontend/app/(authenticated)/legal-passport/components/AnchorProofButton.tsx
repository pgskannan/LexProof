'use client'

import { useEffect, useState } from 'react'
import { Anchor, CheckCircle2, Clock, FileText, Hash, Network, XCircle } from 'lucide-react'
import { Contract, ethers } from 'ethers'
import { toast } from 'sonner'
import { apiFetch } from '../../../../lib/api'
import { hashEvidenceItem } from '../../../../lib/evidenceHash'

const ETHEREUM_SEPOLIA_RPC_URL = process.env.NEXT_PUBLIC_ETHEREUM_SEPOLIA_RPC_URL ?? 'https://ethereum-sepolia-rpc.publicnode.com'
const LEXPROOF_CONTRACT_ADDRESS = process.env.NEXT_PUBLIC_LEXPROOF_CONTRACT_ADDRESS ?? '0x0000000000000000000000000000000000000000'
const ETHEREUM_SEPOLIA_EXPLORER = 'https://sepolia.etherscan.io'

const EVIDENCE_ANCHOR_ABI = [
  'function getEvidenceAnchor(string) view returns (bytes32 evidenceHash, uint256 timestamp, address anchoredBy)',
  'event EvidenceAnchored(string indexed recordId, bytes32 indexed evidenceHash, uint256 timestamp, address anchoredBy)',
]

export interface EthereumAnchorRead {
  evidenceHash: string | null
  timestamp: number | null
  anchoredBy: string | null
  transactionHash: string | null
  blockNumber: number | null
}

export function getEvidenceAnchorContract(provider?: ethers.Provider | ethers.Signer): Contract {
  const targetProvider = provider ?? new ethers.JsonRpcProvider(ETHEREUM_SEPOLIA_RPC_URL)
  return new ethers.Contract(LEXPROOF_CONTRACT_ADDRESS, EVIDENCE_ANCHOR_ABI, targetProvider)
}

export async function readEvidenceAnchorFromEthereum(evidenceId: string): Promise<EthereumAnchorRead | null> {
  try {
    const provider = new ethers.JsonRpcProvider(ETHEREUM_SEPOLIA_RPC_URL)
    const contract = getEvidenceAnchorContract(provider)
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

export function getEtherscanTransactionUrl(txHash: string): string {
  return `${ETHEREUM_SEPOLIA_EXPLORER}/tx/${txHash}`
}

interface EvidenceAnchor {
  evidence_id: string
  blockchain_network: string
  contract_address: string
  transaction_hash: string
  block_number: number
  anchored_at: string
  evidence_hash: string
  anchored_by?: string
}

interface EvidenceComplianceRecord {
  evidence_id: string
  passport_id?: string
  evidence_type?: string
  title?: string
  description?: string | null
  content?: string
  content_type?: string | null
  risk_impact?: number | null
  compliance_impact?: number | null
  evidence_status?: string | null
  contract_reference?: string | null
  policy_reference?: string | null
  analysis_reference?: string | null
  source?: string | null
  source_id?: string | null
  metadata?: Record<string, unknown>
}

interface EvidenceVerification {
  verified: boolean
  status: string
  message: string
  localHash?: string
  ethereumHash?: string
  transactionHash?: string
  blockNumber?: number
  anchoredBy?: string
}

interface AnchorProofButtonProps {
  evidenceId: string
}

export default function AnchorProofButton({ evidenceId }: AnchorProofButtonProps) {
  const [isAnchoring, setIsAnchoring] = useState(false)
  const [anchor, setAnchor] = useState<EvidenceAnchor | null>(null)
  const [verification, setVerification] = useState<EvidenceVerification | null>(null)
  const [loading, setLoading] = useState(true)
  const [record, setRecord] = useState<EvidenceComplianceRecord | null>(null)
  const [anchorError, setAnchorError] = useState('')

  const loadAnchor = async () => {
    setLoading(true)
    setAnchorError('')
    try {
      const statusResponse = await apiFetch(`/api/evidence/${evidenceId}/status`)
      if (!statusResponse.ok) throw new Error('Unable to load evidence anchor status')
      const status: { anchored: boolean } = await statusResponse.json()
      if (status.anchored) {
        const response = await apiFetch(`/api/evidence/${evidenceId}/anchor`)
        if (!response.ok) throw new Error('Unable to load evidence anchor')
        setAnchor(await response.json())
        void verifyOnChain()
      } else {
        setVerification({
          verified: false,
          status: 'NOT_FOUND',
          message: 'No confirmed Ethereum anchor exists for this evidence.',
        })
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load Ethereum anchor status'
      setAnchorError(message)
      console.error('Error loading evidence anchor:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadAnchor()
  }, [evidenceId])

  const verifyOnChain = async () => {
    try {
      const evidenceResponse = await apiFetch(`/api/passports/evidence/${evidenceId}`)
      if (!evidenceResponse.ok) throw new Error('Unable to load evidence details for local hash calculation')
      const evidenceRecord = (await evidenceResponse.json()) as EvidenceComplianceRecord
      setRecord(evidenceRecord)

      const localHash = await hashEvidenceItem(evidenceRecord as unknown as Record<string, unknown>)
      const chainAnchor = await readEvidenceAnchorFromEthereum(evidenceId)
      if (!chainAnchor || !chainAnchor.evidenceHash) {
        const result: EvidenceVerification = {
          verified: false,
          status: 'NOT_FOUND',
          message: '⚠ No Ethereum Anchor Found',
          localHash,
        }
        setVerification(result)
        return result
      }

      const ethereumHash = chainAnchor.evidenceHash
      const normalizeHash = (value: string) => value.toLowerCase().replace(/^0x/, '')
      const verified = normalizeHash(localHash) === normalizeHash(ethereumHash)
      const result: EvidenceVerification = {
        verified,
        status: verified ? 'PASS' : 'FAIL',
        message: verified ? '✓ Cryptographically Verified' : '✕ Evidence Does Not Match Blockchain Anchor',
        localHash,
        ethereumHash,
        transactionHash: chainAnchor.transactionHash ?? undefined,
        blockNumber: chainAnchor.blockNumber ?? undefined,
        anchoredBy: chainAnchor.anchoredBy ?? undefined,
      }
      setVerification(result)
      return result
    } catch (error) {
      console.error('Error verifying evidence on Ethereum:', error)
      const result: EvidenceVerification = {
        verified: false,
        status: 'FAIL',
        message: '✕ Evidence Does Not Match Blockchain Anchor',
      }
      setVerification(result)
      return result
    }
  }

  const handleAnchor = async () => {
    setIsAnchoring(true)
    setVerification(null)
    try {
      const response = await apiFetch(`/api/evidence/${evidenceId}/anchor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evidence_id: evidenceId }),
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to anchor evidence')
      }
      const result: EvidenceAnchor = await response.json()
      setAnchor(result)
      toast.success('Evidence anchored to Ethereum Sepolia')
      const verificationResult = await verifyOnChain()
      if (verificationResult.verified) toast.success('Evidence verified on-chain')
    } catch (error) {
      console.error('Error anchoring evidence:', error)
      toast.error('Failed to anchor evidence', {
        description: error instanceof Error ? error.message : 'Unknown error occurred',
      })
    } finally {
      setIsAnchoring(false)
    }
  }

  const handleVerify = async () => {
    try {
      const result = await verifyOnChain()
      if (!result.verified && result.status !== 'NOT_FOUND') {
        toast.error(result.message)
      }
      if (result.status === 'NOT_FOUND') {
        toast.warning(result.message)
      }
    } catch (error) {
      console.error('Error verifying evidence:', error)
      toast.error('Evidence verification failed')
    }
  }

  const verificationHasTxn = verification && verification.transactionHash
  const anchoredByValue = verification?.anchoredBy ?? anchor?.anchored_by ?? undefined

  if (loading) return <div className="text-sm text-gray-500">Loading Evidence Anchor...</div>

  if (anchorError) {
    return (
      <div className="border-t border-gray-200 pt-4 text-sm text-red-700">
        <p>Unable to load evidence anchor: {anchorError}</p>
        <button type="button" onClick={() => void loadAnchor()} className="mt-2 rounded bg-blue-600 px-3 py-2 font-medium text-white hover:bg-blue-700">
          Retry anchor check
        </button>
      </div>
    )
  }

  return (
    <div className="border-t border-gray-200 pt-4 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h4 className="font-semibold text-gray-900">Evidence Anchor</h4>
          <p className="text-xs text-gray-500">Ethereum Sepolia</p>
        </div>
        {!anchor ? (
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1 rounded-md bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-800">
              <Clock className="h-3 w-3" /> Not anchored
            </span>
            <button type="button" onClick={handleAnchor} disabled={isAnchoring} className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60">
              <Anchor className="h-4 w-4" />
              {isAnchoring ? 'Anchoring...' : 'Anchor to Ethereum'}
            </button>
          </div>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-md bg-green-100 px-2 py-1 text-xs font-medium text-green-800">
            <CheckCircle2 className="h-3 w-3" /> Anchored
          </span>
        )}
      </div>

      {anchor && (
        <div className="space-y-2 text-sm">
          <div className="flex items-start gap-2"><Network className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Network:</strong> Ethereum Sepolia</span></div>
          <div className="flex items-start gap-2"><FileText className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Contract:</strong> <span className="break-all font-mono text-xs">{anchor.contract_address}</span></span></div>
          <div className="flex items-start gap-2"><Hash className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Evidence Item Hash:</strong> <span className="break-all font-mono text-xs">{anchor.evidence_hash}</span></span></div>
          <div className="flex items-start gap-2"><Hash className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Transaction:</strong> <span className="break-all font-mono text-xs">{anchor.transaction_hash}</span></span></div>
          <div><strong>Block:</strong> {anchor.block_number}</div>
          {anchoredByValue && (
            <div>
              <strong>Anchored By:</strong>{' '}
              <span className="break-all font-mono text-xs">{anchoredByValue}</span>
            </div>
          )}
          <div className="flex items-start gap-2"><Clock className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Timestamp:</strong> {new Date(anchor.anchored_at).toLocaleString()}</span></div>
          <a href={getEtherscanTransactionUrl(anchor.transaction_hash)} target="_blank" rel="noreferrer" className="inline-flex items-center text-sm font-medium text-blue-700 hover:text-blue-900">View on Etherscan</a>
          <button type="button" onClick={handleVerify} className="text-sm font-medium text-blue-700 hover:text-blue-900">Check On-chain Verification</button>
        </div>
      )}

      {verification && (
        <div className={verification.verified ? 'text-sm text-green-700' : verification.status === 'NOT_FOUND' ? 'text-sm text-yellow-700' : 'text-sm text-red-700'}>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide">Verification status: {verification.status}</div>
          <div className="flex items-center gap-2 font-medium">
            {verification.verified ? <CheckCircle2 className="h-4 w-4" /> : verification.status === 'NOT_FOUND' ? <Clock className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
            {verification.message}
          </div>
          {verification.status === 'NOT_FOUND' && (
            <div className="mt-1">This evidence has not yet been anchored to Ethereum.</div>
          )}
          {verification.localHash && <div className="mt-1 break-all font-mono text-xs">Local Evidence Item Hash: {verification.localHash}</div>}
          {verification.ethereumHash && <div className="mt-1 break-all font-mono text-xs">Ethereum Evidence Hash: {verification.ethereumHash}</div>}
          {verificationHasTxn && verification.transactionHash && (
            <div className="mt-2">
              <div className="break-all font-mono text-xs">Tx: {verification.transactionHash}</div>
              {verification.blockNumber && <div className="break-all font-mono text-xs">Block: {verification.blockNumber}</div>}
              {verification.anchoredBy && <div className="break-all font-mono text-xs">Anchored By: {verification.anchoredBy}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
