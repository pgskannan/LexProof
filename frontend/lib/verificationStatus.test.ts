import { describe, expect, it } from 'vitest'
import { toStatusMeta, formatVerificationStatus, statusTone } from './verificationStatus'

describe('verification status helpers', () => {
  it('maps the backend verification states to display metadata', () => {
    expect(toStatusMeta('VERIFIED')).toEqual({ label: 'VERIFIED', tone: 'green' })
    expect(toStatusMeta('TAMPERED')).toEqual({ label: 'TAMPERED', tone: 'red' })
    expect(toStatusMeta('ANCHOR_NOT_FOUND')).toEqual({ label: 'NOT YET ANCHORED', tone: 'amber' })
    expect(toStatusMeta('EVIDENCE_NOT_FOUND')).toEqual({ label: 'EVIDENCE NOT FOUND', tone: 'amber' })
  })

  it('normalizes edge-case strings consistently', () => {
    expect(formatVerificationStatus('verified')).toBe('VERIFIED')
    expect(formatVerificationStatus('   tampered   ')).toBe('TAMPERED')
    expect(formatVerificationStatus('missing_anchor')).toBe('NOT YET ANCHORED')
    expect(toStatusMeta('missing_anchor').label).toBe('NOT YET ANCHORED')
    expect(toStatusMeta('missing_anchor').tone).toBe('amber')
  })

  it('exposes the correct UI tone for each state', () => {
    expect(statusTone('VERIFIED')).toBe('green')
    expect(statusTone('TAMPERED')).toBe('red')
    expect(statusTone('ANCHOR_NOT_FOUND')).toBe('amber')
  })
})
