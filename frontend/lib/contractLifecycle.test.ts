import { describe, expect, it } from 'vitest'
import { lifecycleStages, type LifecycleData } from './contractLifecycle'

function data(overrides: Partial<LifecycleData> = {}): LifecycleData {
  return {
    contract: { contract_id: 'contract-1', name: 'NDA', version: 1, analysis_status: 'complete', passport_id: 'passport-v1', evidence_count: 1 },
    versions: [{ version_id: 'version-1', version_number: 1, analysis_status: 'complete', passport_id: 'passport-v1', is_current: true }],
    findingsCount: 1,
    proposals: [],
    passports: [{ passport_id: 'passport-v1', contract_version: 1, evidence_count: 1 }],
    anchoredEvidenceCount: 1,
    evidenceCount: 1,
    anchors: [{ evidence_id: 'evidence-v1', transaction_hash: '0xtx', block_number: 1, blockchain_network: 'ethereum-sepolia', evidence_hash: 'hash' }],
    ...overrides,
  }
}

describe('contract lifecycle', () => {
  it('does not invent completion when API fields are missing', () => {
    const stages = lifecycleStages(data({
      contract: { contract_id: 'contract-1' },
      versions: [{ version_id: 'version-1', version_number: 1, analysis_status: null, is_current: true }],
      passports: [],
      evidenceCount: 0,
      anchoredEvidenceCount: 0,
    }))
    expect(stages.find((stage) => stage.key === 'passport')?.status).toBe('pending')
    expect(stages.find((stage) => stage.key === 'anchor')?.status).toBe('pending')
  })

  it('represents rejected proposals without a publish action', () => {
    const stages = lifecycleStages(data({ proposals: [{ proposal_id: 'proposal-1', status: 'REJECTED', review: { decision: 'REJECTED' } }] }))
    expect(stages.find((stage) => stage.key === 'review')?.detail).toBe('REJECTED')
    expect(stages.find((stage) => stage.key === 'publication')?.status).toBe('pending')
  })

  it('represents approved and published V2 states', () => {
    const stages = lifecycleStages(data({
      versions: [{ version_id: 'version-2', version_number: 2, analysis_status: 'processing', is_current: true }],
      proposals: [{ proposal_id: 'proposal-1', status: 'APPROVED', published_version_id: 'version-2', review: { decision: 'APPROVED' } }],
      passports: [],
      evidenceCount: 0,
      anchoredEvidenceCount: 0,
    }))
    expect(stages.find((stage) => stage.key === 'publication')?.status).toBe('complete')
    expect(stages.find((stage) => stage.key === 'v2-analysis')?.status).toBe('active')
  })

  it.each(['pending', 'processing', 'complete', 'failed'])('maps V2 %s state', (status) => {
    const stage = lifecycleStages(data({
      versions: [{ version_id: 'version-2', version_number: 2, analysis_status: status, is_current: true }],
      contract: { contract_id: 'contract-1', version: 2 },
      passports: [],
      evidenceCount: 0,
      anchoredEvidenceCount: 0,
    })).find((item) => item.key === 'v2-analysis')
    expect(stage?.status).toBe(status === 'processing' ? 'active' : status)
  })
})