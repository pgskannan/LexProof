'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Scale } from 'lucide-react'
import { apiFetch } from '../../../../../lib/api'
import { useOrg } from '../../../../../components/OrgProvider'
import { EmptyState } from '../../../../../components/EmptyState'
import { Skeleton } from '../../../../../components/ui/skeleton'
import { Card } from '../../../../../components/ui/card'
import { PageHeader } from '../../../../../components/ui/page-header'
import { PageContainer } from '../../../../../components/ui/container'

type RegulationContract = {
  contract_id: string
  contract_name: string
  finding_count: number
}

type RegulationEntry = {
  citation: string
  count: number
  severity_counts: Record<string, number>
  contracts: RegulationContract[]
}

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']
const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'bg-red-500',
  HIGH: 'bg-orange-500',
  MEDIUM: 'bg-amber-400',
  LOW: 'bg-slate-400',
  UNKNOWN: 'bg-slate-300',
}

function findingsHref(contractId: string) {
  return `/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`
}

export default function RegulationMapPage() {
  const { currentOrg, loading: orgLoading } = useOrg()
  const orgId = currentOrg?.org_id
  const [regulations, setRegulations] = useState<RegulationEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    setLoading(true)
    setError('')
    void apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/regulation-map`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load the regulation map')
        const body: { regulations: RegulationEntry[] } = await response.json()
        if (!cancelled) setRegulations(body.regulations || [])
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Unable to load the regulation map')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [orgId])

  const maxCount = regulations.reduce((max, entry) => Math.max(max, entry.count), 0)

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Compliance"
        title="Regulation Map"
        description="Every AI finding is checked for the specific, named regulations it implicates (GDPR, CCPA, HIPAA, and others) when the analysis is confident enough to cite one. This view rolls those citations up across your whole portfolio, so you can see at a glance which regulations show up most, at what severity, and in which contracts."
        actions={<Scale className="h-6 w-6 text-[var(--brand-primary,#1d4ed8)]" />}
      />

      <div className="mt-6 space-y-6">
      {(loading || orgLoading) && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {error && !loading && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {!loading && !orgLoading && !error && regulations.length === 0 && (
        <EmptyState
          title="No regulation citations yet"
          description="Regulation citations appear here once AI analysis flags a finding that clearly implicates a specific, named regulation. Not every finding will have one -- LexProof only cites a regulation when it's confident, never a guess."
        />
      )}

      {!loading && !orgLoading && regulations.length > 0 && (
        <div className="space-y-4">
          {regulations.map((entry) => (
            <Card key={entry.citation} className="p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{entry.citation}</h2>
                <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                  {entry.count} finding{entry.count === 1 ? '' : 's'} across {entry.contracts.length} contract
                  {entry.contracts.length === 1 ? '' : 's'}
                </span>
              </div>

              <div className="mt-3 flex h-2.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
                {SEVERITY_ORDER.filter((severity) => entry.severity_counts[severity]).map((severity) => (
                  <div
                    key={severity}
                    className={SEVERITY_COLOR[severity]}
                    style={{ width: `${((entry.severity_counts[severity] || 0) / entry.count) * 100}%` }}
                    title={`${severity}: ${entry.severity_counts[severity]}`}
                  />
                ))}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                {SEVERITY_ORDER.filter((severity) => entry.severity_counts[severity]).map((severity) => (
                  <span key={severity} className="flex items-center gap-1.5">
                    <span className={`h-2 w-2 rounded-full ${SEVERITY_COLOR[severity]}`} />
                    {severity.charAt(0) + severity.slice(1).toLowerCase()}: {entry.severity_counts[severity]}
                  </span>
                ))}
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {entry.contracts.map((contract) => (
                  <Link
                    key={contract.contract_id}
                    href={findingsHref(contract.contract_id)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-700 hover:border-[var(--brand-primary,#93c5fd)] hover:bg-blue-50 hover:text-[var(--brand-primary,#1d4ed8)] dark:border-gray-700 dark:bg-gray-700/40 dark:text-gray-300"
                  >
                    {contract.contract_name}
                    <span className="text-gray-400 dark:text-gray-500">·</span>
                    {contract.finding_count}
                  </Link>
                ))}
              </div>

              {maxCount > 0 && (
                <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-gray-50 dark:bg-gray-700">
                  <div className="h-full rounded-full bg-[var(--brand-primary,#2563eb)]" style={{ width: `${(entry.count / maxCount) * 100}%` }} />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
      </div>
    </PageContainer>
  )
}
