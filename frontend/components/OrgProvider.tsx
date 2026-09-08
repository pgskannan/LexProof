'use client'

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { MeResponse, OrgMembership } from '../lib/org'
import { getCurrentOrgId, setCurrentOrgId } from '../lib/orgStore'
import { isAdmin } from '../lib/roles'
import { useAuth } from './AuthProvider'

type OrgContextValue = {
  loading: boolean
  me: MeResponse | null
  orgs: OrgMembership[]
  currentOrg: OrgMembership | null
  roles: string[]
  isAdmin: boolean
  selectOrg: (orgId: string) => void
  refresh: () => Promise<void>
}

const OrgContext = createContext<OrgContextValue | null>(null)

export function OrgProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const [me, setMe] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [orgId, setOrgId] = useState<string | null>(getCurrentOrgId())

  async function refresh() {
    if (!user) {
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

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.uid])

  const currentOrg = useMemo(
    () => me?.orgs.find((org) => org.org_id === orgId) || me?.orgs[0] || null,
    [me, orgId],
  )
  const roles = currentOrg?.roles || []

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
        selectOrg,
        refresh,
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
