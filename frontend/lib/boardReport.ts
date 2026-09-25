// Legal Risk Board Report (wow item 5): pure aggregation over data the app
// already serves -- GET /api/contracts and GET /api/findings. No new backend
// endpoint and no new business logic; the page just reshapes these into a
// board-friendly, printable view.

export const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const
export type Severity = (typeof SEVERITIES)[number]

export const RISK_THEMES = [
  'Liability',
  'Indemnification',
  'IP & Licensing',
  'Data & Privacy',
  'Termination',
  'Commercial',
  'Law & Disputes',
  'Other',
] as const
export type RiskTheme = (typeof RISK_THEMES)[number]

export type BoardFinding = {
  finding_id: string
  contract_id: string
  title?: string | null
  severity?: string | null
  clause_type?: string | null
  recommendation?: string | null
  risk_impact?: number | null
}

export type BoardContract = {
  contract_id: string
  name?: string | null
  risk_score?: number | null
  risk_level?: string | null
  passport_id?: string | null
  proof_status?: string | null
  evidence_count?: number | null
  anchored_evidence_count?: number | null
}

const SEVERITY_RANK: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 }

export function normalizeSeverity(value?: string | null): Severity | null {
  const upper = (value || '').toUpperCase()
  return (SEVERITIES as readonly string[]).includes(upper) ? (upper as Severity) : null
}

// Keyword rules checked in order; first match wins. clause_type is used when
// the analysis recorded one, but most findings don't carry it, so the title is
// the main signal.
const THEME_RULES: [RiskTheme, RegExp][] = [
  ['Indemnification', /indemn|hold harmless/i],
  ['Liability', /liabilit|damages|\bcap\b|consequential|warrant/i],
  ['Data & Privacy', /data|privacy|gdpr|ccpa|cpra|personal information|breach notification|security|dpa\b|sub-?processor/i],
  ['IP & Licensing', /intellectual property|\bip\b|licen[cs]|ownership|work product/i],
  ['Termination', /terminat|renewal|notice period|exit|expir/i],
  ['Commercial', /payment|price|pricing|fee|invoice|escalat|penalt|audit rights|scope|deliverable|service level|sla\b/i],
  ['Law & Disputes', /governing law|jurisdiction|arbitration|dispute|venue|forum/i],
]

export function riskTheme(finding: Pick<BoardFinding, 'title' | 'clause_type'>): RiskTheme {
  const haystacks = [finding.clause_type, finding.title].filter(
    (value): value is string => Boolean(value && value.trim() && value.trim().toLowerCase() !== 'other'),
  )
  for (const text of haystacks) {
    for (const [theme, pattern] of THEME_RULES) {
      if (pattern.test(text)) return theme
    }
  }
  return 'Other'
}

export type HeatmapCell = { count: number; worst: Severity | null }
export type HeatmapRow = {
  contract: BoardContract
  cells: Record<RiskTheme, HeatmapCell>
  total: number
  worst: Severity | null
}

function worseOf(a: Severity | null, b: Severity | null): Severity | null {
  if (!a) return b
  if (!b) return a
  return SEVERITY_RANK[b] > SEVERITY_RANK[a] ? b : a
}

/** Contracts x risk themes, most exposed contracts first. */
export function buildHeatmap(
  contracts: BoardContract[],
  findings: BoardFinding[],
  limit = 15,
): HeatmapRow[] {
  const byContract = new Map<string, BoardFinding[]>()
  for (const finding of findings) {
    if (!finding.contract_id) continue
    const list = byContract.get(finding.contract_id) || []
    list.push(finding)
    byContract.set(finding.contract_id, list)
  }
  const rows: HeatmapRow[] = []
  for (const contract of contracts) {
    const own = byContract.get(contract.contract_id)
    if (!own || own.length === 0) continue
    const cells = Object.fromEntries(RISK_THEMES.map((theme) => [theme, { count: 0, worst: null }])) as Record<
      RiskTheme,
      HeatmapCell
    >
    let worst: Severity | null = null
    for (const finding of own) {
      const severity = normalizeSeverity(finding.severity)
      const cell = cells[riskTheme(finding)]
      cell.count += 1
      cell.worst = worseOf(cell.worst, severity)
      worst = worseOf(worst, severity)
    }
    rows.push({ contract, cells, total: own.length, worst })
  }
  const exposure = (row: HeatmapRow) =>
    (row.worst ? SEVERITY_RANK[row.worst] : 0) * 1000 + (row.contract.risk_score ?? 0) * 10 + row.total
  // Re-uploads of the same document are separate contracts with the same name;
  // a board view should show each document once (its most exposed copy).
  const seen = new Set<string>()
  return rows
    .sort((a, b) => exposure(b) - exposure(a))
    .filter((row) => {
      const key = (row.contract.name || row.contract.contract_id).trim().toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, limit)
}

export type TopRisk = BoardFinding & { contract_name: string; theme: RiskTheme; severity: Severity }

/** Critical/high findings, worst first, one row per finding. */
export function topRisks(contracts: BoardContract[], findings: BoardFinding[], limit = 8): TopRisk[] {
  const names = new Map(contracts.map((contract) => [contract.contract_id, contract.name || contract.contract_id]))
  return findings
    .map((finding) => ({ finding, severity: normalizeSeverity(finding.severity) }))
    .filter(
      (item): item is { finding: BoardFinding; severity: Severity } =>
        (item.severity === 'CRITICAL' || item.severity === 'HIGH') && names.has(item.finding.contract_id),
    )
    .sort(
      (a, b) =>
        SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] ||
        (b.finding.risk_impact ?? 0) - (a.finding.risk_impact ?? 0),
    )
    .slice(0, limit)
    .map(({ finding, severity }) => ({
      ...finding,
      severity,
      theme: riskTheme(finding),
      contract_name: names.get(finding.contract_id) || finding.contract_id,
    }))
}

export type BoardSummary = {
  contractCount: number
  scoredCount: number
  avgRiskScore: number | null
  highOrCriticalContracts: number
  findingsBySeverity: Record<Severity, number>
  passportCoverage: number
  proofConfirmedOrAnchored: number
  themeTotals: Record<RiskTheme, number>
}

export function summarize(contracts: BoardContract[], findings: BoardFinding[]): BoardSummary {
  const scored = contracts.filter((contract) => typeof contract.risk_score === 'number')
  const findingsBySeverity = Object.fromEntries(SEVERITIES.map((severity) => [severity, 0])) as Record<Severity, number>
  const themeTotals = Object.fromEntries(RISK_THEMES.map((theme) => [theme, 0])) as Record<RiskTheme, number>
  const contractIds = new Set(contracts.map((contract) => contract.contract_id))
  for (const finding of findings) {
    if (!contractIds.has(finding.contract_id)) continue
    const severity = normalizeSeverity(finding.severity)
    if (severity) findingsBySeverity[severity] += 1
    themeTotals[riskTheme(finding)] += 1
  }
  return {
    contractCount: contracts.length,
    scoredCount: scored.length,
    avgRiskScore: scored.length
      ? Math.round(scored.reduce((sum, contract) => sum + (contract.risk_score ?? 0), 0) / scored.length)
      : null,
    highOrCriticalContracts: contracts.filter((contract) =>
      ['high', 'critical'].includes((contract.risk_level || '').toLowerCase()),
    ).length,
    findingsBySeverity,
    passportCoverage: contracts.filter((contract) => contract.passport_id).length,
    proofConfirmedOrAnchored: contracts.filter(
      (contract) =>
        contract.proof_status === 'confirmed' ||
        ((contract.anchored_evidence_count ?? 0) > 0 && contract.anchored_evidence_count === contract.evidence_count),
    ).length,
    themeTotals,
  }
}

// Engineering/test artifacts that live in the demo org (Playwright runs,
// hardening fixtures, seeded RBAC scenarios). The board report hides them by
// default -- visibly, with a count and a toggle -- so the view reflects the
// real contract portfolio rather than test scaffolding.
const TEST_ARTIFACT_PATTERNS = [
  /^e2e[-_ ]/i,
  /^evidence[_ ]validation[_ ]test/i,
  /^pii[_ ]test/i,
  /^ocr[_ ]?(live|test)/i,
  /^demo (cross-tenant|dual-role|duplicate-approval|golden path)/i,
  /(^|[_ -])fixture([_ .-]|$)/i,
]

export function isTestArtifact(contract: Pick<BoardContract, 'name'>): boolean {
  const name = (contract.name || '').trim()
  return TEST_ARTIFACT_PATTERNS.some((pattern) => pattern.test(name))
}

const UUID_LIKE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Board-friendly contract label: no file extension, no underscores, no bare ids. */
export function contractLabel(contract: Pick<BoardContract, 'name' | 'contract_id'>): string {
  const raw = (contract.name || '').trim()
  if (!raw || raw === contract.contract_id || UUID_LIKE.test(raw)) {
    return `Untitled contract (${contract.contract_id.slice(0, 8)})`
  }
  return raw.replace(/\.(docx|pdf|txt|png|jpe?g|tiff?)$/i, '').replace(/_/g, ' ')
}
