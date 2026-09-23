import { auth, getAuthState, AUTH_INITIALIZING, waitForAuthReady } from "./auth"
import { getCurrentOrgId } from "./orgStore"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""

export function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  if (getAuthState() === AUTH_INITIALIZING) {
    await waitForAuthReady()
  }

  const user = auth.currentUser
  const token = user ? await user.getIdToken() : null
  const headers = new Headers(init?.headers)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  const orgId = getCurrentOrgId()
  if (orgId && !headers.has("X-Org-Id")) headers.set("X-Org-Id", orgId)
  return fetch(apiUrl(path), { ...init, headers })
}
