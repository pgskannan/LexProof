'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '../../../../../lib/api'
import { useOrg } from '../../../../../components/OrgProvider'
import { Button } from '../../../../../components/ui/button'
import { Skeleton } from '../../../../../components/ui/skeleton'
import { Badge } from '../../../../../components/ui/badge'
import { Card, CardContent } from '../../../../../components/ui/card'
import { PageHeader } from '../../../../../components/ui/page-header'
import { PageContainer } from '../../../../../components/ui/container'
import { ChatDelivery, listChatDeliveriesPath, testChatNotificationRequest } from '../../../../../lib/chatNotifications'
import { DEFAULT_PRIMARY_COLOR, isValidHexColor } from '../../../../../lib/branding'

type OrgSettings = {
  name?: string
  default_link_expiry_days: number
  notify_on_assignment: boolean
  slack_webhook_url?: string | null
  teams_webhook_url?: string | null
  logo_url?: string | null
  primary_color?: string | null
}

type PlaybookClause = {
  clause_type: string
  standard_position: string
}

export default function AdminSettingsPage() {
  const { currentOrg, isAdmin, loading: orgLoading, refresh, refreshBranding } = useOrg()
  const orgId = currentOrg?.org_id
  const [settings, setSettings] = useState<OrgSettings | null>(null)
  const [name, setName] = useState('')
  const [expiryDays, setExpiryDays] = useState(14)
  const [notifyOnAssignment, setNotifyOnAssignment] = useState(true)
  const [slackWebhookUrl, setSlackWebhookUrl] = useState('')
  const [teamsWebhookUrl, setTeamsWebhookUrl] = useState('')
  const [logoUrl, setLogoUrl] = useState('')
  const [primaryColor, setPrimaryColor] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [deliveries, setDeliveries] = useState<ChatDelivery[]>([])
  const [deliveriesLoading, setDeliveriesLoading] = useState(false)
  const [testSending, setTestSending] = useState(false)
  const [testError, setTestError] = useState('')
  const [playbookClauses, setPlaybookClauses] = useState<PlaybookClause[]>([])
  const [playbookLoading, setPlaybookLoading] = useState(false)
  const [playbookSaving, setPlaybookSaving] = useState(false)
  const [playbookError, setPlaybookError] = useState('')
  const [playbookSaved, setPlaybookSaved] = useState(false)

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
      setSlackWebhookUrl(body.slack_webhook_url || '')
      setTeamsWebhookUrl(body.teams_webhook_url || '')
      setLogoUrl(body.logo_url || '')
      setPrimaryColor(body.primary_color || '')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load settings')
    } finally {
      setLoading(false)
    }
  }

  async function loadDeliveries() {
    if (!orgId) return
    setDeliveriesLoading(true)
    try {
      const response = await apiFetch(listChatDeliveriesPath(orgId, 10))
      if (!response.ok) return
      const body: { deliveries: ChatDelivery[] } = await response.json()
      setDeliveries(body.deliveries)
    } catch {
      // Best-effort -- the delivery log is a convenience, not load-bearing.
    } finally {
      setDeliveriesLoading(false)
    }
  }

  async function loadPlaybook() {
    if (!orgId) return
    setPlaybookLoading(true)
    setPlaybookError('')
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/playbook`)
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load playbook')
      const body: { clauses: PlaybookClause[] } = await response.json()
      setPlaybookClauses(body.clauses)
    } catch (cause) {
      setPlaybookError(cause instanceof Error ? cause.message : 'Unable to load playbook')
    } finally {
      setPlaybookLoading(false)
    }
  }

  useEffect(() => {
    void load()
    void loadPlaybook()
    void loadDeliveries()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId])

  async function sendTestChatNotification() {
    if (!orgId) return
    setTestSending(true)
    setTestError('')
    try {
      const request = testChatNotificationRequest(orgId)
      const response = await apiFetch(request.path, { method: request.method })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to send test notification')
      await loadDeliveries()
    } catch (cause) {
      setTestError(cause instanceof Error ? cause.message : 'Unable to send test notification')
    } finally {
      setTestSending(false)
    }
  }

  async function savePlaybook() {
    if (!orgId) return
    setPlaybookSaving(true)
    setPlaybookError('')
    setPlaybookSaved(false)
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/playbook`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clauses: playbookClauses }),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to save playbook')
      const body: { clauses: PlaybookClause[] } = await response.json()
      setPlaybookClauses(body.clauses)
      setPlaybookSaved(true)
    } catch (cause) {
      setPlaybookError(cause instanceof Error ? cause.message : 'Unable to save playbook')
    } finally {
      setPlaybookSaving(false)
    }
  }

  function updatePlaybookClause(index: number, field: keyof PlaybookClause, value: string) {
    setPlaybookClauses((current) => current.map((clause, i) => (i === index ? { ...clause, [field]: value } : clause)))
  }

  function removePlaybookClause(index: number) {
    setPlaybookClauses((current) => current.filter((_clause, i) => i !== index))
  }

  function addPlaybookClause() {
    setPlaybookClauses((current) => [...current, { clause_type: '', standard_position: '' }])
  }

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
          slack_webhook_url: slackWebhookUrl.trim(),
          teams_webhook_url: teamsWebhookUrl.trim(),
          logo_url: logoUrl.trim(),
          primary_color: primaryColor.trim(),
        }),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to save settings')
      const body: OrgSettings = await response.json()
      setSettings(body)
      setSlackWebhookUrl(body.slack_webhook_url || '')
      setTeamsWebhookUrl(body.teams_webhook_url || '')
      setLogoUrl(body.logo_url || '')
      setPrimaryColor(body.primary_color || '')
      setSaved(true)
      await refresh()
      await refreshBranding()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to save settings')
    } finally {
      setSaving(false)
    }
  }

  function formatDeliveryTime(iso: string): string {
    try {
      return new Date(iso).toLocaleString()
    } catch {
      return iso
    }
  }

  function deliveryStatusVariant(status: string): 'verified' | 'tampered' | 'secondary' {
    if (status === 'sent') return 'verified'
    if (status === 'failed') return 'tampered'
    return 'secondary'
  }

  if (orgLoading) {
    return (
      <PageContainer>
        <div className="space-y-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-48 w-full" />
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

  if (!isAdmin) {
    return (
      <PageContainer>
        <div className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 p-6 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400" role="alert">
          <h1 className="text-xl font-bold">403 — Admin only</h1>
          <p className="mt-2">You need the Admin role in this organization to view or change settings. The API enforces this independently of this page.</p>
        </div>
      </PageContainer>
    )
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Organization"
        title="Organization settings"
        description={`Branding and defaults for ${currentOrg.name || 'this organization'}. Changes apply immediately and are recorded in the audit log.`}
      />

      <div className="mt-6 max-w-2xl space-y-6">
      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {!loading && settings && (
        <>
          <Card>
            <CardContent className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Organization profile</h2>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Organization name
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                  placeholder="Acme Legal"
                />
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Branding</h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                  White-label the app for {currentOrg.name || 'this organization'} -- your logo replaces the LexProof
                  mark in the sidebar (LexProof stays credited as &quot;Powered by&quot;), and your brand color is used
                  for primary buttons and the active-navigation accent throughout the app, including on the public
                  counterparty review page. Leave either blank to keep LexProof&apos;s default look.
                </p>
              </div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Logo URL
                <input
                  value={logoUrl}
                  onChange={(event) => setLogoUrl(event.target.value)}
                  placeholder="https://cdn.example.com/logo.png"
                  className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                />
                <span className="mt-1 block text-xs font-normal text-gray-500 dark:text-gray-400">
                  An https:// URL to a square-ish image (PNG or SVG recommended). Shown at a small size in the sidebar.
                </span>
              </label>
              <div className="flex items-center gap-3">
                <span className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Preview</span>
                {logoUrl.trim() ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={logoUrl.trim()}
                    alt="Logo preview"
                    className="h-10 w-10 rounded-lg border border-gray-200 bg-white object-contain dark:border-gray-700"
                    onError={(event) => {
                      ;(event.target as HTMLImageElement).style.visibility = 'hidden'
                    }}
                    onLoad={(event) => {
                      ;(event.target as HTMLImageElement).style.visibility = 'visible'
                    }}
                  />
                ) : (
                  <span className="text-xs text-gray-400 dark:text-gray-500">No logo set -- the LexProof mark is shown</span>
                )}
              </div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Primary brand color
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <input
                    type="color"
                    value={isValidHexColor(primaryColor) ? primaryColor : DEFAULT_PRIMARY_COLOR}
                    onChange={(event) => setPrimaryColor(event.target.value)}
                    className="h-9 w-14 cursor-pointer rounded border border-gray-300 p-1 dark:border-gray-600"
                    aria-label="Primary brand color picker"
                  />
                  <input
                    value={primaryColor}
                    onChange={(event) => setPrimaryColor(event.target.value)}
                    placeholder="#2563EB"
                    className="w-32 rounded border border-gray-300 px-3 py-2 font-mono text-sm font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                  />
                  <span className="text-xs font-normal text-gray-500 dark:text-gray-400">Used for primary buttons and active navigation.</span>
                </div>
                {primaryColor.trim() && !isValidHexColor(primaryColor) && (
                  <span className="mt-1 block text-xs font-normal text-amber-600 dark:text-amber-400">
                    Must be a 6-digit hex color like #2563EB to save.
                  </span>
                )}
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Counterparty links</h2>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Default link expiry (days)
                <input
                  type="number"
                  min={1}
                  max={90}
                  value={expiryDays}
                  onChange={(event) => setExpiryDays(Number(event.target.value))}
                  className="mt-2 block w-32 rounded border border-gray-300 px-3 py-2 font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                />
                <span className="mt-1 block text-xs font-normal text-gray-500 dark:text-gray-400">
                  Used whenever a redline is shared with a counterparty and no expiry is set explicitly. Between 1 and 90 days.
                </span>
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Notifications</h2>
              <label className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={notifyOnAssignment}
                  onChange={(event) => setNotifyOnAssignment(event.target.checked)}
                />
                Notify members when they are assigned a review
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Chat notifications (Slack / Teams)</h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                  Post SLA escalations (see Contract Reviews) to a Slack or Microsoft Teams channel via an incoming
                  webhook. Leave both blank and notifications still work -- each one is recorded below as a
                  simulated delivery, so you can see exactly what would be sent before wiring up a real webhook.
                </p>
              </div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Slack webhook URL
                <input
                  value={slackWebhookUrl}
                  onChange={(event) => setSlackWebhookUrl(event.target.value)}
                  placeholder="https://hooks.slack.com/services/..."
                  className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                />
              </label>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Microsoft Teams webhook URL
                <input
                  value={teamsWebhookUrl}
                  onChange={(event) => setTeamsWebhookUrl(event.target.value)}
                  placeholder="https://outlook.office.com/webhook/..."
                  className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                />
              </label>
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="outline" disabled={testSending} onClick={() => void sendTestChatNotification()}>
                  {testSending ? 'Sending...' : 'Send test notification'}
                </Button>
                <span className="text-xs text-gray-500 dark:text-gray-400">Save changes first if you just edited a webhook URL above.</span>
              </div>
              {testError && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{testError}</p>}

              <div>
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Recent deliveries</h3>
                {deliveriesLoading && <Skeleton className="mt-2 h-16 w-full" />}
                {!deliveriesLoading && deliveries.length === 0 && (
                  <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No chat notifications sent yet.</p>
                )}
                {!deliveriesLoading && deliveries.length > 0 && (
                  <ul className="mt-2 space-y-2">
                    {deliveries.map((delivery) => (
                      <li key={delivery.delivery_id} className="rounded border border-gray-200 p-3 text-sm dark:border-gray-700">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={deliveryStatusVariant(delivery.status)}>{delivery.status}</Badge>
                          <span className="font-medium text-gray-800 dark:text-gray-200">{delivery.channel}</span>
                          <span className="text-gray-500 dark:text-gray-400">{formatDeliveryTime(delivery.created_at)}</span>
                        </div>
                        <p className="mt-1 font-medium text-gray-900 dark:text-gray-100">{delivery.title}</p>
                        <p className="text-gray-600 dark:text-gray-400">{delivery.message}</p>
                        {delivery.detail && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{delivery.detail}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Playbook</h2>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                  Standard clause positions AI analysis benchmarks every contract against. Findings are flagged as
                  Aligned, a Deviation, or Not Covered relative to what&apos;s defined here. Until customized, a
                  sensible built-in default playbook is used.
                </p>
              </div>
              {playbookLoading && <Skeleton className="h-32 w-full" />}
              {!playbookLoading && (
                <div className="space-y-3">
                  {playbookClauses.map((clause, index) => (
                    <div key={index} className="flex flex-col gap-2 rounded border border-gray-200 p-3 sm:flex-row sm:items-start dark:border-gray-700">
                      <input
                        value={clause.clause_type}
                        onChange={(event) => updatePlaybookClause(index, 'clause_type', event.target.value)}
                        placeholder="Clause type (e.g. Limitation of Liability)"
                        className="w-full rounded border border-gray-300 px-3 py-2 text-sm font-medium sm:w-56 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                      />
                      <textarea
                        value={clause.standard_position}
                        onChange={(event) => updatePlaybookClause(index, 'standard_position', event.target.value)}
                        placeholder="Standard position for this clause type"
                        rows={2}
                        className="w-full flex-1 rounded border border-gray-300 px-3 py-2 text-sm font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="shrink-0 self-start"
                        onClick={() => removePlaybookClause(index)}
                      >
                        Remove
                      </Button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={addPlaybookClause}
                    className="rounded border border-dashed border-gray-300 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700/40"
                  >
                    + Add clause type
                  </button>
                </div>
              )}
              {playbookError && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{playbookError}</p>}
              <div className="flex items-center gap-3">
                <Button disabled={playbookSaving || playbookClauses.length === 0} onClick={() => void savePlaybook()}>
                  {playbookSaving ? 'Saving...' : 'Save playbook'}
                </Button>
                {playbookSaved && !playbookSaving && <span className="text-sm text-green-700 dark:text-green-400">Saved.</span>}
              </div>
            </CardContent>
          </Card>

          {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          <div className="flex items-center gap-3">
            <Button disabled={saving} onClick={() => void save()}>
              {saving ? 'Saving...' : 'Save changes'}
            </Button>
            {saved && !saving && <span className="text-sm text-green-700 dark:text-green-400">Saved.</span>}
          </div>
        </>
      )}
      </div>
    </PageContainer>
  )
}
