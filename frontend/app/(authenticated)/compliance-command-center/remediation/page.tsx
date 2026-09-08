"use client"

import { FormEvent, useEffect, useState } from "react"
import { apiFetch } from "../../../../lib/api"
import { proposalPublishRequest, proposalQuery, proposalReviewRequest, proposalSaveRequest } from "../../../../lib/redlineProposals"
import { Skeleton } from "../../../../components/ui/skeleton"

type FindingContext = {
  findingId: string
  contractId: string
  versionId: string
  title: string
  severity: string
  currentLanguage: string
  recommendation: string
  description: string
  evidenceQuote: string
}

type Proposal = {
  proposal_id: string
  contract_id: string
  source_version_id: string
  finding_id: string
  evidence_id: string | null
  title: string | null
  severity: string | null
  original_text: string
  evidence: unknown
  proposed_text: string
  recommendation: string | null
  reason: string | null
  status: string
  created_by: string
  created_at: string
  updated_at: string
  review: Review | null
  published_version_id?: string
  published_by?: string
  published_at?: string
}

type Review = {
  review_id: string
  proposal_id: string
  decision: "APPROVED" | "REJECTED"
  reviewer_id: string
  comment: string | null
  created_at: string
  updated_at: string
}

export default function RemediationPage() {
  const [context, setContext] = useState<FindingContext | null>(null)
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [proposedText, setProposedText] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [reviewComment, setReviewComment] = useState("")
  const [reviewing, setReviewing] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const nextContext = {
      findingId: params.get("finding_id") ?? "",
      contractId: params.get("contract_id") ?? "",
      versionId: params.get("version_id") ?? "",
      title: params.get("title") ?? "",
      severity: params.get("severity") ?? "",
      currentLanguage: params.get("current_language") ?? "",
      recommendation: params.get("regulatory_requirement") ?? "",
      description: params.get("amendment_reason") ?? "",
      evidenceQuote: params.get("evidence_quote") ?? "",
    }
    setContext(nextContext)
    if (!nextContext.contractId || !nextContext.findingId) {
      setError("A contract and finding are required to create a proposal.")
      setLoading(false)
      return
    }
    const query = proposalQuery(nextContext.findingId, nextContext.versionId)
    void apiFetch(`/api/contracts/${encodeURIComponent(nextContext.contractId)}/redline-proposals?${query}`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Unable to load proposals")
        const proposals: Proposal[] = await response.json()
        const existing = proposals.at(-1) ?? null
        setProposal(existing)
        setProposedText(existing?.proposed_text ?? "")
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load proposals"))
      .finally(() => setLoading(false))
  }, [])

  async function saveProposal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!context) return
    setSaving(true)
    setError("")
    try {
      const request = proposalSaveRequest(proposal?.proposal_id ?? null, proposedText)
      const response = await apiFetch(
        request.path.replace("{contract_id}", encodeURIComponent(context.contractId)),
        { method: request.method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(proposal ? request.body : { ...request.body, source_version_id: context.versionId, finding_id: context.findingId }) },
      )
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Unable to save proposal")
      const saved: Proposal = await response.json()
      setProposal(saved)
      setProposedText(saved.proposed_text)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save proposal")
    } finally {
      setSaving(false)
    }
  }

  async function submitReview(decision: "APPROVED" | "REJECTED") {
    if (!proposal) return
    if (decision === "REJECTED") {
      const confirmed = window.confirm("Reject this redline proposal? This is a final decision and cannot be undone from this screen.")
      if (!confirmed) return
    }
    setReviewing(true)
    setError("")
    try {
      const request = proposalReviewRequest(proposal.proposal_id, decision, reviewComment)
      const response = await apiFetch(request.path, { method: request.method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(request.body) })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Unable to record review")
      const review: Review = await response.json()
      setProposal({ ...proposal, status: review.decision, review, updated_at: review.updated_at })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to record review")
    } finally {
      setReviewing(false)
    }
  }

  async function publishProposal() {
    if (!proposal) return
    setPublishing(true)
    setError("")
    try {
      const request = proposalPublishRequest(proposal.proposal_id)
      const response = await apiFetch(request.path, { method: request.method })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Unable to publish proposal")
      const publication: { published_version_id: string; published_by: string; published_at: string; status: string } = await response.json()
      setProposal({ ...proposal, status: publication.status, published_version_id: publication.published_version_id, published_by: publication.published_by, published_at: publication.published_at, updated_at: publication.published_at })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to publish proposal")
    } finally {
      setPublishing(false)
    }
  }

  const originalText = proposal?.original_text || context?.evidenceQuote || context?.currentLanguage || "Evidence not recorded"
  const recommendation = proposal?.recommendation || context?.recommendation || "Recommendation not recorded"

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <section className="mx-auto max-w-5xl">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">LexProof / redline proposals</p>
        <h1 className="mt-3 text-4xl font-semibold">Reviewable redline proposal</h1>
        <p className="mt-3 max-w-2xl text-slate-400">Preserve the finding context and prepare language for later human review.</p>

        {loading && (
          <div className="mt-10 space-y-4">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        )}
        {context && !loading && <>
          <section className="mt-8 border border-cyan-800 bg-cyan-950/40 p-5">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-300">Finding context</p>
            <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div><p className="meta">Contract</p><p>{context.contractId || "-"}</p></div>
              <div><p className="meta">Source version</p><p>{context.versionId || "-"}</p></div>
              <div><p className="meta">Finding</p><p>{context.title || context.findingId || "-"}</p></div>
              <div><p className="meta">Severity</p><p className="uppercase">{context.severity || "-"}</p></div>
            </div>
          </section>

          <form onSubmit={saveProposal} className="mt-8 space-y-5">
            <div className="grid gap-5 md:grid-cols-2">
              <article className="panel"><h2>Current clause</h2><p>{originalText}</p><h3>Recommendation</h3><p>{recommendation}</p><h3>Reason</h3><p>{proposal?.reason || context.description || "Reason not recorded"}</p></article>
              <article className="panel"><h2>Proposed clause</h2><textarea aria-label="Proposed text" value={proposedText} onChange={(event) => setProposedText(event.target.value)} placeholder="Enter proposed contractual language, or leave blank to save a draft." className="field min-h-48 w-full" /><p className="mt-2 text-xs text-slate-500">No legal language is generated or approved by this step.</p></article>
            </div>
            <div className="panel flex flex-wrap items-center justify-between gap-4"><div><p className="meta">Persisted status</p><p className="mt-1 font-semibold text-cyan-200">{proposal?.status || "Not saved"}</p>{proposal && <p className="mt-1 text-xs text-slate-500">Proposal {proposal.proposal_id} · Updated {new Date(proposal.updated_at).toLocaleString()}</p>}</div><button type="submit" disabled={saving || !context.versionId} className="bg-cyan-300 px-5 py-3 font-semibold text-slate-950 disabled:opacity-50">{saving ? "Saving..." : "Save proposal"}</button></div>
          </form>
        </>}
        {proposal && proposal.status !== "APPROVED" && proposal.status !== "REJECTED" && <section className="panel mt-5"><p className="meta">Human review</p><h2 className="mt-2 text-xl font-semibold text-cyan-200">Human decision</h2><textarea aria-label="Review comment" value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} placeholder="Add a review comment" className="field mt-4 min-h-24 w-full" /><div className="mt-4 flex flex-wrap gap-3"><button type="button" disabled={reviewing} onClick={() => void submitReview("REJECTED")} className="border border-rose-400 px-4 py-3 text-rose-300 disabled:opacity-50">{reviewing ? "Saving..." : "Reject"}</button><button type="button" disabled={reviewing} onClick={() => void submitReview("APPROVED")} className="bg-emerald-300 px-4 py-3 font-semibold text-slate-950 disabled:opacity-50">{reviewing ? "Saving..." : "Approve"}</button></div></section>}
        {proposal?.review && <section className="panel mt-5"><p className="meta">Human decision</p><p className={`mt-2 text-2xl font-semibold ${proposal.review.decision === "APPROVED" ? "text-emerald-300" : "text-rose-300"}`}>{proposal.review.decision}</p><p className="mt-2 text-sm text-slate-400">Reviewed by {proposal.review.reviewer_id} on {new Date(proposal.review.created_at).toLocaleString()}</p><p className="mt-3 whitespace-pre-wrap text-slate-300">{proposal.review.comment || "No comment recorded."}</p></section>}
        {proposal?.status === "APPROVED" && !proposal.published_version_id && <section className="panel mt-5"><p className="meta">Publication</p><p className="mt-2 text-xl font-semibold text-amber-200">Ready to publish</p><p className="mt-2 text-sm text-slate-400">Approved does not mean published. The source version remains unchanged until this action succeeds.</p><button type="button" disabled={publishing} onClick={() => void publishProposal()} className="mt-4 bg-amber-300 px-4 py-3 font-semibold text-slate-950 disabled:opacity-50">{publishing ? "Publishing..." : "Publish new version"}</button></section>}
        {proposal?.published_version_id && <section className="panel mt-5"><p className="meta">Publication</p><p className="mt-2 text-2xl font-semibold text-emerald-300">PUBLISHED</p><p className="mt-2 text-sm text-slate-300">Created version: {proposal.published_version_id}</p><p className="mt-1 text-sm text-slate-400">Parent version: {proposal.source_version_id}</p><p className="mt-1 text-sm text-slate-400">Published by {proposal.published_by} on {proposal.published_at && new Date(proposal.published_at).toLocaleString()}</p></section>}
        {error && <p role="alert" className="mt-5 text-rose-300">{error}</p>}
      </section>
      <style jsx>{`.field{border:1px solid #334155;background:#0f172a;border-radius:.375rem;padding:.75rem;color:#f8fafc}.panel{border:1px solid #334155;background:#0f172a;border-radius:.75rem;padding:1.25rem}.panel h2{font-size:1.05rem;font-weight:600;color:#67e8f9;margin-bottom:.75rem;text-transform:uppercase;letter-spacing:.08em}.panel h3{font-size:.75rem;text-transform:uppercase;letter-spacing:.12em;color:#94a3b8;margin-top:1.25rem;margin-bottom:.35rem}.panel p{color:#cbd5e1;white-space:pre-wrap}.meta{font-size:.68rem;text-transform:uppercase;letter-spacing:.12em;color:#67e8f9;margin-bottom:.3rem}`}</style>
    </main>
  )
}
