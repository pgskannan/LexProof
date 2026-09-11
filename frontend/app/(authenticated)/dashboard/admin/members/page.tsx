'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../../../../lib/api'
import { ALL_ROLES, ROLE_LABELS, type OrgRole } from '../../../../../lib/roles'
import type { OrgMember } from '../../../../../lib/org'
import { useOrg } from '../../../../../components/OrgProvider'
import { Badge } from '../../../../../components/ui/badge'
import { Button } from '../../../../../components/ui/button'
import { Card, CardContent } from '../../../../../components/ui/card'
import { DataTable } from '../../../../../components/ui/data-table'
import { PageHeader } from '../../../../../components/ui/page-header'
import { PageContainer } from '../../../../../components/ui/container'
import { EmptyState } from '../../../../../components/EmptyState'
import { Skeleton } from '../../../../../components/ui/skeleton'

export default function AdminMembersPage() {
  const { currentOrg, isAdmin, loading: orgLoading } = useOrg()
  const orgId = currentOrg?.org_id
  const [members, setMembers] = useState<OrgMember[]>([])
  const [email, setEmail] = useState('')
  const [inviteRoles, setInviteRoles] = useState<OrgRole[]>(['reviewer'])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)

  async function load() {
    if (!orgId) return
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/members`)
      if (response.status === 403) throw new Error('Admin role required to manage members')
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load members')
      setMembers(await response.json())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load members')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId])

  async function invite() {
    if (!orgId || !email.trim()) return
    setBusyId('invite')
    setError('')
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/members/invites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), roles: inviteRoles }),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to invite member')
      setEmail('')
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to invite member')
    } finally {
      setBusyId(null)
    }
  }

  async function saveRoles(member: OrgMember, roles: string[]) {
    if (!orgId) return
    setBusyId(member.user_id)
    setError('')
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(member.user_id)}/roles`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roles }),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to update roles')
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to update roles')
    } finally {
      setBusyId(null)
    }
  }

  async function deactivate(member: OrgMember) {
    if (!orgId) return
    setBusyId(member.user_id)
    setError('')
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(member.user_id)}/deactivate`, {
        method: 'POST',
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to deactivate member')
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to deactivate member')
    } finally {
      setBusyId(null)
    }
  }

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
          <p className="mt-2">Sign-in succeeded, but this account is not an active member of an organization. Run <code className="font-mono">python scripts/migrate_org_workflow.py --email you@example.com</code> from the backend directory.</p>
        </div>
      </PageContainer>
    )
  }
  if (!isAdmin) {
    return (
      <PageContainer>
        <div className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 p-6 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400" role="alert">
          <h1 className="text-xl font-bold">403 — Admin only</h1>
          <p className="mt-2">You need the Admin role in this organization to manage members. The API enforces this independently of this page.</p>
        </div>
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Organization"
        title="Organization members"
        description="Invite colleagues by email and assign one or more of the five fixed roles. Backend membership checks are the authorization source of truth."
      />

      <div className="mt-6 space-y-6">
      <Card>
        <CardContent>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Invite by email</h2>
          <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-end">
            <label className="block flex-1 text-sm font-medium text-gray-700 dark:text-gray-300">
              Email
              <input value={email} onChange={(event) => setEmail(event.target.value)} className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" placeholder="counsel@example.com" />
            </label>
            <div className="flex flex-wrap gap-3">
              {ALL_ROLES.map((role) => (
                <label key={role} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={inviteRoles.includes(role)}
                    onChange={(event) => setInviteRoles((current) => event.target.checked ? [...current, role] : current.filter((item) => item !== role))}
                  />
                  {ROLE_LABELS[role]}
                </label>
              ))}
            </div>
            <Button disabled={busyId === 'invite' || !email.trim() || inviteRoles.length === 0} onClick={() => void invite()}>
              {busyId === 'invite' ? 'Inviting...' : 'Invite'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      )}
      {!loading && members.length === 0 && (
        <EmptyState
          title="No members yet"
          description="Invite colleagues by email above. Each person gets one or more of the five fixed roles, scoped to this organization."
        />
      )}

      {members.length > 0 && (
        <div className="overflow-hidden rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
          <DataTable
            columns={[
              {
                key: 'member',
                header: 'Member',
                className: 'min-w-[220px] w-[28%]',
                render: (member: OrgMember) => (
                  <div>
                    <p className="truncate font-semibold text-gray-900 dark:text-gray-100">{member.display_name || member.email || member.user_id}</p>
                    <p className="mt-0.5 truncate font-mono text-[11px] text-gray-500 dark:text-gray-400">{member.email || member.user_id}</p>
                  </div>
                ),
              },
              {
                key: 'role',
                header: 'Role',
                className: 'whitespace-nowrap',
                render: (member: OrgMember) => (
                  <span className="text-sm text-gray-700 dark:text-gray-300">{(member.roles || []).length ? (member.roles || []).join(', ') : '—'}</span>
                ),
              },
              {
                key: 'status',
                header: 'Status',
                className: 'whitespace-nowrap',
                render: (member: OrgMember) => (
                  <Badge variant={member.status === 'active' ? 'verified' : member.status === 'deactivated' ? 'secondary' : 'pending'}>{member.status}</Badge>
                ),
              },
              {
                key: 'permissions',
                header: 'Permissions',
                className: 'min-w-[260px]',
                render: (member: OrgMember) => (
                  <div className="flex max-w-[260px] flex-wrap gap-2">
                    {ALL_ROLES.map((role) => {
                      const checked = (member.roles || []).includes(role)
                      return (
                        <label key={role} className="flex items-center gap-1.5 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={busyId === member.user_id || member.status === 'deactivated'}
                            onChange={(event) => {
                              const next = event.target.checked
                                ? [...(member.roles || []), role]
                                : (member.roles || []).filter((item) => item !== role)
                              void saveRoles(member, next)
                            }}
                          />
                          {ROLE_LABELS[role]}
                        </label>
                      )
                    })}
                  </div>
                ),
              },
              {
                key: 'action',
                header: 'Actions',
                className: 'text-right whitespace-nowrap',
                render: (member: OrgMember) => (
                  <div className="flex justify-end">
                    {member.status !== 'deactivated' && (
                      <Button variant="outline" size="sm" disabled={busyId === member.user_id} onClick={(event) => { event.stopPropagation(); void deactivate(member); }}>
                        Deactivate
                      </Button>
                    )}
                  </div>
                ),
              },
            ]}
            data={members}
            rowKey={(member) => member.user_id}
            pageSize={10}
          />
        </div>
      )}
      </div>
    </PageContainer>
  )
}
