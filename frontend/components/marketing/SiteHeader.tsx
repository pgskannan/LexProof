"use client"

import { ShieldCheck } from "lucide-react"
import { useAuth } from "../AuthProvider"

const NAV = [
  { href: "/#capabilities", label: "Capabilities" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#who", label: "Who it's for" },
  { href: "/public-verify/tamper", label: "Tamper Test" },
  { href: "/public-verify", label: "Verify evidence" },
]

/** Public site header: brand on the left, Sign in + Request a trial on the right. */
export function SiteHeader() {
  const { user } = useAuth()
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <a href="/" className="flex items-center gap-2" aria-label="LexProof home">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white"><ShieldCheck className="h-5 w-5" aria-hidden /></span>
          <span className="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">LexProof</span>
        </a>
        <nav aria-label="Main" className="hidden items-center gap-6 text-sm font-medium text-slate-600 lg:flex dark:text-slate-300">
          {NAV.map((item) => (
            <a key={item.href} href={item.href} className="text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white">{item.label}</a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          {user ? (
            <a href="/dashboard" className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Open dashboard</a>
          ) : (
            <>
              <a href="/login" className="rounded-lg px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">Sign in</a>
              <a href="/request-demo" className="hidden rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 sm:inline-block dark:border-slate-700 dark:text-slate-100 dark:hover:bg-slate-800">Book a demo</a>
              <a href="/request-trial" className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Request a trial</a>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
