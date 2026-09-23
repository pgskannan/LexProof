import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { ReviewFeedback } from '../components/benchmark-review-feedback'
import {
  NO_MORE_ITEMS_MESSAGE,
  SAVED_MESSAGE,
  aiBlindPayloadKeys,
  nextFinding,
  saveFinding,
  validateFindingDraft,
  type BenchmarkFinding,
  type FindingDraft,
  type ReviewFilters,
  type SaveFindingOptions,
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

const draft = (overrides: Partial<FindingDraft> = {}): FindingDraft => ({
  contract_id: 'c-1',
  version_id: 'v-1',
  finding_category: 'limitation_of_liability',
  clause_reference: 'Section 7',
  expected_severity: 'HIGH',
  expected_finding: 'The cap is too low.',
  expected_evidence: 'Liability is capped at fees paid.',
  expected_recommendation: 'Increase the cap.',
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

type SaveOverrides = Partial<SaveFindingOptions> & Pick<SaveFindingOptions, 'request' | 'reloadFindings'>

/** Updates an existing finding (the normal review path) unless overridden. */
const save = (overrides: SaveOverrides) =>
  saveFinding({
    draft: draft({ ground_truth_id: 'g-1' }),
    datasetId: 'd-1',
    intent: 'update',
    moveNext: false,
    filters: filters(),
    ...overrides,
  })

describe('benchmark review save workflow', () => {
  it('Save Draft: PATCH 200 puts the legitimate finding in the queue', async () => {
    const { request, calls } = transport({ body: finding() })
    const refreshed = [finding()]

    const result = await save({ request, reloadFindings: async () => refreshed })

    expect(calls).toHaveLength(1)
    expect(calls[0].path).toBe('/api/evaluation/benchmarks/d-1/findings/g-1')
    expect(calls[0].init.method).toBe('PATCH')
    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    // The queue renders exactly visibleFindings, so this is the "appears in queue" assertion.
    expect(result.visibleFindings.map((item) => item.ground_truth_id)).toEqual(['g-1'])
    expect(result.findings).toEqual(refreshed)
    expect(result.selectedFindingId).toBe('g-1')
    expect(result.advanced).toBe(false)
  })

  it('Save Draft: reports explicit success feedback', async () => {
    const { request } = transport({ body: finding() })

    const result = await save({ request, reloadFindings: async () => [finding()] })

    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    expect(result.message).toBe(SAVED_MESSAGE)

    const markup = renderToStaticMarkup(<ReviewFeedback success={result.message} />)
    expect(markup).toContain('Finding saved')
    expect(markup).toContain('role="status"')
  })

  it('Save Draft: does NOT create an extra finding — one PATCH, queue length unchanged', async () => {
    const { request, calls } = transport({ body: finding() })
    const existing = [finding({ ground_truth_id: 'g-1' })]

    const result = await save({ request, reloadFindings: async () => existing })

    // Exactly one write, and it is an update of the existing finding.
    expect(calls).toHaveLength(1)
    expect(calls[0].init.method).toBe('PATCH')
    expect(calls.map((call) => call.path)).toEqual(['/api/evaluation/benchmarks/d-1/findings/g-1'])
    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    expect(result.findings).toHaveLength(1)
    expect(result.visibleFindings).toHaveLength(1)
    expect(result.finding.ground_truth_id).toBe('g-1')
  })

  it('Save Draft: an explicit create is the only path that POSTs, and it POSTs once', async () => {
    const { request, calls } = transport({ status: 201, body: finding({ ground_truth_id: 'brand-new-id' }) })

    const result = await save({
      draft: draft(), // no id yet
      intent: 'create',
      request,
      reloadFindings: async () => [finding({ ground_truth_id: 'brand-new-id' })],
    })

    expect(calls).toHaveLength(1)
    expect(calls[0].init.method).toBe('POST')
    expect(calls[0].path).toBe('/api/evaluation/benchmarks/d-1/findings')
    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    expect(result.finding.ground_truth_id).toBe('brand-new-id')
    expect(result.visibleFindings.map((item) => item.ground_truth_id)).toEqual(['brand-new-id'])
  })

  it('Save Draft: a failed PATCH surfaces a visible error and never claims success', async () => {
    const { request, calls } = transport({ status: 500, body: { detail: 'Firestore write failed' } })

    const result = await save({
      request,
      reloadFindings: async () => {
        throw new Error('the queue must not be reloaded after a failed save')
      },
    })

    expect(calls).toHaveLength(1)
    expect(result.status).toBe('error')
    if (result.status !== 'error') return
    expect(result.message).toBe('Firestore write failed')

    const markup = renderToStaticMarkup(<ReviewFeedback error={result.message} />)
    expect(markup).toContain('Firestore write failed')
    expect(markup).toContain('role="alert"')
    expect(markup).not.toContain('Finding saved')
  })

  it('Save & Next: persists the current finding with exactly one PATCH', async () => {
    const { request, calls } = transport({ body: finding({ ground_truth_id: 'g-1' }) })

    const result = await save({
      moveNext: true,
      request,
      reloadFindings: async () => [
        finding({ ground_truth_id: 'g-1' }),
        finding({ ground_truth_id: 'g-2' }),
        finding({ ground_truth_id: 'g-3' }),
      ],
    })

    expect(calls).toHaveLength(1)
    expect(calls[0].init.method).toBe('PATCH')
    expect(calls[0].path).toContain('/findings/g-1')
    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    expect(result.advanced).toBe(true)
    expect(result.selectedFindingId).toBe('g-2')
    expect(result.message).toBe(SAVED_MESSAGE)
  })

  it('Save & Next: never creates a synthetic or verification finding', async () => {
    const { request, calls } = transport({ body: finding({ ground_truth_id: 'g-1' }) })
    // The workspace says there is only the one finding — nothing may be invented.
    const serverTruth = [finding({ ground_truth_id: 'g-1' })]

    const result = await save({ moveNext: true, request, reloadFindings: async () => serverTruth })

    // One request, and it can only ever be an update of the current finding.
    expect(calls).toHaveLength(1)
    expect(calls[0].init.method).toBe('PATCH')
    expect(calls[0].init.method).not.toBe('POST')
    expect(calls[0].path).toBe('/api/evaluation/benchmarks/d-1/findings/g-1')
    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    // The queue mirrors the server exactly: no extra item was manufactured.
    expect(result.findings).toEqual(serverTruth)
    expect(result.visibleFindings).toEqual(serverTruth)
    expect(result.visibleFindings).toHaveLength(1)
    expect(result.finding.ground_truth_id).toBe('g-1')
  })

  it('Save & Next: update intent without an id fails loudly instead of creating a finding', async () => {
    const { request, calls } = transport({ status: 201, body: finding({ ground_truth_id: 'unexpected' }) })

    const result = await save({ draft: draft(), intent: 'update', moveNext: true, request, reloadFindings: async () => [] })

    expect(calls).toHaveLength(0)
    expect(result.status).toBe('error')
    if (result.status !== 'error') return
    expect(result.message).toContain('no id')
  })

  it('Save & Next: with no next finding shows the explicit no-next state and keeps the saved item visible', async () => {
    const { request } = transport({ body: finding({ ground_truth_id: 'g-1' }) })
    const serverTruth = [finding({ ground_truth_id: 'g-1' })]

    const result = await save({ moveNext: true, request, reloadFindings: async () => serverTruth })

    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    expect(result.advanced).toBe(false)
    expect(result.message).toBe(NO_MORE_ITEMS_MESSAGE)
    expect(result.message).toBe('Finding saved. No next finding.')
    expect(result.message).toContain('No next finding')
    // The saved finding stays selected and visible — it is never replaced.
    expect(result.selectedFindingId).toBe('g-1')
    expect(result.visibleFindings.map((item) => item.ground_truth_id)).toEqual(['g-1'])

    const markup = renderToStaticMarkup(<ReviewFeedback success={result.message} />)
    expect(markup).toContain('Finding saved. No next finding.')
    expect(markup).toContain('role="status"')
  })

  it('Save & Next: never wraps past the last item back onto an earlier one', async () => {
    const queue = [finding({ ground_truth_id: 'g-1' }), finding({ ground_truth_id: 'g-2' })]
    expect(nextFinding(queue, 'g-1', 1)?.ground_truth_id).toBe('g-2')
    expect(nextFinding(queue, 'g-2', 1)).toBeNull()
    expect(nextFinding([], 'g-1', 1)).toBeNull()
    expect(nextFinding([finding({ ground_truth_id: 'g-1' })], 'g-1', 1)).toBeNull()
    expect(nextFinding(queue, 'not-in-queue', 1)).toBeNull()
  })

  it('validation failure: shows a field-level error and issues no request at all', async () => {
    const { request, calls } = transport({ body: finding() })

    const result = await save({
      draft: draft({ finding_category: '  ', clause_reference: '', expected_evidence: '' }),
      moveNext: true,
      request,
      reloadFindings: async () => [finding()],
    })

    expect(calls).toHaveLength(0)
    expect(result.status).toBe('invalid')
    if (result.status !== 'invalid') return
    expect(result.message).toContain('Category')
    expect(result.message).toContain('Clause / reference')
    expect(result.message).toContain('Expected evidence')

    const markup = renderToStaticMarkup(<ReviewFeedback error={result.message} />)
    expect(markup).toContain('Complete the required fields')
  })

  it('validation failure: a missing draft and a missing dataset are both rejected before the request', async () => {
    const { request, calls } = transport({ body: finding() })

    const noDraft = await save({ draft: null, request, reloadFindings: async () => [] })
    const noDataset = await save({ datasetId: '', request, reloadFindings: async () => [] })

    expect(calls).toHaveLength(0)
    expect(noDraft.status).toBe('invalid')
    expect(noDataset.status).toBe('invalid')
    expect(validateFindingDraft(null)).not.toBeNull()
  })

  it('a newly created finding gets the server id and lands in the queue', async () => {
    const { request, calls } = transport({ status: 201, body: finding({ ground_truth_id: 'brand-new-id' }) })

    const result = await save({
      draft: draft(),
      intent: 'create',
      request,
      reloadFindings: async () => [finding({ ground_truth_id: 'brand-new-id' })],
    })

    expect(calls[0].path).toBe('/api/evaluation/benchmarks/d-1/findings')
    expect(calls[0].init.method).toBe('POST')
    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    expect(result.finding.ground_truth_id).toBe('brand-new-id')
    expect(result.selectedFindingId).toBe('brand-new-id')
    expect(result.visibleFindings.map((item) => item.ground_truth_id)).toEqual(['brand-new-id'])
  })

  it('a newly created finding is revealed even when the active filters would hide it', async () => {
    const { request } = transport({ status: 201, body: finding({ ground_truth_id: 'brand-new-id' }) })

    const result = await save({
      draft: draft(),
      intent: 'create',
      filters: filters({ status: 'FINALIZED', reviewerFilter: 'someone-else', search: 'nomatch' }),
      request,
      reloadFindings: async () => [finding({ ground_truth_id: 'brand-new-id' })],
    })

    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    expect(result.filters).toEqual({ contractId: 'c-1', status: 'ALL', search: '', reviewerFilter: '' })
    expect(result.visibleFindings.map((item) => item.ground_truth_id)).toEqual(['brand-new-id'])
  })

  it('a successful save keeps the filters the reviewer chose when the finding is already visible', async () => {
    const { request } = transport({ body: finding() })

    const result = await save({
      filters: filters({ status: 'DRAFT', reviewerFilter: 'reviewer-1' }),
      request,
      reloadFindings: async () => [finding()],
    })

    expect(result.status).toBe('saved')
    if (result.status !== 'saved') return
    expect(result.filters).toEqual({ contractId: 'c-1', status: 'DRAFT', search: '', reviewerFilter: 'reviewer-1' })
  })

  it('sends trimmed human-entered values and never any AI-derived field', async () => {
    const { request, calls } = transport({ body: finding() })

    await save({
      draft: draft({ ground_truth_id: 'g-1', finding_category: '  limitation_of_liability  ', expected_recommendation: '   ' }),
      request,
      reloadFindings: async () => [finding()],
    })

    const body = JSON.parse(String(calls[0].init.body))
    expect(body.finding_category).toBe('limitation_of_liability')
    expect(body.expected_recommendation).toBeNull()
    expect(Object.keys(body).sort()).toEqual([
      'clause_reference',
      'contract_id',
      'expected_evidence',
      'expected_finding',
      'expected_recommendation',
      'expected_severity',
      'finding_category',
      'version_id',
    ])
    expect('severity' in body).toBe(false)
    expect('evidence' in body).toBe(false)
    expect('match_score' in body).toBe(false)
  })

  it('reports a server 422 field error instead of "[object Object]"', async () => {
    const { request } = transport({
      status: 422,
      body: { detail: [{ loc: ['body', 'finding_category'], msg: 'String should have at least 1 character' }] },
    })

    const result = await save({ request, reloadFindings: async () => [finding()] })

    expect(result.status).toBe('error')
    if (result.status !== 'error') return
    expect(result.message).toContain('finding_category')
    expect(result.message).not.toContain('[object Object]')
  })

  it('reports a network failure as an error the reviewer can read', async () => {
    const request = async () => {
      throw new Error('Failed to fetch')
    }

    const result = await save({ request, reloadFindings: async () => [finding()] })

    expect(result.status).toBe('error')
    if (result.status !== 'error') return
    expect(result.message).toBe('Failed to fetch')
  })

  it('renders nothing when there is no feedback to show', () => {
    expect(renderToStaticMarkup(<ReviewFeedback />)).toBe('')
  })
})

describe('benchmark data cannot be contaminated by verification flows', () => {
  const here = dirname(fileURLToPath(import.meta.url))
  const sources: Record<string, string> = {
    'lib/benchmarkReview.ts': resolve(here, 'benchmarkReview.ts'),
    'components/benchmark-review-feedback.tsx': resolve(here, '../components/benchmark-review-feedback.tsx'),
    'benchmarks/page.tsx': resolve(here, '../app/(authenticated)/dashboard/ai-evaluation/benchmarks/page.tsx'),
  }
  const contaminationMarkers = [
    'Verification temp',
    'Temporary finding created by the automated',
    'Delete this finding after verification',
  ]

  it('no application source can manufacture a verification finding', () => {
    for (const [label, file] of Object.entries(sources)) {
      const source = readFileSync(file, 'utf8')
      for (const marker of contaminationMarkers) {
        expect(source, `${label} must not contain ${JSON.stringify(marker)}`).not.toContain(marker)
      }
    }
  })

  it('every save targets only the findings endpoint for the selected dataset', async () => {
    const { request, calls } = transport({ body: finding() })
    await save({ moveNext: true, request, reloadFindings: async () => [finding()] })
    await save({ draft: draft(), intent: 'create', request, reloadFindings: async () => [finding({ ground_truth_id: 'new' })] })

    expect(calls).toHaveLength(2)
    for (const call of calls) {
      expect(call.path).toMatch(/^\/api\/evaluation\/benchmarks\/[^/]+\/findings(\/[^/]+)?$/)
      expect(call.path).not.toContain('evaluation_runs')
      expect(call.path).not.toContain('evaluation_matches')
      expect(call.path).not.toContain('evaluation_metrics')
      expect(call.path).not.toContain('risk_findings')
    }
  })

  it('the C2 workspace payload stays AI-blind', () => {
    // The exact key set the workspace endpoint returns for C2.
    const c2Payload = {
      dataset: { dataset_version_id: '9106833f-43df-4e0c-a78e-195ce30277af', ai_blind: true },
      contract_rows: [{ contract_id: '645a2cd6-f436-4e6f-8b14-ac6240d6606a', document_text: 'MASTER SERVICES AGREEMENT' }],
      ground_truth_findings: [finding({ contract_id: '645a2cd6-f436-4e6f-8b14-ac6240d6606a' })],
      review_progress: { contract_total: 3, reviewed_total: 0, total_findings: 1 },
    }
    expect(aiBlindPayloadKeys(c2Payload)).toBe(true)
    for (const forbidden of ['risk_findings', 'evaluation_run_findings', 'evaluation_matches', 'evaluation_metrics']) {
      expect(aiBlindPayloadKeys({ ...c2Payload, [forbidden]: [] })).toBe(false)
    }
  })

  it('a ground-truth finding carries only human-entered fields', () => {
    const created = finding()
    const keys = Object.keys(created)
    expect(keys.some((key) => key.startsWith('evaluation_'))).toBe(false)
    expect(keys).not.toContain('match_score')
    expect(keys).not.toContain('ai_severity')
    expect(keys).not.toContain('evidence_grounding')
  })
})
