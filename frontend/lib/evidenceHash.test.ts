import { describe, expect, it } from 'vitest'
import { canonicalizeEvidenceItem, compareEvidenceHash, hashEvidenceItem, serializeCanonicalEvidence, serializeCanonicalValue } from './evidenceHash'

const GOLDEN_FIXTURE = {
  evidence_id: 'e-1',
  title: 'Clause',
  content: 'This is the evidence content',
  evidence_type: 'clause',
  metadata: { key: 'value' },
}

const GOLDEN_CANONICAL = '{"analysis_reference": null, "compliance_impact": null, "content": "This is the evidence content", "content_type": null, "contract_reference": null, "description": null, "evidence_id": "e-1", "evidence_status": null, "evidence_type": "clause", "metadata": {"key": "value"}, "passport_id": null, "policy_reference": null, "risk_impact": null, "source": null, "source_id": null, "title": "Clause"}'

const EXPECTED_HASH = 'e8c40d43edd6d5dca9fa220c8333001a0e0318456d6f6a2852e2658a2810e9fc'

describe('evidence hash', () => {
  it('matches the golden fixture hash exactly', async () => {
    const canonical = canonicalizeEvidenceItem(GOLDEN_FIXTURE)
    expect(serializeCanonicalEvidence(GOLDEN_FIXTURE)).toBe(GOLDEN_CANONICAL)
    expect(canonical.analysis_reference).toBeNull()
    expect(canonical.title).toBe('Clause')
    expect(await hashEvidenceItem(GOLDEN_FIXTURE)).toBe(EXPECTED_HASH)
  })

  it('matches unicode deterministically', async () => {
    const a = { evidence_id: 'e-1', title: 'Café', content: '💡 Résumé', evidence_type: 'clause', metadata: { city: '東京' } }
    const b = { metadata: { city: '東京' }, evidence_type: 'clause', title: 'Café', content: '💡 Résumé', evidence_id: 'e-1' }
    expect(await hashEvidenceItem(a)).toBe(await hashEvidenceItem(b))
  })

  it('matches nested metadata and reordered keys', async () => {
    const a = {
      evidence_id: 'e-1',
      title: 'Clause',
      content: 'alpha',
      evidence_type: 'clause',
      metadata: { nested: { z: 1, a: [3, 1, 2], x: 'value' } },
      risk_impact: 5,
    }
    const b = {
      risk_impact: 5,
      metadata: { nested: { x: 'value', a: [3, 1, 2], z: 1 } },
      title: 'Clause',
      content: 'alpha',
      evidence_type: 'clause',
      evidence_id: 'e-1',
    }
    expect(await hashEvidenceItem(a)).toBe(await hashEvidenceItem(b))
  })

  it('changes when content changes', async () => {
    const original = { ...GOLDEN_FIXTURE, content: 'One' }
    const changed = { ...GOLDEN_FIXTURE, content: 'Two' }
    expect(await hashEvidenceItem(original)).not.toBe(await hashEvidenceItem(changed))
  })

  it('changes when risk_impact changes', async () => {
    const original = { ...GOLDEN_FIXTURE, risk_impact: 2 }
    const changed = { ...GOLDEN_FIXTURE, risk_impact: 5 }
    expect(await hashEvidenceItem(original)).not.toBe(await hashEvidenceItem(changed))
  })

  it('changes when passport_id changes', async () => {
    const original = { ...GOLDEN_FIXTURE, passport_id: 'p-1' }
    const changed = { ...GOLDEN_FIXTURE, passport_id: 'p-2' }
    expect(await hashEvidenceItem(original)).not.toBe(await hashEvidenceItem(changed))
  })

  it('treats missing fields and null equivalently for canonicalization', () => {
    expect(canonicalizeEvidenceItem({ evidence_id: 'e-1' })).toEqual(canonicalizeEvidenceItem({ evidence_id: 'e-1', passport_id: null }))
  })

  it('preserves array order and handles empty strings', async () => {
    const first = { evidence_id: 'e-1', content: 'x', metadata: { tags: ['a', 'b'] }, evidence_type: 'clause' }
    const second = { evidence_id: 'e-1', content: 'x', metadata: { tags: ['a', 'b'] }, evidence_type: 'clause' }
    const third = { evidence_id: 'e-1', content: '', metadata: { tags: ['a', 'b'] }, evidence_type: 'clause' }
    expect(await hashEvidenceItem(first)).toBe(await hashEvidenceItem(second))
    expect(await hashEvidenceItem(first)).not.toBe(await hashEvidenceItem(third))
  })

  it('rejects unsupported numeric values', async () => {
    await expect(hashEvidenceItem({ evidence_id: 'e-1', risk_impact: Number.NaN, evidence_type: 'clause' })).rejects.toThrow()
    await expect(hashEvidenceItem({ evidence_id: 'e-1', risk_impact: Number.POSITIVE_INFINITY, evidence_type: 'clause' })).rejects.toThrow()
  })

  it('compares local and on-chain hashes correctly', async () => {
    const localHash = await hashEvidenceItem(GOLDEN_FIXTURE)
    expect(await compareEvidenceHash(GOLDEN_FIXTURE, localHash)).toBe(true)
    expect(await compareEvidenceHash(GOLDEN_FIXTURE, '0x' + localHash)).toBe(true)
    expect(await compareEvidenceHash(GOLDEN_FIXTURE, '0x' + '00'.repeat(32))).toBe(false)
  })

  it('matches Python numeric serialization for float edge cases', () => {
    expect(serializeCanonicalValue(-0)).toBe('-0.0')
    expect(serializeCanonicalValue(0)).toBe('0')
    expect(serializeCanonicalValue(1.5)).toBe('1.5')
    expect(serializeCanonicalValue(-1.5)).toBe('-1.5')
    expect(serializeCanonicalValue(1e20)).toBe('1e+20')
    expect(serializeCanonicalValue(-1e20)).toBe('-1e+20')
    expect(serializeCanonicalValue(1e-6)).toBe('1e-06')
    expect(serializeCanonicalValue(-1e-6)).toBe('-1e-06')
    expect(serializeCanonicalValue(1e-7)).toBe('1e-07')
    expect(serializeCanonicalValue(-1e-7)).toBe('-1e-07')
    expect(serializeCanonicalValue(1.23456789e30)).toBe('1.23456789e+30')
    expect(serializeCanonicalValue(1.23456789e-30)).toBe('1.23456789e-30')
  })
})
