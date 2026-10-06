'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { verifyPaymentChain, type PaymentChainCheckpoint } from '../../lib/paymentChain'

type PublicReceipt = {
  tool: string
  decision: string
  time: string
  receipt_hash: string
  canonical: string
  evidence_id: string
  anchor_status: string
  checkpoint_id?: string | null
  checkpoint_count?: number | null
  anchor_tx?: string | null
}

type PublicCheckpoint = PaymentChainCheckpoint & {
  block_number: number | null
  anchored_at: string | null
  etherscan_url: string
}

type PublicChain = {
  passport_id: string
  contract_id: string
  mandate_hash: string
  chain_version: string
  checkpoints: PublicCheckpoint[]
  obligations: { label: string; amount: string; currency: string; status: string; clause_ref: string }[]
  receipts: PublicReceipt[]
}

const STEPS = ['APPROVED', 'INVOICED', 'SENT', 'PAID', 'REFUNDED']

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

export function PaymentProof({ initialPassportId = '' }: { initialPassportId?: string }) {
  const [passportId, setPassportId] = useState(initialPassportId)
  const [chain, setChain] = useState<PublicChain | null>(null)
  const [error, setError] = useState('')
  const [checks, setChecks] = useState<Record<string, string>>({})
  const [chainCheck, setChainCheck] = useState<Awaited<ReturnType<typeof verifyPaymentChain>> | null>(null)

  useEffect(() => {
    if (initialPassportId.trim()) void load(initialPassportId)
    // The query string is the deep link. load is stable for that first id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPassportId])

  async function load(id = passportId) {
    const requested = id.trim()
    if (!requested) return
    setError('')
    setChainCheck(null)
    const response = await apiFetch(`/api/verify/contracts/${encodeURIComponent(requested)}/payments`)
    if (!response.ok) {
      setChain(null)
      setError((await response.json().catch(() => null))?.detail || 'Payments were not found')
      return
    }
    setChain(await response.json())
  }

  async function verify(receipt: PublicReceipt) {
    const digest = await sha256Hex(receipt.canonical)
    setChecks((current) => ({
      ...current,
      [receipt.receipt_hash]: digest === receipt.receipt_hash
        ? receipt.checkpoint_count
          ? `Matched · covered by checkpoint #${receipt.checkpoint_count}`
          : 'Matched · pending next checkpoint'
        : 'Hash did not match',
    }))
  }

  async function verifyChain() {
    if (!chain) return
    setChainCheck(await verifyPaymentChain(chain.contract_id, chain.receipts, chain.checkpoints))
  }

  const checkpointNumbers = new Map(
    (chain?.checkpoints || []).map((checkpoint, index) => [checkpoint.checkpoint_id, index + 1]),
  )

  return (
    <section className="bg-white rounded-xl shadow-lg p-8 mb-8 border border-gray-200" data-testid="payment-proof">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-bold text-gray-900">Payments, with proof</h2>
        {chain ? <button type="button" onClick={() => void verifyChain()} className="rounded border border-gray-300 px-3 py-2 text-sm font-semibold text-gray-800">Verify chain</button> : null}
      </div>
      <p className="mt-2 text-sm text-gray-600">Approved, invoiced, sent, and paid. Blocked attempts stay in the trail. Emails are masked.</p>
      <div className="mt-4 flex gap-3">
        <input
          aria-label="Passport ID"
          value={passportId}
          onChange={(event) => setPassportId(event.target.value)}
          placeholder="Passport ID"
          className="flex-1 px-4 py-3 border border-gray-300 rounded-lg"
        />
        <button type="button" onClick={() => void load()} className="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg">Load</button>
      </div>
      {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
      {chain ? (
        <div className="mt-6 space-y-4">
          <p className="font-mono text-xs text-gray-600">Mandate {chain.mandate_hash || 'not hashed yet'}</p>
          {chainCheck ? (
            <p className="text-sm" role="status">
              {chainCheck.status === 'matched' ? (
                <>Matched · anchored in tx <a className="font-mono text-blue-700 underline" href={chainCheck.checkpoint.etherscan_url || `https://sepolia.etherscan.io/tx/${chainCheck.checkpoint.transaction_hash}`} target="_blank" rel="noreferrer">{`${chainCheck.checkpoint.transaction_hash.slice(0, 6)}…${chainCheck.checkpoint.transaction_hash.slice(-4)}`}</a></>
              ) : chainCheck.status === 'receipt_mismatch' ? (
                `Mismatch · receipt #${chainCheck.index} (${chainCheck.receipt.time} · ${chainCheck.receipt.tool})`
              ) : chainCheck.status === 'missing_receipts' ? (
                `Mismatch · checkpoint includes missing receipt #${chainCheck.index}`
              ) : chainCheck.status === 'chain_mismatch' ? (
                `Mismatch · chain head after receipt #${chainCheck.checkpoint.count}`
              ) : (
                'Pending · no anchored checkpoint'
              )}
            </p>
          ) : null}
          {chain.checkpoints.length ? (
            <ul className="space-y-1 text-xs text-gray-600">
              {chain.checkpoints.map((checkpoint, index) => (
                <li key={checkpoint.checkpoint_id || checkpoint.transaction_hash}>
                  Checkpoint #{index + 1} · {checkpoint.count} receipts · {checkpoint.anchored_at || 'anchored'} · <a className="text-blue-700 underline" href={checkpoint.etherscan_url} target="_blank" rel="noreferrer">Sepolia transaction</a>
                </li>
              ))}
            </ul>
          ) : null}
          <ol className="flex flex-wrap gap-2 text-xs font-semibold">
            {STEPS.map((step) => (
              <li key={step} className="rounded-full bg-gray-100 px-3 py-1 text-gray-700">{step}</li>
            ))}
          </ol>
          <ul className="space-y-2 text-sm">
            {chain.obligations.map((obligation) => (
              <li key={`${obligation.clause_ref}-${obligation.label}`}>
                {obligation.label} · {obligation.currency} {obligation.amount} · {obligation.status}
                {obligation.clause_ref ? ` · ${obligation.clause_ref}` : ''}
              </li>
            ))}
          </ul>
          <ul className="space-y-3">
            {chain.receipts.map((receipt) => {
              const blocked = receipt.decision !== 'allow'
              return (
                <li key={receipt.receipt_hash} className={`rounded-lg border p-3 ${blocked ? 'border-red-300 bg-red-50 text-red-800' : 'border-gray-200'}`}>
                  <p className="text-sm font-medium">{receipt.time} · {receipt.tool} · {receipt.decision}</p>
                  <p className="mt-1 font-mono text-xs">{receipt.receipt_hash.slice(0, 16)} · {receipt.anchor_status}</p>
                  <p className="mt-1 text-xs">
                    {receipt.checkpoint_id && checkpointNumbers.has(receipt.checkpoint_id)
                      ? `covered by checkpoint #${checkpointNumbers.get(receipt.checkpoint_id)}`
                      : 'pending next checkpoint'}
                  </p>
                  <pre className="mt-2 overflow-x-auto text-xs">{receipt.canonical}</pre>
                  <button type="button" className="mt-2 text-sm font-semibold text-blue-700 underline" onClick={() => void verify(receipt)}>Verify</button>
                  {checks[receipt.receipt_hash] ? <p className="mt-1 text-xs">{checks[receipt.receipt_hash]}</p> : null}
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
