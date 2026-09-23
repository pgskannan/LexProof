import { describe, expect, it } from 'vitest'
import { canAccessEvaluation, hasRole, isAdmin, isOrgRole } from './roles'

describe('org roles', () => {
  it('recognizes the five fixed roles', () => {
    expect(isOrgRole('admin')).toBe(true)
    expect(isOrgRole('superuser')).toBe(false)
  })

  it('treats admin as an admin and not a reviewer-only user', () => {
    expect(isAdmin(['admin', 'approver'])).toBe(true)
    expect(hasRole(['reviewer'], 'approver')).toBe(false)
    expect(hasRole(['reviewer'], 'reviewer')).toBe(true)
  })

  it('gates evaluation navigation to evaluation-authorized roles', () => {
    expect(canAccessEvaluation(['admin'])).toBe(true)
    expect(canAccessEvaluation(['reviewer'])).toBe(true)
    expect(canAccessEvaluation(['auditor'])).toBe(true)
    expect(canAccessEvaluation(['contract_owner'])).toBe(false)
  })
})
