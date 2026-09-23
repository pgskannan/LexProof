/**
 * Helpers for the AI-generated, plain-English executive summary shown on a
 * contract's Lifecycle page (Task #107). Mirrors the request-builder /
 * cache-key pattern used by lib/translation.ts: this module only builds
 * paths and request descriptors, the page component owns fetching and state.
 */

export type SeverityCounts = {
  critical: number
  high: number
  medium: number
  low: number
}

export type ExecutiveSummary = {
  contract_id: string
  version_id: string
  summary: string
  risk_score: number | null
  risk_level: string | null
  compliance_score: number | null
  findings_by_severity: SeverityCounts
  generated_at: string
}

export const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low'] as const

export function executiveSummaryPath(contractId: string): string {
  return `/api/contracts/${encodeURIComponent(contractId)}/executive-summary`
}

export function regenerateExecutiveSummaryRequest(contractId: string): { path: string; method: 'POST' } {
  return {
    path: `/api/contracts/${encodeURIComponent(contractId)}/executive-summary/regenerate`,
    method: 'POST',
  }
}

export function severityBreakdownText(counts: SeverityCounts): string {
  return SEVERITY_ORDER.map((severity) => `${counts[severity]} ${severity}`).join(', ')
}
