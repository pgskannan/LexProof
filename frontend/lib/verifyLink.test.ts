import { describe, expect, it } from 'vitest'
import { publicVerifyUrl } from './verifyLink'

describe('publicVerifyUrl', () => {
  it('encodes the existing public-verify deep link shape', () => {
    expect(publicVerifyUrl('ev-123', 'https://lexproof.example')).toBe(
      'https://lexproof.example/public-verify?evidence_id=ev-123',
    )
  })

  it('percent-encodes special characters in the evidence ID', () => {
    expect(publicVerifyUrl('id with space', 'http://localhost:3000')).toBe(
      'http://localhost:3000/public-verify?evidence_id=id%20with%20space',
    )
  })
})
