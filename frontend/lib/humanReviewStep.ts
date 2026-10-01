export interface RedlineProposalSummary {
  status?: string | null
}

export interface HumanReviewStep {
  done: boolean
  detail: string
}

const DECIDED = new Set(['APPROVED', 'REJECTED', 'PUBLISHED'])
const PENDING = new Set(['PROPOSED', 'IN_REVIEW', 'DRAFT'])

/**
 * The Legal Passport's "Human Review" provenance step, derived from the
 * contract's redline proposals (where approve/reject decisions are actually
 * recorded) rather than the passport's own audit events, which only ever
 * hold passport_created. `proposals === null` means still loading / not
 * available; `fallbackReviewed` keeps the old audit-event signal working.
 */
export function humanReviewStep(
  proposals: RedlineProposalSummary[] | null,
  fallbackReviewed = false,
): HumanReviewStep {
  if (proposals === null) {
    return { done: fallbackReviewed, detail: fallbackReviewed ? 'Reviewed' : 'Checking…' }
  }
  const statuses = proposals.map((p) => (p.status || '').toUpperCase())
  const decided = statuses.filter((s) => DECIDED.has(s)).length
  const pending = statuses.filter((s) => PENDING.has(s)).length
  if (decided > 0) {
    const tail = pending > 0 ? ` · ${pending} pending` : ''
    return { done: true, detail: `${decided} redline decision${decided === 1 ? '' : 's'}${tail}` }
  }
  if (pending > 0) {
    return { done: fallbackReviewed, detail: `${pending} awaiting review` }
  }
  return { done: fallbackReviewed, detail: 'No redlines proposed' }
}
