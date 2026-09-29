import { describe, expect, it } from 'vitest'
import {
  canonicalPassportJson,
  computePassportRoot,
  diffIndexes,
  flipHexDigit,
  parseProofBundle,
  passportKeyFor,
} from './passportTamper'

const components = {
  document_hash: 'a'.repeat(64),
  policy_hash: 'b'.repeat(64),
  analysis_hash: 'c'.repeat(64),
  evidence_hash: 'd'.repeat(64),
}

describe('passportTamper', () => {
  it('builds the same canonical JSON as Python json.dumps(sort_keys=True)', () => {
    expect(canonicalPassportJson(components)).toBe(
      `{"analysis_hash": "${'c'.repeat(64)}", "document_hash": "${'a'.repeat(64)}", "evidence_hash": "${'d'.repeat(64)}", "passport_hash_algorithm": "sha256", "policy_hash": "${'b'.repeat(64)}"}`,
    )
  })

  it('reproduces the backend compute_passport_hash root (vector generated with Python)', async () => {
    expect(await computePassportRoot(components)).toBe('bec6fafccc0a336780d3fb43b9c1b12b1291abd4cdfcc82d9e96edfbcd27c033')
  })

  it('a one-digit change to one component changes the root', async () => {
    const tampered = { ...components, evidence_hash: 'e' + 'd'.repeat(63) }
    expect(await computePassportRoot(tampered)).toBe('6150cf0fa412d0a52cafe338a891243a4fe959cd0bf5c991485e3ddac9765d11')
  })

  it('flipHexDigit changes exactly one character and wraps f to 0', () => {
    const h = 'a'.repeat(63) + 'f'
    const t = flipHexDigit(h)
    expect(t.endsWith('0')).toBe(true)
    expect(diffIndexes(h, t)).toEqual([63])
    expect(diffIndexes(h, flipHexDigit(h, 0))).toEqual([0])
  })

  it('derives the on-chain key as keccak256(UTF-8(passport_id))', async () => {
    expect(await passportKeyFor('')).toBe('0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
  })

  it('parses a proof-package bundle and rejects incomplete ones', () => {
    const bundle = parseProofBundle({
      contract: { passport_id: 'p-1', name: 'CONTRACT_01', contract_version: 2 },
      hashes: { ...components, evidence_hash: '0X' + 'D'.repeat(64), passport_hash: 'f'.repeat(64) },
    })
    expect(bundle.passportId).toBe('p-1')
    expect(bundle.components.evidence_hash).toBe('d'.repeat(64))
    expect(bundle.statedRoot).toBe('f'.repeat(64))
    expect(() => parseProofBundle({ contract: {}, hashes: components })).toThrow(/passport ID/)
    expect(() => parseProofBundle({ contract: { passport_id: 'x' }, hashes: { document_hash: 'zz' } })).toThrow(/document hash/)
  })
})
