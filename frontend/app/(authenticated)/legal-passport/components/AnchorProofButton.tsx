'use client'

import { useEffect, useState } from 'react'
import { Anchor, CheckCircle2, Clock, FileText, Hash, Layers, Network, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { apiFetch } from '../../../../lib/api'
import { hashEvidenceItem } from '../../../../lib/evidenceHash'
import { readEvidenceAnchorFromEthereum, getEtherscanTransactionUrl } from '../../../../lib/ethereum'
import { Skeleton } from '../../../../components/ui/skeleton'

// The Ethereum operations are now in lib/ethereum.ts
// This component just uses the exported functions

interface EvidenceAnchor {
  evidence_id: string
  blockchain_network: string
  contract_address: string
  transaction_hash: string
  block_number: number
  anchored_at: string
  evidence_hash: string
  anchored_by?: string
  // Hybrid Anchoring (proposed architecture, see hackathon-polish-roadmap.md #1).
  // Real anchors created through this app are always "SINGLE_HASH"; a
  // "MERKLE_BATCH" record only ever comes from the demo script
  // (scripts/create_merkle_batch_demo_anchor.py) and is explicitly is_mock: true.
  anchoring_method?: 'SINGLE_HASH' | 'MERKLE_BATCH'
  is_mock?: boolean
  batch_id?: string
  batch_size?: number
  merkle_root?: string
  merkle_proof?: Array<{ position: 'left' | 'right'; hash: string }>
  demo_note?: string
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
        const anchorData: EvidenceAnchor = await response.json()
        setAnchor(anchorData)
        if (anchorData.is_mock || anchorData.anchoring_method === 'MERKLE_BATCH') {
          setVerification({
            verified: false,
            status: 'SIMULATED',
            message: 'Simulated batch anchor — not a live Ethereum transaction',
          })
        } else {
          void verifyOnChain()
        }
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

  if (loading) return <Skeleton className="h-24 w-full" />

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
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-md bg-green-100 px-2 py-1 text-xs font-medium text-green-800">
              <CheckCircle2 className="h-3 w-3" /> Anchored
            </span>
            {(anchor.is_mock || anchor.anchoring_method === 'MERKLE_BATCH') ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-purple-100 px-2 py-1 text-xs font-medium text-purple-800">
                <Layers className="h-3 w-3" /> Simulated batch anchor (demo)
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                Single-hash anchor
              </span>
            )}
          </div>
        )}
      </div>

      {anchor && (
        <div className="space-y-3 text-sm">
          <div className="flex items-start gap-2"><Network className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Network:</strong> Ethereum Sepolia</span></div>
          <div className="flex items-start gap-2"><FileText className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Contract:</strong> <span className="break-all font-mono text-xs">{anchor.contract_address}</span></span></div>
          <div className="flex items-start gap-2"><Hash className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Evidence Item Hash:</strong> <span className="break-all font-mono text-xs">{anchor.evidence_hash}</span></span></div>
          <div className="flex items-start gap-2"><Hash className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Transaction:</strong> <span className="break-all font-mono text-xs">{anchor.transaction_hash}</span></span></div>
          <div><strong>Block:</strong> {anchor.block_number ?? (anchor.is_mock ? 'Not applicable (simulated)' : 'Not available')}</div>
          {anchoredByValue && (
            <div>
              <strong>Anchored By:</strong>{' '}
              <span className="break-all font-mono text-xs">{anchoredByValue}</span>
            </div>
          )}
          <div className="flex items-start gap-2"><Clock className="mt-0.5 h-4 w-4 text-gray-500" /><span><strong>Timestamp:</strong> {new Date(anchor.anchored_at).toLocaleString()}</span></div>
          {(anchor.is_mock || anchor.anchoring_method === 'MERKLE_BATCH') && (
            <div className="rounded-lg border-l-4 border-l-purple-500 bg-purple-50 p-3 text-purple-900">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide">
                <Layers className="h-3.5 w-3.5" /> Hybrid Anchoring demo (simulated)
              </div>
              <p className="mt-1 text-xs text-purple-800">
                {anchor.demo_note || 'This anchor illustrates a proposed batched (Merkle-root) anchoring architecture. It was never submitted to Ethereum.'}
              </p>
              <dl className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
                {anchor.batch_id && <div><dt className="font-semibold">Batch ID</dt><dd className="break-all font-mono">{anchor.batch_id}</dd></div>}
                {typeof anchor.batch_size === 'number' && <div><dt className="font-semibold">Batch size</dt><dd>{anchor.batch_size} evidence items</dd></div>}
                {anchor.merkle_root && <div className="sm:col-span-2"><dt className="font-semibold">Merkle root</dt><dd className="break-all font-mono">{anchor.merkle_root}</dd></div>}
              </dl>
            </div>
          )}
          <div className="flex items-center gap-3 pt-2">
            {(anchor.is_mock || anchor.anchoring_method === 'MERKLE_BATCH') ? (
              <span className="text-xs italic text-gray-500">No Etherscan link or live on-chain check — this anchor was never submitted to Ethereum.</span>
            ) : (
              <>
                <a href={getEtherscanTransactionUrl(anchor.transaction_hash)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700">
                  View on Etherscan
                  <span>↗</span>
                </a>
                <button type="button" onClick={handleVerify} className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700">
                  Check On-chain Verification
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {verification && (
        <div className={`rounded-lg border-l-4 p-4 ${
          verification.verified
            ? 'border-l-green-600 bg-green-50'
            : verification.status === 'SIMULATED'
            ? 'border-l-purple-500 bg-purple-50'
            : verification.status === 'NOT_FOUND'
            ? 'border-l-amber-600 bg-amber-50'
            : 'border-l-red-600 bg-red-50'
        }`}>
          <div className={`text-xs font-semibold uppercase tracking-wide ${
            verification.verified
              ? 'text-green-900'
              : verification.status === 'SIMULATED'
              ? 'text-purple-900'
              : verification.status === 'NOT_FOUND'
              ? 'text-amber-900'
              : 'text-red-900'
          }`}>
            Verification status: {verification.status}
          </div>
          <div className={`mt-2 flex items-center gap-2 font-semibold ${
            verification.verified
              ? 'text-green-900'
              : verification.status === 'SIMULATED'
              ? 'text-purple-900'
              : verification.status === 'NOT_FOUND'
              ? 'text-amber-900'
              : 'text-red-900'
          }`}>
            {verification.verified ? <CheckCircle2 className="h-5 w-5" /> : verification.status === 'SIMULATED' ? <Layers className="h-5 w-5" /> : verification.status === 'NOT_FOUND' ? <Clock className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
            {verification.message}
          </div>
          {verification.status === 'NOT_FOUND' && (
            <div className={`mt-2 text-sm ${
              verification.status === 'NOT_FOUND'
              ? 'text-amber-800'
              : 'text-red-800'
            }`}>This evidence has not yet been anchored to Ethereum.</div>
          )}
          {verification.status === 'SIMULATED' && (
            <div className="mt-2 text-sm text-purple-800">This anchor demonstrates a proposed batched anchoring architecture and was never submitted to Ethereum — there is nothing on-chain to independently verify.</div>
          )}
          {verification.localHash && <div className={`mt-2 break-all font-mono text-xs ${
            verification.verified
              ? 'text-green-800'
              : verification.status === 'NOT_FOUND'
              ? 'text-amber-800'
              : 'text-red-800'
          }`}>Local Evidence Item Hash: {verification.localHash}</div>}
          {verification.ethereumHash && <div className={`mt-1 break-all font-mono text-xs ${
            verification.verified
              ? 'text-green-800'
              : 'text-red-800'
          }`}>Ethereum Evidence Hash: {verification.ethereumHash}</div>}
          {verificationHasTxn && verification.transactionHash && (
            <div className={`mt-2 border-t ${
              verification.verified
                ? 'border-t-green-200'
                : 'border-t-red-200'
            } pt-2`}>
              <div className={`break-all font-mono text-xs ${
                verification.verified
                  ? 'text-green-800'
                  : 'text-red-800'
              }`}>Tx: {verification.transactionHash}</div>
              {verification.blockNumber && <div className={`break-all font-mono text-xs ${
                verification.verified
                  ? 'text-green-800'
                  : 'text-red-800'
              }`}>Block: {verification.blockNumber}</div>}
              {verification.anchoredBy && <div className={`break-all font-mono text-xs ${
                verification.verified
                  ? 'text-green-800'
                  : 'text-red-800'
              }`}>Anchored By: {verification.anchoredBy}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
