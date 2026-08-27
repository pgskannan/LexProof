"use client"

import { onAuthStateChanged, User } from "firebase/auth"
import { usePathname, useRouter } from "next/navigation"
import { createContext, useContext, useEffect, useState } from "react"
import { auth, login, logout } from "../lib/auth"

type AuthContextValue = { user: User | null; loading: boolean; login: typeof login; logout: typeof logout }
const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const pathname = usePathname()
  const router = useRouter()
  const isPublicRoute = pathname === "/login" || pathname === "/public-verify"

  useEffect(() => onAuthStateChanged(auth, currentUser => {
    setUser(currentUser)
    setLoading(false)
    if (!currentUser && !isPublicRoute) router.replace("/login")
  }), [isPublicRoute, pathname, router])

  if (loading) return <main className="flex min-h-screen items-center justify-center">Loading...</main>
  if (!user && !isPublicRoute) return null
  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within AuthProvider")
  return context
}