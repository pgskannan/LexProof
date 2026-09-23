import { describe, expect, it } from 'vitest'
import { executiveSummaryPath, regenerateExecutiveSummaryRequest, severityBreakdownText } from './executiveSummary'

describe('executiveSummaryPath', () => {
  it('builds the GET path with the contract id encoded', () => {
    expect(executiveSummaryPath('contract 1')).toBe('/api/contracts/contract%201/executive-summary')
  })
})

describe('regenerateExecutiveSummaryRequest', () => {
  it('builds a POST request descriptor to the regenerate endpoint', () => {
    expect(regenerateExecutiveSummaryRequest('contract-1')).toEqual({
      path: '/api/contracts/contract-1/executive-summary/regenerate',
      method: 'POST',
    })
  })
})

describe('severityBreakdownText', () => {
  it('renders counts in a fixed critical -> high -> medium -> low order', () => {
    expect(severityBreakdownText({ critical: 1, high: 0, medium: 2, low: 3 })).toBe(
      '1 critical, 0 high, 2 medium, 3 low',
    )
  })
})
