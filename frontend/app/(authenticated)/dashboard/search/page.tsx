'use client'

import { FormEvent, useState } from 'react'
import { useRouter } from 'next/navigation'
import { FileText, Loader2, Search as SearchIcon, Shield, ListChecks } from 'lucide-react'
import { apiFetch } from '../../../../lib/api'
import { EmptyState } from '../../../../components/EmptyState'
import { Button } from '../../../../components/ui/button'

type SearchResult = {
  type: 'contract' | 'finding' | 'passport'
  id: string
  title: string
  subtitle?: string
  contract_id?: string | null
  url: string
}

const TYPE_ICON: Record<SearchResult['type'], typeof FileText> = {
  contract: FileText,
  finding: ListChecks,
  passport: Shield,
}

const TYPE_LABEL: Record<SearchResult['type'], string> = {
  contract: 'Contract',
  finding: 'Finding',
  passport: 'Legal Passport',
}

export default function SearchPage() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function runSearch(text: string) {
    const trimmed = text.trim()
    if (!trimmed) {
      setResults(null)
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(`/api/search?q=${encodeURIComponent(trimmed)}`)
      if (!response.ok) throw new Error('Search failed')
      const body: SearchResult[] = await response.json()
      setResults(body)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Search failed')
      setResults(null)
    } finally {
      setLoading(false)
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    void runSearch(query)
  }

  return (
    <div className="space-y-6 p-2">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Search</h1>
        <p className="mt-1 text-slate-600">Find contracts, findings, and legal passports by name or content.</p>
      </div>

      <form onSubmit={onSubmit} className="flex gap-2">
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search contracts, findings, passports…"
            className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
        <Button type="submit" disabled={loading || !query.trim()}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
        </Button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {results === null && !loading && (
        <EmptyState
          title="Search across everything"
          description="Type a contract name, a finding's title or clause text, or a passport ID to jump straight to it."
          icon={<SearchIcon className="h-6 w-6" />}
        />
      )}

      {results !== null && results.length === 0 && !loading && (
        <EmptyState
          title="No matches"
          description={`Nothing matched "${query.trim()}". Try a different word or check the spelling.`}
          icon={<SearchIcon className="h-6 w-6" />}
        />
      )}

      {results !== null && results.length > 0 && (
        <div className="space-y-2">
          {results.map((result) => {
            const Icon = TYPE_ICON[result.type]
            return (
              <button
                key={`${result.type}-${result.id}`}
                type="button"
                onClick={() => router.push(result.url)}
                className="flex w-full items-start gap-3 rounded-lg border border-slate-200 bg-white p-4 text-left hover:border-blue-400 hover:bg-blue-50"
              >
                <Icon className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-semibold text-slate-900">{result.title}</p>
                    <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                      {TYPE_LABEL[result.type]}
                    </span>
                  </div>
                  {result.subtitle && <p className="mt-1 truncate text-xs text-slate-500">{result.subtitle}</p>}
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
