import { describe, expect, it } from 'vitest'
import { shouldAbortPreviousRequest } from '../../../../../lib/contractRequestLifecycle'

describe('contract detail request lifecycle guard', () => {
  it('does not abort a valid request when the same contract context is re-evaluated', () => {
    expect(shouldAbortPreviousRequest(1, 1, 'contract-a:org-a', 'contract-a:org-a')).toBe(false)
    expect(shouldAbortPreviousRequest(1, 2, 'contract-a:org-a', 'contract-a:org-a')).toBe(false)
  })

  it('aborts requests when a different contract or org context becomes active', () => {
    expect(shouldAbortPreviousRequest(1, 2, 'contract-a:org-a', 'contract-b:org-a')).toBe(true)
    expect(shouldAbortPreviousRequest(1, 2, 'contract-a:org-a', 'contract-a:org-b')).toBe(true)
  })
})
