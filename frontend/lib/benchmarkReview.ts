export const REVIEW_STATUSES = ['ALL', 'OPEN', 'DRAFT', 'IN_REVIEW', 'APPROVED', 'FINALIZED'] as const
export type ReviewStatus = typeof REVIEW_STATUSES[number]

export function benchmarkReviewPath(datasetId: string, contractId: string, versionId: string) {
  const params = new URLSearchParams({ dataset_id: datasetId, contract_id: contractId, version_id: versionId })
  return `/dashboard/ai-evaluation/benchmarks/review?${params.toString()}`
}

export function benchmarkLandingPath(datasetId?: string) {
  return datasetId ? `/dashboard/ai-evaluation/benchmarks?dataset_id=${encodeURIComponent(datasetId)}` : '/dashboard/ai-evaluation/benchmarks'
}

export type BenchmarkFinding = {
  ground_truth_id: string
  contract_id: string
  version_id: string
  finding_category: string
  clause_reference: string
  expected_severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  expected_finding: string
  expected_evidence: string
  expected_recommendation?: string | null
  review_status: Exclude<ReviewStatus, 'ALL' | 'OPEN'>
  reviewer_id: string
}

export type ReviewContract = {
  contract_id: string
  version_id: string
  contract_name: string
  version_number?: number | null
  document_text: string
  finding_count: number
  reviewed_count: number
  assigned_reviewer_id?: string | null
  /** When the contract was added to the benchmark dataset (its insertion order). */
  added_at?: string | null
}

export function isVisibleFinding(finding: BenchmarkFinding, status: ReviewStatus, search: string, reviewerId: string) {
  const matchesStatus = status === 'ALL' || (status === 'OPEN' ? finding.review_status !== 'FINALIZED' : finding.review_status === status)
  const query = search.trim().toLowerCase()
  const matchesSearch = !query || [finding.finding_category, finding.clause_reference, finding.expected_finding].some((value) => value.toLowerCase().includes(query))
  const matchesReviewer = !reviewerId || finding.reviewer_id === reviewerId
  return matchesStatus && matchesSearch && matchesReviewer
}

export function nextFindingIndex(currentIndex: number, total: number, direction: -1 | 1) {
  if (total === 0) return -1
  return (currentIndex + direction + total) % total
}

/**
 * Deterministic "next item" for Save & Next.
 *
 * Deliberately does NOT wrap around: advancing past the last visible item
 * returns null so the caller can say "No more items" instead of silently
 * re-selecting something the reviewer already finished. Returns null when
 * there is nothing else to advance to (0 or 1 visible items), and when the
 * saved finding is not in the visible queue (for example because a filter
 * hides it) so the caller can reveal it instead of jumping somewhere random.
 */
export function nextFinding(findings: BenchmarkFinding[], currentId: string, direction: -1 | 1 = 1): BenchmarkFinding | null {
  const index = findings.findIndex((item) => item.ground_truth_id === currentId)
  if (index < 0) return null
  const candidate = findings[index + direction]
  if (!candidate || candidate.ground_truth_id === currentId) return null
  return candidate
}

export function isFinalized(finding: Pick<BenchmarkFinding, 'review_status'> | null | undefined) {
  return finding?.review_status === 'FINALIZED'
}

/**
 * True when the reviewer has somewhere to advance to.
 *
 * Advancing is always driven by `nextFinding`, which never wraps, so a finding
 * at the end of the visible queue reports false. UI actions labelled "& Next"
 * are gated on this so the last finding never offers a Next action that would
 * either do nothing or jump backwards.
 */
export function hasNextFinding(findings: BenchmarkFinding[], currentId: string) {
  return nextFinding(findings, currentId, 1) !== null
}

export type FindingDraft = {
  ground_truth_id?: string
  contract_id: string
  version_id: string
  finding_category: string
  clause_reference: string
  expected_severity: BenchmarkFinding['expected_severity']
  expected_finding: string
  expected_evidence: string
  expected_recommendation?: string | null
  review_status?: BenchmarkFinding['review_status']
  reviewer_id?: string
}

export type ReviewFilters = { contractId: string; status: ReviewStatus; search: string; reviewerFilter: string }

export const RESET_FILTERS = { status: 'ALL' as ReviewStatus, search: '', reviewerFilter: '' }

export const SAVED_MESSAGE = 'Finding saved'
export const NO_MORE_ITEMS_MESSAGE = 'Finding saved. No next finding.'

/**
 * Explicitly states whether this save creates a finding or updates one.
 *
 * It is deliberately NOT inferred from the absence of an id: a draft that has
 * lost its id while the reviewer is editing must fail loudly instead of
 * being reinterpreted as a request to create another finding.
 */
export type SaveIntent = 'create' | 'update'

/** Required human-entered fields, mirroring the API's create contract. */
export const REQUIRED_FINDING_FIELDS: Array<[keyof FindingDraft, string]> = [
  ['finding_category', 'Category'],
  ['clause_reference', 'Clause / reference'],
  ['expected_finding', 'Expected finding'],
  ['expected_evidence', 'Expected evidence'],
]

/** Returns a reviewer-facing message, or null when the draft is complete. */
export function validateFindingDraft(draft: FindingDraft | null | undefined): string | null {
  if (!draft) return 'There is nothing to save yet.'
  const missing = REQUIRED_FINDING_FIELDS
    .filter(([field]) => !String(draft[field] ?? '').trim())
    .map(([, label]) => label)
  if (!missing.length) return null
  return `Complete the required fields before saving: ${missing.join(', ')}.`
}

export function findingSavePath(datasetId: string, groundTruthId?: string) {
  const base = `/api/evaluation/benchmarks/${encodeURIComponent(datasetId)}/findings`
  return groundTruthId ? `${base}/${encodeURIComponent(groundTruthId)}` : base
}

export function visibleFindingsFor(findings: BenchmarkFinding[], filters: ReviewFilters) {
  return findings.filter(
    (finding) =>
      finding.contract_id === filters.contractId &&
      isVisibleFinding(finding, filters.status, filters.search, filters.reviewerFilter),
  )
}

/** Turns any API failure into a message a reviewer can act on (handles FastAPI 422 arrays). */
export function describeSaveFailure(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null | undefined)?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      const entry = item as { loc?: unknown[]; msg?: string }
      const field = Array.isArray(entry?.loc) ? entry.loc[entry.loc.length - 1] : undefined
      return field ? `${String(field)}: ${entry.msg ?? 'invalid'}` : entry.msg ?? 'invalid'
    })
    if (messages.length) return `Unable to save finding (${messages.join('; ')})`
  }
  return `Unable to save finding (HTTP ${status})`
}

export type SaveFindingResult =
  | { status: 'invalid'; message: string }
  | { status: 'error'; message: string }
  | {
      status: 'saved'
      finding: BenchmarkFinding
      findings: BenchmarkFinding[]
      visibleFindings: BenchmarkFinding[]
      filters: ReviewFilters
      message: string
      /** True only when Save & Next actually advanced to another item. */
      advanced: boolean
      /** The item that must stay selected after the save. */
      selectedFindingId: string
    }

export type SaveFindingOptions = {
  draft: FindingDraft | null | undefined
  datasetId: string
  /** 'create' only when the reviewer is composing a new finding. */
  intent: SaveIntent
  moveNext: boolean
  filters: ReviewFilters
  request: (path: string, init: RequestInit) => Promise<Response>
  /** Reloads the workspace and returns the freshly persisted findings. */
  reloadFindings: () => Promise<BenchmarkFinding[]>
}

/**
 * Single source of truth for both Save Draft and Save & Next.
 *
 * Exactly one request is issued, for the reviewer's current draft:
 *   intent 'update' -> PATCH /findings/{id}
 *   intent 'create' -> POST  /findings
 *
 * Save & Next has no code path that can invent a record of its own; advancing
 * is driven entirely by whatever the reloaded workspace reports. Validation
 * runs before any request, so an incomplete draft can never reach the API.
 */
export async function saveFinding({
  draft,
  datasetId,
  intent,
  moveNext,
  filters,
  request,
  reloadFindings,
}: SaveFindingOptions): Promise<SaveFindingResult> {
  const invalid = validateFindingDraft(draft)
  if (invalid) return { status: 'invalid', message: invalid }
  if (!datasetId) return { status: 'invalid', message: 'Select a benchmark dataset before saving.' }
  if (intent === 'update' && !draft?.ground_truth_id) {
    return { status: 'error', message: 'This finding has no id, so it cannot be updated. Reload the review and try again.' }
  }

  const path = findingSavePath(datasetId, intent === 'update' ? draft?.ground_truth_id : undefined)
  let response: Response
  try {
    response = await request(path, {
      method: intent === 'create' ? 'POST' : 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contract_id: draft?.contract_id,
        version_id: draft?.version_id,
        finding_category: draft?.finding_category.trim(),
        clause_reference: draft?.clause_reference.trim(),
        expected_severity: draft?.expected_severity,
        expected_finding: draft?.expected_finding.trim(),
        expected_evidence: draft?.expected_evidence.trim(),
        expected_recommendation: draft?.expected_recommendation?.trim() || null,
      }),
    })
  } catch (reason) {
    return { status: 'error', message: reason instanceof Error ? reason.message : 'Unable to reach the benchmark review API' }
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) return { status: 'error', message: describeSaveFailure(response.status, body) }

  const finding = body as BenchmarkFinding | null
  if (!finding?.ground_truth_id) {
    return { status: 'error', message: 'The saved finding did not include an id, so the queue cannot be updated.' }
  }

  const findings = await reloadFindings()

  // A newly created DRAFT only belongs in the queue when it passes the active
  // filters. When it does not, the filters are reset so the reviewer can see
  // what they just saved rather than watching it disappear.
  let effectiveFilters = filters
  let visibleFindings = visibleFindingsFor(findings, effectiveFilters)
  if (!visibleFindings.some((item) => item.ground_truth_id === finding.ground_truth_id)) {
    effectiveFilters = { ...filters, ...RESET_FILTERS }
    visibleFindings = visibleFindingsFor(findings, effectiveFilters)
  }

  const next = moveNext ? nextFinding(visibleFindings, finding.ground_truth_id, 1) : null
  return {
    status: 'saved',
    finding,
    findings,
    visibleFindings,
    filters: effectiveFilters,
    message: moveNext && !next ? NO_MORE_ITEMS_MESSAGE : SAVED_MESSAGE,
    advanced: Boolean(next),
    selectedFindingId: next?.ground_truth_id ?? finding.ground_truth_id,
  }
}

export function reviewProgress(contracts: ReviewContract[], findings: BenchmarkFinding[]) {
  const reviewedFindings = findings.filter((finding) => finding.review_status === 'APPROVED' || finding.review_status === 'FINALIZED').length
  return {
    contractsReviewed: contracts.filter((contract) => contract.finding_count > 0 && contract.reviewed_count === contract.finding_count).length,
    contractTotal: contracts.length,
    findingsReviewed: reviewedFindings,
    findingTotal: findings.length,
  }
}

export function aiBlindPayloadKeys(payload: Record<string, unknown>) {
  return ['risk_findings', 'evaluation_run_findings', 'evaluation_matches', 'evaluation_metrics'].every((key) => !(key in payload))
}

// ── Benchmark progression ──────────────────────────────────────────────
//
// A "benchmark" is one contract row inside a benchmark dataset (C2, C6, C8 ...).
// Its status is derived exclusively from its human ground-truth findings: the
// least-advanced finding wins, so a benchmark only reads FINALIZED once every
// one of its findings is FINALIZED. Nothing here reads, requests or infers AI
// output — the progression is a pure function of the already-loaded AI-blind
// workspace payload.

export const BENCHMARK_STATUSES = ['DRAFT', 'IN_REVIEW', 'APPROVED', 'FINALIZED'] as const
export type BenchmarkStatus = typeof BENCHMARK_STATUSES[number]

export const CONTINUE_TO_NEXT_CONTRACT = 'Continue to Next Contract'
export const BENCHMARK_REVIEW_COMPLETE = 'Benchmark Review Complete'

/**
 * Aggregate review status of one benchmark's findings.
 *
 * A benchmark with no ground-truth findings is DRAFT by definition: there is
 * nothing finalized to continue past, and this keeps an untouched contract from
 * ever being reported as complete.
 */
export function benchmarkStatus(findings: BenchmarkFinding[]): BenchmarkStatus {
  if (!findings.length) return 'DRAFT'
  // BENCHMARK_STATUSES is ordered from least to most advanced, so the first
  // status that is present anywhere in the benchmark is the aggregate one.
  return BENCHMARK_STATUSES.find((status) => findings.some((finding) => finding.review_status === status)) ?? 'DRAFT'
}

export function benchmarkStatusForContract(findings: BenchmarkFinding[], contractId: string): BenchmarkStatus {
  return benchmarkStatus(findings.filter((finding) => finding.contract_id === contractId))
}

/**
 * The next benchmark in the dataset, in the dataset's own deterministic order.
 *
 * Callers pass the workspace ordered by `orderBenchmarkContracts`, so this is
 * the same sequence the contract list and the default contract selection show.
 * It is never re-sorted here and never wraps: the last benchmark has no next.
 */
export function nextBenchmarkContract(contracts: ReviewContract[], currentContractId: string): ReviewContract | null {
  const index = contracts.findIndex((contract) => contract.contract_id === currentContractId)
  if (index < 0 || index >= contracts.length - 1) return null
  return contracts[index + 1] ?? null
}

/**
 * Deterministic benchmark dataset order.
 *
 * The workspace endpoint returns dataset member rows in Firestore document-id
 * order, which has nothing to do with the order the benchmark was assembled in.
 * The dataset's own insertion order (`added_at`, the member's `added_at`) is the
 * deterministic order the benchmark was created in — for the internal benchmark
 * that is C2, C6, C8 — so the workspace is ordered once, here, and every
 * consumer (contract list, default selection and "Continue to Next Contract")
 * advances through the same sequence.
 *
 * `added_at` is an ISO-8601 UTC timestamp, so string comparison is chronological
 * and needs no Date parsing. Rows without one keep the relative position they
 * were reported in (the sort is stable), so an older payload cannot be shuffled.
 */
export function orderBenchmarkContracts(contracts: ReviewContract[]): ReviewContract[] {
  return contracts
    .map((contract, index) => ({ contract, index }))
    .sort((left, right) => {
      const leftAdded = left.contract.added_at ?? ''
      const rightAdded = right.contract.added_at ?? ''
      if (leftAdded !== rightAdded) return leftAdded < rightAdded ? -1 : 1
      return left.index - right.index
    })
    .map((entry) => entry.contract)
}

export type BenchmarkProgression =
  /** The current benchmark is still DRAFT / IN_REVIEW / APPROVED: no next task yet. */
  | { kind: 'not-finalized'; status: BenchmarkStatus }
  /** The current benchmark is FINALIZED and the dataset has a further benchmark. */
  | { kind: 'next'; status: 'FINALIZED'; next: ReviewContract; path: string }
  /** The current benchmark is FINALIZED and it was the last one in the dataset. */
  | { kind: 'complete'; status: 'FINALIZED' }

export type BenchmarkProgressionInput = {
  contracts: ReviewContract[]
  findings: BenchmarkFinding[]
  currentContractId: string
  datasetId: string
}

/**
 * Whether the reviewer gets a "Continue to Next Contract" action (and where it
 * goes), a "Benchmark Review Complete" state, or nothing at all.
 *
 * Returns 'not-finalized' while the benchmark is still being reviewed, which is
 * what keeps the action off screen before finalization.
 */
export function benchmarkProgression({ contracts, findings, currentContractId, datasetId }: BenchmarkProgressionInput): BenchmarkProgression {
  const status = benchmarkStatusForContract(findings, currentContractId)
  if (status !== 'FINALIZED') return { kind: 'not-finalized', status }
  const next = nextBenchmarkContract(contracts, currentContractId)
  if (!next) return { kind: 'complete', status: 'FINALIZED' }
  return { kind: 'next', status: 'FINALIZED', next, path: benchmarkReviewPath(datasetId, next.contract_id, next.version_id) }
}

export type BenchmarkContinueTarget = { path: string; contractId: string; versionId: string }

/**
 * What the primary action does when the reviewer clicks it.
 *
 * This is the whole of the click behaviour: a client-side navigation to the
 * next benchmark's review workspace, which is then loaded through the same
 * AI-blind read the reviewer arrived through. Continuing never runs an
 * evaluation, never calls an AI endpoint, never writes a ground-truth record.
 * Returns null when there is nothing to continue to.
 */
export function benchmarkContinueTarget(progression: BenchmarkProgression): BenchmarkContinueTarget | null {
  if (progression.kind !== 'next') return null
  return { path: progression.path, contractId: progression.next.contract_id, versionId: progression.next.version_id }
}

// ── Review actions: labels, status transitions, create-mode focus ──────

export const CREATE_FINDING_LABEL = 'Create finding'
export const SAVE_DRAFT_LABEL = 'Save Draft'
export const SAVE_AND_NEXT_LABEL = 'Save & Next'
export const MARK_IN_REVIEW_LABEL = 'Mark In Review'
export const MARK_IN_REVIEW_AND_NEXT_LABEL = 'Mark In Review & Next'
export const APPROVE_LABEL = 'Approve'
export const APPROVE_AND_NEXT_LABEL = 'Approve & Next'
export const FINALIZE_LABEL = 'Finalize'
export const FINALIZE_AND_NEXT_LABEL = 'Finalize & Next'

export type TransitionStatus = Exclude<BenchmarkFinding['review_status'], 'DRAFT'>

export function findingStatusPath(datasetId: string, groundTruthId: string) {
  return `/api/evaluation/benchmarks/${encodeURIComponent(datasetId)}/findings/${encodeURIComponent(groundTruthId)}/status`
}

/** Human label for a status transition, used in reviewer feedback. */
export function transitionStatusLabel(status: TransitionStatus) {
  if (status === 'IN_REVIEW') return 'In Review'
  if (status === 'APPROVED') return 'Approved'
  return 'Finalized'
}

export function transitionFindingMessage(status: TransitionStatus, advanced: boolean, moveNext = false) {
  const label = transitionStatusLabel(status)
  // A plain transition makes no claim about what comes next, so it must not
  // report "no next finding": that reads as a dead end even when the queue has
  // more findings and the benchmark still has a next contract.
  if (!moveNext) return `Finding marked ${label}.`
  return advanced
    ? `Finding marked ${label}. Moved to the next finding.`
    : `Finding marked ${label}. No next finding.`
}

/** Same error decoding as a save, worded for a status change. */
export function describeTransitionFailure(status: number, body: unknown): string {
  return describeSaveFailure(status, body).replace(/^Unable to save finding/, 'Unable to change finding status')
}

export type TransitionFindingOptions = {
  datasetId: string
  groundTruthId: string
  status: TransitionStatus
  /** True only for the "& Next" actions; advancing never wraps. */
  moveNext: boolean
  filters: ReviewFilters
  request: (path: string, init: RequestInit) => Promise<Response>
  /** Reloads the workspace and returns the freshly persisted findings. */
  reloadFindings: () => Promise<BenchmarkFinding[]>
}

export type TransitionFindingResult =
  | { status: 'invalid'; message: string }
  | { status: 'error'; message: string }
  | {
      status: 'transitioned'
      finding: BenchmarkFinding
      findings: BenchmarkFinding[]
      visibleFindings: BenchmarkFinding[]
      filters: ReviewFilters
      message: string
      /** True only when the action actually advanced to another finding. */
      advanced: boolean
      /** The item that must stay selected after the transition. */
      selectedFindingId: string
    }

/**
 * Single source of truth for Mark In Review / Approve / Finalize, with and
 * without "& Next".
 *
 * Exactly one request is issued, for the reviewer's current finding:
 *   POST /findings/{id}/status  { status }
 *
 * Advancing happens entirely from the reloaded queue: the caller cannot pass a
 * pre-transition snapshot in, so a concurrent change by another reviewer is
 * picked up, the selection can never point at a stale item, and `nextFinding`
 * (which never wraps) guarantees the first finding is never re-selected.
 * Nothing here starts an evaluation or touches any non-ground-truth record.
 */
export async function transitionFinding({
  datasetId,
  groundTruthId,
  status,
  moveNext,
  filters,
  request,
  reloadFindings,
}: TransitionFindingOptions): Promise<TransitionFindingResult> {
  if (!datasetId) return { status: 'invalid', message: 'Select a benchmark dataset before changing a status.' }
  if (!groundTruthId) return { status: 'invalid', message: 'This finding has no id, so its status cannot change. Reload the review and try again.' }

  let response: Response
  try {
    response = await request(findingStatusPath(datasetId, groundTruthId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
  } catch (reason) {
    return { status: 'error', message: reason instanceof Error ? reason.message : 'Unable to reach the benchmark review API' }
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) return { status: 'error', message: describeTransitionFailure(response.status, body) }

  // The write has happened. Everything below comes from the fresh queue.
  const findings = await reloadFindings()
  const updated = body as BenchmarkFinding | null
  const finding = updated?.ground_truth_id ? updated : findings.find((item) => item.ground_truth_id === groundTruthId)
  if (!finding) return { status: 'error', message: 'The updated finding was not returned, so the queue cannot be trusted.' }

  // A finding that no longer matches the active filter would silently vanish
  // (for example IN_REVIEW under a DRAFT filter), so the filters are reset to
  // keep the reviewer on what they just changed.
  let effectiveFilters = filters
  let visibleFindings = visibleFindingsFor(findings, effectiveFilters)
  if (!visibleFindings.some((item) => item.ground_truth_id === finding.ground_truth_id)) {
    effectiveFilters = { ...filters, ...RESET_FILTERS }
    visibleFindings = visibleFindingsFor(findings, effectiveFilters)
  }

  const next = moveNext ? nextFinding(visibleFindings, finding.ground_truth_id, 1) : null
  return {
    status: 'transitioned',
    finding,
    findings,
    visibleFindings,
    filters: effectiveFilters,
    message: transitionFindingMessage(status, Boolean(next), moveNext),
    advanced: Boolean(next),
    selectedFindingId: next?.ground_truth_id ?? finding.ground_truth_id,
  }
}

/** Minimal shape of the scrollable viewport, so this stays testable without a DOM. */
export type ScrollableWindow = { scrollTo?: (options: { top: number }) => void }

/**
 * Landing position for a benchmark opened by "Continue to Next Contract".
 *
 * Client-side navigation keeps the scroll offset of the page it left, which
 * dropped the reviewer into the middle of the next contract (measured: the
 * review panel sat 94px below the viewport right after a Continue, so the
 * workspace title, progress and queue were all off screen). Opening a benchmark
 * is a navigation, not a continuation of the previous scroll position, so the
 * workspace is placed at its top where the title, contract information,
 * progress, AI-blind notice and finding queue are immediately visible.
 *
 * Returns true only when a scroll was requested, and does nothing else — it
 * never touches focus, so the finding editor and the create-finding focus flow
 * are unaffected.
 */
export function scrollWorkspaceToTop(scroller: ScrollableWindow | null | undefined) {
  if (!scroller?.scrollTo) return false
  scroller.scrollTo({ top: 0 })
  return true
}

/** Minimal shape of a focusable field, so focus rules are testable without a DOM. */
export type FocusableField = {
  focus: (options?: { preventScroll?: boolean }) => void
  scrollIntoView?: (options?: { block?: 'start' | 'center' | 'end' | 'nearest' }) => void
}

const EDITABLE_TAGS = ['INPUT', 'TEXTAREA', 'SELECT']

/** True when the reviewer is already typing in a field of their own. */
export function isEditingField(element: { tagName?: string; isContentEditable?: boolean } | null | undefined) {
  if (!element) return false
  if (element.isContentEditable === true) return true
  return EDITABLE_TAGS.includes(String(element.tagName || '').toUpperCase())
}

/**
 * Moves focus to the Category field of a newly started finding.
 *
 * Scrolls the field into view first, then focuses without letting the browser
 * scroll again. Returns false — and moves nothing — when there is no field to
 * focus or when the reviewer is already editing another input, so an in-progress
 * answer is never interrupted by focus jumping away mid-typing.
 */
export function focusNewFindingCategory(
  field: FocusableField | null | undefined,
  activeElement: { tagName?: string; isContentEditable?: boolean } | null | undefined,
) {
  if (!field) return false
  if (isEditingField(activeElement)) return false
  field.scrollIntoView?.({ block: 'center' })
  field.focus({ preventScroll: true })
  return true
}
