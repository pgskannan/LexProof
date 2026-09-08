'use client'

import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../../../../../lib/api'
import { ROLE_LABELS } from '../../../../../lib/roles'
import type { WorkflowDefinition } from '../../../../../lib/org'
import { useOrg } from '../../../../../components/OrgProvider'
import { Badge } from '../../../../../components/ui/badge'
import { Button } from '../../../../../components/ui/button'
import { EmptyState } from '../../../../../components/EmptyState'
import { Skeleton } from '../../../../../components/ui/skeleton'

export default function AdminWorkflowsPage() {
  const { currentOrg, isAdmin, loading: orgLoading } = useOrg()
  const orgId = currentOrg?.org_id
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function load() {
    if (!orgId) return
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/workflow-definitions`)
      if (response.status === 403) throw new Error('Admin role required to manage workflow definitions')
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load workflow definitions')
      const records: WorkflowDefinition[] = await response.json()
      setDefinitions(records)
      const next = records.find((item) => item.is_active) || records[0]
      if (next) {
        setSelectedId(next.definition_id)
        setDraft(JSON.stringify({ name: next.name, states: next.states, transitions: next.transitions }, null, 2))
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load workflow definitions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId])

  const selected = useMemo(
    () => definitions.find((item) => item.definition_id === selectedId) || null,
    [definitions, selectedId],
  )

  function choose(definition: WorkflowDefinition) {
    setSelectedId(definition.definition_id)
    setDraft(JSON.stringify({ name: definition.name, states: definition.states, transitions: definition.transitions }, null, 2))
  }

  async function createVersion() {
    if (!orgId) return
    setSaving(true)
    setError('')
    try {
      const parsed = JSON.parse(draft) as { name: string; states: WorkflowDefinition['states']; transitions: WorkflowDefinition['transitions'] }
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/workflow-definitions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to create workflow version')
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to create workflow version')
    } finally {
      setSaving(false)
    }
  }

  if (orgLoading) {
    return (
      <div className="space-y-4 p-8">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }
  if (!currentOrg) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-amber-900" role="status">
          <h1 className="text-xl font-bold">No organization membership</h1>
          <p className="mt-2">This account is not an active member of an organization.</p>
        </div>
      </div>
    )
  }
  if (!isAdmin) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700" role="alert">
          <h1 className="text-xl font-bold">403 — Admin only</h1>
          <p className="mt-2">You need the Admin role to view or version workflow definitions.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Workflow definitions</h1>
        <p className="mt-2 text-gray-600">Versioned state machines for this organization. Editing creates a new version; running instances keep the version they started on.</p>
      </div>

      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[20rem_1fr]">
        <div className="space-y-3">
          {definitions.map((definition) => (
            <button
              key={definition.definition_id}
              type="button"
              onClick={() => choose(definition)}
              className={`w-full rounded-lg border bg-white p-4 text-left shadow-sm ${selectedId === definition.definition_id ? 'border-blue-500' : 'border-gray-200'}`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold text-gray-900">{definition.name}</p>
                {definition.is_active && <Badge variant="verified">Active</Badge>}
              </div>
              <p className="mt-1 text-xs text-gray-500">Version {definition.version}</p>
            </button>
          ))}
          {definitions.length === 0 && !loading && (
            <EmptyState
              compact
              title="No workflow definitions yet"
              description="Run the org migration script to seed the contract redline approval workflow for this organization."
            />
          )}
        </div>

        {selected && (
          <div className="space-y-6 rounded-lg bg-white p-6 shadow">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500">States</p>
              <div className="mt-3 space-y-2">
                {selected.states.map((state) => (
                  <div key={state.id} className="flex flex-wrap items-center justify-between gap-2 border border-gray-100 px-3 py-2">
                    <div>
                      <p className="font-semibold text-gray-900">{state.name}</p>
                      <p className="font-mono text-xs text-gray-500">{state.id}</p>
                    </div>
                    <div className="flex gap-2">
                      {state.is_initial && <Badge variant="pending">Initial</Badge>}
                      {state.is_terminal && <Badge variant="verified">Terminal</Badge>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Transitions</p>
              <div className="mt-3 space-y-2">
                {selected.transitions.map((transition) => (
                  <div key={transition.id} className="border border-gray-100 px-3 py-2">
                    <p className="font-semibold text-gray-900">{transition.action_name}</p>
                    <p className="mt-1 text-sm text-gray-600">{transition.from_state} → {transition.to_state}</p>
                    <p className="mt-1 text-xs text-gray-500">
                      Roles: {(transition.allowed_roles || []).map((role) => ROLE_LABELS[role as keyof typeof ROLE_LABELS] || role).join(', ') || 'None'}
                      {transition.requires_not_actor?.length ? ` · Separation of duties: ${transition.requires_not_actor.join(', ')}` : ''}
                    </p>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Create a new version</p>
              <textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={16} className="mt-3 w-full rounded border border-gray-300 p-3 font-mono text-xs" />
              <Button className="mt-3" disabled={saving} onClick={() => void createVersion()}>
                {saving ? 'Saving...' : 'Save as new version'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
