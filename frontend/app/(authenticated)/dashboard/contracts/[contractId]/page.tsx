'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Circle, Loader2, RotateCcw, XCircle } from 'lucide-react'
import { apiFetch } from '../../../../../lib/api'
import { lifecycleStages, type LifecycleData, type ContractVersion, type LifecycleAnchor, type LifecyclePassport, type LifecycleProposal } from '../../../../../lib/contractLifecycle'
import { useOrg } from '../../../../../components/OrgProvider'
import { Skeleton } from '../../../../../components/ui/skeleton'
import type { WorkflowHistoryEvent, WorkflowInstance } from '../../../../../lib/org'

type ContractSummary = LifecycleData['contract']

type Finding = { finding_id: string; version_id?: string | null }
type Evidence = { evidence_id: string; passport_id?: string | null }

const icons = {
  complete: CheckCircle2,
  active: Loader2,
  pending: Circle,
  failed: XCircle,
  unavailable: Circle,
}

// Evidence and per-evidence anchor lookups can transiently 503 under this
// dev backend's known event-loop-blocking load (see status-and-plan.md's
// notes on the datetime-sort/§2c-class hang). Swallowing a single failed
// lookup as "no evidence" would silently understate this contract's real,
// on-chain-anchored evidence with no error shown to the user -- retry once
// after a short delay before giving up.
async function fetchWithRetry(path: string, signal: AbortSignal, attempts = 2): Promise<Response> {
  let lastResponse: Response | null = null
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const response = await apiFetch(path, { signal })
    if (response.ok || response.status < 500 || attempt === attempts - 1) return response
    lastResponse = response
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
  return lastResponse as Response
}

export default function ContractDetailPage() {
  const params = useParams<{ contractId: string }>()
  const contractId = decodeURIComponent(params.contractId)
  const { currentOrg } = useOrg()
  const [data, setData] = useState<LifecycleData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retrying, setRetrying] = useState<string | null>(null)
  const [workflow, setWorkflow] = useState<{ instance: WorkflowInstance; history: WorkflowHistoryEvent[] } | null>(null)

  async function load(signal: AbortSignal) {
    setLoading(true)
    setError('')
    try {
      const [contractResponse, versionsResponse, findingsResponse, proposalsResponse, passportsResponse] = await Promise.all([
        apiFetch(`/api/contracts/${encodeURIComponent(contractId)}`, { signal }),
        apiFetch(`/api/contracts/${encodeURIComponent(contractId)}/versions`, { signal }),
        apiFetch(`/api/findings?contract_id=${encodeURIComponent(contractId)}`, { signal }),
        apiFetch(`/api/contracts/${encodeURIComponent(contractId)}/redline-proposals`, { signal }),
        apiFetch(`/api/passports?contract_id=${encodeURIComponent(contractId)}&limit=100`, { signal }),
      ])
      for (const response of [contractResponse, versionsResponse, findingsResponse, proposalsResponse, passportsResponse]) {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load contract lifecycle')
      }
      const contract: ContractSummary = await contractResponse.json()
      const versions: ContractVersion[] = await versionsResponse.json()
      const findings: Finding[] = await findingsResponse.json()
      const proposals: LifecycleProposal[] = await proposalsResponse.json()
      const passportPayload = await passportsResponse.json()
      const passportRows: LifecyclePassport[] = Array.isArray(passportPayload) ? passportPayload : passportPayload.passports ?? []
      const evidenceGroups = await Promise.all(passportRows.map(async (passport) => {
        const response = await fetchWithRetry(`/api/passports/${encodeURIComponent(passport.passport_id)}/evidence`, signal)
        if (!response.ok) return { evidence: [] as Evidence[], anchors: [] as LifecycleAnchor[] }
        const evidence: Evidence[] = await response.json()
        const anchorResults = await Promise.all(evidence.map(async (item) => {
          const anchorResponse = await fetchWithRetry(`/api/evidence/${encodeURIComponent(item.evidence_id)}/anchor`, signal)
          return anchorResponse.ok ? await anchorResponse.json() as LifecycleAnchor : null
        }))
        return { evidence, anchors: anchorResults.filter((anchor): anchor is LifecycleAnchor => Boolean(anchor)) }
      }))
      const evidence = evidenceGroups.flatMap((group) => group.evidence)
      const anchors = evidenceGroups.flatMap((group) => group.anchors)
      setData({ contract, versions, findingsCount: findings.length, proposals, passports: passportRows, evidenceCount: evidence.length, anchoredEvidenceCount: anchors.length, anchors })
      const instanceId = proposals.find((proposal) => proposal.workflow_instance_id)?.workflow_instance_id
        || [...proposals].reverse().find((proposal) => proposal.workflow_instance_id)?.workflow_instance_id
      const orgId = currentOrg?.org_id
      if (orgId && instanceId) {
        const [instanceResponse, historyResponse] = await Promise.all([
          apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/workflow-instances/${encodeURIComponent(instanceId)}`, { signal }),
          apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/workflow-instances/${encodeURIComponent(instanceId)}/history`, { signal }),
        ])
        if (instanceResponse.ok && historyResponse.ok) {
          setWorkflow({ instance: await instanceResponse.json(), history: await historyResponse.json() })
        } else {
          setWorkflow(null)
        }
      } else {
        setWorkflow(null)
      }
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') return
      setError(cause instanceof Error ? cause.message : 'Unable to load contract lifecycle')
    } finally {
      if (!signal.aborted) setLoading(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [contractId, currentOrg?.org_id])

  async function retry(version: ContractVersion) {
    const confirmed = window.confirm(
      'Re-run analysis for this version? This can take a while and will replace the current failed analysis state.',
    )
    if (!confirmed) return
    setRetrying(version.version_id)
    setError('')
    try {
      const response = await apiFetch(`/api/contracts/${encodeURIComponent(contractId)}/versions/${encodeURIComponent(version.version_id)}/analyze`, { method: 'POST' })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to retry analysis')
      await load(new AbortController().signal)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to retry analysis')
    } finally {
      setRetrying(null)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 p-2">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  if (error && !data) return <div className="border border-red-200 bg-red-50 p-6 text-red-700" role="alert"><AlertTriangle className="mb-2 h-5 w-5" />{error}</div>
  if (!data) return null

  const stages = lifecycleStages(data)
  const current = data.versions.find((version) => version.is_current) ?? data.versions.at(-1)
  const currentPassport = data.passports.find((passport) => passport.contract_version === current?.version_number)
  const currentProposal = data.proposals.find((proposal) => proposal.published_version_id) ?? data.proposals.at(-1)

  return (
    <main className="space-y-8 text-slate-900">
      <header className="border-b border-slate-200 pb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-bold uppercase tracking-[0.24em] text-blue-700">Contract owner</p><h1 className="mt-2 text-4xl font-bold tracking-tight">{data.contract.name || 'Contract name not available'}</h1><p className="mt-2 font-mono text-xs text-slate-500">{data.contract.contract_id}</p></div>
          <Link href="/dashboard/contracts" className="border border-slate-300 px-4 py-2 text-sm font-semibold hover:border-blue-500">All contracts</Link>
        </div>
        <div className="mt-6 grid gap-px border border-slate-200 bg-slate-200 sm:grid-cols-4">
          <Metric label="Current version" value={current?.version_number ? `V${current.version_number}` : 'Not available'} />
          <Metric label="Analysis status" value={current?.analysis_status || data.contract.analysis_status || 'Not available'} />
          <Metric label="Passport" value={currentPassport?.passport_id || data.contract.passport_id || 'Not created'} mono />
          <Metric label="Evidence" value={`${data.anchoredEvidenceCount}/${data.evidenceCount} anchored`} />
        </div>
      </header>

      <section className="border border-slate-200 bg-white p-6">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Lifecycle</p><h2 className="mt-1 text-2xl font-bold">From upload to public proof</h2></div><p className="text-sm text-slate-500">Responsibilities: AI analysis · Legal review · Human approver · Public verifier</p></div>
        <div className="mt-7 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{stages.map((stage) => { const Icon = icons[stage.status]; return <div key={stage.key} className="flex min-h-28 gap-3 border border-slate-200 p-4"><Icon className={`mt-0.5 h-5 w-5 shrink-0 ${stage.status === 'complete' ? 'text-emerald-600' : stage.status === 'failed' ? 'text-rose-600' : stage.status === 'active' ? 'animate-spin text-blue-600' : 'text-slate-400'}`} /><div className="min-w-0"><p className="text-xs font-bold uppercase tracking-wider text-slate-500">{stage.label}</p><p className="mt-1 font-semibold capitalize text-slate-900">{stage.status}</p><p className="mt-1 break-words text-sm text-slate-600">{stage.detail}</p>{stage.href && <Link href={stage.href} className="mt-2 inline-block text-xs font-semibold text-blue-700 hover:underline">Open stage</Link>}{stage.key === 'v2-analysis' && current?.analysis_status === 'failed' && <button type="button" onClick={() => void retry(current)} disabled={retrying === current.version_id} className="ml-3 inline-flex items-center gap-1 text-xs font-semibold text-rose-700 disabled:opacity-50"><RotateCcw className="h-3 w-3" />{retrying === current.version_id ? 'Retrying' : 'Retry'}</button>}</div></div> })}</div>
      </section>

      <section className="grid gap-8 xl:grid-cols-[1.2fr_.8fr]">
        <div className="border border-slate-200 bg-white p-6"><div className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Versions</p><h2 className="mt-1 text-2xl font-bold">Version history</h2></div><Link href={`/contract-time-machine?contractId=${encodeURIComponent(contractId)}`} className="text-sm font-semibold text-blue-700 hover:underline">Open Time Machine</Link></div><div className="mt-5 space-y-3">{data.versions.length === 0 && <p className="text-sm text-slate-500">Version history is not available.</p>}{data.versions.map((version) => <article key={version.version_id} className="border border-slate-200 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">V{version.version_number} {version.is_current ? <span className="ml-2 text-xs font-bold uppercase text-emerald-700">Current version</span> : <span className="ml-2 text-xs font-bold uppercase text-slate-500">Superseded version</span>}</h3><span className="text-xs font-semibold uppercase text-slate-500">{version.analysis_status || 'Not available'}</span></div><dl className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2"><div><dt className="font-semibold">Version ID</dt><dd className="break-all font-mono">{version.version_id}</dd></div><div><dt className="font-semibold">Parent</dt><dd className="break-all font-mono">{version.parent_version_id || 'Not available'}</dd></div><div><dt className="font-semibold">Created by</dt><dd>{version.created_by || 'Not available'}</dd></div><div><dt className="font-semibold">Created</dt><dd>{version.created_at ? new Date(version.created_at).toLocaleString() : 'Not available'}</dd></div><div><dt className="font-semibold">Passport</dt><dd className="break-all font-mono">{version.passport_id || 'Not available'}</dd></div><div><dt className="font-semibold">Publication</dt><dd>{version.published ? 'Published' : 'Not published'}</dd></div></dl></article>)}</div></div>
        <div className="space-y-8"><div className="border border-slate-200 bg-white p-6"><p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Findings</p><h2 className="mt-1 text-2xl font-bold">{data.findingsCount} persisted</h2><p className="mt-2 text-sm text-slate-600">Every finding retains its contract version relationship.</p><Link href={`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`} className="mt-4 inline-block text-sm font-semibold text-blue-700 hover:underline">Review findings</Link></div><div className="border border-slate-200 bg-white p-6"><p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Redline and review</p><h2 className="mt-1 text-2xl font-bold">{currentProposal?.status || 'No proposal recorded'}</h2><p className="mt-2 text-sm text-slate-600">{currentProposal?.review ? `${currentProposal.review.decision} by ${currentProposal.review.reviewer_id || 'reviewer not recorded'}` : 'Human review not recorded.'}</p><Link href="/dashboard/contracts/reviews" className="mt-4 inline-block text-sm font-semibold text-blue-700 hover:underline">Open review workflow</Link></div><div className="border border-slate-200 bg-white p-6"><p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Public verifier</p><h2 className="mt-1 text-2xl font-bold">{data.anchoredEvidenceCount > 0 ? 'Anchored evidence available' : 'Not available'}</h2><p className="mt-2 text-sm text-slate-600">{data.anchoredEvidenceCount} of {data.evidenceCount} evidence records have readable anchor metadata.</p><Link href="/public-verify" className="mt-4 inline-block text-sm font-semibold text-blue-700 hover:underline">Open public verification</Link></div></div>
      </section>
      <section className="border border-slate-200 bg-white p-6">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Workflow</p>
        <h2 className="mt-1 text-2xl font-bold">Live approval instance</h2>
        {!workflow && <p className="mt-3 text-sm text-slate-500">No workflow instance is recorded for this contract yet. Submitting a redline proposal starts the generic approval engine.</p>}
        {workflow && (
          <div className="mt-5 space-y-4">
            <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div><dt className="text-xs font-bold uppercase text-slate-500">Current state</dt><dd className="mt-1 font-semibold">{workflow.instance.current_state}</dd></div>
              <div><dt className="text-xs font-bold uppercase text-slate-500">Status</dt><dd className="mt-1 font-semibold">{workflow.instance.status}</dd></div>
              <div><dt className="text-xs font-bold uppercase text-slate-500">Entity</dt><dd className="mt-1 break-all font-mono text-xs">{workflow.instance.entity_type} · {workflow.instance.entity_id}</dd></div>
              <div><dt className="text-xs font-bold uppercase text-slate-500">Instance</dt><dd className="mt-1 break-all font-mono text-xs">{workflow.instance.instance_id}</dd></div>
            </dl>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">History</p>
              {workflow.history.length === 0 && <p className="mt-2 text-sm text-slate-500">No transition events recorded.</p>}
              <ol className="mt-3 space-y-2">
                {workflow.history.map((event) => (
                  <li key={`${event.transition_id}-${event.occurred_at}`} className="border border-slate-200 p-3 text-sm">
                    <p className="font-semibold text-slate-900">{event.from_state} → {event.to_state}</p>
                    <p className="mt-1 text-slate-600">{event.transition_id} by {event.actor_id}{event.actor_roles_at_time?.length ? ` (${event.actor_roles_at_time.join(', ')})` : ''}</p>
                    <p className="mt-1 text-xs text-slate-500">{event.occurred_at ? new Date(event.occurred_at).toLocaleString() : 'Time not recorded'}</p>
                    {event.comment && <p className="mt-1 italic text-slate-600">&quot;{event.comment}&quot;</p>}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </section>
      <section className="border border-slate-200 bg-white p-6"><p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Blockchain</p><h2 className="mt-1 text-2xl font-bold">Anchor details</h2>{data.anchors.length === 0 ? <p className="mt-3 text-sm text-slate-500">Anchor metadata is not available.</p> : <div className="mt-5 space-y-3">{data.anchors.map((anchor) => { const isBatch = anchor.is_mock || anchor.anchoring_method === 'MERKLE_BATCH'; return <article key={anchor.evidence_id} className="border border-slate-200 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="break-all font-mono text-xs text-slate-500">Evidence {anchor.evidence_id}</p><span className={`inline-block px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${isBatch ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-700'}`}>{isBatch ? 'Simulated Merkle batch' : 'Single-hash'}</span></div><dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-xs font-bold uppercase text-slate-500">Transaction</dt><dd className="break-all font-mono">{anchor.transaction_hash || 'Not available'}</dd></div><div><dt className="text-xs font-bold uppercase text-slate-500">Block</dt><dd>{anchor.block_number ?? 'Not available'}</dd></div><div><dt className="text-xs font-bold uppercase text-slate-500">Network</dt><dd>{anchor.blockchain_network || 'Not available'}</dd></div><div><dt className="text-xs font-bold uppercase text-slate-500">Evidence hash</dt><dd className="break-all font-mono text-xs">{anchor.evidence_hash || 'Not available'}</dd></div>{isBatch && anchor.merkle_root && <div className="sm:col-span-2 lg:col-span-4"><dt className="text-xs font-bold uppercase text-slate-500">Merkle root ({anchor.batch_size ?? '?'}-item batch {anchor.batch_id || ''})</dt><dd className="break-all font-mono text-xs">{anchor.merkle_root}</dd></div>}</dl></article> })}</div>}</section>
      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
    </main>
  )
}

function Metric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) { return <div className="bg-white p-4"><p className="text-xs font-bold uppercase tracking-wider text-slate-500">{label}</p><p className={`mt-2 break-words font-semibold ${mono ? 'font-mono text-xs' : ''}`}>{value}</p></div> }
