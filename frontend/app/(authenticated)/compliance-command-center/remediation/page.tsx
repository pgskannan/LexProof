"use client"

import { FormEvent, useState } from "react"

type Proposal = {
  id: string
  contract_id: string
  affected_clause: string
  current_language: string
  regulatory_requirement: string
  proposed_amendment: string
  explanation: string
}

type Result = {
  before: { risk: string; compliance: string }
  after: { risk: string; compliance: string }
  passport: { version: number; proof_status: string; document_hash: string }
  previous_proof_preserved: boolean
}

export default function RemediationPage() {
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const [approvedBy, setApprovedBy] = useState("")
  const [error, setError] = useState("")

  async function createProposal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    const form = new FormData(event.currentTarget)
    const response = await fetch("/api/compliance/remediation/proposals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(form)),
    })
    if (!response.ok) return setError("Unable to generate proposal")
    setProposal(await response.json())
  }

  async function decide(approved: boolean) {
    if (!proposal || !approvedBy.trim()) return setError("Reviewer name is required")
    const response = await fetch(`/api/compliance/remediation/proposals/${proposal.id}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved, approved_by: approvedBy }),
    })
    if (!response.ok) return setError("Unable to record decision")
    setResult(await response.json())
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <section className="mx-auto max-w-5xl">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">LexProof / remediation</p>
        <h1 className="mt-3 text-4xl font-semibold">AI amendment review</h1>
        <p className="mt-3 max-w-2xl text-slate-400">Generate language for counsel. Nothing is published until a named human reviewer approves it.</p>

        {!proposal && (
          <form onSubmit={createProposal} className="mt-10 grid gap-4 rounded-xl border border-slate-800 bg-slate-900 p-6">
            <input name="event_id" placeholder="Monitoring event ID" required className="field" />
            <input name="contract_id" placeholder="Contract ID" required className="field" />
            <input name="jurisdiction" placeholder="Jurisdiction" required className="field" />
            <input name="affected_clause" placeholder="Affected clause" required className="field" />
            <textarea name="current_language" placeholder="Current language" required className="field min-h-28" />
            <textarea name="regulatory_requirement" placeholder="Regulatory or policy requirement" required className="field min-h-28" />
            <input name="amendment_reason" placeholder="Why is this amendment needed?" required className="field" />
            <button className="rounded-md bg-cyan-300 px-4 py-3 font-semibold text-slate-950">Generate proposal</button>
          </form>
        )}

        {proposal && !result && (
          <div className="mt-10 space-y-5">
            <div className="grid gap-5 md:grid-cols-3">
              <article className="panel md:col-span-2"><h2>Affected clause</h2><p>{proposal.affected_clause}</p><h3>Current language</h3><p>{proposal.current_language}</p><h3>Requirement</h3><p>{proposal.regulatory_requirement}</p></article>
              <article className="panel"><h2>Gemini proposal</h2><p>{proposal.proposed_amendment}</p><h3>Explanation</h3><p>{proposal.explanation}</p></article>
            </div>
            <div className="panel flex flex-wrap items-center gap-3"><input value={approvedBy} onChange={(e) => setApprovedBy(e.target.value)} placeholder="Reviewer name" className="field flex-1" /><button onClick={() => decide(false)} className="rounded-md border border-rose-400 px-4 py-3 text-rose-300">Reject</button><button onClick={() => decide(true)} className="rounded-md bg-emerald-300 px-4 py-3 font-semibold text-slate-950">Approve and re-proof</button></div>
          </div>
        )}

        {result && <div className="mt-10 grid gap-5 md:grid-cols-3"><article className="panel"><h2>Before</h2><p>Risk: <b>{result.before.risk}</b></p><p>Compliance: <b>{result.before.compliance}</b></p></article><article className="panel"><h2>After</h2><p>Risk: <b>{result.after.risk}</b></p><p>Compliance: <b>{result.after.compliance}</b></p></article><article className="panel"><h2>Blockchain proof</h2><p className="text-emerald-300">{result.passport.proof_status}</p><p>Passport version {result.passport.version}</p><p>Previous proof preserved: {String(result.previous_proof_preserved)}</p></article></div>}
        {error && <p className="mt-5 text-rose-300">{error}</p>}
      </section>
      <style jsx>{`.field{border:1px solid #334155;background:#0f172a;border-radius:.375rem;padding:.75rem;color:#f8fafc}.panel{border:1px solid #334155;background:#0f172a;border-radius:.75rem;padding:1.25rem}.panel h2{font-size:1.05rem;font-weight:600;color:#67e8f9;margin-bottom:.75rem}.panel h3{font-size:.75rem;text-transform:uppercase;letter-spacing:.12em;color:#94a3b8;margin-top:1.25rem;margin-bottom:.35rem}.panel p{color:#cbd5e1;white-space:pre-wrap}`}</style>
    </main>
  )
}
