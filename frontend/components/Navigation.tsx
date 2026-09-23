'use client'

import { useEffect, useRef, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  FileText,
  LayoutDashboard,
  Shield,
  Anchor,
  CheckCircle2,
  Eye,
  BarChart3,
  Settings,
  ListChecks,
  GitPullRequest,
  Users,
  Workflow,
  MessageSquare,
  Sparkles,
  ChevronDown,
  LogOut,
  Bell,
  Search,
  History,
  SlidersHorizontal,
  Sun,
  Moon,
  Laptop,
  Menu,
  X,
  Compass,
  Scale,
  TrendingUp,
  Rocket,
  ClipboardCheck,
} from 'lucide-react'
import { useOrg } from './OrgProvider'
import { useAuth } from './AuthProvider'
import { canAccessEvaluation } from '../lib/roles'
import { useTheme, type Theme } from './ThemeProvider'
import { Skeleton } from './ui/skeleton'
import { NotificationBell } from './NotificationBell'

// navigationItems/adminItems stay a FLAT, unchanged-shape export -- Phase 2
// (shell/nav redesign) groups them visually (see NAV_GROUPS below) without
// touching this data structure, because CommandPalette.tsx imports both by
// name and spreads them into its own flat search pool; regrouping this
// array would have silently broken Cmd+K.
export const navigationItems = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, exact: true },
  // Hardening item #9: the executive "Why LexProof?" dashboard -- placed
  // right after Dashboard so it's the first thing a judge/customer sees,
  // separate from the day-to-day workflow items below it.
  { label: 'Why LexProof?', href: '/dashboard/why-lexproof', icon: Rocket },
  { label: 'Search', href: '/dashboard/search', icon: Search },
  { label: 'Contracts', href: '/dashboard/contracts', icon: FileText },
  { label: 'Findings & Redlines', href: '/dashboard/ai-analysis/findings', icon: ListChecks },
  { label: 'Ask Lexi', href: '/dashboard/ask', icon: Sparkles, accent: 'ai' as const },
  { label: 'Contract Reviews', href: '/dashboard/contracts/reviews', icon: GitPullRequest },
  { label: 'AI Evaluation', href: '/dashboard/ai-evaluation/benchmarks', icon: BarChart3, roles: ['admin', 'reviewer', 'auditor'] as const },
  { label: 'Legal Passport', href: '/legal-passport', icon: Shield },
  { label: 'Blockchain Proof', href: '/dashboard/blockchain-proof', icon: Anchor },
  { label: 'Compliance', href: '/dashboard/compliance', icon: CheckCircle2 },
  { label: 'Regulation Map', href: '/dashboard/compliance/regulations', icon: Scale },
  { label: 'Verification', href: '/dashboard/verification', icon: Eye },
  { label: 'Reports', href: '/dashboard/reports', icon: BarChart3 },
  { label: 'Portfolio Trends', href: '/dashboard/reports/trends', icon: TrendingUp },
  // Hardening item #10: the brutally honest demo-ready vs. production-ready
  // status table.
  { label: 'Production Readiness', href: '/dashboard/production-readiness', icon: ClipboardCheck },
]

export const adminItems = [
  { label: 'Overview', href: '/dashboard/administration', icon: Settings },
  { label: 'Members', href: '/dashboard/admin/members', icon: Users },
  { label: 'Workflows', href: '/dashboard/admin/workflows', icon: Workflow },
  { label: 'Audit Log', href: '/dashboard/admin/audit-log', icon: History },
  { label: 'Settings', href: '/dashboard/admin/settings', icon: SlidersHorizontal },
]

// Phase 2 (2026-09-11): a purely presentational grouping over the flat,
// unchanged navigationItems array above -- each entry is looked up by href
// at render time, so this can never drift out of sync with the real item
// data, and reordering/renaming a group here can't affect CommandPalette
// (which only ever sees the flat navigationItems/adminItems exports).
// Group titles are a design grouping only, per the redesign brief -- every
// existing route and item is preserved, just visually organized.
const NAV_GROUPS: { title: string; hrefs: string[] }[] = [
  {
    title: 'Workspace',
    hrefs: [
      '/dashboard',
      '/dashboard/contracts',
      '/dashboard/ai-analysis/findings',
      '/dashboard/contracts/reviews',
      '/dashboard/ask',
      '/dashboard/search',
      '/dashboard/ai-evaluation/benchmarks',
    ],
  },
  {
    title: 'Evidence',
    hrefs: ['/legal-passport', '/dashboard/blockchain-proof'],
  },
  {
    // "Production Readiness" is a normal, ungated navigationItems entry (as
    // it always was); the collapsible adminItems submenu below it is still
    // gated on isAdmin exactly as before -- grouping them under one visual
    // heading doesn't change who can see which part.
    title: 'Administration',
    hrefs: ['/dashboard/production-readiness'],
  },
]

// Design tokens (Phase 1) + Phase 2 shell redesign: one shared icon size
// (18px, within the redesign brief's 18-20px range) used for every nav
// icon -- main items, the admin toggle, and admin sub-items -- so the
// sidebar reads as one consistent system instead of the previous mix of
// 20px main icons and 16px admin icons.
const NAV_ICON = 'h-[18px] w-[18px] flex-shrink-0'

function isActivePath(pathname: string, href: string, exact?: boolean) {
  if (exact) return pathname === href
  if (href === '/dashboard/contracts') {
    return pathname.startsWith('/dashboard/contracts') && !pathname.startsWith('/dashboard/contracts/reviews')
  }
  return pathname === href || pathname.startsWith(`${href}/`)
}

function isAdminRoute(pathname: string) {
  return pathname === '/dashboard/administration' || pathname.startsWith('/dashboard/admin/')
}

const THEME_OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Laptop },
]

// Sidebar entries the onboarding tour spotlights, keyed by href. Only a
// handful of the full nav list are part of the guided tour; the rest are
// left for the user to discover on their own.
const NAV_TOUR_IDS: Record<string, string> = {
  '/dashboard': 'nav-dashboard',
  '/dashboard/contracts': 'nav-contracts',
  '/dashboard/ai-analysis/findings': 'nav-findings',
  '/dashboard/ask': 'nav-ask-lexi',
  '/dashboard/contracts/reviews': 'nav-reviews',
}

// Shared link classes for a single nav row -- used for both the flat
// (ungrouped, pre-Phase-2) rendering that used to live here and, now, every
// item inside NAV_GROUPS. Kept as a function (not a static string) because
// active vs. inactive and top-level vs. admin-nested rows differ slightly.
function navLinkClassName({ active, nested }: { active: boolean; nested?: boolean }) {
  const base =
    'flex items-center gap-3 rounded-[var(--radius-md,0.5rem)] border-l-2 px-3 py-2 text-sm font-medium transition-colors duration-[var(--duration-fast,120ms)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary,#2563eb)] focus-visible:ring-offset-1'
  const nestedPadding = nested ? 'ml-4' : ''
  if (active) {
    return `${base} ${nestedPadding} bg-[color-mix(in_srgb,var(--brand-primary,#2563eb)_8%,white)] text-[var(--brand-primary,#1d4ed8)] border-[var(--brand-primary,#2563eb)] dark:bg-blue-950 dark:text-blue-300 dark:border-blue-500`
  }
  return `${base} ${nestedPadding} border-transparent text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700/60`
}

export function Navigation() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout } = useAuth()
  const { isAdmin, roles, currentOrg, orgs, selectOrg, loading, me, branding } = useOrg()
  // White-label (Task #109): once an org sets a logo, its own name/logo
  // replaces the LexProof wordmark in the sidebar (LexProof recedes to a
  // small "Powered by" line instead) -- a color-only customization keeps
  // the LexProof identity but still tints buttons/accents via BrandingRoot.
  const orgWordmark = branding?.logo_url ? currentOrg?.name || 'LexProof' : 'LexProof'
  const { theme, setTheme } = useTheme()
  const [adminOpen, setAdminOpen] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const displayName = me?.display_name || user?.displayName || me?.email || user?.email || 'Signed in'
  const email = me?.email || user?.email || ''
  const photoURL = user?.photoURL
  const adminChildActive = adminItems.some((item) => pathname.startsWith(item.href))

  useEffect(() => {
    if (isAdminRoute(pathname)) setAdminOpen(true)
  }, [pathname])

  // Close the mobile drawer whenever the route changes (a link click has
  // already navigated by the time this runs).
  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  useEffect(() => {
    function onDocumentClick(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDocumentClick)
    return () => document.removeEventListener('mousedown', onDocumentClick)
  }, [])

  async function signOut() {
    setMenuOpen(false)
    await logout()
    router.replace('/login')
  }

  return (
    <>
      {/* Mobile top bar: the sidebar itself is off-canvas below the lg
          breakpoint, so small screens need their own persistent header with
          a hamburger to open it as a slide-in drawer. */}
      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-4 dark:border-gray-700 dark:bg-gray-800 lg:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation menu"
          className="-ml-2 flex h-9 w-9 items-center justify-center rounded-[var(--radius-md,0.5rem)] text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary,#2563eb)] dark:text-gray-300 dark:hover:bg-gray-700"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          {branding?.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={branding.logo_url}
              alt={`${currentOrg?.name || 'Organization'} logo`}
              className="h-7 w-7 flex-shrink-0 rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white object-contain"
            />
          ) : (
            <div className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-md,0.5rem)] bg-[var(--brand-primary,#2563eb)]">
              <Shield className="h-4 w-4 text-white" />
            </div>
          )}
          <span className="text-base font-semibold text-gray-900 dark:text-gray-100">{orgWordmark}</span>
        </div>
        <NotificationBell />
      </header>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-gray-900/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      <nav
        aria-label="Primary"
        className={`fixed left-0 top-0 z-50 flex h-screen w-64 flex-col border-r border-gray-200 bg-white transition-transform duration-200 dark:border-gray-700 dark:bg-gray-800 lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <button
          type="button"
          onClick={() => setMobileOpen(false)}
          aria-label="Close navigation menu"
          className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-[var(--radius-md,0.5rem)] text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary,#2563eb)] dark:text-gray-500 dark:hover:bg-gray-700 dark:hover:text-gray-300 lg:hidden"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Brand + organization selector -- compacted from the previous
            px-6/py-8 to a tighter enterprise density, flat brand-color mark
            (no gradient) replacing the previous blue-to-blue gradient box. */}
        <div className="border-b border-gray-200 px-5 py-5 dark:border-gray-700">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2.5">
              {branding?.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={branding.logo_url}
                  alt={`${currentOrg?.name || 'Organization'} logo`}
                  className="h-9 w-9 flex-shrink-0 rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white object-contain"
                />
              ) : (
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[var(--radius-md,0.5rem)] bg-[var(--brand-primary,#2563eb)]">
                  <Shield className="h-5 w-5 text-white" />
                </div>
              )}
              <div className="min-w-0">
                <h1 className="truncate text-base font-semibold text-gray-900 dark:text-gray-100">{orgWordmark}</h1>
                <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                  {branding?.logo_url ? 'Powered by LexProof' : 'Verifiable Intelligence'}
                </p>
              </div>
            </div>
            <NotificationBell />
          </div>
          <label className="mt-3.5 block text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Organization
            {loading && orgs.length === 0 ? (
              <Skeleton className="mt-1.5 h-8 w-full" />
            ) : (
              <select
                value={currentOrg?.org_id || ''}
                onChange={(event) => selectOrg(event.target.value)}
                className="mt-1.5 w-full rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-2.5 py-1.5 text-sm font-normal text-gray-800 transition-colors focus:border-[var(--brand-primary,#2563eb)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary,#3b82f6)] disabled:cursor-not-allowed disabled:bg-gray-50 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                disabled={orgs.length === 0}
              >
                {orgs.length === 0 && <option value="">No organization</option>}
                {orgs.map((org) => (
                  <option key={org.org_id} value={org.org_id}>
                    {org.name || org.org_id}
                  </option>
                ))}
              </select>
            )}
          </label>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-5">
          <button
            type="button"
            data-tour="quick-search"
            onClick={() => window.dispatchEvent(new CustomEvent('lexproof:open-command-palette'))}
            className="mb-4 flex w-full items-center gap-2.5 rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-gray-50 px-3 py-2 text-left text-gray-500 transition-colors hover:border-gray-300 hover:bg-gray-100 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary,#2563eb)] dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:border-gray-600 dark:hover:text-gray-200"
          >
            <Search className="h-4 w-4 flex-shrink-0" />
            <span className="flex-1 text-sm">Quick search</span>
            <kbd className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-gray-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400">
              ⌘K
            </kbd>
          </button>

          <div className="space-y-5">
            {NAV_GROUPS.map((group) => {
              const items = group.hrefs
                .map((href) => navigationItems.find((item) => item.href === href))
                .filter((item) => !item || !('roles' in item) || canAccessEvaluation(roles))
                .filter((item): item is (typeof navigationItems)[number] => Boolean(item))
              const groupHeadingId = `nav-group-${group.title.toLowerCase().replace(/\s+/g, '-')}`

              return (
                <div key={group.title}>
                  <h2
                    id={groupHeadingId}
                    className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500"
                  >
                    {group.title}
                  </h2>
                  <div role="group" aria-labelledby={groupHeadingId} className="space-y-0.5">
                    {items.map((item) => {
                      const Icon = item.icon
                      const isActive = isActivePath(pathname, item.href, 'exact' in item ? item.exact : undefined)
                      const isAi = 'accent' in item && item.accent === 'ai'
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          data-tour={NAV_TOUR_IDS[item.href]}
                          aria-current={isActive ? 'page' : undefined}
                          className={navLinkClassName({ active: isActive })}
                        >
                          {isAi ? (
                            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-[var(--radius-sm,0.25rem)] bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300">
                              <Icon className={NAV_ICON} />
                            </span>
                          ) : (
                            <Icon className={NAV_ICON} />
                          )}
                          <span>{item.label}</span>
                        </Link>
                      )
                    })}

                    {group.title === 'Administration' && !loading && isAdmin && (
                      <div className="pt-0.5">
                        <button
                          type="button"
                          onClick={() => setAdminOpen((open) => !open)}
                          className={`flex w-full items-center justify-between gap-3 rounded-[var(--radius-md,0.5rem)] px-3 py-2 text-left text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary,#2563eb)] focus-visible:ring-offset-1 ${
                            adminChildActive
                              ? 'bg-[color-mix(in_srgb,var(--brand-primary,#2563eb)_8%,white)] text-[var(--brand-primary,#1d4ed8)] dark:bg-blue-950 dark:text-blue-300'
                              : 'text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700/60'
                          }`}
                          aria-expanded={adminOpen}
                        >
                          <span className="flex items-center gap-3">
                            <Settings className={NAV_ICON} />
                            <span>Administration</span>
                          </span>
                          <ChevronDown className={`h-4 w-4 transition-transform ${adminOpen ? 'rotate-180' : ''}`} />
                        </button>
                        {adminOpen && (
                          <div className="mt-0.5 space-y-0.5">
                            {adminItems.map((item) => {
                              const Icon = item.icon
                              const isActive = pathname.startsWith(item.href)
                              return (
                                <Link
                                  key={item.href}
                                  href={item.href}
                                  aria-current={isActive ? 'page' : undefined}
                                  className={navLinkClassName({ active: isActive, nested: true })}
                                >
                                  <Icon className={NAV_ICON} />
                                  <span>{item.label}</span>
                                </Link>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}

            {!loading && (
              <div className="border-t border-gray-200 pt-3 dark:border-gray-700">
                <Link
                  href="/dashboard/why-lexproof"
                  aria-current={pathname.startsWith('/dashboard/why-lexproof') ? 'page' : undefined}
                  className={navLinkClassName({
                    active: isActivePath(pathname, '/dashboard/why-lexproof'),
                  })}
                >
                  <Rocket className={NAV_ICON} />
                  <span>Why LexProof?</span>
                </Link>
              </div>
            )}
          </div>
        </div>

        <div className="border-t border-gray-200 px-4 py-4 dark:border-gray-700">
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              data-tour="account-menu"
              onClick={() => setMenuOpen((open) => !open)}
              className="flex w-full items-center gap-3 rounded-[var(--radius-md,0.5rem)] p-1 text-left hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary,#2563eb)] dark:hover:bg-gray-700"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              {photoURL ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={photoURL} alt="" className="h-9 w-9 flex-shrink-0 rounded-full object-cover" />
              ) : (
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-blue-800 dark:bg-blue-950 dark:text-blue-300">
                  {displayName.slice(0, 1).toUpperCase()}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">{displayName}</p>
                {email && <p className="truncate text-xs text-gray-500 dark:text-gray-400">{email}</p>}
              </div>
              <ChevronDown className={`h-4 w-4 flex-shrink-0 text-gray-400 transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute bottom-full left-0 right-0 mb-2 rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white py-1 shadow-[var(--shadow-md)] dark:border-gray-700 dark:bg-gray-800"
              >
                <div className="px-3 py-2">
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Theme</p>
                  <div className="flex gap-1 rounded-[var(--radius-md,0.5rem)] bg-gray-100 p-1 dark:bg-gray-900">
                    {THEME_OPTIONS.map(({ value, label, icon: ThemeIcon }) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => setTheme(value)}
                        aria-pressed={theme === value}
                        className={`flex flex-1 flex-col items-center gap-0.5 rounded-[var(--radius-sm,0.25rem)] py-1.5 text-[10px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary,#2563eb)] ${
                          theme === value
                            ? 'bg-white text-[var(--brand-primary,#1d4ed8)] shadow-[var(--shadow-xs)] dark:bg-gray-700 dark:text-blue-300'
                            : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                        }`}
                      >
                        <ThemeIcon className="h-3.5 w-3.5" />
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="my-1 border-t border-gray-100 dark:border-gray-700" />
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false)
                    window.dispatchEvent(new CustomEvent('lexproof:start-tour'))
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--brand-primary,#2563eb)] dark:text-gray-200 dark:hover:bg-gray-700"
                >
                  <Compass className="h-4 w-4" />
                  Take the tour
                </button>
                <Link href="/dashboard/settings/notifications" onClick={() => setMenuOpen(false)}>
                  <div
                    role="menuitem"
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
                  >
                    <Bell className="h-4 w-4" />
                    Notification preferences
                  </div>
                </Link>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => void signOut()}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-red-50 hover:text-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-red-500 dark:text-gray-200 dark:hover:bg-red-950 dark:hover:text-red-400"
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            )}
          </div>
          <p className="mt-3 text-center text-[10px] text-gray-400 dark:text-gray-600">LexProof v1.0</p>
        </div>
      </nav>
    </>
  )
}
