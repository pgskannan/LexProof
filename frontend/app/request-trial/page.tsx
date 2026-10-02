"use client"

import { CheckCircle2 } from "lucide-react"
import { FormEvent, useState } from "react"
import { SiteFooter } from "../../components/marketing/SiteFooter"
import { SiteHeader } from "../../components/marketing/SiteHeader"
import { apiUrl } from "../../lib/api"

const ROLES = [
  { value: "procurement", label: "Procurement / source-to-pay" },
  { value: "legal", label: "Legal / legal operations" },
  { value: "compliance_audit", label: "Compliance / internal audit" },
  { value: "executive", label: "Executive" },
  { value: "it_security", label: "IT / security" },
  { value: "other", label: "Other" },
]
const TEAM_SIZES = ["1-10", "11-50", "51-200", "201-1000", "1000+"]

const input = "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
const label = "block text-sm font-medium text-slate-700 dark:text-slate-300"

export default function RequestTrialPage() {
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    const form = new FormData(event.currentTarget)
    const body = {
      full_name: String(form.get("full_name") || ""),
      work_email: String(form.get("work_email") || ""),
      company: String(form.get("company") || ""),
      role: String(form.get("role") || ""),
      team_size: String(form.get("team_size") || "") || null,
      use_case: String(form.get("use_case") || "") || null,
      consent: form.get("consent") === "on",
      website: String(form.get("website") || ""),
    }
    setSubmitting(true)
    setError("")
    try {
      const response = await fetch(apiUrl("/api/public/trial-requests"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        const detail = (await response.json().catch(() => null))?.detail
        const message = Array.isArray(detail) ? detail.map((item: { msg?: string }) => item.msg?.replace(/^Value error, /, "")).filter(Boolean).join(" ") : detail
        throw new Error(message || "We couldn't send your request. Please try again.")
      }
      setDone(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "We couldn't send your request. Please try again.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <SiteHeader />
      <main className="mx-auto grid max-w-6xl gap-12 px-4 py-14 sm:px-6 lg:grid-cols-[1fr_1.2fr]">
        <section>
          <p className="text-sm font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">Request a trial</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">See LexProof on your own contracts</h1>
          <p className="mt-4 leading-relaxed text-slate-600 dark:text-slate-300">
            We&apos;re onboarding a small number of legal and procurement teams as design partners. Tell us a little about your team and we&apos;ll set up a private workspace.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-slate-700 dark:text-slate-300">
            {[
              "A private workspace for your organization",
              "AI review, human approval and Legal Passports on your contracts",
              "Independent verification your auditors can run themselves",
              "A walkthrough with the founder",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2.5"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />{item}</li>
            ))}
          </ul>
          <p className="mt-8 text-sm text-slate-500 dark:text-slate-400">
            Just want to look around? <a href="/public-verify/tamper" className="font-medium text-blue-600 hover:underline dark:text-blue-400">Try the live Tamper Test</a>, no account needed.
          </p>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8 dark:border-slate-800 dark:bg-slate-900">
          {done ? (
            <div role="status" className="py-10 text-center">
              <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-600" aria-hidden />
              <h2 className="mt-4 text-xl font-semibold">Thanks, your request is in</h2>
              <p className="mt-2 text-slate-600 dark:text-slate-300">We&apos;ll be in touch at the email you gave us, usually within two business days.</p>
              <a href="/" className="mt-6 inline-block text-sm font-semibold text-blue-600 hover:underline dark:text-blue-400">Back to home</a>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5" noValidate={false}>
              <div className="grid gap-5 sm:grid-cols-2">
                <div><label htmlFor="full_name" className={label}>Full name</label><input id="full_name" name="full_name" required minLength={2} maxLength={120} autoComplete="name" className={input} /></div>
                <div><label htmlFor="work_email" className={label}>Work email</label><input id="work_email" name="work_email" type="email" required maxLength={254} autoComplete="email" className={input} /></div>
              </div>
              <div><label htmlFor="company" className={label}>Company</label><input id="company" name="company" required minLength={2} maxLength={160} autoComplete="organization" className={input} /></div>
              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <label htmlFor="role" className={label}>Your role</label>
                  <select id="role" name="role" required defaultValue="" className={input}>
                    <option value="" disabled>Select…</option>
                    {ROLES.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="team_size" className={label}>Team size <span className="font-normal text-slate-400">(optional)</span></label>
                  <select id="team_size" name="team_size" defaultValue="" className={input}>
                    <option value="">Select…</option>
                    {TEAM_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label htmlFor="use_case" className={label}>What would you like to use LexProof for? <span className="font-normal text-slate-400">(optional)</span></label>
                <textarea id="use_case" name="use_case" rows={4} maxLength={2000} placeholder="For example: supplier MSAs, DPAs, audit readiness…" className={input} />
              </div>
              {/* Honeypot: hidden from people, filled in by bots. */}
              <div aria-hidden="true" className="hidden">
                <label htmlFor="website">Website</label><input id="website" name="website" tabIndex={-1} autoComplete="off" />
              </div>
              <label className="flex items-start gap-2.5 text-sm text-slate-600 dark:text-slate-300">
                <input type="checkbox" name="consent" required className="mt-0.5 h-4 w-4 rounded border-slate-300" />
                <span>I agree to be contacted about this trial. We use your details only to respond to this request.</span>
              </label>
              {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}
              <button type="submit" disabled={submitting} className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
                {submitting ? "Sending…" : "Request a trial"}
              </button>
              <p className="text-center text-sm text-slate-500 dark:text-slate-400">Already have an account? <a href="/login" className="font-medium text-blue-600 hover:underline dark:text-blue-400">Sign in</a></p>
            </form>
          )}
        </section>
      </main>
      <SiteFooter />
    </div>
  )
}
