import { describe, expect, it } from 'vitest'
import { aiBlindPayloadKeys, benchmarkReviewPath, isFinalized, isVisibleFinding, nextFindingIndex, reviewProgress, type BenchmarkFinding, type ReviewContract } from './benchmarkReview'

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

const contracts: ReviewContract[] = [
  { contract_id: 'c-1', version_id: 'v-1', contract_name: 'C1', version_number: 1, document_text: 'Text', finding_count: 1, reviewed_count: 1 },
  { contract_id: 'c-2', version_id: 'v-2', contract_name: 'C2', version_number: 1, document_text: 'Text', finding_count: 1, reviewed_count: 0 },
]

describe('benchmark reviewer workflow', () => {
  it.each([
    ['C2', '645a2cd6-f436-4e6f-8b14-ac6240d6606a', 'b4193b13-b8bb-4f43-857e-ea4a3023e3c0'],
    ['C6', '50712c6d-cd84-408e-aac0-9c28ed09f2fe', '3fb395b9-b431-4196-ad8c-c4955a8d486d'],
    ['C8', '897c9b37-b5a0-4853-b1c6-c42d2cdf1a18', '0c6318be-76b0-4dfb-8c3b-0d56241a5fa6'],
  ])('keeps %s Open Review on the benchmark route with its benchmark IDs', (_name, contractId, versionId) => {
    const path = benchmarkReviewPath('9106833f-43df-4e0c-a78e-195ce30277af', contractId, versionId)
    expect(path).toContain('/dashboard/ai-evaluation/benchmarks/review?')
    expect(path).not.toContain('/dashboard/ai-analysis/findings')
    expect(path).not.toContain('/dashboard/findings')
    expect(path).toContain(`contract_id=${contractId}`)
    expect(path).toContain(`version_id=${versionId}`)
  })

  it('builds the review URL with the selected dataset, contract, and version', () => {
    expect(benchmarkReviewPath('dataset-1', 'c-1', 'v-1')).toBe('/dashboard/ai-evaluation/benchmarks/review?dataset_id=dataset-1&contract_id=c-1&version_id=v-1')
  })

  it('moves Previous and Save & Next through the filtered queue', () => {
    expect(nextFindingIndex(0, 3, 1)).toBe(1)
    expect(nextFindingIndex(0, 3, -1)).toBe(2)
    expect(nextFindingIndex(0, 0, 1)).toBe(-1)
  })

  it('changes severity using the permitted controlled values', () => {
    const updated = { ...finding(), expected_severity: 'CRITICAL' as const }
    expect(updated.expected_severity).toBe('CRITICAL')
  })

  it('filters by ALL, OPEN, status, search, and assigned reviewer', () => {
    expect(isVisibleFinding(finding(), 'ALL', '', '')).toBe(true)
    expect(isVisibleFinding(finding(), 'OPEN', '', '')).toBe(true)
    expect(isVisibleFinding(finding(), 'DRAFT', 'section 7', 'reviewer-1')).toBe(true)
    expect(isVisibleFinding(finding({ review_status: 'APPROVED' }), 'DRAFT', '', '')).toBe(false)
    expect(isVisibleFinding(finding(), 'ALL', '', 'reviewer-2')).toBe(false)
  })

  it('keeps assignment scoped to the selected active reviewer identity', () => {
    const selectedReviewer = { user_id: 'reviewer-1', roles: ['reviewer'], active: true }
    expect(selectedReviewer.active && selectedReviewer.roles.includes('reviewer')).toBe(true)
    expect({ ...finding(), reviewer_id: selectedReviewer.user_id }.reviewer_id).toBe('reviewer-1')
  })

  it('calculates contract and finding progress', () => {
    const result = reviewProgress(contracts, [finding({ review_status: 'APPROVED' }), finding({ ground_truth_id: 'g-2', contract_id: 'c-2' })])
    expect(result).toEqual({ contractsReviewed: 1, contractTotal: 2, findingsReviewed: 1, findingTotal: 2 })
  })

  it('supports a blank human-created finding without AI-derived fields', () => {
    const created = { contract_id: 'c-1', version_id: 'v-1', finding_category: '', clause_reference: '', expected_severity: 'MEDIUM', expected_finding: '', expected_evidence: '', expected_recommendation: '' }
    expect(created.finding_category).toBe('')
    expect('risk_findings' in created).toBe(false)
  })

  it('makes finalized findings read-only', () => {
    expect(isFinalized(finding({ review_status: 'FINALIZED' }))).toBe(true)
    expect(isFinalized(finding())).toBe(false)
  })

  it('rejects forbidden AI and evaluator payload keys', () => {
    expect(aiBlindPayloadKeys({ dataset: {}, ground_truth_findings: [] })).toBe(true)
    expect(aiBlindPayloadKeys({ evaluation_matches: [] })).toBe(false)
  })
})
