import { describe, expect, it } from 'vitest'
import { hasRole, isAdmin, isOrgRole } from './roles'

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
})
