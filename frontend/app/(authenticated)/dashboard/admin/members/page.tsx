'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../../../../lib/api'
import { ALL_ROLES, ROLE_LABELS, type OrgRole } from '../../../../../lib/roles'
import type { OrgMember } from '../../../../../lib/org'
import { useOrg } from '../../../../../components/OrgProvider'
import { Badge } from '../../../../../components/ui/badge'
import { Button } from '../../../../../components/ui/button'
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
      <div className="space-y-4 p-8">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }
  if (!currentOrg) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-amber-900" role="status">
          <h1 className="text-xl font-bold">No organization membership</h1>
          <p className="mt-2">Sign-in succeeded, but this account is not an active member of an organization. Run <code className="font-mono">python scripts/migrate_org_workflow.py --email you@example.com</code> from the backend directory.</p>
        </div>
      </div>
    )
  }
  if (!isAdmin) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700" role="alert">
          <h1 className="text-xl font-bold">403 — Admin only</h1>
          <p className="mt-2">You need the Admin role in this organization to manage members. The API enforces this independently of this page.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Organization members</h1>
        <p className="mt-2 text-gray-600">Invite colleagues by email and assign one or more of the five fixed roles. Backend membership checks are the authorization source of truth.</p>
      </div>

      <div className="rounded-lg bg-white p-6 shadow">
        <h2 className="text-lg font-semibold text-gray-900">Invite by email</h2>
        <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-end">
          <label className="block flex-1 text-sm font-medium text-gray-700">
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal" placeholder="counsel@example.com" />
          </label>
          <div className="flex flex-wrap gap-3">
            {ALL_ROLES.map((role) => (
              <label key={role} className="flex items-center gap-2 text-sm text-gray-700">
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
      </div>

      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
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

      <div className="space-y-3">
        {members.map((member) => (
          <div key={member.user_id} className="rounded-lg bg-white p-5 shadow">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-gray-900">{member.display_name || member.email || member.user_id}</p>
                <p className="mt-1 font-mono text-xs text-gray-500">{member.email || member.user_id}</p>
              </div>
              <Badge variant={member.status === 'active' ? 'verified' : 'pending'}>{member.status}</Badge>
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              {ALL_ROLES.map((role) => {
                const checked = (member.roles || []).includes(role)
                return (
                  <label key={role} className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      disabled={busyId === member.user_id || member.status === 'deactivated'}
                      checked={checked}
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
            {member.status !== 'deactivated' && (
              <Button variant="outline" className="mt-4" disabled={busyId === member.user_id} onClick={() => void deactivate(member)}>
                Deactivate
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
