"use client"

import { FormEvent, useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { apiFetch } from "../../../../lib/api"
import { proposalPublishRequest, proposalQuery, proposalReviewRequest, proposalSaveRequest, redlineSuggestionRequest } from "../../../../lib/redlineProposals"
import { Skeleton } from "../../../../components/ui/skeleton"
import { Badge } from "../../../../components/ui/badge"
import { Button } from "../../../../components/ui/button"
import { Card, CardContent } from "../../../../components/ui/card"
import { PageHeader } from "../../../../components/ui/page-header"
import { PageContainer } from "../../../../components/ui/container"
import { useOrg } from "../../../../components/OrgProvider"
import { hasRole, isAdmin as isAdminRole } from "../../../../lib/roles"

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

const SEVERITY_VARIANT: Record<string, 'critical' | 'high' | 'medium' | 'low' | 'secondary'> = {
  CRITICAL: 'critical',
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low',
}

function statusVariant(status: string | undefined): 'verified' | 'tampered' | 'pending' | 'secondary' {
  if (status === 'APPROVED' || status === 'PUBLISHED') return 'verified'
  if (status === 'REJECTED') return 'tampered'
  if (!status) return 'secondary'
  return 'pending'
}

export default function RemediationPage() {
  // UI role gating (defense in depth alongside the backend's real
  // enforcement): mirrors the allowed_roles for the "approve"/"reject"
  // workflow transitions (["reviewer", "admin"] -- workflow_catalog.py)
  // and the established isAdmin(roles) || hasRole(roles, X) idiom already
  // used for the same purpose in dashboard/contracts/reviews/page.tsx
  // (canReview/canPublish/canShare). The backend's real 403 from
  // workflow_engine.py's role + requires_not_actor checks remains the
  // actual authorization boundary -- this only controls whether the
  // button is offered as an actionable control to begin with.
  const { roles } = useOrg()
  const canReview = isAdminRole(roles) || hasRole(roles, 'reviewer')
  const [context, setContext] = useState<FindingContext | null>(null)
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [proposedText, setProposedText] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [reviewComment, setReviewComment] = useState("")
  const [reviewing, setReviewing] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState("")
  const [suggesting, setSuggesting] = useState(false)
  const [suggestionRationale, setSuggestionRationale] = useState("")
  const [suggestionError, setSuggestionError] = useState("")

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
    let cancelled = false
    const controller = new AbortController()
    const query = proposalQuery(nextContext.findingId, nextContext.versionId)
    void apiFetch(`/api/contracts/${encodeURIComponent(nextContext.contractId)}/redline-proposals?${query}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Unable to load proposals")
        const proposals: Proposal[] = await response.json()
        if (cancelled) return
        const existing = proposals.at(-1) ?? null
        setProposal(existing)
        // Do not blank a clause the reviewer already typed. React Strict Mode
        // remounts this effect in next dev; the slower first GET used to land
        // after fill and save an empty DRAFT.
        setProposedText((current) => current || existing?.proposed_text || "")
      })
      .catch((reason) => {
        if (cancelled || (reason instanceof DOMException && reason.name === "AbortError")) return
        setError(reason instanceof Error ? reason.message : "Unable to load proposals")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
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

  async function suggestWithAI() {
    if (!context) return
    setSuggesting(true)
    setSuggestionError("")
    try {
      const request = redlineSuggestionRequest(context.contractId, context.findingId)
      const response = await apiFetch(request.path, {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request.body),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Unable to generate an AI suggestion")
      const suggestion: { suggested_text: string; rationale: string } = await response.json()
      setProposedText(suggestion.suggested_text)
      setSuggestionRationale(suggestion.rationale)
    } catch (reason) {
      setSuggestionError(reason instanceof Error ? reason.message : "Unable to generate an AI suggestion")
    } finally {
      setSuggesting(false)
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
  const severityKey = (context?.severity || '').toUpperCase()

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Compliance / redline proposals"
        title="Reviewable redline proposal"
        description="Preserve the finding context and prepare language for later human review."
      />

      {loading && (
        <div className="mt-6 space-y-6">
          <Skeleton className="h-24 w-full" />
          <div className="grid gap-5 md:grid-cols-2">
            <Skeleton className="h-56 w-full" />
            <Skeleton className="h-56 w-full" />
          </div>
        </div>
      )}

      {context && !loading && (
        <div className="mt-6 space-y-6">
          <Card>
            <CardContent>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">Finding context</p>
              <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Contract</p>
                  <p className="mt-1 font-mono text-xs text-gray-900 dark:text-gray-100">{context.contractId || "-"}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Source version</p>
                  <p className="mt-1 font-mono text-xs text-gray-900 dark:text-gray-100">{context.versionId || "-"}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Finding</p>
                  <p className="mt-1 text-gray-900 dark:text-gray-100">{context.title || context.findingId || "-"}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Severity</p>
                  <div className="mt-1">
                    <Badge variant={SEVERITY_VARIANT[severityKey] || 'secondary'}>{context.severity || "-"}</Badge>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <form onSubmit={saveProposal} className="space-y-6">
            <div className="grid gap-5 md:grid-cols-2">
              <Card>
                <CardContent className="space-y-4">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Current clause</h2>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">{originalText}</p>
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Recommendation</h3>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">{recommendation}</p>
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Reason</h3>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">{proposal?.reason || context.description || "Reason not recorded"}</p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Proposed clause</h2>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={suggesting || !context.versionId}
                      onClick={() => void suggestWithAI()}
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      {suggesting ? "Drafting…" : "Suggest with AI"}
                    </Button>
                  </div>
                  <textarea
                    aria-label="Proposed text"
                    value={proposedText}
                    onChange={(event) => setProposedText(event.target.value)}
                    placeholder="Enter proposed contractual language, leave blank to save a draft, or use Suggest with AI for a starting point."
                    className="min-h-48 w-full rounded border border-gray-300 p-3 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                  />
                  {suggestionError && <p className="text-xs text-red-600 dark:text-red-400">{suggestionError}</p>}
                  {suggestionRationale && !suggestionError && <p className="text-xs text-gray-500 dark:text-gray-400">AI rationale: {suggestionRationale}</p>}
                  <p className="text-xs text-gray-500 dark:text-gray-400">AI can draft a starting point below; nothing is proposed or approved until you review it and save.</p>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardContent className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Persisted status</p>
                  <div className="mt-1"><Badge variant={statusVariant(proposal?.status)}>{proposal?.status || "Not saved"}</Badge></div>
                  {proposal && (
                    <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      Proposal <span className="font-mono">{proposal.proposal_id}</span> · Updated {new Date(proposal.updated_at).toLocaleString()}
                    </p>
                  )}
                </div>
                <Button type="submit" disabled={saving || !context.versionId}>
                  {saving ? "Saving..." : "Save proposal"}
                </Button>
              </CardContent>
            </Card>
          </form>

          {proposal && proposal.status !== "APPROVED" && proposal.status !== "REJECTED" && canReview && (
            <Card>
              <CardContent>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Human review</p>
                <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">Human decision</h2>
                <textarea
                  aria-label="Review comment"
                  value={reviewComment}
                  onChange={(event) => setReviewComment(event.target.value)}
                  placeholder="Add a review comment"
                  className="mt-4 min-h-24 w-full rounded border border-gray-300 p-3 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                />
                <div className="mt-4 flex flex-wrap gap-3">
                  <Button type="button" variant="destructive" disabled={reviewing} onClick={() => void submitReview("REJECTED")}>
                    {reviewing ? "Saving..." : "Reject"}
                  </Button>
                  <Button type="button" disabled={reviewing} onClick={() => void submitReview("APPROVED")}>
                    {reviewing ? "Saving..." : "Approve"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {proposal?.review && (
            <Card>
              <CardContent>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Human decision</p>
                <div className="mt-2"><Badge variant={proposal.review.decision === "APPROVED" ? 'verified' : 'tampered'}>{proposal.review.decision}</Badge></div>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Reviewed by {proposal.review.reviewer_id} on {new Date(proposal.review.created_at).toLocaleString()}</p>
                <p className="mt-3 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">{proposal.review.comment || "No comment recorded."}</p>
              </CardContent>
            </Card>
          )}

          {proposal?.status === "APPROVED" && !proposal.published_version_id && (
            <Card>
              <CardContent>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Publication</p>
                <div className="mt-1"><Badge variant="pending">Ready to publish</Badge></div>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Approved does not mean published. The source version remains unchanged until this action succeeds.</p>
                <Button type="button" className="mt-4" disabled={publishing} onClick={() => void publishProposal()}>
                  {publishing ? "Publishing..." : "Publish new version"}
                </Button>
              </CardContent>
            </Card>
          )}

          {proposal?.published_version_id && (
            <Card>
              <CardContent>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Publication</p>
                <div className="mt-1"><Badge variant="verified">Published</Badge></div>
                <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">Created version: <span className="font-mono text-xs">{proposal.published_version_id}</span></p>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Parent version: <span className="font-mono text-xs">{proposal.source_version_id}</span></p>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Published by {proposal.published_by} on {proposal.published_at && new Date(proposal.published_at).toLocaleString()}</p>
              </CardContent>
            </Card>
          )}

          {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
      )}
    </PageContainer>
  )
}
