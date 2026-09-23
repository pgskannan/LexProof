'use client'

// Hardening item #9 -- "Why LexProof?" executive business-impact dashboard.
// One screen answering "what did LexProof actually accomplish for this
// portfolio", for an audience that will never open Contract Reviews or the
// Legal Passport itself: a funnel showing the whole verifiable chain
// (Contracts -> Risks Identified -> Redlines Reviewed -> Versions Published
// -> Evidence Anchored -> Audit Readiness), plus the four business-impact
// KPIs the hardening review named explicitly. This complements, and
// deliberately does not replace, Portfolio Trends (day-over-day history) or
// Reports (per-contract deep dive) -- see the links to both at the bottom.
//
// Every number on this page is either read directly from the backend's
// live aggregation over real records (GET /orgs/{org_id}/executive-summary)
// or computed from one clearly-labeled, user-editable assumption (minutes
// per finding) -- the same "measured, not invented" standard the Reports
// page holds itself to. Nothing here is a hardcoded sample value.
//
// Phase 4 (2026-09-11, gold-standard visual consistency pass): rebuilt onto
// PageContainer/PageHeader/Card -- the prior version had a decorative
// oversized icon+heading hero and raw bordered divs, explicitly flagged by
// the user as still reading like a placeholder screen. Every data value,
// fetch, and computation below is unchanged; this is a presentation-only
// rewrite. Added the explicit provenance-flow diagram the brief asked for
// (Contract -> AI Risk Analysis -> Human Review -> Published Version ->
// Evidence Fingerprint -> Blockchain Anchor -> Independent Verification)
// and four concise value-proposition tiles -- deliberately kept to an
// authenticated product screen's tone, not a marketing landing page: no new
// claims, only a clearer presentation of the same verifiable chain this
// page already described in prose.

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  Anchor,
  ArrowRight,
  BadgeCheck,
  FileText,
  Fingerprint,
  Sparkles,
  TrendingUp,
  UploadCloud,
  UserCheck,
} from 'lucide-react'
import { apiFetch } from '../../../../lib/api'
import { useOrg } from '../../../../components/OrgProvider'
import { EmptyState } from '../../../../components/EmptyState'
import { Skeleton } from '../../../../components/ui/skeleton'
import { Card, CardContent } from '../../../../components/ui/card'
import { PageHeader } from '../../../../components/ui/page-header'
import { PageContainer } from '../../../../components/ui/container'
import {
  executiveSummaryMetricsPath,
  type ExecutiveSummaryMetrics,
} from '../../../../lib/portfolioAnalytics'

const EYEBROW = 'text-xs font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400'

function formatMinutes(minutes: number): string {
  if (minutes < 1) return `${Math.max(1, Math.round(minutes * 60))} sec`
  if (minutes < 60) return `${minutes.toFixed(1)} min`
  const hours = Math.floor(minutes / 60)
  const rest = Math.round(minutes % 60)
  return `${hours} hr ${rest} min`
}

type FunnelStage = {
  label: string
  value: string
  sub?: string
}

function FunnelStrip({ stages }: { stages: FunnelStage[] }) {
  return (
    <div className="flex flex-col gap-2 lg:flex-row lg:items-stretch lg:gap-0">
      {stages.map((stage, index) => (
        <div key={stage.label} className="flex flex-1 items-center">
          <div className="flex-1 rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white p-4 text-center dark:border-gray-700 dark:bg-gray-800">
            <p className="text-3xl font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100">{stage.value}</p>
            <p className="mt-1 text-xs font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">{stage.label}</p>
            {stage.sub && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{stage.sub}</p>}
          </div>
          {index < stages.length - 1 && (
            <ArrowRight className="mx-2 hidden h-5 w-5 flex-shrink-0 text-gray-300 dark:text-gray-600 lg:block" />
          )}
        </div>
      ))}
    </div>
  )
}

const PROVENANCE_STEPS = [
  { label: 'Contract', icon: FileText },
  { label: 'AI Risk Analysis', icon: Sparkles },
  { label: 'Human Review', icon: UserCheck },
  { label: 'Published Version', icon: UploadCloud },
  { label: 'Evidence Fingerprint', icon: Fingerprint },
  { label: 'Blockchain Anchor', icon: Anchor },
  { label: 'Independent Verification', icon: BadgeCheck },
]

function ProvenanceFlow() {
  return (
    <div className="flex flex-col gap-2 overflow-x-auto pb-1 lg:flex-row lg:items-center lg:gap-0">
      {PROVENANCE_STEPS.map((step, index) => {
        const Icon = step.icon
        return (
          <div key={step.label} className="flex flex-1 items-center">
            <div className="flex flex-1 flex-col items-center gap-2 rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white px-3 py-4 text-center dark:border-gray-700 dark:bg-gray-800">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
                <Icon className="h-4.5 w-4.5" />
              </span>
              <p className="text-xs font-semibold text-gray-900 dark:text-gray-100">{step.label}</p>
            </div>
            {index < PROVENANCE_STEPS.length - 1 && (
              <ArrowRight className="mx-1.5 hidden h-4 w-4 flex-shrink-0 text-gray-300 dark:text-gray-600 lg:block" />
            )}
          </div>
        )
      })}
    </div>
  )
}

const VALUE_PROPS = [
  {
    icon: Sparkles,
    title: 'AI-powered contract intelligence',
    description: 'Gemini-backed risk and compliance analysis flags what matters in a contract, with a measured processing time behind every result.',
  },
  {
    icon: UserCheck,
    title: 'Human-controlled decisions',
    description: 'AI never approves or publishes anything itself -- every redline is reviewed and decided by a person, with server-enforced separation of duties.',
  },
  {
    icon: Fingerprint,
    title: 'Cryptographically verifiable evidence',
    description: 'Every published version and finding is fingerprinted with a deterministic hash the moment it is created.',
  },
  {
    icon: BadgeCheck,
    title: 'Independent verification',
    description: 'Anyone can recompute the fingerprint and check it against Ethereum directly from their own browser -- no LexProof login required.',
  },
]

export default function WhyLexProofPage() {
  const router = useRouter()
  const { currentOrg, loading: orgLoading } = useOrg()
  const orgId = currentOrg?.org_id

  const [metrics, setMetrics] = useState<ExecutiveSummaryMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Same editable assumption as the Reports page, same default -- kept
  // consistent across the app rather than inventing a second number for the
  // same thing. This is the only non-measured input on this page.
  const [minutesPerFinding, setMinutesPerFinding] = useState(12)

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    setLoading(true)
    setError('')
    void apiFetch(executiveSummaryMetricsPath(orgId))
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load executive summary')
        const body: ExecutiveSummaryMetrics = await response.json()
        if (!cancelled) setMetrics(body)
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Unable to load executive summary')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [orgId])

  const isEmptyPortfolio = metrics != null && metrics.contract_count === 0
  const attentionItems = metrics?.contracts_requiring_attention ?? []
  const visibleAttentionItems = attentionItems.slice(0, 5)
  const showAttentionViewAll = attentionItems.length > visibleAttentionItems.length

  // Audit readiness -- the same weighted formula the Reports page uses for
  // one contract (40% evidence anchored, 30% redlines reviewed, 15%
  // published, 15% analysis complete), extended to the whole portfolio.
  // "Analysis complete" is approximated as the fraction of contracts that
  // have at least one Legal Passport, since a passport is only ever created
  // once analysis finishes.
  const evidenceAnchoredPct = metrics && metrics.evidence_records_total > 0
    ? (metrics.evidence_anchored_total / metrics.evidence_records_total) * 100
    : 0
  const proposalsReviewedPct = metrics && metrics.proposals_total > 0
    ? (metrics.redlines_reviewed_total / metrics.proposals_total) * 100
    : metrics && metrics.proposals_total === 0 ? 100 : 0
  const publishedRatePct = metrics && metrics.proposals_total > 0
    ? (metrics.versions_published_total / metrics.proposals_total) * 100
    : 0
  const analysisCompletePct = metrics && metrics.contract_count > 0
    ? (metrics.passport_count / metrics.contract_count) * 100
    : 0
  const auditReadinessScore = metrics
    ? Math.round(evidenceAnchoredPct * 0.4 + proposalsReviewedPct * 0.3 + publishedRatePct * 0.15 + analysisCompletePct * 0.15)
    : null

  // Review-time-saved KPI -- same comparison Reports makes per contract,
  // applied to portfolio averages (avg findings per contract vs. the real
  // measured avg AI analysis time).
  const avgFindingsPerContract = metrics && metrics.contract_count > 0 ? metrics.findings_total / metrics.contract_count : 0
  const manualMinutesPerContract = minutesPerFinding * avgFindingsPerContract
  const aiMinutesPerAnalysis = metrics?.avg_ai_analysis_duration_ms != null ? metrics.avg_ai_analysis_duration_ms / 60000 : null
  const savingsPercent = aiMinutesPerAnalysis !== null && manualMinutesPerContract > 0
    ? Math.max(0, Math.min(100, 100 * (1 - aiMinutesPerAnalysis / manualMinutesPerContract)))
    : null

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Business impact"
        title="Why LexProof?"
        description="AI can tell you what's wrong. LexProof can prove what happened -- the whole verifiable chain across your portfolio, from a contract landing in LexProof to evidence anyone can independently verify on Ethereum."
      />

      <div className="mt-6 space-y-6">
        <Card>
          <CardContent>
            <p className={EYEBROW}>The verifiable chain</p>
            <div className="mt-3">
              <ProvenanceFlow />
            </div>
          </CardContent>
        </Card>

        {(loading || orgLoading) && (
          <div className="space-y-4">
            <Skeleton className="h-5 w-40" />
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="h-20 w-full" />
              ))}
            </div>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-28 w-full" />
              ))}
            </div>
          </div>
        )}

        {error && !loading && (
          <p role="alert" className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
            {error}
          </p>
        )}

        {!loading && !orgLoading && isEmptyPortfolio && (
          <EmptyState
            icon={<Sparkles className="h-6 w-6" />}
            title="No portfolio data yet"
            description="This dashboard fills in as contracts are uploaded, analyzed, reviewed, published, and anchored -- there's nothing to summarize until then."
            actionLabel="Go to contracts"
            onAction={() => router.push('/dashboard/contracts')}
          />
        )}

        {!loading && !orgLoading && metrics && !isEmptyPortfolio && (
          <>
            <div>
              <h2 className={EYEBROW}>Portfolio funnel</h2>
              <div className="mt-3">
                <FunnelStrip
                  stages={[
                    { label: 'Contracts', value: String(metrics.contract_count) },
                    { label: 'Risks identified', value: String(metrics.findings_total) },
                    { label: 'Redlines reviewed', value: String(metrics.redlines_reviewed_total), sub: `of ${metrics.proposals_total} proposed` },
                    { label: 'Versions published', value: String(metrics.versions_published_total) },
                    { label: 'Evidence anchored', value: String(metrics.evidence_anchored_total), sub: `of ${metrics.evidence_records_total} items` },
                    { label: 'Audit readiness', value: auditReadinessScore !== null ? `${auditReadinessScore}%` : '—' },
                  ]}
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Card>
                <CardContent>
                  <p className={EYEBROW}>Estimated review time</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        Estimated manual baseline
                      </p>
                      <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100">
                        {manualMinutesPerContract > 0 ? formatMinutes(manualMinutesPerContract) : 'Not available'}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        Measured AI analysis
                      </p>
                      <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100">
                        {aiMinutesPerAnalysis !== null ? formatMinutes(aiMinutesPerAnalysis) : 'Not yet measured'}
                      </p>
                    </div>
                  </div>
                  <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                    {manualMinutesPerContract > 0
                      ? `${formatMinutes(manualMinutesPerContract)} is an estimated manual-review baseline; AI analysis is measured directly.`
                      : 'An estimated manual-review baseline; AI analysis is measured directly.'}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <p className={EYEBROW}>Avg. AI analysis time</p>
                  <p className="mt-2 text-3xl font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100">
                    {aiMinutesPerAnalysis !== null ? formatMinutes(aiMinutesPerAnalysis) : 'Not yet measured'}
                  </p>
                  <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {metrics.ai_analysis_measurement_count > 0
                      ? `Measured directly around the Gemini call, averaged across ${metrics.ai_analysis_measurement_count} analys${metrics.ai_analysis_measurement_count === 1 ? 'is' : 'es'}.`
                      : 'No passports with real timing instrumentation yet -- analyze a contract to start measuring.'}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <p className={EYEBROW}>Evidence anchored &amp; verifiable</p>
                  <p className="mt-2 text-3xl font-bold tabular-nums tracking-tight text-purple-700 dark:text-purple-400">
                    {metrics.evidence_records_total > 0 ? `${evidenceAnchoredPct.toFixed(0)}%` : 'Not available'}
                  </p>
                  <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {metrics.evidence_anchored_total} of {metrics.evidence_records_total} evidence items anchored on
                    Ethereum Sepolia and independently verifiable by anyone.
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <p className={EYEBROW}>Contracts requiring attention</p>
                  <p className={`mt-2 text-3xl font-bold tabular-nums tracking-tight ${metrics.contracts_requiring_attention_count > 0 ? 'text-red-700 dark:text-red-400' : 'text-green-700 dark:text-green-400'}`}>
                    {metrics.contracts_requiring_attention_count}
                  </p>
                  <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    Failed AI analysis, or high risk (&ge;70) with no redline published yet.
                  </p>
                </CardContent>
              </Card>
            </div>

            {attentionItems.length > 0 && (
              <Card className="border-red-200 dark:border-red-900/50">
                <CardContent>
                  <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-red-800 dark:text-red-400">
                    <AlertTriangle className="h-4 w-4" />
                    Needs attention
                  </h2>
                  <ul className="mt-3 space-y-2">
                    {visibleAttentionItems.map((item) => (
                      <li key={item.contract_id} className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-md,0.5rem)] bg-red-50/60 p-3 text-sm dark:bg-red-950/20">
                        <div>
                          <p className="font-semibold text-gray-900 dark:text-gray-100">{item.name}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{item.reason}</p>
                        </div>
                        <Link
                          href={`/dashboard/contracts/${encodeURIComponent(item.contract_id)}`}
                          className="text-xs font-semibold text-[var(--brand-primary,#2563eb)] hover:underline"
                        >
                          Open contract
                        </Link>
                      </li>
                    ))}
                  </ul>
                  {showAttentionViewAll && (
                    <Link
                      href="/dashboard/ai-analysis/findings"
                      className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-red-700 hover:underline dark:text-red-400"
                    >
                      View all {metrics.contracts_requiring_attention_count} →
                    </Link>
                  )}
                </CardContent>
              </Card>
            )}

            <div>
              <h2 className={EYEBROW}>What LexProof delivers</h2>
              <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {VALUE_PROPS.map((prop) => {
                  const Icon = prop.icon
                  return (
                    <Card key={prop.title}>
                      <CardContent>
                        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
                          <Icon className="h-4.5 w-4.5" />
                        </span>
                        <p className="mt-3 text-sm font-semibold text-gray-900 dark:text-gray-100">{prop.title}</p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{prop.description}</p>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-4 border-t border-gray-200 pt-6 text-sm text-gray-600 dark:border-gray-700 dark:text-gray-400">
              <TrendingUp className="h-4 w-4 text-[var(--brand-primary,#2563eb)]" />
              <span>Want the trend over time, or a single contract&apos;s numbers?</span>
              <Link href="/dashboard/reports/trends" className="font-semibold text-[var(--brand-primary,#2563eb)] hover:underline">
                Portfolio Trends
              </Link>
              <Link href="/dashboard/reports" className="font-semibold text-[var(--brand-primary,#2563eb)] hover:underline">
                Per-contract Reports
              </Link>
            </div>
          </>
        )}
      </div>
    </PageContainer>
  )
}
