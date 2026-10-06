'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { PaymentsTab, type PaymentsData, type ToolCallChip } from './PaymentsTab'

const empty: PaymentsData = { obligations: [], mandate_hash: '', invoices: [], receipts: [], actions: [] }

export function ContractPayments({ contractId, roles, actorId, readOnlyAccount = false }: { contractId: string; roles: string[]; actorId?: string; readOnlyAccount?: boolean }) {
  const [data, setData] = useState<PaymentsData>(empty)
  const [transcript, setTranscript] = useState<ToolCallChip[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function reload() {
    const response = await apiFetch(`/api/contracts/${encodeURIComponent(contractId)}/payments`)
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load payments')
    setData(await response.json())
  }

  useEffect(() => {
    let cancelled = false
    void reload().catch((cause: unknown) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : 'Unable to load payments')
    })
    return () => {
      cancelled = true
    }
  }, [contractId])

  const waitingOnPayPal = data.invoices.some((invoice) => invoice.status === 'SENT')
  useEffect(() => {
    if (!waitingOnPayPal) return
    const timer = window.setInterval(() => {
      void reload().catch(() => undefined)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [waitingOnPayPal, contractId])

  async function run(path: string, init?: RequestInit) {
    setBusy(true)
    setError('')
    try {
      const response = await apiFetch(path, init)
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Payment request failed')
      return await response.json()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Payment request failed')
      return null
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      {error ? <p className="text-sm text-red-700 dark:text-red-400" role="alert">{error}</p> : null}
      <PaymentsTab
        roles={roles}
        actorId={actorId}
        data={data}
        busy={busy}
        transcript={transcript}
        onExtract={() => void run(`/api/contracts/${encodeURIComponent(contractId)}/payments/obligations:extract`, { method: 'POST' }).then(() => reload())}
        onEdit={(obligationId, changes) => void run(`/api/payment-obligations/${encodeURIComponent(obligationId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) }).then(() => reload())}
        onApprove={(obligationId) => void run(`/api/payment-obligations/${encodeURIComponent(obligationId)}:approve`, { method: 'POST' }).then(() => reload())}
        onReject={(obligationId) => void run(`/api/payment-obligations/${encodeURIComponent(obligationId)}:reject`, { method: 'POST' }).then(() => reload())}
        onSend={(message) => void run(`/api/contracts/${encodeURIComponent(contractId)}/payments/agent`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }) }).then((body) => {
          if (body?.tool_calls) setTranscript(body.tool_calls)
          return reload()
        })}
        onTransition={(actionId, transitionId) => void run(`/api/payment-actions/${encodeURIComponent(actionId)}/transition`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ transition_id: transitionId }) }).then(() => reload())}
        onExecute={(actionId) => void run(`/api/payment-actions/${encodeURIComponent(actionId)}:execute`, { method: 'POST' }).then(() => reload())}
        onVerify={(evidenceId) => void apiFetch(`/api/verify/${encodeURIComponent(evidenceId)}`)}
        readOnlyAccount={readOnlyAccount}
      />
    </div>
  )
}
