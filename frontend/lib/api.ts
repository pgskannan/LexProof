import { auth } from "./auth"
import { onAuthStateChanged, User } from "firebase/auth"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ""

export function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`
}

function waitForCurrentUser(): Promise<User | null> {
  if (auth.currentUser) return Promise.resolve(auth.currentUser)
  return new Promise(resolve => {
    const unsubscribe = onAuthStateChanged(auth, user => {
      unsubscribe()
      resolve(user)
    })
  })
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const user = await waitForCurrentUser()
  const token = user ? await user.getIdToken() : null
  const headers = new Headers(init?.headers)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  return fetch(apiUrl(path), { ...init, headers })
}