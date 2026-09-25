'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { FileBarChart2, Printer, ShieldCheck } from 'lucide-react'
import { apiFetch } from '../../../../../lib/api'
import { useOrg } from '../../../../../components/OrgProvider'
import { EmptyState } from '../../../../../components/EmptyState'
import { Skeleton } from '../../../../../components/ui/skeleton'
import { Button } from '../../../../../components/ui/button'
import { Card, CardContent } from '../../../../../components/ui/card'
import { PageHeader } from '../../../../../components/ui/page-header'
import { PageContainer } from '../../../../../components/ui/container'
import {
  executiveSummaryMetricsPath,
  listPortfolioSnapshotsPath,
  type ExecutiveSummaryMetrics,
  type PortfolioSnapshot,
} from '../../../../../lib/portfolioAnalytics'
import {
  RISK_THEMES,
  SEVERITIES,
  buildHeatmap,
  contractLabel,
  isTestArtifact,
  summarize,
  topRisks,
  type BoardContract,
  type BoardFinding,
  type Severity,
} from '../../../../../lib/boardReport'

// Same risk-color language as the dashboard's Risk Overview and Portfolio Trends.
const SEVERITY_COLOR: Record<Severity, string> = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#fbbf24',
  LOW: '#94a3b8',
}
const SEVERITY_TEXT: Record<Severity, string> = {
  CRITICAL: '#ffffff',
  HIGH: '#ffffff',
  MEDIUM: '#111827',
  LOW: '#111827',
}

function titleCase(value: string) {
  return value.charAt(0) + value.slice(1).toLowerCase()
}

function RiskTrend({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  const points = snapshots.filter((snapshot) => snapshot.avg_risk_score !== null)
  if (points.length < 2) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Trend builds up from daily portfolio snapshots — {points.length === 1 ? 'one day' : 'no days'} captured so far.
      </p>
    )
  }
  const width = 560
  const height = 120
  const step = width / (points.length - 1)
  const y = (value: number) => height - (Math.max(0, Math.min(100, value)) / 100) * height
  const line = points.map((snapshot, index) => `${index * step},${y(snapshot.avg_risk_score as number)}`).join(' ')
  const round = (value: number) => Math.round(value * 10) / 10
  const first = round(points[0].avg_risk_score as number)
  const last = round(points[points.length - 1].avg_risk_score as number)
  const delta = round(last - first)
  return (
    <div>
      <svg viewBox={`-6 -6 ${width + 12} ${height + 12}`} className="h-32 w-full" role="img" aria-label="Average portfolio risk score over time">
        {[25, 50, 75].map((tick) => (
          <line key={tick} x1={0} x2={width} y1={y(tick)} y2={y(tick)} stroke="currentColor" className="text-gray-200 dark:text-gray-700" strokeWidth={1} />
        ))}
        <polyline points={line} fill="none" stroke="#ef4444" strokeWidth={2.5} strokeLinejoin="round" />
        {points.map((snapshot, index) => (
          <circle key={snapshot.snapshot_id} cx={index * step} cy={y(snapshot.avg_risk_score as number)} r={3} fill="#ef4444">
            <title>{`${snapshot.snapshot_date}: ${snapshot.avg_risk_score}`}</title>
          </circle>
        ))}
      </svg>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
        Average risk score moved from <strong>{first}</strong> to <strong>{last}</strong> ({delta > 0 ? '+' : ''}
        {delta}) between {points[0].snapshot_date} and {points[points.length - 1].snapshot_date}.
      </p>
    </div>
  )
}

export default function BoardReportPage() {
  const { currentOrg, loading: orgLoading } = useOrg()
  const orgId = currentOrg?.org_id
  const [contracts, setContracts] = useState<BoardContract[]>([])
  const [findings, setFindings] = useState<BoardFinding[]>([])
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([])
  const [executive, setExecutive] = useState<ExecutiveSummaryMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [generatedAt] = useState(() => new Date())
  const [includeTestArtifacts, setIncludeTestArtifacts] = useState(false)

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    setLoading(true)
    setError('')
    ;(async () => {
      try {
        const [contractsResponse, findingsResponse] = await Promise.all([apiFetch('/api/contracts'), apiFetch('/api/findings')])
        if (!contractsResponse.ok || !findingsResponse.ok) throw new Error('Unable to load portfolio data for the board report')
        const contractBody = await contractsResponse.json()
        const findingBody = await findingsResponse.json()
        if (cancelled) return
        setContracts(Array.isArray(contractBody) ? contractBody : [])
        setFindings(Array.isArray(findingBody) ? findingBody : findingBody?.findings || [])
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Unable to load the board report')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [orgId])

  // Trend and anchoring totals load separately and never hold up the report:
  // the executive-summary aggregation is the slowest call on this page.
  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    void apiFetch(listPortfolioSnapshotsPath(orgId, 90))
      .then(async (response) => {
        if (response.ok && !cancelled) setSnapshots((await response.json()).snapshots || [])
      })
      .catch(() => undefined)
    void apiFetch(executiveSummaryMetricsPath(orgId))
      .then(async (response) => {
        if (response.ok && !cancelled) setExecutive(await response.json())
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [orgId])

  const hiddenCount = useMemo(() => contracts.filter(isTestArtifact).length, [contracts])
  const reportContracts = useMemo(
    () => (includeTestArtifacts ? contracts : contracts.filter((contract) => !isTestArtifact(contract))),
    [contracts, includeTestArtifacts],
  )
  const summary = useMemo(() => summarize(reportContracts, findings), [reportContracts, findings])
  const heatmap = useMemo(() => buildHeatmap(reportContracts, findings, 15), [reportContracts, findings])
  const risks = useMemo(() => topRisks(reportContracts, findings, 8), [reportContracts, findings])
  const totalFindings = SEVERITIES.reduce((sum, severity) => sum + summary.findingsBySeverity[severity], 0)
  const busy = loading || orgLoading

  return (
    <PageContainer>
      <style>{'@media print { header { display: none !important; } main { padding-top: 0 !important; } .board-card { break-inside: avoid; } }'}</style>
      <PageHeader
        eyebrow="Analytics"
        title="Legal Risk Board Report"
        description="A one-page view of portfolio legal risk for executives and the board: exposure by contract and risk theme, the top risks to act on, the trend, and how much of it is independently provable on chain."
        actions={
          <div className="no-print flex gap-2">
            <Link href="/dashboard/reports/trends" className="inline-flex items-center rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800">
              Portfolio trends
            </Link>
            <Button type="button" onClick={() => window.print()} disabled={busy || !!error}>
              <Printer className="mr-2 h-4 w-4" /> Print / Save as PDF
            </Button>
          </div>
        }
      />

      <div className="mt-6 space-y-6">
        {error && !busy && (
          <p role="alert" className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
            {error}
          </p>
        )}

        {busy && (
          <div className="space-y-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-72 w-full" />
            <Skeleton className="h-52 w-full" />
          </div>
        )}

        {!busy && !error && contracts.length === 0 && (
          <EmptyState
            icon={<FileBarChart2 className="h-6 w-6" />}
            title="Nothing to report yet"
            description="Upload and analyze contracts first — the board report summarizes their findings, risk scores and on-chain proof."
          />
        )}

        {!busy && !error && contracts.length > 0 && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
              <p>
                {currentOrg?.name || orgId} · generated {generatedAt.toLocaleString()} · {summary.contractCount} contracts, {totalFindings} findings
                {!includeTestArtifacts && hiddenCount > 0 ? ` · ${hiddenCount} test/fixture contracts excluded` : ''}
              </p>
              {hiddenCount > 0 && (
                <label className="no-print flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5"
                    checked={includeTestArtifacts}
                    onChange={(event) => setIncludeTestArtifacts(event.target.checked)}
                  />
                  Include test &amp; fixture contracts ({hiddenCount})
                </label>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              {[
                { label: 'Average risk score', value: summary.avgRiskScore ?? '—', note: `across ${summary.scoredCount} scored contracts` },
                { label: 'High / critical contracts', value: summary.highOrCriticalContracts, note: `of ${summary.contractCount} in the portfolio` },
                { label: 'Critical + high findings', value: summary.findingsBySeverity.CRITICAL + summary.findingsBySeverity.HIGH, note: `${summary.findingsBySeverity.CRITICAL} critical · ${summary.findingsBySeverity.HIGH} high` },
                executive && executive.evidence_records_total > 0
                  ? { label: 'Evidence anchored on chain', value: `${executive.evidence_anchored_total}/${executive.evidence_records_total}`, note: `${summary.passportCoverage} of ${summary.contractCount} contracts have a Legal Passport` }
                  : { label: 'Legal Passport coverage', value: `${summary.passportCoverage}/${summary.contractCount}`, note: 'contracts with a fingerprinted passport' },
              ].map((tile) => (
                <Card key={tile.label} className="board-card">
                  <CardContent className="p-4">
                    <p className="text-xs font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">{tile.label}</p>
                    <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100">{tile.value}</p>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{tile.note}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Card className="board-card overflow-hidden">
              <CardContent>
                <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Risk heatmap — contracts × risk theme</h2>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  The {heatmap.length} most exposed contracts. Each cell shows how many findings fall in that theme, colored by the worst severity among them.
                </p>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[760px] border-separate border-spacing-1 text-xs">
                    <thead>
                      <tr>
                        <th className="w-56 px-2 py-1 text-left font-semibold text-gray-500 dark:text-gray-400">Contract</th>
                        <th className="px-1 py-1 text-center font-semibold text-gray-500 dark:text-gray-400">Risk</th>
                        {RISK_THEMES.map((theme) => (
                          <th key={theme} className="px-1 py-1 text-center font-semibold text-gray-500 dark:text-gray-400">{theme}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {heatmap.map((row) => (
                        <tr key={row.contract.contract_id}>
                          <td className="max-w-[14rem] truncate px-2 py-1 font-medium text-gray-900 dark:text-gray-100" title={row.contract.name || row.contract.contract_id}>
                            <Link href={`/dashboard/contracts/${encodeURIComponent(row.contract.contract_id)}`} className="hover:underline">
                              {contractLabel(row.contract)}
                            </Link>
                          </td>
                          <td className="px-1 py-1 text-center tabular-nums text-gray-700 dark:text-gray-300">{row.contract.risk_score ?? '—'}</td>
                          {RISK_THEMES.map((theme) => {
                            const cell = row.cells[theme]
                            return (
                              <td
                                key={theme}
                                className="h-8 rounded text-center font-semibold tabular-nums"
                                style={
                                  cell.worst
                                    ? { backgroundColor: SEVERITY_COLOR[cell.worst], color: SEVERITY_TEXT[cell.worst], printColorAdjust: 'exact', WebkitPrintColorAdjust: 'exact' }
                                    : undefined
                                }
                                title={cell.count ? `${cell.count} finding(s), worst ${cell.worst ? titleCase(cell.worst) : 'unrated'}` : 'No findings'}
                              >
                                {cell.count ? cell.count : <span className="text-gray-300 dark:text-gray-600">·</span>}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                  {SEVERITIES.map((severity) => (
                    <span key={severity} className="flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: SEVERITY_COLOR[severity] }} />
                      {titleCase(severity)}
                    </span>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-6 lg:grid-cols-5">
              <Card className="board-card lg:col-span-3">
                <CardContent>
                  <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Top risks to act on</h2>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Critical and high findings, worst first, with the AI&apos;s recommended fix.</p>
                  {risks.length === 0 ? (
                    <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">No critical or high findings.</p>
                  ) : (
                    <ol className="mt-4 space-y-3">
                      {risks.map((risk, index) => (
                        <li key={risk.finding_id} className="flex gap-3">
                          <span className="mt-0.5 w-5 shrink-0 text-right text-sm font-bold tabular-nums text-gray-400">{index + 1}</span>
                          <div className="min-w-0">
                            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                              <span
                                className="mr-2 inline-block rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
                                style={{ backgroundColor: SEVERITY_COLOR[risk.severity], color: SEVERITY_TEXT[risk.severity], printColorAdjust: 'exact', WebkitPrintColorAdjust: 'exact' }}
                              >
                                {risk.severity}
                              </span>
                              {risk.title}
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">{contractLabel({ contract_id: risk.contract_id, name: risk.contract_name })} · {risk.theme}</p>
                            {risk.recommendation && (
                              <p className="mt-1 line-clamp-2 text-xs text-gray-600 dark:text-gray-300">{risk.recommendation}</p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </CardContent>
              </Card>

              <div className="space-y-6 lg:col-span-2">
                <Card className="board-card">
                  <CardContent>
                    <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Where the risk sits</h2>
                    <div className="mt-3 space-y-2">
                      {[...RISK_THEMES]
                        .sort((a, b) => summary.themeTotals[b] - summary.themeTotals[a])
                        .map((theme) => {
                          const count = summary.themeTotals[theme]
                          const max = Math.max(1, ...RISK_THEMES.map((item) => summary.themeTotals[item]))
                          return (
                            <div key={theme} className="flex items-center gap-2 text-xs">
                              <span className="w-28 shrink-0 text-gray-600 dark:text-gray-300">{theme}</span>
                              <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
                                <span className="block h-full rounded-full bg-blue-600" style={{ width: `${(count / max) * 100}%`, printColorAdjust: 'exact', WebkitPrintColorAdjust: 'exact' }} />
                              </span>
                              <span className="w-6 text-right tabular-nums text-gray-700 dark:text-gray-300">{count}</span>
                            </div>
                          )
                        })}
                    </div>
                  </CardContent>
                </Card>

                <Card className="board-card">
                  <CardContent>
                    <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Risk trend</h2>
                    <div className="mt-3">
                      <RiskTrend snapshots={snapshots} />
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>

            <Card className="board-card">
              <CardContent className="flex gap-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-green-600" />
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  <strong className="text-gray-900 dark:text-gray-100">Why the board can trust these numbers:</strong> every finding here is tied to a Legal Passport whose evidence is SHA-256 fingerprinted{executive && executive.evidence_anchored_total > 0 ? `, and ${executive.evidence_anchored_total} evidence items are anchored on Ethereum Sepolia` : ''}. Anyone can re-check a passport without trusting LexProof, using the public verifier or the offline proof package.
                </p>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </PageContainer>
  )
}
