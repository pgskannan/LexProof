import { describe, expect, it } from 'vitest'
import { humanReviewStep } from './humanReviewStep'

describe('humanReviewStep', () => {
  it('is done when at least one redline was approved, rejected or published', () => {
    expect(humanReviewStep([{ status: 'APPROVED' }, { status: 'PROPOSED' }])).toEqual({
      done: true,
      detail: '1 redline decision · 1 pending',
    })
    expect(humanReviewStep([{ status: 'PUBLISHED' }, { status: 'REJECTED' }]).detail).toBe('2 redline decisions')
  })

  it('is not done while proposals are only awaiting review', () => {
    expect(humanReviewStep([{ status: 'PROPOSED' }, { status: 'draft' }])).toEqual({ done: false, detail: '2 awaiting review' })
  })

  it('says plainly when no redlines were proposed', () => {
    expect(humanReviewStep([])).toEqual({ done: false, detail: 'No redlines proposed' })
  })

  it('shows a loading state and honours the legacy audit-event signal', () => {
    expect(humanReviewStep(null)).toEqual({ done: false, detail: 'Checking…' })
    expect(humanReviewStep(null, true)).toEqual({ done: true, detail: 'Reviewed' })
  })
})
