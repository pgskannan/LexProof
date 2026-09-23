'use client'

import { useEffect, useState } from 'react'
import { Bell, Mail } from 'lucide-react'
import { apiFetch } from '../../../../../lib/api'
import { Button } from '../../../../../components/ui/button'
import { Skeleton } from '../../../../../components/ui/skeleton'
import { Card, CardContent } from '../../../../../components/ui/card'
import { PageHeader } from '../../../../../components/ui/page-header'
import { PageContainer } from '../../../../../components/ui/container'

type NotificationPreferences = {
  in_app_analysis_complete: boolean
  in_app_analysis_failed: boolean
  email_analysis_complete: boolean
  email_analysis_failed: boolean
}

type PreferenceRow = {
  key: keyof NotificationPreferences
  label: string
}

const IN_APP_ROWS: PreferenceRow[] = [
  { key: 'in_app_analysis_complete', label: 'AI analysis complete' },
  { key: 'in_app_analysis_failed', label: 'AI analysis failed' },
]

const EMAIL_ROWS: PreferenceRow[] = [
  { key: 'email_analysis_complete', label: 'AI analysis complete' },
  { key: 'email_analysis_failed', label: 'AI analysis failed' },
]

export default function NotificationPreferencesPage() {
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch('/api/notifications/preferences')
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load preferences')
      setPreferences(await response.json())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load preferences')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function toggle(key: keyof NotificationPreferences) {
    if (!preferences) return
    const nextValue = !preferences[key]
    const previous = preferences
    setPreferences({ ...preferences, [key]: nextValue })
    setSaving(key)
    setError('')
    try {
      const response = await apiFetch('/api/notifications/preferences', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: nextValue }),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to save preference')
      setPreferences(await response.json())
    } catch (cause) {
      setPreferences(previous)
      setError(cause instanceof Error ? cause.message : 'Unable to save preference')
    } finally {
      setSaving(null)
    }
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Personal settings"
        title="Notification preferences"
        description="Choose which events notify you, and how. These settings are personal — they follow you across every organization you belong to."
      />

      <div className="mt-6 max-w-2xl space-y-6">
      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!loading && preferences && (
        <>
          <Card>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-[var(--brand-primary,#2563eb)]" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">In-app notifications</h2>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Shown in the notification bell at the top of the app.</p>
              <div className="divide-y divide-gray-100 dark:divide-gray-700">
                {IN_APP_ROWS.map((row) => (
                  <label key={row.key} className="flex items-center justify-between gap-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                    {row.label}
                    <input
                      type="checkbox"
                      checked={preferences[row.key]}
                      disabled={saving === row.key}
                      onChange={() => void toggle(row.key)}
                      className="h-4 w-4"
                    />
                  </label>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2">
                <Mail className="h-5 w-5 text-[var(--brand-primary,#2563eb)]" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Email notifications</h2>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Your preference is saved either way. Outbound email delivery is not yet configured for this
                workspace, so enabling these does not send email today — it queues your preference for when it is.
              </p>
              <div className="divide-y divide-gray-100 dark:divide-gray-700">
                {EMAIL_ROWS.map((row) => (
                  <label key={row.key} className="flex items-center justify-between gap-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                    {row.label}
                    <input
                      type="checkbox"
                      checked={preferences[row.key]}
                      disabled={saving === row.key}
                      onChange={() => void toggle(row.key)}
                      className="h-4 w-4"
                    />
                  </label>
                ))}
              </div>
            </CardContent>
          </Card>

          <Button variant="outline" onClick={() => void load()} disabled={loading}>
            Refresh
          </Button>
        </>
      )}
      </div>
    </PageContainer>
  )
}
