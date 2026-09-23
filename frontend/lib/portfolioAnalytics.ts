export type FindingSeverityCounts = Record<string, number>
export type ProposalStatusCounts = Record<string, number>

export type PortfolioSnapshot = {
  snapshot_id: string
  org_id: string
  snapshot_date: string
  captured_at: string
  first_captured_at: string
  contract_count: number
  findings_total: number
  findings_by_severity: FindingSeverityCounts
  proposals_total: number
  proposals_by_status: ProposalStatusCounts
  passport_count: number
  evidence_total: number
  avg_risk_score: number | null
  avg_compliance_score: number | null
}

export function listPortfolioSnapshotsPath(orgId: string, limit?: number): string {
  const query = limit ? `?limit=${encodeURIComponent(String(limit))}` : ''
  return `/api/orgs/${encodeURIComponent(orgId)}/portfolio-snapshots${query}`
}

export function capturePortfolioSnapshotRequest(orgId: string) {
  return {
    path: `/api/orgs/${encodeURIComponent(orgId)}/portfolio-snapshots`,
    method: 'POST' as const,
  }
}

// Hardening item #9 -- "Why LexProof?" executive dashboard. Extends the same
// current-state snapshot shape above with funnel/KPI-shaped fields that only
// this dashboard needs (see compute_executive_metrics() on the backend).
export type ContractRequiringAttention = {
  contract_id: string
  name: string
  reason: string
}

export type ExecutiveSummaryMetrics = PortfolioSnapshot & {
  redlines_reviewed_total: number
  versions_published_total: number
  evidence_records_total: number
  evidence_anchored_total: number
  avg_ai_analysis_duration_ms: number | null
  ai_analysis_measurement_count: number
  contracts_requiring_attention_count: number
  contracts_requiring_attention: ContractRequiringAttention[]
}

export function executiveSummaryMetricsPath(orgId: string): string {
  return `/api/orgs/${encodeURIComponent(orgId)}/executive-summary`
}
