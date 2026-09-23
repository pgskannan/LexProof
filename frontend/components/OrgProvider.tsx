'use client'

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { OrgBranding } from '../lib/branding'
import type { MeResponse, OrgMembership } from '../lib/org'
import { getCurrentOrgId, setCurrentOrgId } from '../lib/orgStore'
import { isAdmin } from '../lib/roles'
import { AUTHENTICATED } from '../lib/auth'
import { useAuth } from './AuthProvider'

type OrgContextValue = {
  loading: boolean
  me: MeResponse | null
  orgs: OrgMembership[]
  currentOrg: OrgMembership | null
  roles: string[]
  isAdmin: boolean
  branding: OrgBranding | null
  selectOrg: (orgId: string) => void
  refresh: () => Promise<void>
  refreshBranding: () => Promise<void>
}

const OrgContext = createContext<OrgContextValue | null>(null)

export function OrgProvider({ children }: { children: React.ReactNode }) {
  const { user, authState } = useAuth()
  const [me, setMe] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [orgId, setOrgId] = useState<string | null>(getCurrentOrgId())
  const [branding, setBranding] = useState<OrgBranding | null>(null)

  async function refresh() {
    if (!user || authState !== AUTHENTICATED) {
      setMe(null)
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const response = await apiFetch('/api/me')
      if (!response.ok) throw new Error('Unable to load organization membership')
      const profile: MeResponse = await response.json()
      setMe(profile)
      const stored = getCurrentOrgId()
      const next = profile.orgs.find((org) => org.org_id === stored)?.org_id || profile.orgs[0]?.org_id || null
      setCurrentOrgId(next)
      setOrgId(next)
    } catch {
      setMe(null)
    } finally {
      setLoading(false)
    }
  }

  const currentOrg = useMemo(
    () => me?.orgs.find((org) => org.org_id === orgId) || me?.orgs[0] || null,
    [me, orgId],
  )
  const roles = currentOrg?.roles || []

  // White-label branding (Task #109) lives in org settings, not the
  // lightweight /api/me membership payload, so it's fetched separately
  // whenever the selected org changes. Any active member can read
  // settings (see api/organizations.py's get_org_settings), so this needs
  // no permission beyond already being a signed-in member.
  async function loadBranding(id: string | null) {
    if (!id) {
      setBranding(null)
      return
    }
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(id)}/settings`)
      if (!response.ok) {
        setBranding(null)
        return
      }
      const body: { logo_url?: string | null; primary_color?: string | null } = await response.json()
      setBranding({ logo_url: body.logo_url ?? null, primary_color: body.primary_color ?? null })
    } catch {
      setBranding(null)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.uid])

  useEffect(() => {
    void loadBranding(currentOrg?.org_id || null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentOrg?.org_id])

  function selectOrg(nextOrgId: string) {
    setCurrentOrgId(nextOrgId)
    setOrgId(nextOrgId)
  }

  return (
    <OrgContext.Provider
      value={{
        loading,
        me,
        orgs: me?.orgs || [],
        currentOrg,
        roles,
        isAdmin: isAdmin(roles),
        branding,
        selectOrg,
        refresh,
        refreshBranding: () => loadBranding(currentOrg?.org_id || null),
      }}
    >
      {children}
    </OrgContext.Provider>
  )
}

export function useOrg() {
  const context = useContext(OrgContext)
  if (!context) throw new Error('useOrg must be used within OrgProvider')
  return context
}
