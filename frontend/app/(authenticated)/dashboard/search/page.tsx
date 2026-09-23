'use client'

import { FormEvent, useState } from 'react'
import { useRouter } from 'next/navigation'
import { FileText, Loader2, Search as SearchIcon, Shield, ListChecks } from 'lucide-react'
import { apiFetch } from '../../../../lib/api'
import { EmptyState } from '../../../../components/EmptyState'
import { Button } from '../../../../components/ui/button'
import { Badge } from '../../../../components/ui/badge'
import { DataTable } from '../../../../components/ui/data-table'
import { PageHeader } from '../../../../components/ui/page-header'
import { PageContainer } from '../../../../components/ui/container'

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
    <PageContainer>
      <PageHeader
        eyebrow="LexProof"
        title="Search"
        description="Find contracts, findings, and legal passports by name or content."
        className="max-w-none"
      />

      <form onSubmit={onSubmit} className="mt-6 flex w-full max-w-full items-center gap-2">
        <div className="relative flex-1 min-w-0">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search contracts, findings, passports…"
            className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-[var(--brand-primary,#2563eb)] focus:outline-none focus:ring-1 focus:ring-[var(--brand-primary,#2563eb)] dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          />
        </div>
        <Button type="submit" disabled={loading || !query.trim()} className="shrink-0">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
        </Button>
      </form>

      <div className="mt-6 w-full max-w-full space-y-6">
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {results === null && !loading && (
        <div className="w-full max-w-full">
          <EmptyState
            title="Search across everything"
            description="Type a contract name, a finding's title or clause text, or a passport ID to jump straight to it."
            icon={<SearchIcon className="h-6 w-6" />}
          />
        </div>
      )}

      {results !== null && results.length === 0 && !loading && (
        <div className="w-full max-w-full">
          <EmptyState
            title="No matches"
            description={`Nothing matched "${query.trim()}". Try a different word or check the spelling.`}
            icon={<SearchIcon className="h-6 w-6" />}
          />
        </div>
      )}

      {results !== null && results.length > 0 && (
        results.length <= 5 ? (
          <div className="space-y-2">
            {results.map((result) => {
              const Icon = TYPE_ICON[result.type]
              return (
                <button
                  key={`${result.type}-${result.id}`}
                  type="button"
                  onClick={() => router.push(result.url)}
                  className="flex w-full items-start gap-3 rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white p-4 text-left shadow-[var(--shadow-sm)] hover:border-[var(--brand-primary,#3b82f6)] hover:bg-blue-50/60 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700/40"
                >
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--brand-primary,#2563eb)]" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate font-semibold text-gray-900 dark:text-gray-100">{result.title}</p>
                      <Badge variant="secondary" className="shrink-0">{TYPE_LABEL[result.type]}</Badge>
                    </div>
                    {result.subtitle && <p className="mt-1 truncate text-xs text-gray-500 dark:text-gray-400">{result.subtitle}</p>}
                  </div>
                </button>
              )
            })}
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
            <DataTable
              columns={[
                {
                  key: 'type',
                  header: 'Type',
                  className: 'w-[120px] whitespace-nowrap',
                  render: (result: SearchResult) => <Badge variant="secondary">{TYPE_LABEL[result.type]}</Badge>,
                },
                {
                  key: 'title',
                  header: 'Title',
                  className: 'min-w-[260px]',
                  render: (result: SearchResult) => (
                    <div>
                      <p className="truncate font-medium text-gray-900 dark:text-gray-100">{result.title}</p>
                      {result.subtitle && <p className="mt-1 truncate text-xs text-gray-500 dark:text-gray-400">{result.subtitle}</p>}
                    </div>
                  ),
                },
                {
                  key: 'reference',
                  header: 'Reference',
                  className: 'min-w-[180px] whitespace-nowrap',
                  render: (result: SearchResult) => (
                    <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">{result.contract_id || result.id}</span>
                  ),
                },
                {
                  key: 'action',
                  header: 'Action',
                  className: 'text-right whitespace-nowrap',
                  render: (result: SearchResult) => (
                    <Button type="button" variant="outline" size="sm" onClick={(event) => { event.stopPropagation(); router.push(result.url); }}>
                      Open
                    </Button>
                  ),
                },
              ]}
              data={results}
              rowKey={(result) => `${result.type}-${result.id}`}
              pageSize={10}
              onRowClick={(result) => router.push(result.url)}
            />
          </div>
        )
      )}
      </div>
    </PageContainer>
  )
}
