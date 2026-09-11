'use client'

import { useEffect, useState } from 'react'
import { History } from 'lucide-react'
import { apiFetch } from '../../../../../lib/api'
import { useOrg } from '../../../../../components/OrgProvider'
import { EmptyState } from '../../../../../components/EmptyState'
import { Skeleton } from '../../../../../components/ui/skeleton'
import { Badge } from '../../../../../components/ui/badge'
import { Card } from '../../../../../components/ui/card'
import { PageHeader } from '../../../../../components/ui/page-header'
import { PageContainer } from '../../../../../components/ui/container'

type AuditLogEntry = {
  id: string
  actor_id: string
  actor_email?: string | null
  action: string
  resource_type: string
  resource_id?: string | null
  resource_name?: string | null
  summary: string
  org_id?: string | null
  metadata: Record<string, unknown>
  created_at?: string | null
}

const ACTION_LABELS: Record<string, string> = {
  'contract.uploaded': 'Contract uploaded',
  'passport.created': 'AI analysis complete',
  'redline.approved': 'Redline approved',
  'redline.rejected': 'Redline rejected',
  'redline.published': 'Redline published',
  'compliance.event_approved': 'Compliance event approved',
  'compliance.event_rejected': 'Compliance event rejected',
  'org.settings_updated': 'Settings updated',
}

function formatTimestamp(iso?: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function AuditLogPage() {
  const { currentOrg, roles, loading: orgLoading } = useOrg()
  const orgId = currentOrg?.org_id
  const canView = roles.includes('admin') || roles.includes('auditor')
  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    if (!orgId || !canView) return
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch('/api/audit-log?limit=200')
      if (response.status === 403) throw new Error('Admin or Auditor role required to view the audit log')
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load audit log')
      setEntries(await response.json())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load audit log')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, canView])

  if (orgLoading) {
    return (
      <PageContainer>
        <div className="space-y-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      </PageContainer>
    )
  }

  if (!currentOrg) {
    return (
      <PageContainer>
        <div className="rounded-[var(--radius-lg,0.75rem)] border border-amber-200 bg-amber-50 p-6 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200" role="status">
          <h1 className="text-xl font-bold">No organization membership</h1>
          <p className="mt-2">Sign-in succeeded, but this account is not an active member of an organization.</p>
        </div>
      </PageContainer>
    )
  }

  if (!canView) {
    return (
      <PageContainer>
        <div className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 p-6 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400" role="alert">
          <h1 className="text-xl font-bold">403 — Admin or Auditor role required</h1>
          <p className="mt-2">You need the Admin or Auditor role in this organization to view the audit log. The API enforces this independently of this page.</p>
        </div>
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Organization"
        title="Audit log"
        description="Everything that happened in this organization, most recent first — contract uploads, AI analysis, redline decisions, and compliance approvals."
      />

      <div className="mt-6 space-y-6">
      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}
      {!loading && entries.length === 0 && !error && (
        <EmptyState
          icon={<History className="h-6 w-6" />}
          title="No activity yet"
          description="Actions like contract uploads, AI analysis, redline approvals, and compliance decisions will appear here as they happen."
        />
      )}

      {!loading && entries.length > 0 && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-gray-100 bg-gray-50 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:bg-gray-700/40 dark:text-gray-400">
                <tr>
                  <th className="px-4 py-3 font-medium">When</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                  <th className="px-4 py-3 font-medium">Summary</th>
                  <th className="px-4 py-3 font-medium">Actor</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50 dark:divide-gray-700">
                {entries.map((entry) => (
                  <tr key={entry.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/40">
                    <td className="whitespace-nowrap px-4 py-3 text-gray-500 dark:text-gray-400">{formatTimestamp(entry.created_at)}</td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <Badge variant="secondary">{ACTION_LABELS[entry.action] || entry.action}</Badge>
                    </td>
                    <td className="px-4 py-3 text-gray-900 dark:text-gray-100">{entry.summary}</td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">{entry.actor_email || entry.actor_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      </div>
    </PageContainer>
  )
}
