'use client'

// Phase 4 (2026-09-11, gold-standard visual consistency pass): rebuilt onto
// PageContainer/PageHeader/Card -- the prior version was raw border-only
// sections with no shared container, off the visual system used by
// Contracts/Findings/Contract Review/Legal Passport/Verification. Every
// fetch, handler, and piece of state below is unchanged; this is a
// presentation-only rewrite.

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Circle, Loader2, RefreshCw, RotateCcw, XCircle } from 'lucide-react'
import { apiFetch } from '../../../../../lib/api'
import { lifecycleStages, proofStatusLabel, publishedProofStatus, type LifecycleData, type ContractVersion, type LifecycleAnchor, type LifecyclePassport, type LifecycleProposal } from '../../../../../lib/contractLifecycle'
import { shouldAbortPreviousRequest } from '../../../../../lib/contractRequestLifecycle'
import { executiveSummaryPath, regenerateExecutiveSummaryRequest, severityBreakdownText, type ExecutiveSummary } from '../../../../../lib/executiveSummary'
import { useOrg } from '../../../../../components/OrgProvider'
import { Skeleton } from '../../../../../components/ui/skeleton'
import { Card, CardContent } from '../../../../../components/ui/card'
import { Button } from '../../../../../components/ui/button'
import { Badge } from '../../../../../components/ui/badge'
import { PageHeader } from '../../../../../components/ui/page-header'
import { PageContainer } from '../../../../../components/ui/container'
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
  const latestRequestIdRef = useRef(0)
  const latestRequestContextRef = useRef<string | null>(null)
  const latestSummaryRequestIdRef = useRef(0)
  const [data, setData] = useState<LifecycleData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retrying, setRetrying] = useState<string | null>(null)
  const [workflow, setWorkflow] = useState<{ instance: WorkflowInstance; history: WorkflowHistoryEvent[] } | null>(null)
  const [summary, setSummary] = useState<ExecutiveSummary | null>(null)
  const [summaryStatus, setSummaryStatus] = useState<'idle' | 'loading' | 'ready' | 'unavailable' | 'error'>('idle')
  const [summaryError, setSummaryError] = useState('')
  const [regenerating, setRegenerating] = useState(false)

  async function load(signal: AbortSignal, requestId: number, requestContextKey: string) {
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
      if (shouldAbortPreviousRequest(requestId, latestRequestIdRef.current, requestContextKey, latestRequestContextRef.current ?? requestContextKey)) return
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
      if (shouldAbortPreviousRequest(requestId, latestRequestIdRef.current, requestContextKey, latestRequestContextRef.current ?? requestContextKey)) return
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
        if (shouldAbortPreviousRequest(requestId, latestRequestIdRef.current, requestContextKey, latestRequestContextRef.current ?? requestContextKey)) return
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
      if (shouldAbortPreviousRequest(requestId, latestRequestIdRef.current, requestContextKey, latestRequestContextRef.current ?? requestContextKey)) return
      setError(cause instanceof Error ? cause.message : 'Unable to load contract lifecycle')
    } finally {
      if (requestId === latestRequestIdRef.current && !signal.aborted) setLoading(false)
    }
  }

  useEffect(() => {
    const requestContextKey = `${contractId}:${currentOrg?.org_id ?? 'none'}`
    const previousContextKey = latestRequestContextRef.current
    const requestId = latestRequestIdRef.current + 1
    latestRequestIdRef.current = requestId
    latestRequestContextRef.current = requestContextKey
    const controller = new AbortController()
    void load(controller.signal, requestId, requestContextKey)
    return () => {
      if (previousContextKey !== null && previousContextKey !== requestContextKey) {
        controller.abort()
      }
    }
  }, [contractId, currentOrg?.org_id])

  // Loaded independently of the main lifecycle data: a contract with no
  // analyzed version yet is a normal, common state (not an error) and
  // should not block or fail the rest of the page.
  async function loadSummary(signal: AbortSignal, requestId: number) {
    setSummaryStatus('loading')
    setSummaryError('')
    try {
      const response = await apiFetch(executiveSummaryPath(contractId), { signal })
      if (requestId !== latestSummaryRequestIdRef.current) return
      if (response.status === 404) {
        setSummary(null)
        setSummaryStatus('unavailable')
        return
      }
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load executive summary')
      const body: ExecutiveSummary = await response.json()
      if (requestId !== latestSummaryRequestIdRef.current) return
      setSummary(body)
      setSummaryStatus('ready')
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') return
      if (requestId !== latestSummaryRequestIdRef.current) return
      setSummaryStatus('error')
      setSummaryError(cause instanceof Error ? cause.message : 'Unable to load executive summary')
    }
  }

  useEffect(() => {
    const requestId = latestSummaryRequestIdRef.current + 1
    latestSummaryRequestIdRef.current = requestId
    const controller = new AbortController()
    void loadSummary(controller.signal, requestId)
    return () => {
      if (latestSummaryRequestIdRef.current !== requestId) {
        controller.abort()
      }
    }
  }, [contractId])

  async function regenerateSummary() {
    setRegenerating(true)
    setSummaryError('')
    try {
      const { path, method } = regenerateExecutiveSummaryRequest(contractId)
      const response = await apiFetch(path, { method })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to regenerate executive summary')
      const body: ExecutiveSummary = await response.json()
      setSummary(body)
      setSummaryStatus('ready')
    } catch (cause) {
      setSummaryError(cause instanceof Error ? cause.message : 'Unable to regenerate executive summary')
    } finally {
      setRegenerating(false)
    }
  }

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
      const requestContextKey = `${contractId}:${currentOrg?.org_id ?? 'none'}`
      const requestId = latestRequestIdRef.current + 1
      latestRequestIdRef.current = requestId
      latestRequestContextRef.current = requestContextKey
      const controller = new AbortController()
      await load(controller.signal, requestId, requestContextKey)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to retry analysis')
    } finally {
      setRetrying(null)
    }
  }

  if (loading) {
    return (
      <PageContainer>
        <div className="space-y-6">
          <div className="space-y-2">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-8 w-80" />
            <Skeleton className="h-4 w-56" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </PageContainer>
    )
  }
  if (error && !data) {
    return (
      <PageContainer>
        <div className="flex items-start gap-3 rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 p-6 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400" role="alert">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" />
          <p>{error}</p>
        </div>
      </PageContainer>
    )
  }
  if (!data) return null

  const stages = lifecycleStages(data)
  const current = data.versions.find((version) => version.is_current) ?? data.versions.at(-1)
  const currentPassport = data.passports.find((passport) => passport.contract_version === current?.version_number)
  const currentProposal = data.proposals.find((proposal) => proposal.published_version_id) ?? data.proposals.at(-1)
  const currentProofStatus = publishedProofStatus(data)

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Contract"
        title={data.contract.name || 'Contract name not available'}
        description={data.contract.contract_id}
        actions={
          <>
            {currentPassport && current?.version_number ? (
              <Link
                href={`/legal-passport?contractId=${encodeURIComponent(contractId)}&contractVersion=${current.version_number}`}
              >
                <Button type="button">Open Legal Passport</Button>
              </Link>
            ) : null}
            <Link href={`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`}>
              <Button type="button" variant="outline">Review findings</Button>
            </Link>
            <Link href="/dashboard/contracts">
              <Button type="button" variant="outline">All contracts</Button>
            </Link>
          </>
        }
      />

      <div className="mt-6 space-y-6">
        <Card className="overflow-hidden">
          <div className="grid divide-y divide-gray-200 dark:divide-gray-700 sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
            <Metric label="Current version" value={current?.version_number ? `V${current.version_number}` : 'Not available'} />
            <Metric label="Current status" value={proofStatusLabel(currentProofStatus)} />
            {currentPassport && current?.version_number ? (
              <Link
                href={`/legal-passport?contractId=${encodeURIComponent(contractId)}&contractVersion=${current.version_number}`}
                className="p-4 hover:bg-blue-50 dark:hover:bg-blue-950/30"
              >
                <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Passport</p>
                <p className="mt-2 break-words font-mono text-xs font-semibold text-[var(--brand-primary,#1d4ed8)] hover:underline">{currentPassport.passport_id}</p>
              </Link>
            ) : (
              <Metric label="Passport" value={data.contract.passport_id || 'Not created'} mono />
            )}
            <Metric label="Evidence" value={`${data.anchoredEvidenceCount}/${data.evidenceCount} anchored`} />
          </div>
        </Card>

        <Card>
          <CardContent>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Executive summary</p>
                <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">Plain-English brief</h2>
              </div>
              {summary && (
                <Button type="button" variant="outline" size="sm" onClick={() => void regenerateSummary()} disabled={regenerating}>
                  <RefreshCw className={`h-3.5 w-3.5 ${regenerating ? 'animate-spin' : ''}`} />
                  {regenerating ? 'Regenerating' : 'Regenerate'}
                </Button>
              )}
            </div>
            {summaryStatus === 'loading' && <p className="mt-4 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400"><Loader2 className="h-4 w-4 animate-spin" />Generating a plain-English brief for non-legal stakeholders...</p>}
            {summaryStatus === 'unavailable' && <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">This contract has not been analyzed yet -- run AI analysis on a version to generate an executive summary.</p>}
            {summary && (
              <div className="mt-4 space-y-4">
                <p className="text-sm leading-relaxed text-gray-800 dark:text-gray-200">{summary.summary}</p>
                <dl className="grid gap-3 text-sm sm:grid-cols-3">
                  <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Risk score</dt><dd className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{summary.risk_score ?? 'Not recorded'}{summary.risk_level ? ` (${summary.risk_level})` : ''}</dd></div>
                  <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Compliance score</dt><dd className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{summary.compliance_score ?? 'Not recorded'}</dd></div>
                  <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Findings by severity</dt><dd className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{severityBreakdownText(summary.findings_by_severity)}</dd></div>
                </dl>
              </div>
            )}
            {summaryError && <p className="mt-3 text-sm text-red-700 dark:text-red-400" role="alert">{summaryError}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Lifecycle</p>
                <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">From upload to public proof</h2>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Responsibilities: AI analysis · Legal review · Human approver · Public verifier</p>
            </div>
            <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {stages.map((stage) => {
                const Icon = icons[stage.status]
                return (
                  <div key={stage.key} className="flex min-h-28 gap-3 rounded-[var(--radius-md,0.5rem)] border border-gray-200 p-4 dark:border-gray-700">
                    <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${stage.status === 'complete' ? 'text-emerald-600' : stage.status === 'failed' ? 'text-red-600' : stage.status === 'active' ? 'animate-spin text-blue-600' : 'text-gray-400'}`} />
                    <div className="min-w-0">
                      <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">{stage.label}</p>
                      <p className="mt-1 font-semibold capitalize text-gray-900 dark:text-gray-100">{stage.status}</p>
                      <p className="mt-1 break-words text-sm text-gray-600 dark:text-gray-400">{stage.detail}</p>
                      {stage.href && <Link href={stage.href} className="mt-2 inline-block text-xs font-semibold text-[var(--brand-primary,#2563eb)] hover:underline">Open stage</Link>}
                      {stage.key === 'v2-analysis' && current?.recommended_action === 'retry' && currentProofStatus !== 'confirmed' && (
                        <button type="button" onClick={() => void retry(current)} disabled={retrying === current.version_id} className="ml-3 inline-flex items-center gap-1 text-xs font-semibold text-red-700 dark:text-red-400 disabled:opacity-50">
                          <RotateCcw className="h-3 w-3" />{retrying === current.version_id ? 'Retrying' : 'Retry'}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-6 xl:grid-cols-[1.2fr_.8fr]">
          <Card>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Versions</p>
                  <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">Version history</h2>
                </div>
                <Link href={`/contract-time-machine?contractId=${encodeURIComponent(contractId)}`} className="text-sm font-semibold text-[var(--brand-primary,#2563eb)] hover:underline">Open Time Machine</Link>
              </div>
              <div className="mt-5 space-y-3">
                {data.versions.length === 0 && <p className="text-sm text-gray-500 dark:text-gray-400">Version history is not available.</p>}
                {data.versions.map((version) => (
                  <article key={version.version_id} className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 p-4 dark:border-gray-700">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                        V{version.version_number}{' '}
                        {version.is_current ? <Badge variant="verified">Current version</Badge> : <Badge variant="secondary">Superseded version</Badge>}
                      </h3>
                      <span className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">{version.analysis_status || 'Not available'}</span>
                    </div>
                    <dl className="mt-3 grid gap-2 text-xs text-gray-600 dark:text-gray-400 sm:grid-cols-2">
                      <div><dt className="font-semibold">Version ID</dt><dd className="break-all font-mono">{version.version_id}</dd></div>
                      <div><dt className="font-semibold">Parent</dt><dd className="break-all font-mono">{version.parent_version_id || 'Not available'}</dd></div>
                      <div><dt className="font-semibold">Created by</dt><dd>{version.created_by || 'Not available'}</dd></div>
                      <div><dt className="font-semibold">Created</dt><dd>{version.created_at ? new Date(version.created_at).toLocaleString() : 'Not available'}</dd></div>
                      <div><dt className="font-semibold">Passport</dt><dd className="break-all font-mono">{version.passport_id || 'Not available'}</dd></div>
                      <div><dt className="font-semibold">Publication</dt><dd>{version.published ? 'Published' : 'Not published'}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
            </CardContent>
          </Card>
          <div className="space-y-6">
            <Card>
              <CardContent>
                <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Findings</p>
                <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">{data.findingsCount} persisted</h2>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Every finding retains its contract version relationship.</p>
                <Link href={`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`} className="mt-4 inline-block text-sm font-semibold text-[var(--brand-primary,#2563eb)] hover:underline">Review findings</Link>
              </CardContent>
            </Card>
            <Card>
              <CardContent>
                <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Redline and review</p>
                <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">{currentProposal?.status || 'No proposal recorded'}</h2>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{currentProposal?.review ? `${currentProposal.review.decision} by ${currentProposal.review.reviewer_id || 'reviewer not recorded'}` : 'Human review not recorded.'}</p>
                <Link href="/dashboard/contracts/reviews" className="mt-4 inline-block text-sm font-semibold text-[var(--brand-primary,#2563eb)] hover:underline">Open review workflow</Link>
              </CardContent>
            </Card>
            <Card>
              <CardContent>
                <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Public verifier</p>
                <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">{data.anchoredEvidenceCount > 0 ? 'Anchored evidence available' : 'Not available'}</h2>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{data.anchoredEvidenceCount} of {data.evidenceCount} evidence records have readable anchor metadata.</p>
                <Link href="/public-verify" className="mt-4 inline-block text-sm font-semibold text-[var(--brand-primary,#2563eb)] hover:underline">Open public verification</Link>
              </CardContent>
            </Card>
          </div>
        </div>

        <Card>
          <CardContent>
            <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Workflow</p>
            <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">Live approval instance</h2>
            {!workflow && <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">No workflow instance is recorded for this contract yet. Submitting a redline proposal starts the generic approval engine.</p>}
            {workflow && (
              <div className="mt-5 space-y-4">
                <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                  <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Current state</dt><dd className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{workflow.instance.current_state}</dd></div>
                  <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Status</dt><dd className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{workflow.instance.status}</dd></div>
                  <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Entity</dt><dd className="mt-1 break-all font-mono text-xs text-gray-700 dark:text-gray-300">{workflow.instance.entity_type} · {workflow.instance.entity_id}</dd></div>
                  <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Instance</dt><dd className="mt-1 break-all font-mono text-xs text-gray-700 dark:text-gray-300">{workflow.instance.instance_id}</dd></div>
                </dl>
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">History</p>
                  {workflow.history.length === 0 && <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No transition events recorded.</p>}
                  <ol className="mt-3 space-y-2">
                    {workflow.history.map((event) => (
                      <li key={`${event.transition_id}-${event.occurred_at}`} className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 p-3 text-sm dark:border-gray-700">
                        <p className="font-semibold text-gray-900 dark:text-gray-100">{event.from_state} → {event.to_state}</p>
                        <p className="mt-1 text-gray-600 dark:text-gray-400">{event.transition_id} by {event.actor_id}{event.actor_roles_at_time?.length ? ` (${event.actor_roles_at_time.join(', ')})` : ''}</p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">{event.occurred_at ? new Date(event.occurred_at).toLocaleString() : 'Time not recorded'}</p>
                        {event.comment && <p className="mt-1 italic text-gray-600 dark:text-gray-400">&quot;{event.comment}&quot;</p>}
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Blockchain</p>
            <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">Anchor details</h2>
            {data.anchors.length === 0 ? (
              <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">Anchor metadata is not available.</p>
            ) : (
              <div className="mt-5 space-y-3">
                {data.anchors.map((anchor) => {
                  const isBatch = anchor.is_mock || anchor.anchoring_method === 'MERKLE_BATCH'
                  return (
                    <article key={anchor.evidence_id} className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 p-4 dark:border-gray-700">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="break-all font-mono text-xs text-gray-500 dark:text-gray-400">Evidence {anchor.evidence_id}</p>
                        <Badge variant={isBatch ? 'secondary' : 'default'}>{isBatch ? 'Simulated Merkle batch' : 'Single-hash'}</Badge>
                      </div>
                      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                        <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Transaction</dt><dd className="break-all font-mono text-gray-900 dark:text-gray-100">{anchor.transaction_hash || 'Not available'}</dd></div>
                        <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Block</dt><dd className="text-gray-900 dark:text-gray-100">{anchor.block_number ?? 'Not available'}</dd></div>
                        <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Network</dt><dd className="text-gray-900 dark:text-gray-100">{anchor.blockchain_network || 'Not available'}</dd></div>
                        <div><dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Evidence hash</dt><dd className="break-all font-mono text-xs text-gray-900 dark:text-gray-100">{anchor.evidence_hash || 'Not available'}</dd></div>
                        {isBatch && anchor.merkle_root && (
                          <div className="sm:col-span-2 lg:col-span-4">
                            <dt className="text-xs font-bold uppercase text-gray-500 dark:text-gray-400">Merkle root ({anchor.batch_size ?? '?'}-item batch {anchor.batch_id || ''})</dt>
                            <dd className="break-all font-mono text-xs text-gray-900 dark:text-gray-100">{anchor.merkle_root}</dd>
                          </div>
                        )}
                      </dl>
                    </article>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {error && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      </div>
    </PageContainer>
  )
}

function Metric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="p-4">
      <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`mt-2 break-words font-semibold text-gray-900 dark:text-gray-100 ${mono ? 'font-mono text-xs' : ''}`}>{value}</p>
    </div>
  )
}
