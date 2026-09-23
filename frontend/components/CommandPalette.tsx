'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Search, ArrowRight, Loader2, type LucideIcon } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { useOrg } from './OrgProvider'
import { navigationItems, adminItems } from './Navigation'
import { canAccessEvaluation } from '../lib/roles'

type SearchResult = {
  type: 'contract' | 'finding' | 'passport'
  id: string
  title: string
  subtitle: string
  contract_id?: string | null
  url: string
}

type PaletteItem =
  | { kind: 'nav'; key: string; label: string; href: string; icon: LucideIcon }
  | { kind: 'result'; key: string; result: SearchResult }

const RESULT_BADGE: Record<SearchResult['type'], string> = {
  contract: 'bg-blue-100 text-blue-700',
  finding: 'bg-amber-100 text-amber-700',
  passport: 'bg-purple-100 text-purple-700',
}

// A global "jump anywhere" palette: Cmd+K / Ctrl+K opens it from any
// authenticated page. With no query typed it's a fast page-jump list built
// from the same nav items as the sidebar; once you type, it also searches
// contracts/findings/passports via the existing GET /api/search endpoint
// (debounced -- that endpoint does a full Firestore scan per call).
export function CommandPalette() {
  const router = useRouter()
  const { isAdmin, roles } = useOrg()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const isMac = /mac/i.test(navigator.platform || '')
      const modifierPressed = isMac ? event.metaKey : event.ctrlKey
      if (modifierPressed && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((prev) => !prev)
      } else if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    function onOpenEvent() {
      setOpen(true)
    }
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('lexproof:open-command-palette', onOpenEvent)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('lexproof:open-command-palette', onOpenEvent)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    setQuery('')
    setResults([])
    setActiveIndex(0)
    const focusHandle = setTimeout(() => inputRef.current?.focus(), 0)
    return () => clearTimeout(focusHandle)
  }, [open])

  useEffect(() => {
    if (!open) return
    const trimmed = query.trim()
    if (!trimmed) {
      setResults([])
      setSearching(false)
      return
    }
    setSearching(true)
    const debounceHandle = setTimeout(() => {
      void apiFetch(`/api/search?q=${encodeURIComponent(trimmed)}&limit=20`)
        .then(async (response) => {
          if (!response.ok) {
            setResults([])
            return
          }
          setResults(await response.json())
        })
        .catch(() => setResults([]))
        .finally(() => setSearching(false))
    }, 250)
    return () => clearTimeout(debounceHandle)
  }, [query, open])

  const navPool = useMemo(() => {
    const visibleNavigation = navigationItems.filter((item) => !('roles' in item) || canAccessEvaluation(roles))
    return isAdmin ? [...visibleNavigation, ...adminItems] : visibleNavigation
  }, [isAdmin, roles])

  const filteredNav = useMemo(() => {
    const trimmed = query.trim().toLowerCase()
    if (!trimmed) return navPool
    return navPool.filter((item) => item.label.toLowerCase().includes(trimmed))
  }, [navPool, query])

  const paletteItems: PaletteItem[] = useMemo(() => {
    const resultItems: PaletteItem[] = results.map((result) => ({
      kind: 'result',
      key: `result-${result.type}-${result.id}`,
      result,
    }))
    const navItems: PaletteItem[] = filteredNav.map((item) => ({
      kind: 'nav',
      key: `nav-${item.href}`,
      label: item.label,
      href: item.href,
      icon: item.icon,
    }))
    // With a query typed, live search results lead (they're the more
    // specific match); with no query, it's purely a page-jump list.
    return query.trim() ? [...resultItems, ...navItems] : navItems
  }, [filteredNav, results, query])

  useEffect(() => {
    setActiveIndex(0)
  }, [paletteItems.length])

  function go(item: PaletteItem) {
    setOpen(false)
    router.push(item.kind === 'nav' ? item.href : item.result.url)
  }

  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((index) => Math.min(index + 1, paletteItems.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      const item = paletteItems[activeIndex]
      if (item) go(item)
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-gray-900/40 px-4 pt-[12vh]"
      onClick={() => setOpen(false)}
      role="presentation"
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="flex items-center gap-3 border-b border-gray-100 px-4 py-3">
          <Search className="h-5 w-5 flex-shrink-0 text-gray-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onInputKeyDown}
            placeholder="Search contracts, findings, passports, or jump to a page…"
            className="flex-1 border-0 bg-transparent text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-0"
          />
          {searching && <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-gray-300" />}
          <kbd className="flex-shrink-0 rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-[10px] font-medium text-gray-400">
            ESC
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto py-2">
          {paletteItems.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-gray-400">
              {searching ? 'Searching…' : query.trim() ? 'No results' : 'No pages match'}
            </p>
          )}
          {paletteItems.map((item, index) => {
            const isActive = index === activeIndex
            if (item.kind === 'nav') {
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => go(item)}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm ${
                    isActive ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
                  }`}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  <span className="flex-1 truncate">{item.label}</span>
                  <ArrowRight className="h-3.5 w-3.5 flex-shrink-0 text-gray-300" />
                </button>
              )
            }
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => go(item)}
                onMouseEnter={() => setActiveIndex(index)}
                className={`flex w-full items-center gap-3 px-4 py-2.5 text-left ${isActive ? 'bg-blue-50' : ''}`}
              >
                <span className={`flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${RESULT_BADGE[item.result.type]}`}>
                  {item.result.type}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-gray-900">{item.result.title}</span>
                  {item.result.subtitle && (
                    <span className="block truncate text-xs text-gray-500">{item.result.subtitle}</span>
                  )}
                </span>
              </button>
            )
          })}
        </div>

        <div className="flex items-center justify-between border-t border-gray-100 px-4 py-2 text-[11px] text-gray-400">
          <span>↑↓ navigate · ↵ select</span>
          <span>⌘K / Ctrl+K to toggle</span>
        </div>
      </div>
    </div>
  )
}
