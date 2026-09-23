'use client'

import { useEffect, useState } from 'react'
import { Bookmark, Plus, X } from 'lucide-react'
import { apiFetch } from '../lib/api'

export type SavedView = {
  id: string
  page: string
  name: string
  filters: Record<string, unknown>
}

type SavedViewsProps = {
  page: string
  currentFilters: Record<string, unknown>
  onApply: (filters: Record<string, unknown>) => void
}

export function SavedViews({ page, currentFilters, onApply }: SavedViewsProps) {
  const [views, setViews] = useState<SavedView[]>([])
  const [loading, setLoading] = useState(true)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [showSaveInput, setShowSaveInput] = useState(false)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    try {
      const response = await apiFetch(`/api/saved-views?page=${encodeURIComponent(page)}`)
      if (response.ok) setViews(await response.json())
    } catch {
      // Saved views are a convenience layer -- a failed load just means no
      // views show up, the underlying filter bar still works normally.
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  function apply(view: SavedView) {
    setActiveId(view.id)
    onApply(view.filters)
  }

  async function saveCurrent() {
    const trimmed = name.trim()
    if (!trimmed) return
    setSaving(true)
    setError('')
    try {
      const response = await apiFetch('/api/saved-views', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page, name: trimmed, filters: currentFilters }),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to save view')
      const created: SavedView = await response.json()
      setViews((current) => [...current, created])
      setActiveId(created.id)
      setName('')
      setShowSaveInput(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save view')
    } finally {
      setSaving(false)
    }
  }

  async function remove(view: SavedView) {
    const confirmed = window.confirm(`Delete the saved view "${view.name}"? This cannot be undone.`)
    if (!confirmed) return
    const previous = views
    setViews((current) => current.filter((v) => v.id !== view.id))
    if (activeId === view.id) setActiveId(null)
    try {
      const response = await apiFetch(`/api/saved-views/${encodeURIComponent(view.id)}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Unable to delete view')
    } catch {
      setViews(previous)
    }
  }

  if (loading) return null

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-gray-400">
        <Bookmark className="h-3.5 w-3.5" />
        Views
      </span>
      {views.map((view) => (
        <span
          key={view.id}
          className={`group inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium ${
            activeId === view.id
              ? 'border-blue-300 bg-blue-50 text-blue-700'
              : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300 hover:text-blue-700'
          }`}
        >
          <button type="button" onClick={() => apply(view)}>
            {view.name}
          </button>
          <button
            type="button"
            aria-label={`Delete view ${view.name}`}
            onClick={() => void remove(view)}
            className="text-gray-400 hover:text-red-600"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      {!showSaveInput && (
        <button
          type="button"
          onClick={() => setShowSaveInput(true)}
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-gray-300 px-3 py-1 text-xs font-medium text-gray-500 hover:border-blue-300 hover:text-blue-700"
        >
          <Plus className="h-3 w-3" />
          Save current filters
        </button>
      )}
      {showSaveInput && (
        <span className="inline-flex items-center gap-1">
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void saveCurrent()
              if (event.key === 'Escape') {
                setShowSaveInput(false)
                setName('')
              }
            }}
            placeholder="View name"
            className="w-32 rounded-full border border-gray-300 px-3 py-1 text-xs"
          />
          <button
            type="button"
            disabled={saving || !name.trim()}
            onClick={() => void saveCurrent()}
            className="rounded-full bg-blue-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setShowSaveInput(false)
              setName('')
            }}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Cancel
          </button>
        </span>
      )}
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  )
}
