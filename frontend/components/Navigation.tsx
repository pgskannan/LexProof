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
  ChevronDown,
  LogOut,
  Search,
  History,
  SlidersHorizontal,
} from 'lucide-react'
import { useOrg } from './OrgProvider'
import { useAuth } from './AuthProvider'
import { Skeleton } from './ui/skeleton'
import { NotificationBell } from './NotificationBell'

const navigationItems = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, exact: true },
  { label: 'Search', href: '/dashboard/search', icon: Search },
  { label: 'Contracts', href: '/dashboard/contracts', icon: FileText },
  { label: 'Findings & Redlines', href: '/dashboard/ai-analysis/findings', icon: ListChecks },
  { label: 'Ask Your Contracts', href: '/dashboard/ask', icon: MessageSquare },
  { label: 'Contract Reviews', href: '/dashboard/contracts/reviews', icon: GitPullRequest },
  { label: 'Legal Passport', href: '/legal-passport', icon: Shield },
  { label: 'Blockchain Proof', href: '/dashboard/blockchain-proof', icon: Anchor },
  { label: 'Compliance', href: '/dashboard/compliance', icon: CheckCircle2 },
  { label: 'Verification', href: '/dashboard/verification', icon: Eye },
  { label: 'Reports', href: '/dashboard/reports', icon: BarChart3 },
]

const adminItems = [
  { label: 'Overview', href: '/dashboard/administration', icon: Settings },
  { label: 'Members', href: '/dashboard/admin/members', icon: Users },
  { label: 'Workflows', href: '/dashboard/admin/workflows', icon: Workflow },
  { label: 'Audit Log', href: '/dashboard/admin/audit-log', icon: History },
  { label: 'Settings', href: '/dashboard/admin/settings', icon: SlidersHorizontal },
]

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

export function Navigation() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout } = useAuth()
  const { isAdmin, currentOrg, orgs, selectOrg, loading, me } = useOrg()
  const [adminOpen, setAdminOpen] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const displayName = me?.display_name || user?.displayName || me?.email || user?.email || 'Signed in'
  const email = me?.email || user?.email || ''
  const photoURL = user?.photoURL
  const adminChildActive = adminItems.some((item) => pathname.startsWith(item.href))

  useEffect(() => {
    if (isAdminRoute(pathname)) setAdminOpen(true)
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
    <nav className="fixed left-0 top-0 h-screen w-64 bg-white border-r border-gray-200 shadow-sm flex flex-col">
      <div className="px-6 py-8 border-b border-gray-200">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-gray-900">LexProof</h1>
              <p className="text-xs text-gray-500">Verifiable Intelligence</p>
            </div>
          </div>
          <NotificationBell />
        </div>
        <label className="mt-4 block text-xs font-semibold uppercase tracking-wide text-gray-500">
          Organization
          {loading && orgs.length === 0 ? (
            <Skeleton className="mt-1 h-8 w-full" />
          ) : (
            <select
              value={currentOrg?.org_id || ''}
              onChange={(event) => selectOrg(event.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm font-normal text-gray-800"
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

      <div className="flex-1 overflow-y-auto px-3 py-6">
        <div className="space-y-1">
          {navigationItems.map((item) => {
            const Icon = item.icon
            const isActive = isActivePath(pathname, item.href, item.exact)
            return (
              <Link key={item.href} href={item.href}>
                <div
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 border-l-4 border-blue-600'
                      : 'text-gray-600 hover:bg-gray-50 border-l-4 border-transparent'
                  }`}
                >
                  <Icon className="w-5 h-5 flex-shrink-0" />
                  <span className="text-sm font-medium">{item.label}</span>
                </div>
              </Link>
            )
          })}
          {!loading && isAdmin && (
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setAdminOpen((open) => !open)}
                className={`flex w-full items-center justify-between gap-3 rounded-lg px-4 py-3 text-left ${
                  adminChildActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
                aria-expanded={adminOpen}
              >
                <span className="flex items-center gap-3">
                  <Settings className="h-5 w-5 flex-shrink-0" />
                  <span className="text-sm font-medium">Administration</span>
                </span>
                <ChevronDown className={`h-4 w-4 transition-transform ${adminOpen ? 'rotate-180' : ''}`} />
              </button>
              {adminOpen &&
                adminItems.map((item) => {
                  const Icon = item.icon
                  const isActive = pathname.startsWith(item.href)
                  return (
                    <Link key={item.href} href={item.href}>
                      <div
                        className={`ml-4 flex items-center gap-3 rounded-lg px-4 py-2.5 transition-all duration-200 ${
                          isActive
                            ? 'bg-blue-50 text-blue-700 border-l-4 border-blue-600'
                            : 'text-gray-600 hover:bg-gray-50 border-l-4 border-transparent'
                        }`}
                      >
                        <Icon className="h-4 w-4 flex-shrink-0" />
                        <span className="text-sm font-medium">{item.label}</span>
                      </div>
                    </Link>
                  )
                })}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-gray-200 px-4 py-4">
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="flex w-full items-center gap-3 rounded-lg p-1 text-left hover:bg-gray-50"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            {photoURL ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={photoURL} alt="" className="h-9 w-9 flex-shrink-0 rounded-full object-cover" />
            ) : (
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-blue-800">
                {displayName.slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-gray-900">{displayName}</p>
              {email && <p className="truncate text-xs text-gray-500">{email}</p>}
            </div>
            <ChevronDown className={`h-4 w-4 flex-shrink-0 text-gray-400 transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
          </button>
          {menuOpen && (
            <div
              role="menu"
              className="absolute bottom-full left-0 right-0 mb-2 rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => void signOut()}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-red-50 hover:text-red-700"
              >
                <LogOut className="h-4 w-4" />
                Sign out
              </button>
            </div>
          )}
        </div>
        <p className="mt-3 text-center text-[10px] text-gray-400">LexProof v1.0</p>
      </div>
    </nav>
  )
}
