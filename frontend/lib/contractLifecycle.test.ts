import { describe, expect, it } from 'vitest'
import { lifecycleStages, proofStatusLabel, type LifecycleData } from './contractLifecycle'

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
      versions: [{ version_id: 'version-2', version_number: 2, analysis_status: status, proof_status: status === 'complete' ? 'confirmed' : status === 'pending' || status === 'processing' ? 'processing' : 'failed', is_current: true }],
      contract: { contract_id: 'contract-1', version: 2 },
      passports: [],
      evidenceCount: 0,
      anchoredEvidenceCount: 0,
    })).find((item) => item.key === 'v2-analysis')
    expect(stage?.status).toBe(status === 'processing' || status === 'pending' ? 'active' : status === 'complete' ? 'complete' : 'failed')
  })

  it('prefers confirmed proof over stale failed analysis', () => {
    const stages = lifecycleStages(data({
      versions: [{ version_id: 'version-2', version_number: 2, analysis_status: 'failed', proof_status: 'confirmed', recommended_action: 'none', is_current: true }],
      proposals: [{ proposal_id: 'proposal-1', status: 'PUBLISHED', published_version_id: 'version-2', analysis_status: 'failed', proof_status: 'confirmed', recommended_action: 'none' }],
      contract: { contract_id: 'contract-1', version: 2, analysis_status: 'failed' },
    }))
    expect(proofStatusLabel('confirmed')).toBe('Confirmed')
    expect(stages.find((stage) => stage.key === 'v2-analysis')?.status).toBe('complete')
    expect(stages.find((stage) => stage.key === 'anchor')?.status).toBe('complete')
  })

  it('keeps Human review active while a proposal is awaiting review and the workflow is in_review', () => {
    const stages = lifecycleStages(data({
      proposals: [{ proposal_id: 'proposal-1', status: 'PROPOSED', workflow_instance_id: 'wf-1' }],
    }))

    expect(stages.find((stage) => stage.key === 'review')?.status).toBe('active')
    expect(stages.find((stage) => stage.key === 'review')?.detail).toBe('Pending review')
    expect(stages.find((stage) => stage.key === 'publication')?.status).toBe('pending')
  })

  it('keeps the Human review stage visible when the workflow is active but the current user cannot review', () => {
    const stages = lifecycleStages(data({
      proposals: [{ proposal_id: 'proposal-1', status: 'PROPOSED', workflow_instance_id: 'wf-1' }],
    }))

    expect(stages.find((stage) => stage.key === 'review')).toBeTruthy()
    expect(stages.find((stage) => stage.key === 'review')?.status).toBe('active')
    expect(stages.find((stage) => stage.key === 'review')?.detail).toBe('Pending review')
  })

  it('marks Human review complete after approval and leaves publish pending until publication', () => {
    const stages = lifecycleStages(data({
      proposals: [{ proposal_id: 'proposal-1', status: 'APPROVED', review: { decision: 'APPROVED' } }],
    }))

    expect(stages.find((stage) => stage.key === 'review')?.status).toBe('complete')
    expect(stages.find((stage) => stage.key === 'publication')?.status).toBe('active')
  })

  it('marks Human review and approval as complete when the proposal is published', () => {
    const stages = lifecycleStages(data({
      proposals: [{ proposal_id: 'proposal-1', status: 'PUBLISHED', published_version_id: 'version-2', review: { decision: 'APPROVED' } }],
      versions: [{ version_id: 'version-2', version_number: 2, analysis_status: 'complete', proof_status: 'confirmed', published: true, is_current: true }],
    }))

    expect(stages.find((stage) => stage.key === 'review')?.status).toBe('complete')
    expect(stages.find((stage) => stage.key === 'publication')?.status).toBe('complete')
  })
})