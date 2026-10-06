'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'

type PublicReceipt = {
  tool: string
  decision: string
  time: string
  receipt_hash: string
  canonical: string
  evidence_id: string
  anchor_status: string
}

type PublicChain = {
  passport_id: string
  mandate_hash: string
  obligations: { label: string; amount: string; currency: string; status: string; clause_ref: string }[]
  receipts: PublicReceipt[]
}

const STEPS = ['APPROVED', 'INVOICED', 'SENT', 'PAID']

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

export function PaymentProof({ initialPassportId = '' }: { initialPassportId?: string }) {
  const [passportId, setPassportId] = useState(initialPassportId)
  const [chain, setChain] = useState<PublicChain | null>(null)
  const [error, setError] = useState('')
  const [checks, setChecks] = useState<Record<string, string>>({})

  useEffect(() => {
    if (initialPassportId.trim()) void load(initialPassportId)
    // The query string is the deep link. load is stable for that first id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPassportId])

  async function load(id = passportId) {
    const requested = id.trim()
    if (!requested) return
    setError('')
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
      [receipt.receipt_hash]: digest === receipt.receipt_hash ? `Matched · ${receipt.anchor_status}` : 'Hash did not match',
    }))
  }

  return (
    <section className="bg-white rounded-xl shadow-lg p-8 mb-8 border border-gray-200" data-testid="payment-proof">
      <h2 className="text-2xl font-bold text-gray-900">Payments, with proof</h2>
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
