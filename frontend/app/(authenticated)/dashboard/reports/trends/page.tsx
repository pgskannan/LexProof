'use client'

import { useCallback, useEffect, useState } from 'react'
import { TrendingUp } from 'lucide-react'
import { apiFetch } from '../../../../../lib/api'
import { useOrg } from '../../../../../components/OrgProvider'
import { EmptyState } from '../../../../../components/EmptyState'
import { Skeleton } from '../../../../../components/ui/skeleton'
import { Button } from '../../../../../components/ui/button'
import { Card, CardContent } from '../../../../../components/ui/card'
import { PageHeader } from '../../../../../components/ui/page-header'
import { PageContainer } from '../../../../../components/ui/container'
import {
  capturePortfolioSnapshotRequest,
  listPortfolioSnapshotsPath,
  type PortfolioSnapshot,
} from '../../../../../lib/portfolioAnalytics'

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']
const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#fbbf24',
  LOW: '#94a3b8',
  UNKNOWN: '#cbd5e1',
}

const CHART_WIDTH = 640
const CHART_HEIGHT = 160
const CHART_GAP = 8

function formatDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return day
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function formatWhen(value?: string | null): string {
  if (!value) return 'Not available'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function FindingsTrendChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  const maxFindings = Math.max(1, ...snapshots.map((s) => s.findings_total))
  const barWidth = Math.max(6, (CHART_WIDTH - CHART_GAP * Math.max(0, snapshots.length - 1)) / snapshots.length)

  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT + 24}`} className="w-full" role="img" aria-label="Findings by severity over time">
      {snapshots.map((snapshot, index) => {
        const x = index * (barWidth + CHART_GAP)
        let yCursor = CHART_HEIGHT
        return (
          <g key={snapshot.snapshot_id}>
            {SEVERITY_ORDER.filter((severity) => snapshot.findings_by_severity[severity]).map((severity) => {
              const count = snapshot.findings_by_severity[severity] || 0
              const segmentHeight = (count / maxFindings) * CHART_HEIGHT
              yCursor -= segmentHeight
              return (
                <rect
                  key={severity}
                  x={x}
                  y={yCursor}
                  width={barWidth}
                  height={segmentHeight}
                  fill={SEVERITY_COLOR[severity]}
                >
                  <title>{`${formatDay(snapshot.snapshot_date)} — ${severity}: ${count}`}</title>
                </rect>
              )
            })}
            {snapshot.findings_total === 0 && (
              <rect x={x} y={CHART_HEIGHT - 2} width={barWidth} height={2} fill="#e5e7eb" />
            )}
            <text x={x + barWidth / 2} y={CHART_HEIGHT + 16} fontSize={10} textAnchor="middle" fill="#6b7280">
              {formatDay(snapshot.snapshot_date)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function ScoreTrendChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  const barWidth = Math.max(6, (CHART_WIDTH - CHART_GAP * Math.max(0, snapshots.length - 1)) / snapshots.length)
  const xFor = (index: number) => index * (barWidth + CHART_GAP) + barWidth / 2
  const yFor = (value: number) => CHART_HEIGHT - (Math.max(0, Math.min(100, value)) / 100) * CHART_HEIGHT

  const riskPoints = snapshots
    .map((snapshot, index) => (snapshot.avg_risk_score !== null ? [xFor(index), yFor(snapshot.avg_risk_score)] : null))
    .filter((point): point is [number, number] => point !== null)
  const compliancePoints = snapshots
    .map((snapshot, index) =>
      snapshot.avg_compliance_score !== null ? [xFor(index), yFor(snapshot.avg_compliance_score)] : null,
    )
    .filter((point): point is [number, number] => point !== null)

  const toPolyline = (points: [number, number][]) => points.map(([x, y]) => `${x},${y}`).join(' ')

  return (
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT + 24}`} className="w-full" role="img" aria-label="Average risk and compliance score over time">
      {[0, 25, 50, 75, 100].map((tick) => (
        <line key={tick} x1={0} y1={yFor(tick)} x2={CHART_WIDTH} y2={yFor(tick)} stroke="#f1f5f9" strokeWidth={1} />
      ))}
      {riskPoints.length > 1 && <polyline points={toPolyline(riskPoints)} fill="none" stroke="#ef4444" strokeWidth={2} />}
      {compliancePoints.length > 1 && (
        <polyline points={toPolyline(compliancePoints)} fill="none" stroke="#16a34a" strokeWidth={2} />
      )}
      {riskPoints.map(([x, y], index) => (
        <circle key={`risk-${index}`} cx={x} cy={y} r={3} fill="#ef4444" />
      ))}
      {compliancePoints.map(([x, y], index) => (
        <circle key={`compliance-${index}`} cx={x} cy={y} r={3} fill="#16a34a" />
      ))}
      {snapshots.map((snapshot, index) => (
        <text key={snapshot.snapshot_id} x={xFor(index)} y={CHART_HEIGHT + 16} fontSize={10} textAnchor="middle" fill="#6b7280">
          {formatDay(snapshot.snapshot_date)}
        </text>
      ))}
    </svg>
  )
}

export default function PortfolioTrendsPage() {
  const { currentOrg, loading: orgLoading } = useOrg()
  const orgId = currentOrg?.org_id

  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [capturing, setCapturing] = useState(false)
  const [error, setError] = useState('')

  const loadSnapshots = useCallback(async (id: string) => {
    const response = await apiFetch(listPortfolioSnapshotsPath(id))
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load portfolio trends')
    const body: { snapshots: PortfolioSnapshot[] } = await response.json()
    setSnapshots(body.snapshots || [])
  }, [])

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    setLoading(true)
    setError('')
    ;(async () => {
      // There is no scheduler in this app, so capture today's snapshot
      // opportunistically on page load (best-effort -- a failed capture
      // should never block showing whatever history already exists).
      try {
        const request = capturePortfolioSnapshotRequest(orgId)
        await apiFetch(request.path, { method: request.method })
      } catch {
        // ignore -- fall through to loading whatever history already exists
      }
      try {
        await loadSnapshots(orgId)
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Unable to load portfolio trends')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [orgId, loadSnapshots])

  async function captureNow() {
    if (!orgId) return
    setCapturing(true)
    setError('')
    try {
      const request = capturePortfolioSnapshotRequest(orgId)
      const response = await apiFetch(request.path, { method: request.method })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to capture a snapshot')
      await loadSnapshots(orgId)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to capture a snapshot')
    } finally {
      setCapturing(false)
    }
  }

  const latest = snapshots.at(-1) ?? null;
  const published = latest?.proposals_by_status?.PUBLISHED || 0;
  const pending = (latest?.proposals_by_status?.PROPOSED || 0) + (latest?.proposals_by_status?.DRAFT || 0) + (latest?.proposals_by_status?.APPROVED || 0);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Analytics"
        title="Portfolio Trends"
        description="A daily snapshot of your portfolio's risk posture over time -- contracts, findings by severity, redline status, and average risk/compliance score. LexProof has no background scheduler, so a snapshot is captured automatically whenever this page loads (at most once per day)."
        actions={
          <Button type="button" variant="outline" onClick={() => void captureNow()} disabled={capturing || !orgId}>
            {capturing ? 'Capturing…' : 'Capture snapshot now'}
          </Button>
        }
      />

      <div className="mt-6 space-y-6">
      {error && !loading && (
        <p role="alert" className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </p>
      )}

      {(loading || orgLoading) && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-52 w-full" />
          <Skeleton className="h-52 w-full" />
        </div>
      )}

      {!loading && !orgLoading && snapshots.length === 0 && !error && (
        <EmptyState
          icon={<TrendingUp className="h-6 w-6" />}
          title="No portfolio history yet"
          description="Trend data builds up automatically -- one snapshot per day -- as your team uses LexProof. Capture the first one now to see today's numbers, then check back over the coming days to see the trend."
          actionLabel="Capture snapshot now"
          onAction={() => void captureNow()}
        />
      )}

      {!loading && !orgLoading && snapshots.length > 0 && latest && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
            {[
              { label: 'Contracts', value: String(latest.contract_count) },
              { label: 'Open findings', value: String(latest.findings_total) },
              { label: 'Evidence items', value: String(latest.evidence_total) },
              { label: 'Proposals published', value: String(published) },
              { label: 'Proposals pending', value: String(pending) },
              {
                label: 'Avg risk / compliance',
                value: `${latest.avg_risk_score ?? '—'} / ${latest.avg_compliance_score ?? '—'}`,
              },
            ].map((tile) => (
              <Card key={tile.label}>
                <CardContent className="p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">{tile.label}</p>
                  <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100">{tile.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Latest snapshot captured {formatWhen(latest.captured_at)} ({latest.snapshot_date}). History began{' '}
            {formatWhen(snapshots[0]?.first_captured_at)}.
          </p>

          <Card>
            <CardContent>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Findings by severity, over time</h2>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Every open finding across your portfolio on the day it was captured.</p>
              {snapshots.length === 1 ? (
                <p className="mt-3 text-xs italic text-gray-500 dark:text-gray-400">
                  Only one day of history so far -- this will become a real trend as more snapshots are captured on
                  later days.
                </p>
              ) : null}
              <div className="mt-4">
                <FindingsTrendChart snapshots={snapshots} />
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                {SEVERITY_ORDER.map((severity) => (
                  <span key={severity} className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: SEVERITY_COLOR[severity] }} />
                    {severity.charAt(0) + severity.slice(1).toLowerCase()}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Average risk &amp; compliance score, over time</h2>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Averaged across every contract with a Legal Passport in your portfolio (0–100).
              </p>
              <div className="mt-4">
                <ScoreTrendChart snapshots={snapshots} />
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-500" /> Avg risk score</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-green-600" /> Avg compliance score</span>
              </div>
            </CardContent>
          </Card>

          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="border-b border-gray-200 text-xs font-bold uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
                  <tr>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Contracts</th>
                    <th className="px-4 py-3">Findings</th>
                    <th className="px-4 py-3">Evidence</th>
                    <th className="px-4 py-3">Avg risk</th>
                    <th className="px-4 py-3">Avg compliance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {[...snapshots].reverse().map((snapshot) => (
                    <tr key={snapshot.snapshot_id}>
                      <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-gray-100">{snapshot.snapshot_date}</td>
                      <td className="px-4 py-2.5 tabular-nums text-gray-700 dark:text-gray-300">{snapshot.contract_count}</td>
                      <td className="px-4 py-2.5 tabular-nums text-gray-700 dark:text-gray-300">{snapshot.findings_total}</td>
                      <td className="px-4 py-2.5 tabular-nums text-gray-700 dark:text-gray-300">{snapshot.evidence_total}</td>
                      <td className="px-4 py-2.5 tabular-nums text-gray-700 dark:text-gray-300">{snapshot.avg_risk_score ?? '—'}</td>
                      <td className="px-4 py-2.5 tabular-nums text-gray-700 dark:text-gray-300">{snapshot.avg_compliance_score ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
      </div>
    </PageContainer>
  )
}
