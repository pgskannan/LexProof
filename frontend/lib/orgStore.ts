const STORAGE_KEY = 'lexproof.org_id'

let currentOrgId: string | null = null

export function getCurrentOrgId(): string | null {
  if (currentOrgId) return currentOrgId
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(STORAGE_KEY)
}

export function setCurrentOrgId(orgId: string | null): void {
  currentOrgId = orgId
  if (typeof window === 'undefined') return
  if (orgId) window.localStorage.setItem(STORAGE_KEY, orgId)
  else window.localStorage.removeItem(STORAGE_KEY)
}
