"use client"

import { onAuthStateChanged, User } from "firebase/auth"
import { usePathname, useRouter } from "next/navigation"
import { createContext, useContext, useEffect, useMemo, useState } from "react"
import { auth, AUTHENTICATED, AUTH_INITIALIZING, login, logout, setAuthState, type AuthState, UNAUTHENTICATED } from "../lib/auth"
import { isPublicPath } from "../lib/publicRoutes"
import { Skeleton } from "./ui/skeleton"

type AuthContextValue = { user: User | null; authState: AuthState; loading: boolean; login: typeof login; logout: typeof logout }
const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [authState, setAuthStatus] = useState<AuthState>(AUTH_INITIALIZING)
  const [loading, setLoading] = useState(true)
  const pathname = usePathname()
  const router = useRouter()
  const isPublicRoute = isPublicPath(pathname)

  useEffect(() => onAuthStateChanged(auth, currentUser => {
    const nextAuthState = currentUser ? AUTHENTICATED : UNAUTHENTICATED
    setAuthState(nextAuthState)
    setAuthStatus(nextAuthState)
    setUser(currentUser)
    setLoading(false)
    if (!currentUser && !isPublicRoute) router.replace("/login")
  }), [isPublicRoute, pathname, router])

  const value = useMemo(() => ({ user, authState, loading, login, logout }), [authState, loading, user])

  if (authState === AUTH_INITIALIZING || loading) {
    return (
      <div className="flex min-h-screen bg-gray-50">
        <div className="w-64 space-y-4 border-r border-gray-200 bg-white p-6">
          <Skeleton className="h-10 w-36" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
        <div className="flex-1 space-y-4 p-8">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    )
  }
  if (!user && !isPublicRoute) return null
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within AuthProvider")
  return context
}
