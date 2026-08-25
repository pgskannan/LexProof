"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "../../components/AuthProvider"

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleLogin() {
    setLoading(true); setError("")
    try { await login(); router.replace("/dashboard") }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to sign in") }
    finally { setLoading(false) }
  }

  return <main className="flex min-h-screen items-center justify-center bg-gray-50 p-6"><section className="w-full max-w-md rounded-lg bg-white p-8 shadow"><h1 className="text-3xl font-bold text-gray-900">LexProof</h1><p className="mt-2 text-gray-600">Sign in to analyze and prove your contracts.</p><button onClick={handleLogin} disabled={loading} className="mt-8 w-full rounded bg-blue-600 px-4 py-3 font-medium text-white disabled:opacity-50">{loading ? "Signing in..." : "Continue with Google"}</button>{error && <p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}</section></main>
}