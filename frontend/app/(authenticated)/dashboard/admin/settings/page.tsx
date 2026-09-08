'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../../../../lib/api'
import { useOrg } from '../../../../../components/OrgProvider'
import { Button } from '../../../../../components/ui/button'
import { Skeleton } from '../../../../../components/ui/skeleton'

type OrgSettings = {
  name?: string
  default_link_expiry_days: number
  notify_on_assignment: boolean
}

export default function AdminSettingsPage() {
  const { currentOrg, isAdmin, loading: orgLoading, refresh } = useOrg()
  const orgId = currentOrg?.org_id
  const [settings, setSettings] = useState<OrgSettings | null>(null)
  const [name, setName] = useState('')
  const [expiryDays, setExpiryDays] = useState(14)
  const [notifyOnAssignment, setNotifyOnAssignment] = useState(true)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  async function load() {
    if (!orgId) return
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/settings`)
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load settings')
      const body: OrgSettings = await response.json()
      setSettings(body)
      setName(currentOrg?.name || '')
      setExpiryDays(body.default_link_expiry_days)
      setNotifyOnAssignment(body.notify_on_assignment)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load settings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId])

  async function save() {
    if (!orgId) return
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/settings`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim() || undefined,
          default_link_expiry_days: expiryDays,
          notify_on_assignment: notifyOnAssignment,
        }),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to save settings')
      const body: OrgSettings = await response.json()
      setSettings(body)
      setSaved(true)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (orgLoading) {
    return (
      <div className="space-y-4 p-8">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (!currentOrg) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-amber-900" role="status">
          <h1 className="text-xl font-bold">No organization membership</h1>
          <p className="mt-2">Sign-in succeeded, but this account is not an active member of an organization.</p>
        </div>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700" role="alert">
          <h1 className="text-xl font-bold">403 — Admin only</h1>
          <p className="mt-2">You need the Admin role in this organization to view or change settings. The API enforces this independently of this page.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-6 p-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Organization settings</h1>
        <p className="mt-2 text-gray-600">Branding and defaults for {currentOrg.name || 'this organization'}. Changes apply immediately and are recorded in the audit log.</p>
      </div>

      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {!loading && settings && (
        <>
          <div className="space-y-4 rounded-lg bg-white p-6 shadow">
            <h2 className="text-lg font-semibold text-gray-900">Organization profile</h2>
            <label className="block text-sm font-medium text-gray-700">
              Organization name
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal"
                placeholder="Acme Legal"
              />
            </label>
          </div>

          <div className="space-y-4 rounded-lg bg-white p-6 shadow">
            <h2 className="text-lg font-semibold text-gray-900">Counterparty links</h2>
            <label className="block text-sm font-medium text-gray-700">
              Default link expiry (days)
              <input
                type="number"
                min={1}
                max={90}
                value={expiryDays}
                onChange={(event) => setExpiryDays(Number(event.target.value))}
                className="mt-2 block w-32 rounded border border-gray-300 px-3 py-2 font-normal"
              />
              <span className="mt-1 block text-xs font-normal text-gray-500">
                Used whenever a redline is shared with a counterparty and no expiry is set explicitly. Between 1 and 90 days.
              </span>
            </label>
          </div>

          <div className="space-y-4 rounded-lg bg-white p-6 shadow">
            <h2 className="text-lg font-semibold text-gray-900">Notifications</h2>
            <label className="flex items-center gap-3 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={notifyOnAssignment}
                onChange={(event) => setNotifyOnAssignment(event.target.checked)}
              />
              Notify members when they are assigned a review
            </label>
          </div>

          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          <div className="flex items-center gap-3">
            <Button disabled={saving} onClick={() => void save()}>
              {saving ? 'Saving...' : 'Save changes'}
            </Button>
            {saved && !saving && <span className="text-sm text-green-700">Saved.</span>}
          </div>
        </>
      )}
    </div>
  )
}
