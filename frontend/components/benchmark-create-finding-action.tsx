'use client'

import { Plus } from 'lucide-react'
import { CREATE_FINDING_LABEL } from '../lib/benchmarkReview'
import { Button } from './ui/button'

/**
 * The single "+ Create finding" action used everywhere in the review workspace
 * (top of the workspace, the empty-queue state, and the bottom of the queue).
 *
 * The workspace is long — contract summary, queue, document text, then the
 * editor — so reviewers had to scroll back to the top to start another finding.
 * Rather than add a second implementation of the action, every placement renders
 * this component with the same `startCreate` handler, which means one code path
 * for create mode, one place where focus/scroll is decided, and no way for the
 * placements to drift apart.
 *
 * It is presentation only: no request, no state of its own. Clicking it starts
 * create mode in the caller and persists nothing until the reviewer saves.
 */
export function CreateFindingAction({
  onCreate,
  disabled = false,
}: {
  /** The workspace's create handler (startCreate); identical for every placement. */
  onCreate: () => void
  disabled?: boolean
}) {
  return (
    <Button type="button" variant="outline" onClick={onCreate} disabled={disabled}>
      <Plus className="mr-2 h-4 w-4" />
      {CREATE_FINDING_LABEL}
    </Button>
  )
}
