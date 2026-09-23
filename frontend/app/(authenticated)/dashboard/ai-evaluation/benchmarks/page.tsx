'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, FileText, LockKeyhole, Save, ShieldCheck } from 'lucide-react'
import { apiFetch } from '../../../../../lib/api'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { APPROVE_AND_NEXT_LABEL, APPROVE_LABEL, FINALIZE_AND_NEXT_LABEL, FINALIZE_LABEL, MARK_IN_REVIEW_AND_NEXT_LABEL, MARK_IN_REVIEW_LABEL, SAVE_AND_NEXT_LABEL, SAVE_DRAFT_LABEL, aiBlindPayloadKeys, benchmarkContinueTarget, benchmarkLandingPath, benchmarkProgression, benchmarkReviewPath, focusNewFindingCategory, hasNextFinding, isFinalized, isVisibleFinding, nextFindingIndex, orderBenchmarkContracts, reviewProgress, scrollWorkspaceToTop, transitionFinding, REVIEW_STATUSES, saveFinding, type BenchmarkFinding, type FindingDraft, type ReviewContract, type ReviewStatus, type TransitionStatus } from '../../../../../lib/benchmarkReview'
import { ReviewFeedback } from '../../../../../components/benchmark-review-feedback'
import { BenchmarkProgressionPanel } from '../../../../../components/benchmark-progression'
import { CreateFindingAction } from '../../../../../components/benchmark-create-finding-action'
import { PageContainer } from '../../../../../components/ui/container'
import { PageHeader } from '../../../../../components/ui/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '../../../../../components/ui/card'
import { Button } from '../../../../../components/ui/button'
import { Badge } from '../../../../../components/ui/badge'

type Dataset = { dataset_version_id: string; name: string; version_label: string; contract_count: number; ai_blind: boolean; status: string }
type Reviewer = { user_id: string; display_name: string; email?: string | null; roles: string[] }
type Workspace = { dataset: Dataset; contract_rows: ReviewContract[]; ground_truth_findings: BenchmarkFinding[]; review_progress: { contract_total: number; reviewed_total: number; total_findings: number } }
type Draft = FindingDraft

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const

async function readJson(response: Response) {
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.detail || 'Unable to load benchmark review data')
  return data
}

/**
 * Placeholder shown while the workspace payload is in flight.
 *
 * The review shell (page header, AI-blind badge, dataset selector) renders
 * immediately; only the data-dependent sections wait. Previously the whole
 * page was replaced by a one-line "Loading..." screen until the slowest of the
 * benchmark list, workspace and reviewer requests had resolved.
 */
function ReviewWorkspaceSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-4 py-6">
        <p role="status" className="text-sm text-gray-500">Loading benchmark review workspace...</p>
        <div className="h-4 w-32 animate-pulse rounded bg-gray-200" />
        <div className="h-7 w-72 animate-pulse rounded bg-gray-200" />
        <div className="h-4 w-96 max-w-full animate-pulse rounded bg-gray-200" />
        <div className="space-y-2 pt-2">
          {[0, 1, 2, 3, 4, 5].map((row) => (
            <div key={row} className="h-3 w-full animate-pulse rounded bg-gray-100" />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export default function BenchmarkReviewPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const isDedicatedReview = pathname.endsWith('/benchmarks/review')
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetId, setDatasetId] = useState('')
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [reviewers, setReviewers] = useState<Reviewer[]>([])
  const [contractId, setContractId] = useState('')
  const [selectedFindingId, setSelectedFindingId] = useState('')
  const [status, setStatus] = useState<ReviewStatus>('ALL')
  const [search, setSearch] = useState('')
  const [reviewerFilter, setReviewerFilter] = useState('')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [creating, setCreating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  // Feedback for the save workflow itself, rendered next to the Save buttons.
  // Without it a successful PATCH produced no visible change at all, because
  // the form re-rendered from the refreshed server record and the queue chip
  // was often already present.
  const [saveFeedback, setSaveFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)
  // Focus target for the create-finding form, plus the one-shot flag that says
  // a create was just started (so the effect below focuses exactly once).
  const categoryInputRef = useRef<HTMLInputElement | null>(null)
  const focusCategoryOnCreate = useRef(false)
  // Benchmark-level progression panel: scrolled into view when the benchmark
  // becomes FINALIZED during the session (it sits below a long review page, so
  // without this the reviewer only saw "No next finding" and stopped).
  const progressionRef = useRef<HTMLDivElement | null>(null)
  const previousProgressionKind = useRef<string | null>(null)
  // Set only by "Continue to Next Contract": the next benchmark must open at the
  // top of its workspace instead of inheriting the previous contract's scroll
  // offset (client-side navigation preserves it).
  const positionWorkspaceAtTopOnContractChange = useRef(false)
  const requestedDatasetId = searchParams.get('dataset_id') || ''
  const requestedContractId = searchParams.get('contract_id') || ''

  useEffect(() => {
    void apiFetch('/api/evaluation/benchmarks')
      .then(readJson)
      .then((items: Dataset[]) => {
        setDatasets(items)
        const internal = items.find((item) => item.name === 'LexProof Internal Benchmark v1' || item.name.includes('Internal Benchmark v1')) || items[0]
        const requested = items.find((item) => item.dataset_version_id === requestedDatasetId)
        setDatasetId(requested?.dataset_version_id || internal?.dataset_version_id || '')
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : 'Unable to load benchmarks'))
      .finally(() => setLoading(false))
  }, [])

  async function loadWorkspace(id: string): Promise<Workspace | null> {
    if (!id) return null
    setLoading(true)
    setError('')
    setSaveFeedback(null)
    // Reviewers only populate the assignment dropdown, so they are loaded
    // concurrently but must not hold up the workspace payload (contract
    // metadata, document text and the finding queue) that the user clicked
    // through for. A reviewer failure is non-fatal for the same reason.
    const reviewersPromise = apiFetch(`/api/evaluation/benchmarks/${encodeURIComponent(id)}/reviewers`)
      .then(readJson)
      .then((items: Reviewer[]) => setReviewers(items))
      .catch(() => undefined)
    let payload: Workspace | null = null
    try {
      const workspaceResponse = await apiFetch(`/api/evaluation/benchmarks/${encodeURIComponent(id)}/workspace`)
      const nextWorkspace = await readJson(workspaceResponse) as Workspace
      // Order once, here: the contract list, the default selection and the
      // "Continue to Next Contract" progression all walk this same sequence.
      const ordered: Workspace = { ...nextWorkspace, contract_rows: orderBenchmarkContracts(nextWorkspace.contract_rows || []) }
      if (!aiBlindPayloadKeys(ordered as unknown as Record<string, unknown>)) throw new Error('AI-blind review boundary violated')
      payload = ordered
      setWorkspace(ordered)
      const firstContract = ordered.contract_rows[0]
      setContractId((current) => {
        if (requestedContractId && ordered.contract_rows.some((row) => row.contract_id === requestedContractId)) return requestedContractId
        return ordered.contract_rows.some((row) => row.contract_id === current) ? current : firstContract?.contract_id || ''
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load review workspace')
    } finally {
      setLoading(false)
    }
    await reviewersPromise
    return payload
  }

  useEffect(() => { void loadWorkspace(datasetId) }, [datasetId, requestedContractId])

  const findings = workspace?.ground_truth_findings || []
  const visibleFindings = useMemo(() => findings.filter((finding) => finding.contract_id === contractId && isVisibleFinding(finding, status, search, reviewerFilter)), [findings, contractId, status, search, reviewerFilter])
  const selectedFinding = visibleFindings.find((finding) => finding.ground_truth_id === selectedFindingId) || visibleFindings[0] || null
  const selectedContract = workspace?.contract_rows.find((row) => row.contract_id === contractId) || null
  const progress = reviewProgress(workspace?.contract_rows || [], findings)
  // While a new finding is being created the selected finding is only the
  // template for the next id in the queue, so a finalized neighbour must not
  // lock the Save buttons (it did: `disabled={readOnly}` made Save a no-op).
  const readOnly = !creating && isFinalized(selectedFinding)
  // Review progression for the current benchmark contract. Pure derivation
  // from the loaded workspace: it issues no read and no write, so it can never
  // start an analysis run or create a ground-truth record.
  const progression = useMemo(
    () => benchmarkProgression({ contracts: workspace?.contract_rows ?? [], findings, currentContractId: contractId, datasetId }),
    [workspace, findings, contractId, datasetId],
  )
  // Whether the reviewer has somewhere to advance to. Every "& Next" action is
  // gated on this (never wraps), so the last finding never offers a Next action.
  const hasNext = hasNextFinding(visibleFindings, selectedFinding?.ground_truth_id || '')

  /**
   * Brings the benchmark-level action into view when the current benchmark
   * becomes finalized during this session. Finalizing the last finding happens
   * at the bottom of a long page, so without this the action renders below the
   * fold and the reviewer sees only the finding-level message.
   *
   * Deliberately ignores the first kind computed from a loaded workspace: a
   * contract that is already finalized when the page opens must land at the top
   * of the workspace (title, progress, AI-blind notice, queue), not scrolled
   * down to this panel.
   */
  useEffect(() => {
    if (!workspace) return
    const previous = previousProgressionKind.current
    previousProgressionKind.current = progression.kind
    if (previous === null || previous === progression.kind) return
    if (progression.kind === 'not-finalized') return
    progressionRef.current?.scrollIntoView({ block: 'center' })
  }, [progression.kind, workspace])

  useEffect(() => {
    if (selectedFinding?.ground_truth_id) setSelectedFindingId(selectedFinding.ground_truth_id)
    else if (!creating) setSelectedFindingId('')
  }, [selectedFinding?.ground_truth_id, creating])

  useEffect(() => {
    setCreating(false)
    setDraft(null)
  }, [contractId])

  /**
   * Predictable landing position for a contract opened by Continue to Next
   * Contract. Runs once per Continue click and only on the contract change it
   * causes, so it cannot interfere with the finding editor or the create-finding
   * focus/scroll behaviour.
   */
  useEffect(() => {
    if (!positionWorkspaceAtTopOnContractChange.current) return
    positionWorkspaceAtTopOnContractChange.current = false
    scrollWorkspaceToTop(typeof window === 'undefined' ? null : window)
  }, [contractId])

  useEffect(() => {
    if (!selectedFinding || creating) return
    setDraft({ ...selectedFinding })
  }, [selectedFinding, creating])

  function updateDraft<K extends keyof Draft>(key: K, value: Draft[K]) {
    setSaveFeedback(null)
    setDraft((current) => current ? { ...current, [key]: value } : current)
  }

  function selectContract(id: string, versionId?: string) {
    setContractId(id)
    setStatus('ALL')
    setSelectedFindingId('')
    setSaveFeedback(null)
    if (datasetId && versionId) router.push(benchmarkReviewPath(datasetId, id, versionId))
  }

  /**
   * "Continue to Next Contract": open the next benchmark's review workspace.
   *
   * The next benchmark is loaded by the same AI-blind read the reviewer arrived
   * through, so producing this navigation can never expose production AI
   * findings, start an AI analysis, or create a ground-truth record. Only the
   * per-benchmark view state (filters, selection, draft) is reset, so the next
   * contract opens on its own finding queue. Previous and Back to Benchmarks
   * navigation are unchanged.
   */
  function continueToNextBenchmark() {
    const target = benchmarkContinueTarget(progression)
    if (!target) return
    setStatus('ALL')
    setSearch('')
    setReviewerFilter('')
    setSelectedFindingId('')
    setCreating(false)
    setDraft(null)
    setSaveFeedback(null)
    setContractId(target.contractId)
    // Open the next benchmark at the top of its workspace rather than wherever
    // the previous contract happened to be scrolled to.
    positionWorkspaceAtTopOnContractChange.current = true
    router.push(target.path)
  }

  function startCreate() {
    if (!selectedContract) return
    focusCategoryOnCreate.current = true
    setCreating(true)
    setSelectedFindingId('')
    setSaveFeedback(null)
    setDraft({ contract_id: selectedContract.contract_id, version_id: selectedContract.version_id, finding_category: '', clause_reference: '', expected_severity: 'MEDIUM', expected_finding: '', expected_evidence: '', expected_recommendation: '' })
  }

  /**
   * Starting a finding is local-only (no request is issued). The reviewer is
   * put straight into the Category field once the form has rendered, unless
   * they are already typing in another field.
   */
  useEffect(() => {
    if (!creating || !focusCategoryOnCreate.current) return
    focusCategoryOnCreate.current = false
    focusNewFindingCategory(categoryInputRef.current, document.activeElement)
  }, [creating])

  /**
   * Both Save buttons go through saveFinding(): validate, persist, refresh the
   * queue, then report exactly what happened. Previously the PATCH succeeded
   * but nothing told the reviewer, and Save & Next recomputed its target from
   * the stale pre-save queue (so it either jumped to item 1 or re-selected the
   * item already on screen).
   */
  async function saveDraft(moveNext = false) {
    if (!draft || readOnly || !datasetId) return
    setSaving(true)
    setError('')
    setSaveFeedback(null)
    try {
      const result = await saveFinding({
        draft,
        datasetId,
        // 'create' only while the reviewer is composing a new finding; every
        // other save is an update of an existing ground-truth finding.
        intent: creating ? 'create' : 'update',
        moveNext,
        filters: { contractId, status, search, reviewerFilter },
        request: apiFetch,
        reloadFindings: async () => {
          const fresh = await loadWorkspace(datasetId)
          return fresh?.ground_truth_findings ?? []
        },
      })
      if (result.status !== 'saved') {
        setSaveFeedback({ kind: 'error', message: result.message })
        return
      }
      setStatus(result.filters.status)
      setSearch(result.filters.search)
      setReviewerFilter(result.filters.reviewerFilter)
      setCreating(false)
      setSelectedFindingId(result.selectedFindingId)
      setSaveFeedback({ kind: 'success', message: result.message })
    } catch (reason) {
      setSaveFeedback({ kind: 'error', message: reason instanceof Error ? reason.message : 'Unable to save finding' })
    } finally {
      setSaving(false)
    }
  }

  /**
   * Mark In Review / Approve / Finalize, with and without "& Next".
   *
   * One write per click, then the queue is reloaded and the advance target is
   * taken from that fresh queue — never from what was on screen before the
   * click, and never by wrapping back to the first finding.
   */
  async function transitionTo(nextStatus: TransitionStatus, advance = false) {
    if (!selectedFinding || readOnly || !datasetId) return
    setSaving(true)
    setSaveFeedback(null)
    try {
      const result = await transitionFinding({
        datasetId,
        groundTruthId: selectedFinding.ground_truth_id,
        status: nextStatus,
        moveNext: advance,
        filters: { contractId, status, search, reviewerFilter },
        request: apiFetch,
        reloadFindings: async () => (await loadWorkspace(datasetId))?.ground_truth_findings ?? [],
      })
      if (result.status !== 'transitioned') {
        setSaveFeedback({ kind: 'error', message: result.message })
        return
      }
      setStatus(result.filters.status)
      setSearch(result.filters.search)
      setReviewerFilter(result.filters.reviewerFilter)
      setSelectedFindingId(result.selectedFindingId)
      // State the benchmark-level consequence next to the finding-level message,
      // so "Finding marked Finalized." can never read as a dead end while C8 (or
      // any other benchmark) remains. Derived from the reloaded findings.
      const hint = benchmarkProgression({
        contracts: workspace?.contract_rows ?? [],
        findings: result.findings,
        currentContractId: contractId,
        datasetId,
      })
      const nextStep = hint.kind === 'next'
        ? `Benchmark finalized \u2014 continue to ${hint.next.contract_name}.`
        : hint.kind === 'complete' ? 'Benchmark finalized \u2014 this was the last benchmark in the dataset.' : ''
      setSaveFeedback({ kind: 'success', message: [result.message, nextStep].filter(Boolean).join(' ') })
    } catch (reason) {
      setSaveFeedback({ kind: 'error', message: reason instanceof Error ? reason.message : 'Unable to change finding status' })
    } finally {
      setSaving(false)
    }
  }

  async function assign(reviewerId: string) {
    if (!selectedFinding || readOnly) return
    setSaving(true)
    setSaveFeedback(null)
    try {
      await readJson(await apiFetch(`/api/evaluation/benchmarks/${encodeURIComponent(datasetId)}/findings/${encodeURIComponent(selectedFinding.ground_truth_id)}/assign`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reviewer_id: reviewerId }) }))
      await loadWorkspace(datasetId)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to assign finding') } finally { setSaving(false) }
  }

  function move(direction: -1 | 1) {
    const index = visibleFindings.findIndex((finding) => finding.ground_truth_id === selectedFinding?.ground_truth_id)
    const next = nextFindingIndex(index < 0 ? 0 : index, visibleFindings.length, direction)
    if (next >= 0) {
      setSaveFeedback(null)
      setSelectedFindingId(visibleFindings[next].ground_truth_id)
    }
  }

  return (
    <PageContainer>
      <PageHeader eyebrow="AI Evaluation" title={isDedicatedReview ? 'Benchmark Review' : 'Benchmarks'} description={isDedicatedReview ? 'Human ground-truth review. Contract text only; AI findings and evaluation outputs are intentionally unavailable.' : 'Select a benchmark contract to enter its AI-blind human review workspace.'} actions={isDedicatedReview ? <div className="flex items-center gap-2"><a href={benchmarkLandingPath(datasetId)} className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"><ArrowLeft className="h-4 w-4" />Back to Benchmarks</a><Badge variant="verified"><LockKeyhole className="mr-1 h-3.5 w-3.5" />AI-blind</Badge></div> : undefined} />
      <div className="mt-6 space-y-6">
        {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>}
        <Card className={isDedicatedReview ? 'border-blue-100 bg-blue-50/30' : ''}>
          <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
            <div><label className="text-xs font-semibold uppercase tracking-wide text-gray-500" htmlFor="benchmark">Dataset</label><select id="benchmark" value={datasetId} onChange={(event) => setDatasetId(event.target.value)} className="mt-1 block min-w-72 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"><option value="">Select dataset</option>{datasets.map((dataset) => <option key={dataset.dataset_version_id} value={dataset.dataset_version_id}>{dataset.name} · {dataset.version_label}</option>)}</select></div>
            <div className="flex flex-wrap gap-6 text-sm"><span><strong>Contract {selectedContract?.reviewed_count ?? 0}/{selectedContract?.finding_count ?? 0}</strong><span className="ml-1 text-gray-500">reviewed</span></span><span><strong>Dataset {progress.contractsReviewed}/{progress.contractTotal}</strong><span className="ml-1 text-gray-500">reviewed</span></span><span><strong>{progress.findingsReviewed}/{progress.findingTotal}</strong><span className="ml-1 text-gray-500">findings reviewed</span></span></div>
          </CardContent>
        </Card>

            <div className={`grid gap-6 ${isDedicatedReview ? 'xl:grid-cols-1' : 'xl:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.4fr)]'}`}>
          <Card className={`h-fit ${isDedicatedReview ? 'hidden' : ''}`}>
                <CardHeader><CardTitle className="text-lg">Contracts <span className="text-sm font-normal text-gray-500">({workspace?.contract_rows.length ?? 0})</span></CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {(workspace?.contract_rows ?? []).map((contract) => <button key={contract.contract_id} type="button" onClick={() => selectContract(contract.contract_id, contract.version_id)} className={`w-full rounded-lg border p-4 text-left transition ${contract.contract_id === contractId ? 'border-blue-500 bg-blue-50' : 'border-gray-200 bg-white hover:border-blue-300'}`}><div className="flex items-start justify-between gap-3"><div><p className="font-semibold text-gray-900">{contract.contract_name}</p><p className="mt-1 text-xs text-gray-500">Version {contract.version_number ?? contract.version_id}</p></div><FileText className="h-4 w-4 text-gray-400" /></div><div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-500"><span>{contract.finding_count} findings</span><span>{contract.reviewed_count}/{contract.finding_count} reviewed</span></div><span className="mt-3 inline-flex text-xs font-semibold text-blue-700">Open Review <ArrowRight className="ml-1 h-3.5 w-3.5" /></span></button>)}
            </CardContent>
          </Card>

          <div id="benchmark-review-panel" className={`space-y-6 scroll-mt-6 ${isDedicatedReview ? '' : 'hidden'}`}>
            {loading && !workspace && <ReviewWorkspaceSkeleton />}

            {/* The reviewer's next task, first: as soon as this benchmark is
                FINALIZED the Continue action is the most important thing on the
                page, so it is rendered above the queue and document text rather
                than below a long editor. Renders nothing until FINALIZED. */}
            <div ref={progressionRef} className="scroll-mt-6">
              <BenchmarkProgressionPanel progression={progression} onContinue={continueToNextBenchmark} />
            </div>
            {selectedContract && <Card><CardContent className="flex flex-wrap items-start justify-between gap-4 py-5"><div><p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Selected contract</p><h2 className="mt-1 text-xl font-bold text-gray-900">{selectedContract.contract_name}</h2><p className="text-sm text-gray-500">Version {selectedContract.version_number ?? selectedContract.version_id} · {selectedContract.finding_count} findings · Assigned reviewer {selectedContract.assigned_reviewer_id || 'Unassigned'} · Review progress {selectedContract.reviewed_count}/{selectedContract.finding_count}</p></div><CreateFindingAction onCreate={startCreate} disabled={creating} /></CardContent></Card>}

            {selectedContract && <Card><CardContent className="space-y-3 py-4"><div className="flex items-center justify-between"><h3 className="font-semibold text-gray-900">Finding queue</h3><span className="text-xs text-gray-500">{visibleFindings.length} visible</span></div><div className="grid gap-2 md:grid-cols-[1fr_auto_auto]"><input aria-label="Search findings" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search category, clause, finding" className="rounded-md border border-gray-300 px-3 py-2 text-sm" /><select aria-label="Filter status" value={status} onChange={(event) => setStatus(event.target.value as ReviewStatus)} className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">{REVIEW_STATUSES.map((item) => <option key={item}>{item}</option>)}</select><select aria-label="Filter assigned reviewer" value={reviewerFilter} onChange={(event) => setReviewerFilter(event.target.value)} className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"><option value="">All reviewers</option>{reviewers.map((reviewer) => <option key={reviewer.user_id} value={reviewer.user_id}>{reviewer.display_name}</option>)}</select></div>{visibleFindings.length === 0 ? <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-4"><div><p className="text-sm font-semibold text-gray-800">No human ground-truth findings yet</p><p className="mt-1 text-xs text-gray-500">Review the document text and create the first finding independently. Production AI findings are intentionally not shown here.</p></div><CreateFindingAction onCreate={startCreate} disabled={creating} /></div> : <div className="flex flex-wrap gap-2">{visibleFindings.map((finding, index) => <button type="button" key={finding.ground_truth_id} onClick={() => { setCreating(false); setSelectedFindingId(finding.ground_truth_id) }} className={`rounded-full border px-3 py-1 text-xs ${finding.ground_truth_id === selectedFinding?.ground_truth_id ? 'border-blue-600 bg-blue-600 text-white' : 'border-gray-300 text-gray-600'}`}>{index + 1}. {finding.finding_category || 'Untitled'} · {finding.review_status}</button>)}</div>}</CardContent></Card>}

            {selectedContract && <Card><CardHeader><CardTitle className="flex items-center gap-2 text-lg"><FileText className="h-5 w-5 text-blue-600" />Document text <span className="text-xs font-normal text-gray-500">Version {selectedContract.version_number ?? selectedContract.version_id}</span></CardTitle></CardHeader><CardContent><pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm leading-6 text-gray-700">{selectedContract.document_text || 'No extracted document text is available for this version.'}</pre></CardContent></Card>}

            {(selectedFinding || creating) && <Card><CardHeader><div className="flex flex-wrap items-center justify-between gap-3"><CardTitle className="text-lg">{creating ? 'Create human finding' : `Finding ${Math.max(1, visibleFindings.findIndex((finding) => finding.ground_truth_id === selectedFinding?.ground_truth_id) + 1)} of ${visibleFindings.length}`}</CardTitle>{!creating && <Badge variant={readOnly ? 'secondary' : 'pending'}>{selectedFinding?.review_status}</Badge>}</div></CardHeader><CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2"><label className="text-sm font-medium text-gray-700">Category<input ref={categoryInputRef} value={draft?.finding_category || ''} disabled={readOnly} onChange={(event) => updateDraft('finding_category', event.target.value)} className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 font-normal" /></label><label className="text-sm font-medium text-gray-700">Clause / reference<input value={draft?.clause_reference || ''} disabled={readOnly} onChange={(event) => updateDraft('clause_reference', event.target.value)} className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 font-normal" /></label></div>
              <label className="block text-sm font-medium text-gray-700">Severity<select value={draft?.expected_severity || 'MEDIUM'} disabled={readOnly} onChange={(event) => updateDraft('expected_severity', event.target.value as Draft['expected_severity'])} className="mt-1 block rounded-md border border-gray-300 bg-white px-3 py-2 font-normal">{SEVERITIES.map((severity) => <option key={severity}>{severity}</option>)}</select></label>
              <label className="block text-sm font-medium text-gray-700">Expected finding<textarea value={draft?.expected_finding || ''} disabled={readOnly} onChange={(event) => updateDraft('expected_finding', event.target.value)} rows={3} className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 font-normal" /></label><label className="block text-sm font-medium text-gray-700">Expected evidence<textarea value={draft?.expected_evidence || ''} disabled={readOnly} onChange={(event) => updateDraft('expected_evidence', event.target.value)} rows={3} className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 font-normal" /></label><label className="block text-sm font-medium text-gray-700">Expected recommendation<textarea value={draft?.expected_recommendation || ''} disabled={readOnly} onChange={(event) => updateDraft('expected_recommendation', event.target.value)} rows={2} className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 font-normal" /></label>
              <label className="block text-sm font-medium text-gray-700">Assigned reviewer<select value={draft?.reviewer_id || ''} disabled={readOnly} onChange={(event) => { updateDraft('reviewer_id', event.target.value); if (!creating && selectedFinding) void assign(event.target.value) }} className="mt-1 block rounded-md border border-gray-300 bg-white px-3 py-2 font-normal"><option value="">Select reviewer</option>{reviewers.map((reviewer) => <option key={reviewer.user_id} value={reviewer.user_id}>{reviewer.display_name} · {reviewer.roles.join(', ')}</option>)}</select><span className="mt-1 block text-xs font-normal text-gray-500">{creating ? 'Applies to the finding being created once saved.' : 'Reassigns this finding immediately.'}</span></label>
              <ReviewFeedback success={saveFeedback?.kind === 'success' ? saveFeedback.message : undefined} error={saveFeedback?.kind === 'error' ? saveFeedback.message : undefined} />
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 pt-4">
                <div className="flex gap-2">
                  <Button type="button" variant="outline" onClick={() => move(-1)} disabled={visibleFindings.length < 2}><ArrowLeft className="mr-2 h-4 w-4" />Previous</Button>
                  {/* No Next action on the last finding: there is nowhere left to advance to. */}
                  {!creating && hasNext && <Button type="button" variant="outline" onClick={() => void saveDraft(true)} disabled={saving || readOnly}><Save className="mr-2 h-4 w-4" />{SAVE_AND_NEXT_LABEL}</Button>}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" onClick={() => void saveDraft(false)} disabled={saving || readOnly}>{SAVE_DRAFT_LABEL}</Button>
                  {!creating && selectedFinding?.review_status === 'DRAFT' && <Button type="button" onClick={() => void transitionTo('IN_REVIEW')} disabled={saving}>{MARK_IN_REVIEW_LABEL}</Button>}
                  {!creating && selectedFinding?.review_status === 'DRAFT' && hasNext && <Button type="button" variant="outline" onClick={() => void transitionTo('IN_REVIEW', true)} disabled={saving}>{MARK_IN_REVIEW_AND_NEXT_LABEL}</Button>}
                  {!creating && selectedFinding?.review_status === 'IN_REVIEW' && <Button type="button" onClick={() => void transitionTo('APPROVED')} disabled={saving}>{APPROVE_LABEL}</Button>}
                  {!creating && selectedFinding?.review_status === 'IN_REVIEW' && hasNext && <Button type="button" variant="outline" onClick={() => void transitionTo('APPROVED', true)} disabled={saving}>{APPROVE_AND_NEXT_LABEL}</Button>}
                  {!creating && selectedFinding?.review_status === 'APPROVED' && <Button type="button" onClick={() => void transitionTo('FINALIZED')} disabled={saving}>{FINALIZE_LABEL}</Button>}
                  {/* Advancing from APPROVED is the last finding-level step before the
                      benchmark itself finalizes; `hasNext` (never wraps) keeps this
                      off the last finding, where benchmark progression takes over. */}
                  {!creating && selectedFinding?.review_status === 'APPROVED' && hasNext && <Button type="button" variant="outline" onClick={() => void transitionTo('FINALIZED', true)} disabled={saving}>{FINALIZE_AND_NEXT_LABEL}</Button>}
                </div>
              </div>
              {readOnly && <p className="flex items-center gap-2 text-xs text-gray-500"><ShieldCheck className="h-4 w-4" />Finalized findings are read-only.</p>}
            </CardContent></Card>}

            {/* Same action as the top of the workspace, at the bottom of the
                queue, so starting another finding never needs a scroll back up.
                Same handler, same create mode, nothing written until save. */}
            {selectedContract && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-4">
              <p className="text-sm text-gray-600">Add another human ground-truth finding for <strong className="font-semibold text-gray-900">{selectedContract.contract_name}</strong>.</p>
              <CreateFindingAction onCreate={startCreate} disabled={creating} />
            </div>}
          </div>
        </div>
      </div>
    </PageContainer>
  )
}
