'use client'

import { FormEvent, useState } from 'react'
import Link from 'next/link'
import { Loader2, MessageSquare, Send } from 'lucide-react'
import { apiFetch } from '../../../../lib/api'
import { getCurrentOrgId } from '../../../../lib/orgStore'
import { Button } from '../../../../components/ui/button'

type Citation = {
  finding_id: string
  evidence_id?: string | null
  contract_id?: string | null
  contract_name?: string | null
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  grounded?: boolean
  citations?: Citation[]
}

function citationHref(citation: Citation) {
  const params = new URLSearchParams()
  if (citation.contract_id) params.set('contract_id', citation.contract_id)
  if (citation.finding_id) params.set('finding_id', citation.finding_id)
  return `/dashboard/ai-analysis/findings?${params}`
}

export default function AskYourContractsPage() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const text = question.trim()
    if (!text || sending) return
    const orgId = getCurrentOrgId()
    if (!orgId) {
      setError('Select an organization before asking.')
      return
    }
    setError('')
    setQuestion('')
    setMessages((current) => [...current, { role: 'user', content: text }])
    setSending(true)
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(body?.detail || 'Unable to answer from your findings')
      }
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: body.answer,
          grounded: body.grounded,
          citations: body.citations || [],
        },
      ])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to answer from your findings')
    } finally {
      setSending(false)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-10 text-slate-900">
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        <header className="border-b border-slate-200 pb-6">
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.24em] text-blue-700">LexProof / Portfolio</p>
          <h1 className="text-4xl font-bold tracking-tight">Ask Your Contracts</h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Answers come only from your verified findings. Every citation is a live link back to the
            evidence — if we cannot retrieve supporting findings, we will say so instead of guessing.
          </p>
        </header>

        <div className="flex min-h-[28rem] flex-col rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex-1 space-y-4 overflow-y-auto p-5">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center py-16 text-center text-slate-500">
                <MessageSquare className="mb-3 h-8 w-8 text-blue-600" />
                <p className="text-sm">Try “Which contracts have unfavorable governing law clauses?”</p>
              </div>
            )}
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`max-w-[90%] rounded-lg px-4 py-3 text-sm ${
                  message.role === 'user'
                    ? 'ml-auto bg-blue-600 text-white'
                    : message.grounded === false
                      ? 'border border-amber-200 bg-amber-50 text-amber-950'
                      : 'bg-slate-100 text-slate-900'
                }`}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
                {message.role === 'assistant' && message.grounded === false && (
                  <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
                    Not grounded in retrieved findings
                  </p>
                )}
                {message.citations && message.citations.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {message.citations.map((citation) => (
                      <Link
                        key={`${citation.finding_id}-${citation.evidence_id || ''}`}
                        href={citationHref(citation)}
                        className="rounded-full border border-blue-200 bg-white px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50"
                      >
                        {citation.contract_name || citation.contract_id || 'Finding'} · {citation.finding_id.slice(0, 8)}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {sending && (
              <div className="inline-flex items-center gap-2 rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-600">
                <Loader2 className="h-4 w-4 animate-spin" />
                Retrieving verified findings…
              </div>
            )}
          </div>
          <form onSubmit={onSubmit} className="border-t border-slate-200 p-4">
            {error && <p className="mb-3 text-sm text-red-700">{error}</p>}
            <div className="flex gap-2">
              <input
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask about governing law, liability, termination…"
                className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <Button type="submit" disabled={sending || !question.trim()}>
                <Send className="h-4 w-4" />
                Ask
              </Button>
            </div>
          </form>
        </div>
      </div>
    </main>
  )
}
