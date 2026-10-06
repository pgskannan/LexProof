"use client"

import { FormEvent, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "../../components/AuthProvider"
import { loginWithEmailPassword, mapFirebaseAuthError } from "../../lib/auth"

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")

  async function handleGoogleLogin() {
    setLoading(true); setError("")
    try {
      const mode = await login()
      if (mode !== "redirect") router.replace("/dashboard")
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to sign in") }
    finally { setLoading(false) }
  }

  async function handleEmailLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return
    setLoading(true); setError("")
    try {
      await loginWithEmailPassword(email, password)
      router.replace("/dashboard")
    } catch (cause) {
      setError(mapFirebaseAuthError(cause))
    } finally {
      setLoading(false)
    }
  }

  return <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-gray-50 p-6"><a href="/" className="text-sm font-medium text-gray-500 hover:text-gray-800">← Back to home</a><section className="w-full max-w-md rounded-lg bg-white p-8 shadow"><h1 className="text-3xl font-bold text-gray-900">LexProof</h1><p className="mt-2 text-gray-600">Sign in to analyze and prove your contracts.</p><button type="button" onClick={handleGoogleLogin} disabled={loading} className="mt-8 w-full rounded bg-blue-600 px-4 py-3 font-medium text-white disabled:opacity-50">{loading ? "Signing in..." : "Continue with Google"}</button><div className="mt-6 flex items-center gap-3 text-xs font-medium uppercase tracking-wide text-gray-400"><span className="h-px flex-1 bg-gray-200" aria-hidden="true" />Or<span className="h-px flex-1 bg-gray-200" aria-hidden="true" /></div><form className="mt-6 space-y-4" onSubmit={handleEmailLogin} noValidate><div><label htmlFor="email" className="block text-sm font-medium text-gray-700">Email</label><input id="email" name="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} disabled={loading} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 disabled:opacity-50" /></div><div><label htmlFor="password" className="block text-sm font-medium text-gray-700">Password</label><input id="password" name="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} disabled={loading} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 disabled:opacity-50" /></div><button type="submit" disabled={loading} className="w-full rounded border border-blue-600 px-4 py-3 font-medium text-blue-600 disabled:opacity-50">{loading ? "Signing in..." : "Sign in"}</button></form>{error && <p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}<p className="mt-8 border-t border-gray-100 pt-4 text-center text-sm text-gray-600">No account? <a href="/request-trial" className="font-medium text-blue-600 hover:underline">Request a trial</a> or <a href="/public-verify/tamper" className="font-medium text-blue-600 hover:underline">try the live Tamper Test</a>, no login needed.</p></section></main>
}
