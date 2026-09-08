'use client'

import { useCallback, useEffect, useState } from 'react'
import { Copy, Link2 } from 'lucide-react'
import { apiFetch } from '../lib/api'
import {
  counterpartyShareUrl,
  createCounterpartyLinkRequest,
  listCounterpartyLinksPath,
} from '../lib/counterparty'
import { Button } from './ui/button'
import { EmptyState } from './EmptyState'
import { Skeleton } from './ui/skeleton'

export type ExistingCounterpartyLink = {
  token_id: string
  created_at?: string | null
  expires_at?: string | null
  revoked?: boolean
  countersigned?: boolean
  countersign_evidence_id?: string | null
  counterparty_name?: string | null
  counterparty_email?: string | null
}

type ShareWithCounterpartyProps = {
  orgId: string
  contractId: string
  proposalId: string
}

function formatWhen(value?: string | null) {
  if (!value) return 'Unknown'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export function ShareWithCounterparty({ orgId, contractId, proposalId }: ShareWithCounterpartyProps) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [expiresInDays, setExpiresInDays] = useState('14')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [shareUrl, setShareUrl] = useState('')
  const [copied, setCopied] = useState(false)
  const [links, setLinks] = useState<ExistingCounterpartyLink[]>([])
  const [linksLoading, setLinksLoading] = useState(false)

  const loadLinks = useCallback(async () => {
    if (!orgId || !contractId || !proposalId) return
    setLinksLoading(true)
    try {
      const response = await apiFetch(listCounterpartyLinksPath(orgId, contractId, proposalId))
      if (!response.ok) {
        throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load counterparty links')
      }
      setLinks(await response.json())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load counterparty links')
    } finally {
      setLinksLoading(false)
    }
  }, [orgId, contractId, proposalId])

  useEffect(() => {
    void loadLinks()
  }, [loadLinks])

  async function createLink() {
    setBusy(true)
    setError('')
    setCopied(false)
    try {
      const days = Number(expiresInDays)
      const request = createCounterpartyLinkRequest(orgId, contractId, {
        redline_proposal_id: proposalId,
        counterparty_name: name.trim(),
        counterparty_email: email.trim(),
        expires_in_days: Number.isFinite(days) && days > 0 ? days : undefined,
      })
      const response = await apiFetch(request.path, {
        method: request.method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request.body),
      })
      if (!response.ok) {
        throw new Error((await response.json().catch(() => null))?.detail || 'Unable to create counterparty link')
      }
      const created = await response.json()
      const url = created.share_url || counterpartyShareUrl(created.token)
      setShareUrl(url)
      setName('')
      setEmail('')
      await loadLinks()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to create counterparty link')
    } finally {
      setBusy(false)
    }
  }

  async function copyUrl() {
    if (!shareUrl) return
    await navigator.clipboard.writeText(shareUrl)
    setCopied(true)
  }

  return (
    <div className="border-t border-gray-100 pt-4">
      <Button type="button" variant="outline" onClick={() => setOpen((current) => !current)}>
        <Link2 className="h-4 w-4" />
        Share with counterparty
      </Button>
      {open && (
        <div className="mt-4 space-y-4 rounded border border-blue-100 bg-blue-50/60 p-4">
          <p className="text-sm text-gray-700">
            Generate a scoped link for the other side of this negotiation. They will not need a LexProof account.
            A countersignature is recorded as evidence on this contract&apos;s Legal Passport — it does not change
            the internal approval workflow.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-medium text-gray-700">
              Counterparty name
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm font-normal"
                placeholder="Jordan Chen"
              />
            </label>
            <label className="block text-sm font-medium text-gray-700">
              Counterparty email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm font-normal"
                placeholder="jordan@example.com"
              />
            </label>
          </div>
          <label className="block max-w-xs text-sm font-medium text-gray-700">
            Expires in (days)
            <input
              type="number"
              min={1}
              max={90}
              value={expiresInDays}
              onChange={(event) => setExpiresInDays(event.target.value)}
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 text-sm font-normal"
            />
          </label>
          <Button
            type="button"
            disabled={busy || !name.trim() || !email.trim()}
            onClick={() => void createLink()}
          >
            {busy ? 'Creating link…' : 'Create access link'}
          </Button>
          {shareUrl && (
            <div className="rounded border border-gray-200 bg-white p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Shareable link</p>
              <p className="mt-1 break-all font-mono text-xs text-gray-900">{shareUrl}</p>
              <Button type="button" variant="outline" className="mt-2" onClick={() => void copyUrl()}>
                <Copy className="h-4 w-4" />
                {copied ? 'Copied' : 'Copy link'}
              </Button>
            </div>
          )}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Existing links</p>
            {linksLoading && (
              <div className="mt-2 space-y-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            )}
            {!linksLoading && links.length === 0 && (
              <EmptyState
                compact
                title="No counterparty links yet"
                description="Create a time-limited access link so an external party can review this redline without a LexProof account."
              />
            )}
            <ul className="mt-2 space-y-2">
              {links.map((link) => (
                <li key={link.token_id} className="rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700">
                  <p>
                    <span className="font-medium">{link.counterparty_name || 'Counterparty'}</span>
                    {link.counterparty_email ? ` · ${link.counterparty_email}` : ''}
                  </p>
                  <p className="text-xs text-gray-500">
                    Created {formatWhen(link.created_at)} · Expires {formatWhen(link.expires_at)}
                    {link.revoked ? ' · Revoked' : ''}
                    {link.countersigned
                      ? ` · Countersigned${link.countersign_evidence_id ? ` (${link.countersign_evidence_id})` : ''}`
                      : ' · Not yet countersigned'}
                  </p>
                </li>
              ))}
            </ul>
          </div>
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
        </div>
      )}
      {!open && (
        <div className="mt-3">
          {linksLoading && (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
            </div>
          )}
          {!linksLoading && links.length > 0 && (
            <ul className="space-y-2">
              {links.map((link) => (
                <li key={link.token_id} className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                  <p>
                    <span className="font-medium">{link.counterparty_name || 'Counterparty'}</span>
                    {link.counterparty_email ? ` · ${link.counterparty_email}` : ''}
                  </p>
                  <p className="text-xs text-gray-500">
                    Created {formatWhen(link.created_at)} · Expires {formatWhen(link.expires_at)}
                    {link.countersigned ? ' · Countersigned' : ' · Not yet countersigned'}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
