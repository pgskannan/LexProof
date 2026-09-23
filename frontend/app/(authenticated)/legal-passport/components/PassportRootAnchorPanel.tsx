'use client'

/**
 * Blockchain Commitment panel for the Legal Passport ROOT anchor
 * (docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md). This is additive and
 * completely separate from AnchorProofButton (per-evidence-item anchors on
 * the existing LexProofRegistry contract) -- it renders the passport-level
 * `anchor_status` already returned by the extended `POST
 * /api/passports/{id}/verify` response (see legal-passport/page.tsx's
 * `fetchIntegrity`) and, when eligible, calls the dedicated
 * `POST /api/passports/{id}/anchor-root` endpoint. No hash, score, or other
 * value is ever sent from this component -- the server independently
 * recomputes and verifies everything before anchoring.
 */

import { useState } from 'react'
import { Anchor, CheckCircle2, Clock, Hash, Network, ShieldAlert, WifiOff, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { apiFetch } from '../../../../lib/api'
import { getEtherscanAddressUrl, getEtherscanTransactionUrl } from '../../../../lib/ethereum'

export type PassportRootAnchorStatus =
  | 'PASS'
  | 'FAIL'
  | 'UNVERIFIABLE'
  | 'NOT_ANCHORED'
  | 'NETWORK_ERROR'
  | 'CHAIN_MISMATCH'
  | 'INVALID_PROOF'

export interface PassportRootAnchorIntegrity {
  anchor_status?: PassportRootAnchorStatus
  anchor_ineligible_reasons?: string[]
  anchor_error?: string
  blockchain_network?: string | null
  contract_address?: string | null
  chain_id?: number | null
  transaction_hash?: string | null
  block_number?: number | null
  on_chain_root?: string | null
}

interface PassportRootAnchorPanelProps {
  passportId: string
  integrity: PassportRootAnchorIntegrity | null
  integrityLoading: boolean
  onAnchored: () => void | Promise<void>
}

export default function PassportRootAnchorPanel({
  passportId,
  integrity,
  integrityLoading,
  onAnchored,
}: PassportRootAnchorPanelProps) {
  const [isAnchoring, setIsAnchoring] = useState(false)

  const handleAnchor = async () => {
    setIsAnchoring(true)
    try {
      const response = await apiFetch(`/api/passports/${encodeURIComponent(passportId)}/anchor-root`, {
        method: 'POST',
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        const detail = body?.detail
        const message =
          typeof detail === 'string'
            ? detail
            : detail?.message
              ? [detail.message, ...(detail.reasons ?? [])].join(' — ')
              : `Unable to anchor passport root (${response.status})`
        throw new Error(message)
      }
      toast.success('Passport root anchored on Ethereum Sepolia')
      await onAnchored()
    } catch (error) {
      toast.error('Failed to anchor passport root', {
        description: error instanceof Error ? error.message : 'Unknown error occurred',
      })
    } finally {
      setIsAnchoring(false)
    }
  }

  // The parent's own integrity skeleton already covers this loading window;
  // this panel piggybacks on that same fetch rather than duplicating it.
  if (integrityLoading) return null
  if (!integrity || !integrity.anchor_status) return null

  const status = integrity.anchor_status

  return (
    <div className="border-t border-gray-200 pt-4 space-y-3" data-testid="passport-root-anchor-panel">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h4 className="font-semibold text-gray-900">Blockchain Commitment</h4>
          <p className="text-xs text-gray-500">
            Legal Passport root, anchored independently of individual evidence items
          </p>
        </div>
        {renderBadge(status)}
      </div>

      {status === 'PASS' && (
        <div className="space-y-2 rounded-lg border-l-4 border-l-green-600 bg-green-50 p-4 text-sm text-green-900">
          <div className="flex items-center gap-2 font-semibold">
            <CheckCircle2 className="h-5 w-5" /> Passport root anchored and matches this fingerprint
          </div>
          <div className="flex items-start gap-2">
            <Network className="mt-0.5 h-4 w-4" />
            <span>
              {integrity.blockchain_network ?? 'Ethereum Sepolia'}
              {integrity.chain_id ? ` (chain ${integrity.chain_id})` : ''}
            </span>
          </div>
          {integrity.contract_address && (
            <div className="flex items-start gap-2">
              <Hash className="mt-0.5 h-4 w-4" />
              <a
                href={getEtherscanAddressUrl(integrity.contract_address)}
                target="_blank"
                rel="noreferrer"
                className="break-all font-mono text-xs underline"
              >
                {integrity.contract_address}
              </a>
            </div>
          )}
          {integrity.transaction_hash && (
            <div className="flex items-start gap-2">
              <Hash className="mt-0.5 h-4 w-4" />
              <a
                href={getEtherscanTransactionUrl(integrity.transaction_hash)}
                target="_blank"
                rel="noreferrer"
                className="break-all font-mono text-xs underline"
              >
                {integrity.transaction_hash}
              </a>
            </div>
          )}
          {integrity.block_number != null && <div>Block: {integrity.block_number}</div>}
        </div>
      )}

      {status === 'NOT_ANCHORED' && (
        <div className="space-y-3 rounded-lg border-l-4 border-l-amber-500 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="flex items-center gap-2 font-semibold">
            <Clock className="h-5 w-5" /> Eligible, not yet anchored
          </div>
          <p>
            This passport&apos;s integrity is fully verified. Anchor its root fingerprint on Ethereum
            Sepolia for an independent, tamper-evident commitment.
          </p>
          <button
            type="button"
            onClick={() => void handleAnchor()}
            disabled={isAnchoring}
            className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            <Anchor className="h-4 w-4" />
            {isAnchoring ? 'Anchoring…' : 'Anchor to Ethereum Sepolia'}
          </button>
        </div>
      )}

      {(status === 'FAIL' || status === 'UNVERIFIABLE') && (
        <div className="space-y-2 rounded-lg border-l-4 border-l-gray-400 bg-gray-50 p-4 text-sm text-gray-700">
          <div className="flex items-center gap-2 font-semibold text-gray-800">
            <ShieldAlert className="h-5 w-5" /> Not eligible for anchoring
          </div>
          <p>
            Every claimed component must PASS before a passport root can be anchored.{' '}
            {status === 'UNVERIFIABLE'
              ? 'One or more components are not claimed in this snapshot.'
              : 'One or more components failed verification above.'}
          </p>
          {integrity.anchor_ineligible_reasons && integrity.anchor_ineligible_reasons.length > 0 && (
            <ul className="list-disc pl-5 font-mono text-xs">
              {integrity.anchor_ineligible_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {status === 'INVALID_PROOF' && (
        <div className="space-y-2 rounded-lg border-l-4 border-l-red-600 bg-red-50 p-4 text-sm text-red-900">
          <div className="flex items-center gap-2 font-semibold">
            <XCircle className="h-5 w-5" /> On-chain root does not match this passport
          </div>
          <p>
            A root is anchored for this passport ID, but it does not match the passport&apos;s current
            recomputed fingerprint. This can indicate the passport was re-created or its data changed
            after anchoring.
          </p>
          {integrity.on_chain_root && (
            <p className="break-all font-mono text-xs">On-chain root: {integrity.on_chain_root}</p>
          )}
        </div>
      )}

      {(status === 'NETWORK_ERROR' || status === 'CHAIN_MISMATCH') && (
        <div className="space-y-2 rounded-lg border-l-4 border-l-gray-400 bg-gray-50 p-4 text-sm text-gray-700">
          <div className="flex items-center gap-2 font-semibold text-gray-800">
            <WifiOff className="h-5 w-5" /> Blockchain network unavailable
          </div>
          <p>
            {integrity.anchor_error ||
              "Unable to reach the Ethereum network right now. This does not affect the passport's local integrity verification above."}
          </p>
        </div>
      )}
    </div>
  )
}

function renderBadge(status: PassportRootAnchorStatus) {
  switch (status) {
    case 'PASS':
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-green-100 px-2 py-1 text-xs font-medium text-green-800">
          <CheckCircle2 className="h-3 w-3" /> Anchored
        </span>
      )
    case 'NOT_ANCHORED':
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-800">
          <Clock className="h-3 w-3" /> Not anchored
        </span>
      )
    case 'INVALID_PROOF':
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-red-100 px-2 py-1 text-xs font-medium text-red-800">
          <XCircle className="h-3 w-3" /> Mismatch
        </span>
      )
    case 'NETWORK_ERROR':
    case 'CHAIN_MISMATCH':
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
          <WifiOff className="h-3 w-3" /> Network unavailable
        </span>
      )
    default:
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
          Not eligible
        </span>
      )
  }
}
