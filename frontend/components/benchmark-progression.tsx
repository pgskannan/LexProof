'use client'

import { ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react'
import { BENCHMARK_REVIEW_COMPLETE, CONTINUE_TO_NEXT_CONTRACT, type BenchmarkProgression } from '../lib/benchmarkReview'
import { Button } from './ui/button'
import { Card, CardContent } from './ui/card'

/**
 * The reviewer's "what do I do next" panel for the benchmark workflow.
 *
 * The review path used to end at the last finding of a benchmark: once every
 * ground truth was FINALIZED the screen simply stopped, with no indication of
 * whether the dataset was finished or which benchmark came next. This panel
 * closes that loop with exactly two states, both derived from the already
 * loaded workspace:
 *
 *   - FINALIZED and another benchmark remains -> a primary
 *     "Continue to Next Contract" action.
 *   - FINALIZED and it was the last benchmark -> "Benchmark Review Complete".
 *
 * While the benchmark is DRAFT, IN_REVIEW or APPROVED the panel renders nothing
 * at all, so the action can never be mistaken for an invitation to skip review
 * work. It is a pure presentation component: it performs no reads and no writes
 * of its own — continuing is a navigation to an existing benchmark workspace.
 */
export function BenchmarkProgressionPanel({
  progression,
  onContinue,
}: {
  progression: BenchmarkProgression
  /** Navigates to the next benchmark workspace. Only called for kind 'next'. */
  onContinue: () => void
}) {
  if (progression.kind === 'not-finalized') return null

  if (progression.kind === 'complete') {
    return (
      <Card className="border-emerald-200 bg-emerald-50/40" data-benchmark-progression="complete">
        <CardContent className="space-y-2 py-6">
          <h2 role="status" className="flex items-center gap-2 text-lg font-semibold text-gray-900">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            {BENCHMARK_REVIEW_COMPLETE}
          </h2>
          <p className="text-sm text-gray-600">
            This was the last benchmark in the dataset and its ground truth is finalized. Every benchmark contract has been reviewed and its ground truth is
            immutable. There is no further review task in this dataset.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-blue-200 bg-blue-50/40" data-benchmark-progression="next">
      <CardContent className="flex flex-wrap items-center justify-between gap-4 py-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-900">
            <ShieldCheck className="h-5 w-5 text-blue-600" />
            Benchmark finalized
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            This benchmark&apos;s ground truth is finalized and immutable. Next benchmark in this dataset:{' '}
            <strong className="font-semibold text-gray-900">{progression.next.contract_name}</strong>.
          </p>
        </div>
        <Button type="button" size="lg" onClick={onContinue}>
          {CONTINUE_TO_NEXT_CONTRACT}
          <ArrowRight className="h-4 w-4" />
        </Button>
      </CardContent>
    </Card>
  )
}
