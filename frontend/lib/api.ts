import { auth } from "./auth"
import { onAuthStateChanged, User } from "firebase/auth"
import { getCurrentOrgId } from "./orgStore"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""
const AUTH_WAIT_TIMEOUT_MS = 5000

export function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`
}

function waitForCurrentUser(): Promise<User | null> {
  if (auth.currentUser) return Promise.resolve(auth.currentUser)
  return new Promise(resolve => {
    let settled = false
    const unsubscribe = onAuthStateChanged(auth, user => {
      if (settled) return
      settled = true
      unsubscribe()
      resolve(user)
    })
    // Defensive timeout: onAuthStateChanged should fire promptly with the
    // current auth state, but if it never fires (stale listener, duplicate
    // app instance, long-lived tab) this call must not hang forever with a
    // silent, un-cancellable spinner. Fall back to whatever auth.currentUser
    // reads at that point (possibly null) so the caller gets a response.
    setTimeout(() => {
      if (settled) return
      settled = true
      unsubscribe()
      resolve(auth.currentUser)
    }, AUTH_WAIT_TIMEOUT_MS)
  })
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const user = await waitForCurrentUser()
  const token = user ? await user.getIdToken() : null
  const headers = new Headers(init?.headers)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  const orgId = getCurrentOrgId()
  if (orgId && !headers.has("X-Org-Id")) headers.set("X-Org-Id", orgId)
  return fetch(apiUrl(path), { ...init, headers })
}
