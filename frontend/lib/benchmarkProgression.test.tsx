import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { BenchmarkProgressionPanel } from '../components/benchmark-progression'
import {
  BENCHMARK_REVIEW_COMPLETE,
  CONTINUE_TO_NEXT_CONTRACT,
  aiBlindPayloadKeys,
  benchmarkContinueTarget,
  benchmarkProgression,
  benchmarkReviewPath,
  benchmarkStatusForContract,
  nextBenchmarkContract,
  orderBenchmarkContracts,
  type BenchmarkFinding,
  type BenchmarkProgression,
  type ReviewContract,
} from './benchmarkReview'

// The real C2 / C6 / C8 benchmark dataset identifiers.
const DATASET_ID = '9106833f-43df-4e0c-a78e-195ce30277af'
const C2 = { contract_id: '645a2cd6-f436-4e6f-8b14-ac6240d6606a', version_id: 'b4193b13-b8bb-4f43-857e-ea4a3023e3c0' }
const C6 = { contract_id: '50712c6d-cd84-408e-aac0-9c28ed09f2fe', version_id: '3fb395b9-b431-4196-ad8c-c4955a8d486d' }
const C8 = { contract_id: '897c9b37-b5a0-4853-b1c6-c42d2cdf1a18', version_id: '0c6318be-76b0-4dfb-8c3b-0d56241a5fa6' }

const contract = (
  ids: typeof C2,
  contract_name: string,
  added_at: string,
  finding_count: number,
  reviewed_count: number,
): ReviewContract => ({ ...ids, contract_name, version_number: 1, document_text: `${contract_name} TEXT`, finding_count, reviewed_count, added_at })

/**
 * `contract_rows` exactly as the workspace endpoint reports them: Firestore
 * document-id order, which is C2, C8, C6 for this dataset — not the order the
 * benchmark was assembled in.
 */
const reportedRows: ReviewContract[] = [
  contract(C2, 'C2', '2026-09-14T19:42:47.008786Z', 8, 8),
  contract(C8, 'C8', '2026-09-14T19:42:48.335102Z', 4, 0),
  contract(C6, 'C6', '2026-09-14T19:42:47.770374Z', 5, 0),
]

/** What the review page stores after ordering the payload once on load. */
const contracts = orderBenchmarkContracts(reportedRows)

const finding = (contractId: string, index: number, review_status: BenchmarkFinding['review_status']): BenchmarkFinding => ({
  ground_truth_id: `${contractId}-g${index}`,
  contract_id: contractId,
  version_id: 'v-1',
  finding_category: 'limitation_of_liability',
  clause_reference: `Section ${index}`,
  expected_severity: 'HIGH',
  expected_finding: 'The cap is too low.',
  expected_evidence: 'Liability is capped at fees paid.',
  expected_recommendation: 'Increase the cap.',
  review_status,
  reviewer_id: 'reviewer-1',
})

/** The real C2 state: 8/8 ground-truth findings finalized. */
const finalized = (contractId: string, count: number) =>
  Array.from({ length: count }, (_, index) => finding(contractId, index + 1, 'FINALIZED'))

const c2Finalized = finalized(C2.contract_id, 8)
const c6Finalized = [...c2Finalized, ...finalized(C6.contract_id, 5)]
const c8Finalized = [...c6Finalized, ...finalized(C8.contract_id, 4)]

const progressionFor = (findings: BenchmarkFinding[], currentContractId: string): BenchmarkProgression =>
  benchmarkProgression({ contracts, findings, currentContractId, datasetId: DATASET_ID })

const render = (progression: BenchmarkProgression) =>
  renderToStaticMarkup(<BenchmarkProgressionPanel progression={progression} onContinue={() => undefined} />)

describe('benchmark dataset order', () => {
  it('orders the workspace by the dataset insertion order: C2 -> C6 -> C8', () => {
    expect(reportedRows.map((row) => row.contract_name)).toEqual(['C2', 'C8', 'C6'])
    expect(contracts.map((row) => row.contract_name)).toEqual(['C2', 'C6', 'C8'])
    expect(contracts.map((row) => row.contract_id)).toEqual([C2.contract_id, C6.contract_id, C8.contract_id])
  })

  it('is deterministic for any reported order and never depends on the names', () => {
    const shuffled = orderBenchmarkContracts([reportedRows[1], reportedRows[2], reportedRows[0]])
    expect(shuffled.map((row) => row.contract_name)).toEqual(['C2', 'C6', 'C8'])
  })

  it('keeps the reported relative order for rows without an added_at (future datasets)', () => {
    const legacy: ReviewContract[] = [
      { ...contract(C8, 'C8', '', 0, 0), added_at: undefined },
      { ...contract(C2, 'C2', '', 0, 0), added_at: undefined },
      { ...contract(C6, 'C6', '', 0, 0), added_at: undefined },
    ]
    expect(orderBenchmarkContracts(legacy).map((row) => row.contract_name)).toEqual(['C8', 'C2', 'C6'])
  })

  it('advances one benchmark at a time and never wraps past the last', () => {
    expect(nextBenchmarkContract(contracts, C2.contract_id)?.contract_name).toBe('C6')
    expect(nextBenchmarkContract(contracts, C6.contract_id)?.contract_name).toBe('C8')
    expect(nextBenchmarkContract(contracts, C8.contract_id)).toBeNull()
    expect(nextBenchmarkContract(contracts, 'unknown-contract')).toBeNull()
    expect(nextBenchmarkContract([], C2.contract_id)).toBeNull()
  })
})

describe('benchmark workflow progression', () => {
  it('C2 FINALIZED 8/8 -> offers "Continue to Next Contract" with C6 as the next benchmark', () => {
    const progression = progressionFor(c2Finalized, C2.contract_id)

    expect(benchmarkStatusForContract(c2Finalized, C2.contract_id)).toBe('FINALIZED')
    expect(progression.kind).toBe('next')
    if (progression.kind !== 'next') return
    expect(progression.next.contract_id).toBe(C6.contract_id)
    expect(progression.next.contract_name).toBe('C6')

    const markup = render(progression)
    expect(markup).toContain(CONTINUE_TO_NEXT_CONTRACT)
    expect(markup).toContain('Continue to Next Contract')
    expect(markup).toContain('data-benchmark-progression="next"')
    expect(markup).not.toContain(BENCHMARK_REVIEW_COMPLETE)
  })

  it('clicking "Continue to Next Contract" from C2 navigates to the C6 review workspace', () => {
    const target = benchmarkContinueTarget(progressionFor(c2Finalized, C2.contract_id))

    expect(target).not.toBeNull()
    // This is the exact URL the click hands to the router.
    expect(target!.path).toBe(benchmarkReviewPath(DATASET_ID, C6.contract_id, C6.version_id))
    expect(target!.path).toBe(
      `/dashboard/ai-evaluation/benchmarks/review?dataset_id=${DATASET_ID}&contract_id=${C6.contract_id}&version_id=${C6.version_id}`,
    )
    // It opens C6's benchmark review workspace — not a findings/analysis page.
    expect(target!.path.startsWith('/dashboard/ai-evaluation/benchmarks/review?')).toBe(true)
    expect(target!.contractId).toBe(C6.contract_id)
    expect(target!.versionId).toBe(C6.version_id)
    // C2 and C8 are never targeted from C2.
    expect(target!.path).not.toContain(C2.contract_id)
    expect(target!.path).not.toContain(C8.contract_id)
  })

  it('C6 FINALIZED -> clicking "Continue to Next Contract" navigates to C8', () => {
    const progression = progressionFor(c6Finalized, C6.contract_id)
    expect(progression.kind).toBe('next')
    if (progression.kind !== 'next') return
    expect(progression.next.contract_id).toBe(C8.contract_id)

    const target = benchmarkContinueTarget(progression)
    expect(target!.path).toBe(benchmarkReviewPath(DATASET_ID, C8.contract_id, C8.version_id))
    expect(render(progression)).toContain(CONTINUE_TO_NEXT_CONTRACT)
  })

  it('C2 -> C6 -> C8 is walked in dataset order, one benchmark at a time', () => {
    const first = benchmarkContinueTarget(progressionFor(c2Finalized, C2.contract_id))
    const second = benchmarkContinueTarget(progressionFor(c6Finalized, C6.contract_id))
    const third = benchmarkContinueTarget(progressionFor(c8Finalized, C8.contract_id))

    expect(first!.contractId).toBe(C6.contract_id)
    expect(second!.contractId).toBe(C8.contract_id)
    // The last benchmark in the dataset has no next benchmark.
    expect(third).toBeNull()
  })

  it('C8 FINALIZED -> "Benchmark Review Complete" and no Continue action', () => {
    const progression = progressionFor(c8Finalized, C8.contract_id)

    expect(progression.kind).toBe('complete')
    expect(benchmarkContinueTarget(progression)).toBeNull()

    const markup = render(progression)
    expect(markup).toContain(BENCHMARK_REVIEW_COMPLETE)
    expect(markup).toContain('data-benchmark-progression="complete"')
    expect(markup).not.toContain(CONTINUE_TO_NEXT_CONTRACT)
  })

  it.each(['DRAFT', 'IN_REVIEW', 'APPROVED'] as const)('the action is absent while the benchmark is %s', (status) => {
    const findings = [...c2Finalized.slice(0, 7), finding(C2.contract_id, 8, status)]

    expect(benchmarkStatusForContract(findings, C2.contract_id)).toBe(status)
    const progression = progressionFor(findings, C2.contract_id)
    expect(progression.kind).toBe('not-finalized')
    expect(benchmarkContinueTarget(progression)).toBeNull()
    expect(render(progression)).toBe('')
  })

  it('the action is absent while any single finding is still not FINALIZED', () => {
    // Seven finalized findings plus one still only APPROVED is not finalized.
    const findings = [...c2Finalized.slice(0, 7), finding(C2.contract_id, 8, 'APPROVED')]
    expect(progressionFor(findings, C2.contract_id).kind).toBe('not-finalized')

    // A benchmark with no ground-truth findings is never reported as finalized.
    expect(benchmarkStatusForContract([], C2.contract_id)).toBe('DRAFT')
    expect(progressionFor([], C2.contract_id).kind).toBe('not-finalized')

    // Nor is a benchmark the reviewer has not opened yet.
    expect(progressionFor(c2Finalized, C6.contract_id).kind).toBe('not-finalized')
  })

  it('continuing issues no request and mutates nothing it was given', () => {
    const contractsSnapshot = JSON.parse(JSON.stringify(contracts))
    const findingsSnapshot = JSON.parse(JSON.stringify(c2Finalized))
    const progression = progressionFor(c2Finalized, C2.contract_id)

    const target = benchmarkContinueTarget(progression)
    expect(target).toEqual(benchmarkContinueTarget(progression))

    expect(contracts).toEqual(contractsSnapshot)
    expect(c2Finalized).toEqual(findingsSnapshot)
  })

  it('the AI-blind workspace payload survives ordering and continuation unchanged', () => {
    // The pipeline the page runs: read payload -> order rows -> derive.
    const payload = {
      dataset: { dataset_version_id: DATASET_ID, ai_blind: true },
      contract_rows: reportedRows,
      ground_truth_findings: c6Finalized,
      review_progress: { contract_total: 3, reviewed_total: 13, total_findings: 17 },
    }

    expect(aiBlindPayloadKeys(payload)).toBe(true)
    for (const forbidden of ['risk_findings', 'evaluation_run_findings', 'evaluation_matches', 'evaluation_metrics']) {
      expect(aiBlindPayloadKeys({ ...payload, [forbidden]: [] })).toBe(false)
    }

    const ordered = orderBenchmarkContracts(payload.contract_rows)
    expect(aiBlindPayloadKeys({ ...payload, contract_rows: ordered })).toBe(true)

    const progression = benchmarkProgression({
      contracts: ordered,
      findings: payload.ground_truth_findings,
      currentContractId: C6.contract_id,
      datasetId: payload.dataset.dataset_version_id,
    })
    expect(progression).toEqual({
      kind: 'next',
      status: 'FINALIZED',
      next: contracts[2],
      path: benchmarkReviewPath(DATASET_ID, C8.contract_id, C8.version_id),
    })
    // The next step is a navigation URL and nothing else — no payload is built.
    expect(Object.keys(benchmarkContinueTarget(progression)!)).toEqual(['path', 'contractId', 'versionId'])
  })
})

describe('benchmark progression cannot start AI work or invent ground truth', () => {
  const here = dirname(fileURLToPath(import.meta.url))
  const sources: Record<string, string> = {
    'lib/benchmarkReview.ts': resolve(here, 'benchmarkReview.ts'),
    'components/benchmark-progression.tsx': resolve(here, '../components/benchmark-progression.tsx'),
    'benchmarks/page.tsx': resolve(here, '../app/(authenticated)/dashboard/ai-evaluation/benchmarks/page.tsx'),
  }

  it('no source on the continuation path can reach an AI or evaluation endpoint', () => {
    const aiExecutionMarkers = ['evaluation_runs', 'runEvaluation', 'startEvaluation', 'triggerAnalysis', 'analyzeContract', '/analysis', '/ai-analysis']
    for (const [label, file] of Object.entries(sources)) {
      const source = readFileSync(file, 'utf8')
      for (const marker of aiExecutionMarkers) {
        expect(source, `${label} must not reference ${JSON.stringify(marker)}`).not.toContain(marker)
      }
    }
  })

  it('the progression panel is presentation only: it performs no I/O', () => {
    const source = readFileSync(sources['components/benchmark-progression.tsx'], 'utf8')
    for (const marker of ['fetch(', 'apiFetch', 'XMLHttpRequest', 'axios', 'useEffect', 'useState']) {
      expect(source, `benchmark-progression.tsx must not contain ${JSON.stringify(marker)}`).not.toContain(marker)
    }
    // Clicking Continue only routes to the path the pure helper returned.
    const page = readFileSync(sources['benchmarks/page.tsx'], 'utf8')
    expect(page).toContain('router.push(target.path)')
    expect(page).toContain('benchmarkContinueTarget(progression)')
  })

  it('no source on the continuation path can manufacture a ground-truth record', () => {
    const contaminationMarkers = ['method: \'POST\'', 'Verification temp', 'Temporary finding created by the automated']
    const page = readFileSync(sources['benchmarks/page.tsx'], 'utf8')
    const continuation = page.slice(page.indexOf('function continueToNextBenchmark'), page.indexOf('function startCreate'))
    for (const marker of contaminationMarkers) {
      expect(continuation, `the continuation must not contain ${JSON.stringify(marker)}`).not.toContain(marker)
    }
    // The continuation body never writes: it resets view state and navigates.
    expect(continuation).not.toContain('apiFetch')
    expect(continuation).not.toContain('saveDraft')
    expect(continuation).not.toContain('transition')
  })

  it('keeps the existing Previous and Back to Benchmarks navigation', () => {
    const page = readFileSync(sources['benchmarks/page.tsx'], 'utf8')
    expect(page).toContain('>Previous</Button>')
    expect(page).toContain('onClick={() => move(-1)}')
    expect(page).toContain('Back to Benchmarks')
    expect(page).toContain('benchmarkLandingPath(datasetId)')
  })

  it('never reassigns an existing finding while a new one is being created', () => {
    // In create mode the reviewer dropdown must not POST /assign: with a
    // non-empty queue `selectedFinding` falls back to the first visible
    // finding, so an unguarded call reassigns an unrelated record.
    const page = readFileSync(sources['benchmarks/page.tsx'], 'utf8')
    expect(page).toContain('if (!creating && selectedFinding) void assign(event.target.value)')
    expect(page).not.toContain('if (selectedFinding) void assign(event.target.value)')
  })
})
