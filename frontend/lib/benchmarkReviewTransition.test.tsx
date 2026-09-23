import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { BenchmarkProgressionPanel } from '../components/benchmark-progression'
import { CreateFindingAction } from '../components/benchmark-create-finding-action'
import {
  APPROVE_AND_NEXT_LABEL,
  APPROVE_LABEL,
  CONTINUE_TO_NEXT_CONTRACT,
  BENCHMARK_REVIEW_COMPLETE,
  CREATE_FINDING_LABEL,
  FINALIZE_AND_NEXT_LABEL,
  FINALIZE_LABEL,
  MARK_IN_REVIEW_AND_NEXT_LABEL,
  MARK_IN_REVIEW_LABEL,
  SAVE_AND_NEXT_LABEL,
  SAVE_DRAFT_LABEL,
  benchmarkContinueTarget,
  benchmarkProgression,
  focusNewFindingCategory,
  hasNextFinding,
  nextFinding,
  orderBenchmarkContracts,
  scrollWorkspaceToTop,
  transitionFinding,
  transitionFindingMessage,
  type BenchmarkFinding,
  type ReviewContract,
  type ReviewFilters,
  type TransitionFindingOptions,
  type TransitionStatus,
} from './benchmarkReview'

const finding = (overrides: Partial<BenchmarkFinding> = {}): BenchmarkFinding => ({
  ground_truth_id: 'g-1',
  contract_id: 'c-1',
  version_id: 'v-1',
  finding_category: 'limitation_of_liability',
  clause_reference: 'Section 7',
  expected_severity: 'HIGH',
  expected_finding: 'The cap is too low.',
  expected_evidence: 'Liability is capped at fees paid.',
  expected_recommendation: 'Increase the cap.',
  review_status: 'DRAFT',
  reviewer_id: 'reviewer-1',
  ...overrides,
})

const filters = (overrides: Partial<ReviewFilters> = {}): ReviewFilters => ({
  contractId: 'c-1',
  status: 'ALL',
  search: '',
  reviewerFilter: '',
  ...overrides,
})

/** Records every request and replies with a real Response, like apiFetch does. */
function transport(reply: { status?: number; body?: unknown }) {
  const calls: Array<{ path: string; init: RequestInit }> = []
  const request = async (path: string, init: RequestInit) => {
    calls.push({ path, init })
    return new Response(JSON.stringify(reply.body ?? {}), {
      status: reply.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  return { request, calls }
}

/** Returns the same queue every time, like reloading the workspace does. */
const queue = (...findings: BenchmarkFinding[]) => async () => findings

type TransitionOverrides = Partial<TransitionFindingOptions> & Pick<TransitionFindingOptions, 'request' | 'reloadFindings'>

const runTransition = (overrides: TransitionOverrides) =>
  transitionFinding({
    datasetId: 'd-1',
    groundTruthId: 'g-1',
    status: 'IN_REVIEW',
    moveNext: true,
    filters: filters(),
    ...overrides,
  })

describe('reviewer-facing action labels', () => {
  it('exposes the exact labels the review form renders', () => {
    expect(SAVE_DRAFT_LABEL).toBe('Save Draft')
    expect(SAVE_AND_NEXT_LABEL).toBe('Save & Next')
    expect(MARK_IN_REVIEW_LABEL).toBe('Mark In Review')
    expect(MARK_IN_REVIEW_AND_NEXT_LABEL).toBe('Mark In Review & Next')
    expect(APPROVE_LABEL).toBe('Approve')
    expect(APPROVE_AND_NEXT_LABEL).toBe('Approve & Next')
    expect(FINALIZE_LABEL).toBe('Finalize')
  })
})

describe('Mark In Review & Next', () => {
  it('issues exactly one write and then advances once, using the fresh queue', async () => {
    const { request, calls } = transport({ body: finding({ review_status: 'IN_REVIEW' }) })
    const fresh = [finding({ review_status: 'IN_REVIEW' }), finding({ ground_truth_id: 'g-2' }), finding({ ground_truth_id: 'g-3' })]
    const reload = vi.fn(queue(...fresh))

    const result = await runTransition({ request, reloadFindings: reload })

    expect(calls).toHaveLength(1)
    expect(calls[0].path).toBe('/api/evaluation/benchmarks/d-1/findings/g-1/status')
    expect(calls[0].init.method).toBe('POST')
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ status: 'IN_REVIEW' })
    expect(reload).toHaveBeenCalledTimes(1)
    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    // The queue on screen afterwards is the reloaded one, not a local guess.
    expect(result.findings).toEqual(fresh)
    expect(result.visibleFindings).toEqual(fresh)
    expect(result.advanced).toBe(true)
    expect(result.selectedFindingId).toBe('g-2')
    expect(result.message).toBe('Finding marked In Review. Moved to the next finding.')
  })

  it('advances exactly one position when invoked repeatedly', async () => {
    const fresh = [finding({ review_status: 'IN_REVIEW' }), finding({ ground_truth_id: 'g-2' }), finding({ ground_truth_id: 'g-3' })]
    // Each call targets a different finding, so each response carries that id.
    const first = transport({ body: finding({ ground_truth_id: 'g-1', review_status: 'IN_REVIEW' }) })
    const second = transport({ body: finding({ ground_truth_id: 'g-2', review_status: 'IN_REVIEW' }) })

    const once = await runTransition({ request: first.request, reloadFindings: queue(...fresh) })
    const twice = await transitionFinding({
      datasetId: 'd-1',
      groundTruthId: 'g-2',
      status: 'IN_REVIEW',
      moveNext: true,
      filters: filters(),
      request: second.request,
      reloadFindings: queue(...fresh),
    })

    expect(once.status === 'transitioned' && once.selectedFindingId).toBe('g-2')
    expect(twice.status === 'transitioned' && twice.selectedFindingId).toBe('g-3')
    // Never the same item twice, never back to the start.
    expect(twice.status === 'transitioned' && twice.selectedFindingId).not.toBe('g-1')
    expect(second.calls).toHaveLength(1)
  })

  it('never wraps back to the first finding when it is the last one', async () => {
    const { request, calls } = transport({ body: finding({ ground_truth_id: 'g-last', review_status: 'IN_REVIEW' }) })
    const fresh = [finding({ ground_truth_id: 'g-first' }), finding({ ground_truth_id: 'g-last', review_status: 'IN_REVIEW' })]

    const result = await runTransition({
      groundTruthId: 'g-last',
      request,
      reloadFindings: queue(...fresh),
    })

    expect(calls).toHaveLength(1)
    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    expect(result.advanced).toBe(false)
    expect(result.selectedFindingId).toBe('g-last')
    expect(result.message).toBe('Finding marked In Review. No next finding.')
    expect(nextFinding(fresh, 'g-last', 1)).toBeNull()
  })

  it('reveals the transitioned finding when the active filter would hide it', async () => {
    const { request } = transport({ body: finding({ review_status: 'IN_REVIEW' }) })
    const fresh = [finding({ review_status: 'IN_REVIEW' })]

    const result = await runTransition({
      filters: filters({ status: 'DRAFT', reviewerFilter: 'someone-else', search: 'nomatch' }),
      request,
      reloadFindings: queue(...fresh),
    })

    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    expect(result.filters).toEqual({ contractId: 'c-1', status: 'ALL', search: '', reviewerFilter: '' })
    expect(result.visibleFindings.map((item) => item.ground_truth_id)).toEqual(['g-1'])
    expect(result.selectedFindingId).toBe('g-1')
  })
})

describe('Approve & Next', () => {
  it('issues exactly one write and then advances once', async () => {
    const { request, calls } = transport({ body: finding({ review_status: 'APPROVED' }) })
    const fresh = [finding({ review_status: 'APPROVED' }), finding({ ground_truth_id: 'g-2', review_status: 'DRAFT' })]
    const reload = vi.fn(queue(...fresh))

    const result = await runTransition({ status: 'APPROVED', request, reloadFindings: reload })

    expect(calls).toHaveLength(1)
    expect(calls[0].path).toBe('/api/evaluation/benchmarks/d-1/findings/g-1/status')
    expect(calls[0].init.method).toBe('POST')
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ status: 'APPROVED' })
    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    expect(result.advanced).toBe(true)
    expect(result.selectedFindingId).toBe('g-2')
    expect(result.message).toBe('Finding marked Approved. Moved to the next finding.')
  })

  it('does not wrap on the last finding, and stays on it', async () => {
    const { request, calls } = transport({ body: finding({ ground_truth_id: 'g-last', review_status: 'APPROVED' }) })
    const fresh = [finding({ ground_truth_id: 'g-first' }), finding({ ground_truth_id: 'g-last', review_status: 'APPROVED' })]

    const result = await runTransition({ status: 'APPROVED', groundTruthId: 'g-last', request, reloadFindings: queue(...fresh) })

    expect(calls).toHaveLength(1)
    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    expect(result.advanced).toBe(false)
    expect(result.selectedFindingId).toBe('g-last')
    expect(result.message).toBe('Finding marked Approved. No next finding.')
  })
})

describe('status transitions use the fresh queue and never invent work', () => {
  it('follows the reloaded queue even when it differs from what was on screen', async () => {
    const { request } = transport({ body: finding({ review_status: 'IN_REVIEW' }) })
    // g-2 was concurrently removed and g-9 concurrently added by another reviewer.
    const fresh = [finding({ review_status: 'IN_REVIEW' }), finding({ ground_truth_id: 'g-9' })]

    const result = await runTransition({ request, reloadFindings: queue(...fresh) })

    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    expect(result.visibleFindings.map((item) => item.ground_truth_id)).toEqual(['g-1', 'g-9'])
    // The stale neighbour is never selected, and no record is manufactured.
    expect(result.selectedFindingId).toBe('g-9')
    expect(result.selectedFindingId).not.toBe('g-2')
    expect(result.findings).toHaveLength(2)
  })

  it('issues no request for an incomplete or unknown finding', async () => {
    const { request, calls } = transport({ body: finding() })

    const noDataset = await runTransition({ datasetId: '', request, reloadFindings: queue(finding()) })
    const noId = await runTransition({ groundTruthId: '', request, reloadFindings: queue(finding()) })

    expect(calls).toHaveLength(0)
    expect(noDataset.status).toBe('invalid')
    expect(noId.status).toBe('invalid')
    if (noId.status !== 'invalid') return
    expect(noId.message).toContain('no id')
  })

  it('reports a failed transition and never claims an advance', async () => {
    const { request } = transport({ status: 500, body: { detail: 'Firestore write failed' } })
    const reloadFindings = vi.fn(queue(finding()))

    const result = await runTransition({ request, reloadFindings })

    expect(result.status).toBe('error')
    if (result.status !== 'error') return
    expect(result.message).toBe('Firestore write failed')
    expect(reloadFindings).not.toHaveBeenCalled()
  })

  it('reports a 422 field error in reviewer-readable words', async () => {
    const { request } = transport({
      status: 422,
      body: { detail: [{ loc: ['body', 'status'], msg: 'Invalid ground-truth transition: FINALIZED -> DRAFT' }] },
    })

    const result = await runTransition({ request, reloadFindings: queue(finding()) })

    expect(result.status).toBe('error')
    if (result.status !== 'error') return
    expect(result.message).toContain('Unable to change finding status')
    expect(result.message).toContain('status: Invalid ground-truth transition')
    expect(result.message).not.toContain('Unable to save finding')
  })

  it('sends only the status in the transition body', async () => {
    const { request, calls } = transport({ body: finding({ review_status: 'APPROVED' }) })

    await runTransition({ status: 'APPROVED', request, reloadFindings: queue(finding()) })

    const body = JSON.parse(String(calls[0].init.body))
    expect(Object.keys(body)).toEqual(['status'])
    expect(body.status).toBe('APPROVED')
    expect(calls[0].path).toMatch(/^\/api\/evaluation\/benchmarks\/[^/]+\/findings\/[^/]+\/status$/)
  })

  it('reads "no next finding" only from an advancing action, never from a plain transition', () => {
    expect(transitionFindingMessage('IN_REVIEW', true, true)).toBe('Finding marked In Review. Moved to the next finding.')
    expect(transitionFindingMessage('IN_REVIEW', false, true)).toBe('Finding marked In Review. No next finding.')
    expect(transitionFindingMessage('APPROVED', false, true)).toBe('Finding marked Approved. No next finding.')
    expect(transitionFindingMessage('FINALIZED', false, true)).toBe('Finding marked Finalized. No next finding.')
    // Plain transitions make no claim about what comes next, so finalizing the
    // last finding can never read as a dead end on its own.
    expect(transitionFindingMessage('FINALIZED', false)).toBe('Finding marked Finalized.')
    expect(transitionFindingMessage('FINALIZED', false)).not.toContain('No next finding')
    expect(transitionFindingMessage('IN_REVIEW', false)).toBe('Finding marked In Review.')
    expect(transitionFindingMessage('APPROVED', false)).toBe('Finding marked Approved.')
  })
})

describe('hasNextFinding gates every Next action', () => {
  const queueOf3 = [finding({ ground_truth_id: 'g-1' }), finding({ ground_truth_id: 'g-2' }), finding({ ground_truth_id: 'g-3' })]

  it('is true while another finding follows and false on the last one', () => {
    expect(hasNextFinding(queueOf3, 'g-1')).toBe(true)
    expect(hasNextFinding(queueOf3, 'g-2')).toBe(true)
    expect(hasNextFinding(queueOf3, 'g-3')).toBe(false)
    expect(hasNextFinding(queueOf3, 'not-in-queue')).toBe(false)
    expect(hasNextFinding([], 'g-1')).toBe(false)
    // A single item is both first and last.
    expect(hasNextFinding([finding({ ground_truth_id: 'only' })], 'only')).toBe(false)
  })

  it('is not affected by the queue filters it is given', () => {
    const filtered = [finding({ ground_truth_id: 'g-1' })]
    expect(hasNextFinding(filtered, 'g-1')).toBe(false)
  })
})

describe('create-finding focus', () => {
  const field = () => {
    const calls: string[] = []
    return {
      calls,
      focus: (options?: { preventScroll?: boolean }) => { calls.push(`focus:${JSON.stringify(options)}`) },
      scrollIntoView: (options?: { block?: string }) => { calls.push(`scroll:${JSON.stringify(options)}`) },
    }
  }

  it('scrolls the Category field into view and focuses it without a second scroll', () => {
    const target = field()

    expect(focusNewFindingCategory(target, { tagName: 'BUTTON' })).toBe(true)
    expect(target.calls).toEqual(['scroll:{"block":"center"}', 'focus:{"preventScroll":true}'])
  })

  it('focuses when nothing is focused yet', () => {
    const target = field()
    expect(focusNewFindingCategory(target, null)).toBe(true)
    expect(target.calls).toContain('focus:{"preventScroll":true}')
  })

  it.each(['INPUT', 'TEXTAREA', 'SELECT'] as const)('never steals focus while the reviewer is editing a %s', (tagName) => {
    const target = field()

    expect(focusNewFindingCategory(target, { tagName })).toBe(false)
    expect(target.calls).toEqual([])
  })

  it('never steals focus from a contenteditable or when there is no field', () => {
    const target = field()

    expect(focusNewFindingCategory(target, { tagName: 'DIV', isContentEditable: true })).toBe(false)
    expect(focusNewFindingCategory(null, { tagName: 'BODY' })).toBe(false)
    expect(focusNewFindingCategory(undefined, { tagName: 'BODY' })).toBe(false)
    expect(target.calls).toEqual([])
  })

  it('tolerates a field without scrollIntoView', () => {
    const calls: string[] = []
    const bare = { focus: (options?: { preventScroll?: boolean }) => { calls.push(`focus:${JSON.stringify(options)}`) } }

    expect(focusNewFindingCategory(bare, { tagName: 'BODY' })).toBe(true)
    expect(calls).toEqual(['focus:{"preventScroll":true}'])
  })
})

describe('benchmark workflow progression stays intact', () => {
  const datasetId = '9106833f-43df-4e0c-a78e-195ce30277af'
  const ids = {
    c2: { contract_id: '645a2cd6-f436-4e6f-8b14-ac6240d6606a', version_id: 'b4193b13-b8bb-4f43-857e-ea4a3023e3c0' },
    c6: { contract_id: '50712c6d-cd84-408e-aac0-9c28ed09f2fe', version_id: '3fb395b9-b431-4196-ad8c-c4955a8d486d' },
    c8: { contract_id: '897c9b37-b5a0-4853-b1c6-c42d2cdf1a18', version_id: '0c6318be-76b0-4dfb-8c3b-0d56241a5fa6' },
  }
  const contracts: ReviewContract[] = orderBenchmarkContracts([
    { ...ids.c2, contract_name: 'C2', document_text: '', finding_count: 1, reviewed_count: 1, added_at: '2026-09-14T19:42:47.008786Z' },
    { ...ids.c8, contract_name: 'C8', document_text: '', finding_count: 0, reviewed_count: 0, added_at: '2026-09-14T19:42:48.335102Z' },
    { ...ids.c6, contract_name: 'C6', document_text: '', finding_count: 0, reviewed_count: 0, added_at: '2026-09-14T19:42:47.770374Z' },
  ])
  const finalized = (contractId: string, count: number) =>
    Array.from({ length: count }, (_, index) => finding({ ground_truth_id: `${contractId}-${index}`, contract_id: contractId, review_status: 'FINALIZED' }))

  const step = (findings: BenchmarkFinding[], currentContractId: string) =>
    benchmarkContinueTarget(benchmarkProgression({ contracts, findings, currentContractId, datasetId }))

  it('walks C2 -> C6 -> C8 -> Benchmark Review Complete', () => {
    const c2 = finalized(ids.c2.contract_id, 8)
    const c6 = [...c2, ...finalized(ids.c6.contract_id, 5)]
    const c8 = [...c6, ...finalized(ids.c8.contract_id, 4)]

    expect(step(c2, ids.c2.contract_id)!.path).toContain(`contract_id=${ids.c6.contract_id}`)
    expect(step(c6, ids.c6.contract_id)!.path).toContain(`contract_id=${ids.c8.contract_id}`)
    expect(step(c8, ids.c8.contract_id)).toBeNull()
    expect(benchmarkProgression({ contracts, findings: c8, currentContractId: ids.c8.contract_id, datasetId }).kind).toBe('complete')

    // And the actions added here still offer the same forward path.
    expect(CONTINUE_TO_NEXT_CONTRACT).toBe('Continue to Next Contract')
    expect(BENCHMARK_REVIEW_COMPLETE).toBe('Benchmark Review Complete')
  })

  it('does not offer Continue while the benchmark is unfinished', () => {
    const c2Unfinished = [...finalized(ids.c2.contract_id, 7), finding({ contract_id: ids.c2.contract_id, review_status: 'APPROVED' })]
    expect(step(c2Unfinished, ids.c2.contract_id)).toBeNull()
  })

  it('C6 with 11 finalized findings offers Continue to C8 (the reported stuck state)', () => {
    const c6AllFinalized = [...finalized(ids.c2.contract_id, 8), ...finalized(ids.c6.contract_id, 11)]
    const progression = benchmarkProgression({ contracts, findings: c6AllFinalized, currentContractId: ids.c6.contract_id, datasetId })

    expect(progression.kind).toBe('next')
    if (progression.kind !== 'next') return
    expect(progression.next.contract_name).toBe('C8')
    expect(benchmarkContinueTarget(progression)!.path).toContain(`contract_id=${ids.c8.contract_id}`)

    const markup = renderToStaticMarkup(<BenchmarkProgressionPanel progression={progression} onContinue={() => undefined} />)
    expect(markup).toContain(CONTINUE_TO_NEXT_CONTRACT)
    expect(markup).toContain('data-benchmark-progression="next"')
    expect(markup).not.toContain(BENCHMARK_REVIEW_COMPLETE)
  })

  it('finalizing the last finding hands over to the benchmark action, not a dead end', async () => {
    const c6Last = finding({ ground_truth_id: 'c6-last', contract_id: ids.c6.contract_id, review_status: 'FINALIZED' })
    const fresh = [...finalized(ids.c2.contract_id, 8), ...finalized(ids.c6.contract_id, 10).map(f => ({ ...f, contract_id: ids.c6.contract_id })), c6Last]
    const { request, calls } = transport({ body: c6Last })

    const result = await transitionFinding({
      datasetId,
      groundTruthId: 'c6-last',
      status: 'FINALIZED',
      moveNext: false,
      filters: { contractId: ids.c6.contract_id, status: 'ALL', search: '', reviewerFilter: '' },
      request,
      reloadFindings: async () => fresh,
    })

    expect(calls).toHaveLength(1)
    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    // The finding-level message no longer claims there is no next finding...
    expect(result.message).toBe('Finding marked Finalized.')
    // ...and the benchmark-level action is available from the reloaded queue.
    const progression = benchmarkProgression({ contracts, findings: result.findings, currentContractId: ids.c6.contract_id, datasetId })
    expect(progression.kind).toBe('next')
    expect(benchmarkContinueTarget(progression)!.contractId).toBe(ids.c8.contract_id)
  })

  it('never reports benchmark completion while any finding of the contract is still open', () => {
    const stillOpen = [
      ...finalized(ids.c2.contract_id, 8),
      ...finalized(ids.c6.contract_id, 10),
      finding({ ground_truth_id: 'c6-open', contract_id: ids.c6.contract_id, review_status: 'APPROVED' }),
    ]
    const progression = benchmarkProgression({ contracts, findings: stillOpen, currentContractId: ids.c6.contract_id, datasetId })

    expect(progression.kind).toBe('not-finalized')
    expect(benchmarkContinueTarget(progression)).toBeNull()
    expect(renderToStaticMarkup(<BenchmarkProgressionPanel progression={progression} onContinue={() => undefined} />)).toBe('')
  })

  it('shows the same benchmark action after a reload of the reloaded queue', () => {
    const c6AllFinalized = [...finalized(ids.c2.contract_id, 8), ...finalized(ids.c6.contract_id, 11)]
    const inSession = benchmarkProgression({ contracts, findings: c6AllFinalized, currentContractId: ids.c6.contract_id, datasetId })
    // A fresh page load re-derives from the parsed workspace payload, with no
    // in-session state involved.
    const afterReload = benchmarkProgression({
      contracts: JSON.parse(JSON.stringify(contracts)),
      findings: JSON.parse(JSON.stringify(c6AllFinalized)),
      currentContractId: ids.c6.contract_id,
      datasetId,
    })

    expect(afterReload).toEqual(inSession)
    expect(afterReload.kind).toBe('next')
    expect(afterReload.kind === 'next' && afterReload.path).toBe(benchmarkContinueTarget(inSession)!.path)
  })
})

describe('Finalize & Next', () => {
  const queueOf = (...ids: string[]) => ids.map((id, index) => finding({ ground_truth_id: id, review_status: index === 0 ? 'APPROVED' : 'DRAFT' }))

  /** Each call targets its own finding, so every response carries that id. */
  const transportFor = (id: string, review_status: BenchmarkFinding['review_status']) => {
    const { request, calls } = transport({ body: finding({ ground_truth_id: id, review_status }) })
    return { request, calls }
  }

  it('is offered exactly when another finding follows, and hidden on the last one', () => {
    const queue = queueOf('g-1', 'g-2', 'g-3')
    expect(hasNextFinding(queue, 'g-1')).toBe(true)
    expect(hasNextFinding(queue, 'g-3')).toBe(false)
    expect(FINALIZE_AND_NEXT_LABEL).toBe('Finalize & Next')
  })

  it('performs exactly one status mutation and opens the actual next finding', async () => {
    const fresh = [finding({ ground_truth_id: 'g-1', review_status: 'FINALIZED' }), finding({ ground_truth_id: 'g-2' }), finding({ ground_truth_id: 'g-3' })]
    const { request, calls } = transportFor('g-1', 'FINALIZED')

    const result = await transitionFinding({
      datasetId: 'd-1',
      groundTruthId: 'g-1',
      status: 'FINALIZED',
      moveNext: true,
      filters: filters(),
      request,
      reloadFindings: queue(...fresh),
    })

    expect(calls).toHaveLength(1)
    expect(calls[0].path).toBe('/api/evaluation/benchmarks/d-1/findings/g-1/status')
    expect(calls[0].init.method).toBe('POST')
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ status: 'FINALIZED' })
    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    // The next finding is the one that opens, taken from the fresh queue.
    expect(result.advanced).toBe(true)
    expect(result.selectedFindingId).toBe('g-2')
    expect(result.message).toBe('Finding marked Finalized. Moved to the next finding.')
    // No create path was touched, and the queue did not grow.
    expect(calls.some((call) => /\/findings$/.test(call.path))).toBe(false)
    expect(result.findings).toHaveLength(fresh.length)
  })

  it('does not wrap from the last finding back to the first', async () => {
    const fresh = [finding({ ground_truth_id: 'g-1' }), finding({ ground_truth_id: 'g-2', review_status: 'FINALIZED' })]
    const { request, calls } = transportFor('g-2', 'FINALIZED')

    const result = await transitionFinding({
      datasetId: 'd-1',
      groundTruthId: 'g-2',
      status: 'FINALIZED',
      moveNext: true,
      filters: filters(),
      request,
      reloadFindings: queue(...fresh),
    })

    expect(calls).toHaveLength(1)
    expect(result.status).toBe('transitioned')
    if (result.status !== 'transitioned') return
    expect(result.advanced).toBe(false)
    expect(result.selectedFindingId).toBe('g-2')
    expect(result.selectedFindingId).not.toBe('g-1')
  })

  it('walks the whole ladder one finding at a time, with one write per step', async () => {
    const fresh = (statuses: Record<string, BenchmarkFinding['review_status']>) =>
      Object.entries(statuses).map(([id, review_status]) => finding({ ground_truth_id: id, review_status }))
    const step = (id: string, status: TransitionStatus, queueFindings: BenchmarkFinding[]) =>
      transitionFinding({
        datasetId: 'd-1',
        groundTruthId: id,
        status,
        moveNext: true,
        filters: filters(),
        request: transportFor(id, status).request,
        reloadFindings: queue(...queueFindings),
      })

    const inReview = await step('g-1', 'IN_REVIEW', fresh({ 'g-1': 'IN_REVIEW', 'g-2': 'DRAFT', 'g-3': 'DRAFT' }))
    const approved = await step('g-2', 'APPROVED', fresh({ 'g-1': 'IN_REVIEW', 'g-2': 'APPROVED', 'g-3': 'DRAFT' }))
    const finalized = await step('g-3', 'FINALIZED', fresh({ 'g-1': 'IN_REVIEW', 'g-2': 'APPROVED', 'g-3': 'FINALIZED' }))

    // Mark In Review & Next and Approve & Next still advance one step each...
    expect(inReview.status === 'transitioned' && inReview.selectedFindingId).toBe('g-2')
    expect(approved.status === 'transitioned' && approved.selectedFindingId).toBe('g-3')
    // ...and the last finding stays put instead of wrapping.
    expect(finalized.status === 'transitioned' && finalized.advanced).toBe(false)
    expect(finalized.status === 'transitioned' && finalized.selectedFindingId).toBe('g-3')
    for (const result of [inReview, approved, finalized]) {
      expect(result.status === 'transitioned' && result.findings).toHaveLength(3)
    }
  })
})

describe('Create Finding placements share one implementation', () => {
  const here = dirname(fileURLToPath(import.meta.url))
  const pagePath = resolve(here, '../app/(authenticated)/dashboard/ai-evaluation/benchmarks/page.tsx')
  const componentPath = resolve(here, '../components/benchmark-create-finding-action.tsx')
  const source = readFileSync(pagePath, 'utf8').replace(/\r\n/g, '\n')
  const component = readFileSync(componentPath, 'utf8').replace(/\r\n/g, '\n')

  it('renders the shared action at the top, the empty queue and the bottom', () => {
    const placements = source.split('<CreateFindingAction').length - 1
    expect(placements).toBe(3)
    expect(source.split('onCreate={startCreate}').length - 1).toBe(3)
    // No placement keeps its own inline implementation of the action.
    expect(source).not.toContain('onClick={startCreate}')
  })

  it('is a single presentation-only component with the shared label', () => {
    expect(CREATE_FINDING_LABEL).toBe('Create finding')
    expect(component).toContain('CREATE_FINDING_LABEL')
    for (const marker of ['fetch(', 'apiFetch', 'useEffect', 'useState', 'saveFinding']) {
      expect(component, `the create action must not contain ${marker}`).not.toContain(marker)
    }
    const markup = renderToStaticMarkup(<CreateFindingAction onCreate={() => undefined} />)
    expect(markup).toContain('Create finding')
  })

  it('cannot start a second create while one is open', () => {
    expect(source.split('disabled={creating}').length - 1).toBe(3)
    const markup = renderToStaticMarkup(<CreateFindingAction onCreate={() => undefined} disabled />)
    expect(markup).toContain('disabled')
  })

  it('keeps the create handler local-only and the focus behaviour wired', () => {
    const startCreateBody = source.slice(
      source.indexOf('function startCreate'),
      source.indexOf('  }, [creating])') + '  }, [creating])'.length,
    )
    expect(startCreateBody).not.toContain('apiFetch')
    expect(startCreateBody).not.toContain('saveFinding')
    expect(startCreateBody).not.toContain('transitionFinding')
    expect(startCreateBody).toContain('focusCategoryOnCreate.current = true')
    expect(source).toContain('focusNewFindingCategory(categoryInputRef.current, document.activeElement)')
  })
})

describe('workspace landing position after Continue to Next Contract', () => {
  const here = dirname(fileURLToPath(import.meta.url))
  const pagePath = resolve(here, '../app/(authenticated)/dashboard/ai-evaluation/benchmarks/page.tsx')
  const source = readFileSync(pagePath, 'utf8').replace(/\r\n/g, '\n')
  const continuation = source.slice(source.indexOf('function continueToNextBenchmark'), source.indexOf('function startCreate'))

  it('scrolls the new workspace to its top exactly once, and does not touch focus', () => {
    const calls: Array<{ top: number }> = []
    const focus = vi.fn()
    const scroller = { scrollTo: (options: { top: number }) => { calls.push(options) }, focus }

    expect(scrollWorkspaceToTop(scroller)).toBe(true)
    expect(calls).toEqual([{ top: 0 }])
    expect(focus).not.toHaveBeenCalled()
  })

  it('is a no-op when there is no scrollable window', () => {
    expect(scrollWorkspaceToTop(null)).toBe(false)
    expect(scrollWorkspaceToTop(undefined)).toBe(false)
    expect(scrollWorkspaceToTop({})).toBe(false)
  })

  it('is triggered by Continue to Next Contract, and by nothing else', () => {
    expect(continuation).toContain('positionWorkspaceAtTopOnContractChange.current = true')
    // The create handler keeps its own, separate one-shot flag.
    const startCreateBody = source.slice(source.indexOf('function startCreate'), source.indexOf('  }, [creating])'))
    expect(startCreateBody).not.toContain('positionWorkspaceAtTopOnContractChange')
    // Selecting a contract from the list is not a Continue, so it does not move
    // the reviewer's viewport.
    const selectContractBody = source.slice(source.indexOf('function selectContract'), source.indexOf('function continueToNextBenchmark'))
    expect(selectContractBody).not.toContain('positionWorkspaceAtTopOnContractChange')
  })

  it('consumes the landing flag on the contract change it caused', () => {
    expect(source).toContain('if (!positionWorkspaceAtTopOnContractChange.current) return')
    expect(source).toContain('positionWorkspaceAtTopOnContractChange.current = false')
    // Keyed on the contract, so it runs once for the navigation.
    expect(source).toContain("scrollWorkspaceToTop(typeof window === 'undefined' ? null : window)\n  }, [contractId])")
  })

  it('leaves the finalize logic and both create placements unchanged', () => {
    expect(source).toContain("transitionTo('FINALIZED', true)")
    expect(source).toContain("{FINALIZE_LABEL}</Button>")
    expect(source.split('<CreateFindingAction').length - 1).toBe(3)
    expect(source.split('onCreate={startCreate}').length - 1).toBe(3)
  })
})

describe('the review page wires the new actions safely', () => {
  const here = dirname(fileURLToPath(import.meta.url))
  const pagePath = resolve(here, '../app/(authenticated)/dashboard/ai-evaluation/benchmarks/page.tsx')
  const source = readFileSync(pagePath, 'utf8').replace(/\r\n/g, '\n')
  // Exactly the create-finding handler plus the focus effect that follows it.
  const startCreateBody = source.slice(
    source.indexOf('function startCreate'),
    source.indexOf('  }, [creating])') + '  }, [creating])'.length,
  )

  it('Create Finding is local-only and focuses the Category field', () => {
    expect(startCreateBody).not.toContain('apiFetch')
    expect(startCreateBody).not.toContain('fetch(')
    expect(startCreateBody).not.toContain('saveFinding')
    expect(startCreateBody).not.toContain('transitionFinding')
    expect(startCreateBody).toContain('focusCategoryOnCreate.current = true')
    expect(source).toContain('ref={categoryInputRef}')
    expect(startCreateBody).toContain('focusNewFindingCategory(categoryInputRef.current, document.activeElement)')
    expect(source).toContain('useEffect(() => {\n    if (!creating || !focusCategoryOnCreate.current) return')
  })

  it('renders every "& Next" action behind the hasNext gate', () => {
    expect(source).toContain('{!creating && hasNext && <Button type="button" variant="outline" onClick={() => void saveDraft(true)}')
    expect(source).toContain("transitionTo('IN_REVIEW', true)")
    expect(source).toContain("transitionTo('APPROVED', true)")
    expect(source).toContain("transitionTo('FINALIZED')")
    expect(source).toContain("transitionTo('FINALIZED', true)")
    expect(source).toContain('{!creating && selectedFinding?.review_status === \'DRAFT\' && hasNext &&')
    expect(source).toContain('{!creating && selectedFinding?.review_status === \'IN_REVIEW\' && hasNext &&')
    expect(source).toContain('{!creating && selectedFinding?.review_status === \'APPROVED\' && hasNext &&')
    expect(source).toContain('hasNextFinding(visibleFindings, selectedFinding?.ground_truth_id')
    // The plain Finalize is the one action that survives on the last finding.
    expect(source).toContain("{FINALIZE_LABEL}</Button>")
    expect(source).toContain('{FINALIZE_AND_NEXT_LABEL}</Button>')
  })

  it('keeps Save Draft and the plain transitions available on the last finding', () => {
    expect(source).toContain('{SAVE_DRAFT_LABEL}')
    expect(source).toContain('{MARK_IN_REVIEW_LABEL}')
    expect(source).toContain('{APPROVE_LABEL}')
    expect(source).toContain('{FINALIZE_LABEL}')
  })

  it('preserves the create-mode reviewer guard and the AI-blind boundary', () => {
    expect(source).toContain('if (!creating && selectedFinding) void assign(event.target.value)')
    expect(source).toContain('aiBlindPayloadKeys')
    expect(source).toContain('AI-blind review boundary violated')
  })

  it('renders the benchmark action above the finding queue and document text', () => {
    const panelStart = source.indexOf('<div id="benchmark-review-panel"')
    const progressionIndex = source.indexOf('<BenchmarkProgressionPanel', panelStart)
    const queueIndex = source.indexOf('Finding queue', panelStart)
    const documentIndex = source.indexOf('Document text', panelStart)
    const editorIndex = source.indexOf('Create human finding', panelStart)

    expect(panelStart).toBeGreaterThan(-1)
    expect(progressionIndex).toBeGreaterThan(panelStart)
    // Above the queue, the document text and the finding editor: the reviewer's
    // next task is never below a long page again.
    expect(progressionIndex).toBeLessThan(queueIndex)
    expect(progressionIndex).toBeLessThan(documentIndex)
    expect(progressionIndex).toBeLessThan(editorIndex)
  })

  it('scrolls the benchmark action into view when the benchmark becomes finalized', () => {
    expect(source).toContain('ref={progressionRef}')
    expect(source).toContain('if (previous === null || previous === progression.kind) return')
    expect(source).toContain("progressionRef.current?.scrollIntoView({ block: 'center' })")
    // The finding-level feedback states the benchmark-level consequence too.
    expect(source).toContain("hint.kind === 'next'")
    expect(source).toContain('Benchmark finalized')
    expect(source).toContain('this was the last benchmark in the dataset')
  })

  it('does not scroll on open of an already-finalized contract', () => {
    // The first kind computed from a loaded workspace is not a transition: a
    // contract that is finalized when the page opens must stay at the top.
    expect(source).toContain('if (!workspace) return\n    const previous = previousProgressionKind.current')
    expect(source).toContain('}, [progression.kind, workspace])')
  })

  it('introduces no AI, evaluation-run or blockchain call', () => {
    const libPath = resolve(here, 'benchmarkReview.ts')
    const componentPath = resolve(here, '../components/benchmark-progression.tsx')
    const createActionPath = resolve(here, '../components/benchmark-create-finding-action.tsx')
    const markers = ['evaluation_runs', 'runEvaluation', 'startEvaluation', 'triggerAnalysis', 'analyzeContract', '/analysis', '/ai-analysis', 'passport', 'blockchain', 'ipfs', 'etherscan']
    for (const file of [pagePath, libPath, componentPath, createActionPath]) {
      const text = readFileSync(file, 'utf8')
      for (const marker of markers) {
        expect(text, `${file} must not reference ${marker}`).not.toContain(marker)
      }
    }
  })
})
