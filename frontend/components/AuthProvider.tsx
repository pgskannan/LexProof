"use client"

import { onAuthStateChanged, User } from "firebase/auth"
import { usePathname, useRouter } from "next/navigation"
import { createContext, useContext, useEffect, useState } from "react"
import { auth, login, logout } from "../lib/auth"
import { isPublicPath } from "../lib/publicRoutes"
import { Skeleton } from "./ui/skeleton"

type AuthContextValue = { user: User | null; loading: boolean; login: typeof login; logout: typeof logout }
const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const pathname = usePathname()
  const router = useRouter()
  const isPublicRoute = isPublicPath(pathname)

  useEffect(() => onAuthStateChanged(auth, currentUser => {
    setUser(currentUser)
    setLoading(false)
    if (!currentUser && !isPublicRoute) router.replace("/login")
  }), [isPublicRoute, pathname, router])

  if (loading) {
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
  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within AuthProvider")
  return context
}
