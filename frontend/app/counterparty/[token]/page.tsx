'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import {
  COUNTERPARTY_ATTESTATION,
  externalAccessPath,
  externalCommentPath,
  externalCountersignPath,
} from '../../../lib/counterparty'
import { ClauseDiff } from '../../../components/ClauseDiff'
import { Button } from '../../../components/ui/button'
import { brandCssVars } from '../../../lib/branding'

type Comment = {
  comment_id?: string
  author_name?: string | null
  body: string
  created_at?: string | null
}

type ExternalView = {
  contract_name: string
  contract_version?: number | null
  proposal_status?: string | null
  title?: string | null
  original_text: string
  proposed_text: string
  recommendation?: string | null
  reason?: string | null
  counterparty_name?: string | null
  permissions?: string[]
  expires_at?: string | null
  already_countersigned: boolean
  countersign_evidence_id?: string | null
  attestation_statement: string
  comments: Comment[]
  org_name?: string | null
  org_logo_url?: string | null
  org_primary_color?: string | null
}

function errorMessage(status: number, detail: unknown, fallback: string) {
  const text = typeof detail === 'string' ? detail : fallback
  if (status === 410) return text || 'This access link has expired.'
  if (status === 403) return text || 'This access link is no longer available.'
  if (status === 404) return text || 'This access link is invalid or no longer available.'
  if (status === 429) return text || 'Too many requests. Please wait a moment and try again.'
  return text || fallback
}

function formatWhen(value?: string | null) {
  if (!value) return ''
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export default function CounterpartyPage() {
  const params = useParams<{ token: string }>()
  const token = typeof params?.token === 'string' ? params.token : ''
  const [view, setView] = useState<ExternalView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [comment, setComment] = useState('')
  const [typedName, setTypedName] = useState('')
  const [attested, setAttested] = useState(false)
  const [busy, setBusy] = useState<'comment' | 'countersign' | null>(null)
  const [evidenceId, setEvidenceId] = useState('')
  const [actionError, setActionError] = useState('')

  const load = useCallback(async () => {
    if (!token) {
      setError('This access link is invalid or no longer available.')
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(externalAccessPath(token))
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(errorMessage(response.status, payload.detail, 'Unable to open this access link'))
      }
      setView(payload)
      if (payload.already_countersigned && payload.countersign_evidence_id) {
        setEvidenceId(payload.countersign_evidence_id)
      }
    } catch (cause) {
      setView(null)
      setError(cause instanceof Error ? cause.message : 'Unable to open this access link')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  const canComment = Boolean(view?.permissions?.includes('comment'))
  const canCountersign = Boolean(view?.permissions?.includes('countersign'))
  const alreadySigned = Boolean(view?.already_countersigned || evidenceId)
  const nameMatches = typedName.trim().toLowerCase() === (view?.counterparty_name || '').trim().toLowerCase()
  const countersignEnabled = Boolean(view && canCountersign && !alreadySigned && attested && nameMatches && !busy)

  async function submitComment() {
    if (!token || !comment.trim()) return
    setBusy('comment')
    setActionError('')
    try {
      const response = await apiFetch(externalCommentPath(token), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: comment.trim() }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(errorMessage(response.status, payload.detail, 'Unable to add comment'))
      }
      setComment('')
      await load()
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Unable to add comment')
    } finally {
      setBusy(null)
    }
  }

  async function submitCountersign() {
    if (!token || !countersignEnabled) return
    setBusy('countersign')
    setActionError('')
    try {
      const response = await apiFetch(externalCountersignPath(token), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          typed_name: typedName.trim(),
          attestation_accepted: true,
          attestation: COUNTERPARTY_ATTESTATION,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(errorMessage(response.status, payload.detail, 'Unable to countersign'))
      }
      setEvidenceId(payload.evidence_id)
      await load()
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Unable to countersign')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div
      className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4 sm:px-6 lg:px-8"
      style={brandCssVars({ primary_color: view?.org_primary_color }) as React.CSSProperties}
    >
      <div className="mx-auto max-w-4xl">
        <div className="mb-10 text-center">
          {/* White-label (Task #109): the sending org's own logo/name is
              shown here when they've set one -- LexProof stays credited as
              the underlying verification/evidence platform, since the
              cryptographic trust story (see IndependentVerificationPanel)
              is intentionally never white-labeled away. */}
          {view?.org_logo_url ? (
            <div className="mb-4 flex flex-col items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={view.org_logo_url}
                alt={`${view.org_name || 'Organization'} logo`}
                className="h-14 w-14 rounded-lg border border-gray-200 bg-white object-contain shadow-sm"
              />
              {view.org_name && <p className="text-lg font-semibold text-gray-900">{view.org_name}</p>}
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-400">Secured by LexProof</p>
            </div>
          ) : (
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-700">{view?.org_name || 'LexProof'}</p>
          )}
          <h1 className="mt-2 text-4xl font-bold text-gray-900">Counterparty review</h1>
          <p className="mx-auto mt-3 max-w-2xl text-gray-600">
            You have been invited to review a proposed redline. You do not need a LexProof account. A
            countersignature is cryptographically recorded as evidence on this contract&apos;s Legal Passport.
          </p>
        </div>

        {loading && (
          <div className="flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white p-10 text-gray-600 shadow">
            <Loader2 className="h-5 w-5 animate-spin" /> Opening this access link…
          </div>
        )}

        {!loading && error && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center shadow">
            <h2 className="text-xl font-semibold text-amber-900">This link is not available</h2>
            <p className="mt-3 text-sm text-amber-800">{error}</p>
            <p className="mt-4 text-sm text-amber-700">
              If you were expecting access, ask the sending organization to issue a new counterparty link.
            </p>
          </div>
        )}

        {!loading && view && (
          <div className="space-y-6">
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Contract</p>
              <h2 className="mt-1 text-2xl font-bold text-gray-900">{view.contract_name}</h2>
              <p className="mt-2 text-sm text-gray-600">
                {view.title || 'Redline proposal'}
                {view.proposal_status ? ` · ${view.proposal_status}` : ''}
                {view.expires_at ? ` · Link expires ${formatWhen(view.expires_at)}` : ''}
              </p>
              {(view.reason || view.recommendation) && (
                <div className="mt-4 space-y-1 text-sm text-gray-700">
                  {view.reason && (
                    <p>
                      <span className="font-semibold">Why it matters: </span>
                      {view.reason}
                    </p>
                  )}
                  {view.recommendation && (
                    <p>
                      <span className="font-semibold">Recommendation: </span>
                      {view.recommendation}
                    </p>
                  )}
                </div>
              )}
              <ClauseDiff className="mt-6" originalText={view.original_text} proposedText={view.proposed_text} />
            </div>

            {alreadySigned && (
              <div className="rounded-xl border-2 border-green-500 bg-green-50 p-8 text-center shadow">
                <CheckCircle2 className="mx-auto h-12 w-12 text-green-600" />
                <h2 className="mt-4 text-2xl font-bold text-green-800">Countersignature recorded</h2>
                <p className="mx-auto mt-3 max-w-2xl text-sm text-green-800">
                  Your agreement is now part of this contract&apos;s permanent, evidence-backed record. It has been
                  cryptographically recorded on the Legal Passport and can later be anchored on-chain through
                  LexProof&apos;s existing evidence workflow.
                </p>
                {evidenceId && (
                  <p className="mt-4 break-all font-mono text-xs text-green-900">Evidence ID: {evidenceId}</p>
                )}
              </div>
            )}

            {canComment && (
              <div className="rounded-xl border border-gray-200 bg-white p-6 shadow">
                <h3 className="text-lg font-semibold text-gray-900">Comments</h3>
                <p className="mt-1 text-sm text-gray-600">
                  Comments are stored with this access link as {view.counterparty_name || 'the invited counterparty'}.
                </p>
                <ul className="mt-4 space-y-2">
                  {(view.comments || []).map((item) => (
                    <li key={item.comment_id || item.created_at} className="rounded border border-gray-100 bg-gray-50 p-3 text-sm">
                      <p className="font-medium text-gray-800">{item.author_name}</p>
                      <p className="mt-1 text-gray-700">{item.body}</p>
                      {item.created_at && <p className="mt-1 text-xs text-gray-500">{formatWhen(item.created_at)}</p>}
                    </li>
                  ))}
                </ul>
                <label className="mt-4 block text-sm font-medium text-gray-700">
                  Add a comment
                  <textarea
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                    rows={3}
                    className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 text-sm font-normal"
                    placeholder="Ask a question or note an exception"
                  />
                </label>
                <Button
                  className="mt-3"
                  type="button"
                  disabled={busy !== null || !comment.trim()}
                  onClick={() => void submitComment()}
                >
                  {busy === 'comment' ? 'Sending…' : 'Send comment'}
                </Button>
              </div>
            )}

            {canCountersign && !alreadySigned && (
              <div className="rounded-xl border border-gray-200 bg-white p-6 shadow">
                <h3 className="text-lg font-semibold text-gray-900">Countersign</h3>
                <p className="mt-1 text-sm text-gray-600">
                  Type your name exactly as invited ({view.counterparty_name}) and confirm the attestation. This
                  creates a cryptographically recorded evidence item — it is not a new step in the sending
                  organization&apos;s internal approval workflow.
                </p>
                <label className="mt-4 block text-sm font-medium text-gray-700">
                  Type your name
                  <input
                    value={typedName}
                    onChange={(event) => setTypedName(event.target.value)}
                    className="mt-2 block w-full max-w-md rounded border border-gray-300 px-3 py-2 text-sm font-normal"
                    placeholder={view.counterparty_name || 'Your full name'}
                  />
                </label>
                <label className="mt-4 flex items-start gap-3 text-sm text-gray-800">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={attested}
                    onChange={(event) => setAttested(event.target.checked)}
                  />
                  <span>{view.attestation_statement || COUNTERPARTY_ATTESTATION}</span>
                </label>
                <Button
                  className="mt-4"
                  type="button"
                  disabled={!countersignEnabled}
                  onClick={() => void submitCountersign()}
                >
                  {busy === 'countersign' ? 'Recording…' : 'Countersign this redline'}
                </Button>
              </div>
            )}

            {actionError && (
              <p role="alert" className="text-sm text-red-600">
                {actionError}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
