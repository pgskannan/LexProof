import { describe, expect, it } from 'vitest'
import { isPublicPath } from './publicRoutes'

describe('isPublicPath', () => {
  it('allows the counterparty token page without a LexProof session', () => {
    expect(isPublicPath('/counterparty/opaque-token')).toBe(true)
  })

  it('keeps existing public routes public and authenticated routes private', () => {
    expect(isPublicPath('/login')).toBe(true)
    expect(isPublicPath('/public-verify')).toBe(true)
    expect(isPublicPath('/dashboard/contracts/reviews')).toBe(false)
    expect(isPublicPath('/counterparty')).toBe(false)
  })
})
