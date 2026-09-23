'use client'

// Phase 4 (2026-09-11, gold-standard visual consistency pass): rebuilt onto
// PageContainer/PageHeader/Card -- the prior version was a full-bleed
// slate-50 page with its own gradient-icon hero and purple/fuchsia accent
// system, entirely off the shared design language, reading like a generic
// consumer chatbot rather than an enterprise legal-intelligence workspace.
// Every handler, API call, suggestion-ranking algorithm, voice-input
// integration, and citation link below is unchanged -- this is a
// presentation-only rewrite. The assistant message bubble now visually
// separates the answer text from its supporting evidence citations, and
// the accent color is the app's shared --brand-primary rather than a
// bespoke purple gradient, so white-labeled orgs get one consistent brand
// color across every screen, this one included.

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { Loader2, Sparkles, Send, Mic, MicOff, FileCheck2 } from 'lucide-react'
import { apiFetch } from '../../../../lib/api'
import { getCurrentOrgId } from '../../../../lib/orgStore'
import { Button } from '../../../../components/ui/button'
import { Card } from '../../../../components/ui/card'
import { PageHeader } from '../../../../components/ui/page-header'
import { PageContainer } from '../../../../components/ui/container'
import {
  getSpeechRecognitionConstructor,
  isSpeechRecognitionSupported,
  speechErrorMessage,
  transcriptFrom,
  type SpeechRecognitionInstance,
} from '../../../../lib/speechRecognition'

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

type ContractSummary = {
  contract_id: string
  name?: string | null
}

type SuggestionCategory = 'clause' | 'contract' | 'popular'

type Suggestion = {
  text: string
  category: SuggestionCategory
}

// Mirrors backend/app/lexproof/services/ask_contracts.py's KNOWN_TERMS so
// suggestions stay aligned with the clause types the retriever actually
// recognizes.
const CLAUSE_TOPICS = [
  'governing law',
  'indemnification',
  'limitation of liability',
  'termination',
  'warranty',
  'confidentiality',
  'assignment',
  'force majeure',
  'intellectual property',
  'non-compete',
  'privacy',
  'GDPR',
  'audit',
  'insurance',
  'payment',
  'renewal',
  'notice',
  'dispute resolution',
  'arbitration',
  'jurisdiction',
  'data protection',
  'service level',
  'exclusivity',
  'change of control',
]

const POPULAR_QUESTIONS = [
  'What are my highest-risk contracts right now?',
  'Which contracts are missing a limitation of liability clause?',
  'Summarize all critical findings across my portfolio',
  'Which contracts should I review first?',
  'Which contracts have unfavorable governing law clauses?',
  'Are there any contracts with unusual indemnification terms?',
]

const CATEGORY_DOT: Record<SuggestionCategory, string> = {
  clause: 'bg-purple-500',
  contract: 'bg-blue-500',
  popular: 'bg-emerald-500',
}

const CATEGORY_LABEL: Record<SuggestionCategory, string> = {
  clause: 'Clause',
  contract: 'Contract',
  popular: 'Popular',
}

function citationHref(citation: Citation) {
  const params = new URLSearchParams()
  if (citation.contract_id) params.set('contract_id', citation.contract_id)
  if (citation.finding_id) params.set('finding_id', citation.finding_id)
  return `/dashboard/ai-analysis/findings?${params}`
}

function rankSuggestions(pool: Suggestion[], query: string, limit: number): Suggestion[] {
  const lowered = query.trim().toLowerCase()
  if (!lowered) return []
  const scored: { suggestion: Suggestion; score: number }[] = []
  for (const suggestion of pool) {
    const haystack = suggestion.text.toLowerCase()
    const index = haystack.indexOf(lowered)
    if (index === -1) continue
    const startsBonus = index === 0 ? 0 : 50
    scored.push({ suggestion, score: startsBonus + index + suggestion.text.length * 0.01 })
  }
  scored.sort((a, b) => a.score - b.score)
  const seen = new Set<string>()
  const results: Suggestion[] = []
  for (const item of scored) {
    if (seen.has(item.suggestion.text)) continue
    seen.add(item.suggestion.text)
    results.push(item.suggestion)
    if (results.length >= limit) break
  }
  return results
}

export default function AskLexiPage() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [contracts, setContracts] = useState<ContractSummary[]>([])
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [activeSuggestion, setActiveSuggestion] = useState(-1)
  const [voiceSupported, setVoiceSupported] = useState(false)
  const [listening, setListening] = useState(false)
  const [voiceError, setVoiceError] = useState('')
  const inputAreaRef = useRef<HTMLDivElement>(null)
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)

  useEffect(() => {
    let cancelled = false
    async function loadContracts() {
      try {
        const response = await apiFetch('/api/contracts')
        if (!response.ok) return
        const body = await response.json().catch(() => null)
        if (!cancelled && Array.isArray(body)) {
          setContracts(body.slice(0, 8))
        }
      } catch {
        // Suggested questions still work without contract names.
      }
    }
    void loadContracts()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    function onDocumentMouseDown(event: MouseEvent) {
      if (!inputAreaRef.current?.contains(event.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', onDocumentMouseDown)
    return () => document.removeEventListener('mousedown', onDocumentMouseDown)
  }, [])

  useEffect(() => {
    setVoiceSupported(isSpeechRecognitionSupported())
    // Stop any in-flight recognition if the page unmounts mid-session, so
    // the microphone is never left listening in the background.
    return () => recognitionRef.current?.abort()
  }, [])

  function toggleVoiceInput() {
    if (listening) {
      recognitionRef.current?.stop()
      return
    }
    const RecognitionCtor = getSpeechRecognitionConstructor()
    if (!RecognitionCtor) return
    const recognition = new RecognitionCtor()
    recognition.lang = 'en-US'
    recognition.continuous = false
    recognition.interimResults = true
    recognition.onresult = (event) => {
      const transcript = transcriptFrom(event)
      setQuestion(transcript)
      updateSuggestionsFor(transcript)
    }
    recognition.onerror = (event) => {
      const message = speechErrorMessage(event.error)
      if (message) setVoiceError(message)
      setListening(false)
    }
    recognition.onend = () => setListening(false)
    recognitionRef.current = recognition
    setVoiceError('')
    setShowSuggestions(false)
    setListening(true)
    recognition.start()
  }

  const suggestionPool = useMemo<Suggestion[]>(() => {
    const pool: Suggestion[] = []
    for (const topic of CLAUSE_TOPICS) {
      pool.push({ text: `Which contracts have unfavorable ${topic} clauses?`, category: 'clause' })
      pool.push({ text: `Summarize the ${topic} terms across my portfolio`, category: 'clause' })
      pool.push({ text: `Are there any high-risk ${topic} findings?`, category: 'clause' })
    }
    for (const contract of contracts) {
      const name = (contract.name || contract.contract_id || '').trim()
      if (!name) continue
      pool.push({ text: `Summarize the risks in ${name}`, category: 'contract' })
      pool.push({ text: `Does ${name} have an indemnification clause?`, category: 'contract' })
      pool.push({ text: `What is the governing law in ${name}?`, category: 'contract' })
    }
    for (const text of POPULAR_QUESTIONS) {
      pool.push({ text, category: 'popular' })
    }
    return pool
  }, [contracts])

  const starterQuestions = useMemo(() => {
    const starters = [...POPULAR_QUESTIONS.slice(0, 4)]
    const firstContract = contracts[0]
    const contractName = firstContract?.name || firstContract?.contract_id
    if (contractName) {
      starters.push(`Summarize the risks in ${contractName}`)
    }
    starters.push('Which contracts have unfavorable governing law clauses?')
    return starters.slice(0, 6)
  }, [contracts])

  function updateSuggestionsFor(value: string) {
    setSuggestions(rankSuggestions(suggestionPool, value, 6))
    setActiveSuggestion(-1)
  }

  function onQuestionChange(event: React.ChangeEvent<HTMLInputElement>) {
    const value = event.target.value
    setQuestion(value)
    updateSuggestionsFor(value)
    setShowSuggestions(value.trim().length > 0)
  }

  function onInputFocus() {
    if (question.trim().length > 0) {
      updateSuggestionsFor(question)
      setShowSuggestions(true)
    }
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!showSuggestions || suggestions.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveSuggestion((current) => (current + 1) % suggestions.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveSuggestion((current) => (current <= 0 ? suggestions.length - 1 : current - 1))
    } else if (event.key === 'Enter' && activeSuggestion >= 0) {
      event.preventDefault()
      const chosen = suggestions[activeSuggestion]
      setShowSuggestions(false)
      void submitQuestion(chosen.text)
    } else if (event.key === 'Escape') {
      setShowSuggestions(false)
      setActiveSuggestion(-1)
    }
  }

  async function submitQuestion(text: string) {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    const orgId = getCurrentOrgId()
    if (!orgId) {
      setError('Select an organization before asking.')
      return
    }
    setError('')
    setQuestion('')
    setShowSuggestions(false)
    setActiveSuggestion(-1)
    setSuggestions([])
    // Sent as conversation context so Lexi can resolve follow-ups like "what
    // about indemnification?" or "is that a problem?" -- it is never a source
    // of facts on its own; every claim in the answer still has to cite a
    // retrieved finding_id, same as a first-turn question.
    const history = messages.slice(-8).map((message) => ({ role: message.role, content: message.content }))
    setMessages((current) => [...current, { role: 'user', content: trimmed }])
    setSending(true)
    try {
      const response = await apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed, history }),
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

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    await submitQuestion(question)
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="AI Copilot"
        title="Ask Lexi"
        description="Lexi answers only from your verified findings, with a live citation back to the evidence for every claim -- if she can't retrieve supporting findings, she says so instead of guessing."
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-400">
            <Sparkles className="h-3.5 w-3.5" />
            Grounded in your evidence
          </span>
        }
      />

      <div className="mt-6">
        <Card className="flex min-h-[28rem] flex-col overflow-hidden">
          <div className="flex-1 space-y-4 overflow-y-auto p-5">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-start gap-5 pt-6 pb-4 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950">
                  <Sparkles className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">Hi, I&rsquo;m Lexi</p>
                  <p className="mx-auto mt-1 max-w-sm text-sm text-gray-500 dark:text-gray-400">
                    Ask about a clause type, a risk, or a specific contract by name. Start typing below and
                    I&rsquo;ll suggest questions as you go.
                  </p>
                </div>
                <div className="grid w-full max-w-xl grid-cols-1 gap-2 sm:grid-cols-2">
                  {starterQuestions.map((text) => (
                    <button
                      key={text}
                      type="button"
                      onClick={() => void submitQuestion(text)}
                      className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white px-4 py-3 text-left text-sm text-gray-700 shadow-[var(--shadow-xs)] transition hover:border-[var(--brand-primary,#2563eb)] hover:bg-blue-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-blue-950/30"
                    >
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`flex items-start gap-2 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {message.role === 'assistant' && (
                  <div className="mt-1 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950">
                    <Sparkles className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-[var(--radius-lg,0.75rem)] px-4 py-3 text-sm ${
                    message.role === 'user'
                      ? 'bg-[var(--brand-primary,#2563eb)] text-white'
                      : message.grounded === false
                        ? 'border border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200'
                        : 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100'
                  }`}
                >
                  {message.role === 'assistant' && (
                    <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-gray-400 dark:text-gray-500">Answer</p>
                  )}
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  {message.role === 'assistant' && message.grounded === false && (
                    <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
                      Not grounded in retrieved findings
                    </p>
                  )}
                  {message.citations && message.citations.length > 0 && (
                    <div className="mt-3 border-t border-black/5 pt-3 dark:border-white/10">
                      <p className="mb-1.5 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                        <FileCheck2 className="h-3 w-3" />
                        Evidence &amp; source
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {message.citations.map((citation) => (
                          <Link
                            key={`${citation.finding_id}-${citation.evidence_id || ''}`}
                            href={citationHref(citation)}
                            className="rounded-full border border-blue-200 bg-white px-3 py-1 text-xs font-medium text-[var(--brand-primary,#1d4ed8)] hover:bg-blue-50 dark:border-blue-900 dark:bg-gray-800 dark:hover:bg-blue-950/40"
                          >
                            {citation.contract_name || citation.contract_id || 'Finding'} · {citation.finding_id.slice(0, 8)}
                          </Link>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950">
                  <Sparkles className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                </div>
                <div className="inline-flex items-center gap-2 rounded-[var(--radius-lg,0.75rem)] bg-gray-100 px-4 py-3 text-sm text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Retrieving verified findings…
                </div>
              </div>
            )}
          </div>
          <form onSubmit={onSubmit} className="border-t border-gray-200 p-4 dark:border-gray-700">
            {error && <p className="mb-3 text-sm text-red-700 dark:text-red-400">{error}</p>}
            {voiceError && <p className="mb-3 text-sm text-red-700 dark:text-red-400">{voiceError}</p>}
            {listening && <p className="mb-3 flex items-center gap-2 text-sm font-medium text-[var(--brand-primary,#2563eb)]"><span className="h-2 w-2 animate-pulse rounded-full bg-[var(--brand-primary,#2563eb)]" />Listening…</p>}
            <div ref={inputAreaRef} className="relative flex gap-2">
              {showSuggestions && suggestions.length > 0 && (
                <div className="absolute bottom-full left-0 z-10 mb-2 w-full overflow-hidden rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white shadow-[var(--shadow-lg)] dark:border-gray-700 dark:bg-gray-800">
                  {suggestions.map((suggestion, index) => (
                    <button
                      key={suggestion.text}
                      type="button"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => void submitQuestion(suggestion.text)}
                      onMouseEnter={() => setActiveSuggestion(index)}
                      className={`flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm transition ${
                        index === activeSuggestion ? 'bg-blue-50 text-blue-900 dark:bg-blue-950/40 dark:text-blue-200' : 'text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700/50'
                      }`}
                    >
                      <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${CATEGORY_DOT[suggestion.category]}`} />
                      <span className="flex-1 truncate">{suggestion.text}</span>
                      <span className="flex-shrink-0 text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">
                        {CATEGORY_LABEL[suggestion.category]}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              <input
                value={question}
                onChange={onQuestionChange}
                onFocus={onInputFocus}
                onKeyDown={onInputKeyDown}
                placeholder={listening ? 'Listening…' : 'Ask Lexi about governing law, liability, termination…'}
                autoComplete="off"
                className="flex-1 rounded-[var(--radius-md,0.5rem)] border border-gray-300 px-3 py-2 text-sm focus:border-[var(--brand-primary,#2563eb)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary,#3b82f6)]/20 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
              />
              {voiceSupported && (
                <button
                  type="button"
                  onClick={toggleVoiceInput}
                  aria-label={listening ? 'Stop voice input' : 'Ask by voice'}
                  title={listening ? 'Stop voice input' : 'Ask by voice'}
                  className={`flex items-center justify-center rounded-[var(--radius-md,0.5rem)] border px-3 py-2 transition ${
                    listening
                      ? 'border-red-300 bg-red-50 text-red-700 hover:bg-red-100 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400'
                      : 'border-gray-300 text-gray-600 hover:border-[var(--brand-primary,#2563eb)] hover:bg-blue-50 hover:text-[var(--brand-primary,#1d4ed8)] dark:border-gray-600 dark:text-gray-300 dark:hover:bg-blue-950/30'
                  }`}
                >
                  {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                </button>
              )}
              <Button type="submit" disabled={sending || !question.trim()}>
                <Send className="h-4 w-4" />
                Ask
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </PageContainer>
  )
}
