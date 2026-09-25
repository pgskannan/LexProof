import { describe, expect, it } from 'vitest'
import { buildHeatmap, contractLabel, isTestArtifact, riskTheme, summarize, topRisks, type BoardContract, type BoardFinding } from './boardReport'

const contracts: BoardContract[] = [
  { contract_id: 'c1', name: 'SaaS MSA', risk_score: 92, risk_level: 'critical', passport_id: 'p1', proof_status: 'confirmed' },
  { contract_id: 'c2', name: 'NDA', risk_score: 20, risk_level: 'low', passport_id: 'p2' },
  { contract_id: 'c3', name: 'Unanalyzed', risk_score: null },
]

const findings: BoardFinding[] = [
  { finding_id: 'f1', contract_id: 'c1', title: 'Grossly Inadequate Liability Cap', severity: 'CRITICAL', risk_impact: 95 },
  { finding_id: 'f2', contract_id: 'c1', title: 'Broad Data License', severity: 'critical', risk_impact: 90 },
  { finding_id: 'f3', contract_id: 'c1', title: 'Unfavorable Governing Law', severity: 'HIGH', risk_impact: 70 },
  { finding_id: 'f4', contract_id: 'c2', title: 'One-Sided Indemnification', severity: 'MEDIUM' },
  { finding_id: 'f5', contract_id: 'orphan', title: 'Liability cap', severity: 'CRITICAL' },
]

describe('riskTheme', () => {
  it('classifies by title when clause_type is missing', () => {
    expect(riskTheme({ title: 'Grossly Inadequate Liability Cap' })).toBe('Liability')
    expect(riskTheme({ title: 'Unfavorable Governing Law and Dispute Resolution' })).toBe('Law & Disputes')
    expect(riskTheme({ title: 'Intellectual Property Ownership and License Termination' })).toBe('IP & Licensing')
    expect(riskTheme({ title: 'Automatic Renewal Without Notice' })).toBe('Termination')
  })

  it('prefers a meaningful clause_type and ignores "Other"', () => {
    expect(riskTheme({ clause_type: 'Indemnification', title: 'Something about liability' })).toBe('Indemnification')
    expect(riskTheme({ clause_type: 'Other', title: 'Broad Data License' })).toBe('Data & Privacy')
  })

  it('falls back to Other', () => {
    expect(riskTheme({ title: 'Ambiguous definitions' })).toBe('Other')
  })
})

describe('buildHeatmap', () => {
  it('only includes contracts with findings, most exposed first', () => {
    const rows = buildHeatmap(contracts, findings)
    expect(rows.map((row) => row.contract.contract_id)).toEqual(['c1', 'c2'])
    expect(rows[0].worst).toBe('CRITICAL')
    expect(rows[0].cells.Liability).toEqual({ count: 1, worst: 'CRITICAL' })
    expect(rows[0].cells['Law & Disputes']).toEqual({ count: 1, worst: 'HIGH' })
    expect(rows[1].cells.Indemnification.worst).toBe('MEDIUM')
  })

  it('shows a re-uploaded document once, keeping its most exposed copy', () => {
    const dupes: BoardContract[] = [...contracts, { contract_id: 'c1-copy', name: 'SaaS MSA', risk_score: 50 }]
    const rows = buildHeatmap(dupes, [...findings, { finding_id: 'f9', contract_id: 'c1-copy', title: 'Payment terms', severity: 'LOW' }])
    expect(rows.map((row) => row.contract.contract_id)).toEqual(['c1', 'c2'])
  })

  it('respects the row limit', () => {
    expect(buildHeatmap(contracts, findings, 1)).toHaveLength(1)
  })
})

describe('topRisks', () => {
  it('lists critical before high, by impact, and skips findings for unknown contracts', () => {
    const risks = topRisks(contracts, findings)
    expect(risks.map((risk) => risk.finding_id)).toEqual(['f1', 'f2', 'f3'])
    expect(risks[0].contract_name).toBe('SaaS MSA')
    expect(risks[1].severity).toBe('CRITICAL')
  })
})

describe('summarize', () => {
  it('rolls up scores, severities, coverage and themes', () => {
    const summary = summarize(contracts, findings)
    expect(summary.contractCount).toBe(3)
    expect(summary.avgRiskScore).toBe(56)
    expect(summary.highOrCriticalContracts).toBe(1)
    expect(summary.findingsBySeverity).toEqual({ CRITICAL: 2, HIGH: 1, MEDIUM: 1, LOW: 0 })
    expect(summary.passportCoverage).toBe(2)
    expect(summary.proofConfirmedOrAnchored).toBe(1)
    expect(summary.themeTotals.Liability).toBe(1)
  })
})

describe('isTestArtifact / contractLabel', () => {
  it('flags engineering and fixture contracts but not real ones', () => {
    expect(isTestArtifact({ name: 'e2e-full-lifecycle-E2E-1789750197033-qitdbp.txt' })).toBe(true)
    expect(isTestArtifact({ name: 'evidence_validation_test2_duplicate_orgscoped_2026_09_11.txt' })).toBe(true)
    expect(isTestArtifact({ name: 'pii test contract' })).toBe(true)
    expect(isTestArtifact({ name: 'Demo Cross-Tenant A Master Services Agreement' })).toBe(true)
    expect(isTestArtifact({ name: 'CONTRACT_03_SaaS_HighRisk.docx' })).toBe(false)
    expect(isTestArtifact({ name: 'OCR_E2E_Scanned_ServiceAgreement_2026-09-25.png' })).toBe(false)
  })

  it('labels contracts for a board audience', () => {
    expect(contractLabel({ contract_id: 'c1', name: 'CONTRACT_03_SaaS_HighRisk.docx' })).toBe('CONTRACT 03 SaaS HighRisk')
    const id = '797b61c9-4d50-41f6-b095-078561545fbd'
    expect(contractLabel({ contract_id: id, name: id })).toBe('Untitled contract (797b61c9)')
    expect(contractLabel({ contract_id: id, name: null })).toBe('Untitled contract (797b61c9)')
  })
})
