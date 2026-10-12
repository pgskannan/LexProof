'use client'

import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ArrowUp,
  Check,
  ChevronDown,
  Mic,
  MicOff,
  Radio,
  ShieldCheck,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import {
  buildVoiceTurnRequest,
  countdownLabel,
  countdownSeconds,
  formatTraceArguments,
  mergeTrace,
  englishVoices,
  mcpHost,
  pickVoice,
  readHandsFreePreference,
  SPEECH_INPUT_FALLBACK,
  VOICE_PREFERENCE_KEY,
  shouldAutoSend,
  shouldHandleRecognitionEvent,
  shouldPauseHandsFree,
  shouldResumeListening,
  type AwaitingConfirmation,
  type VoiceTraceEntry,
  type VoiceTurnResponse,
} from '../lib/voiceConsole'
import {
  getSpeechRecognitionConstructor,
  speechErrorMessage,
  type SpeechRecognitionEventLike,
  type SpeechRecognitionInstance,
} from '../lib/speechRecognition'

type TranscriptMessage = {
  id: number
  role: 'you' | 'lexi'
  text: string
  isError?: boolean
}

const SUGGESTIONS = [
  'What contracts do I have?',
  'Is the master services agreement verified?',
  'What payments are due this month?',
  "What's waiting for my approval?",
]

const MCP_HEADER = `MCP 2025-11-25 · Streamable HTTP · ${mcpHost()}`

export function TranscriptBubble({
  role,
  text,
  isError = false,
}: Pick<TranscriptMessage, 'role' | 'text' | 'isError'>) {
  const isUser = role === 'you'
  const className = isUser
    ? 'rounded-br-md bg-[#d4f2dd] text-[#183329]'
    : 'rounded-bl-md border border-white/10 bg-[#192723] text-[#f1f5ee]'

  return (
    <div data-state={isError ? 'error' : 'normal'} className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 ${className}`}>
      <p className={`mb-1 font-mono text-[9px] uppercase tracking-[0.12em] ${isUser ? 'text-[#183329]' : 'text-[#b8ccc1]'}`}>
        {isUser ? 'You' : 'Lexi'}
      </p>
      <p className={`whitespace-pre-wrap break-words ${isUser ? 'text-[#183329]' : 'text-[#f1f5ee]'}`}>{text}</p>
    </div>
  )
}

export function VoiceConsole() {
  const [supported, setSupported] = useState(false)
  const [draft, setDraft] = useState('')
  const [interim, setInterim] = useState('')
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [muted, setMuted] = useState(false)
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [voiceName, setVoiceName] = useState('')
  const [handsFree, setHandsFree] = useState(readHandsFreePreference)
  const [handsFreePaused, setHandsFreePaused] = useState(false)
  const [sending, setSending] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<TranscriptMessage[]>([])
  const [trace, setTrace] = useState<VoiceTraceEntry[]>([])
  const [awaiting, setAwaiting] = useState<AwaitingConfirmation | null>(null)
  const [traceOpen, setTraceOpen] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(0)
  const [error, setError] = useState('')
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const finalTranscriptRef = useRef('')
  const messageIdRef = useRef(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const transcriptBottomRef = useRef<HTMLLIElement>(null)
  const turnNumberRef = useRef(0)
  const handsFreeRef = useRef(handsFree)
  const mutedRef = useRef(muted)
  const voiceNameRef = useRef(voiceName)
  const sendingRef = useRef(sending)
  const handsFreePausedRef = useRef(handsFreePaused)
  const hasUserTypedRef = useRef(false)
  const cancelledByUsRef = useRef(false)
  const currentUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null)
  const resumeTimeoutRef = useRef<number | null>(null)

  handsFreeRef.current = handsFree
  mutedRef.current = muted
  voiceNameRef.current = voiceName
  sendingRef.current = sending
  handsFreePausedRef.current = handsFreePaused

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [])

  useEffect(() => {
    transcriptBottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, awaiting])

  useEffect(() => {
    setSupported(Boolean(getSpeechRecognitionConstructor(window)))
  }, [])

  useEffect(() => {
    if (!('speechSynthesis' in window)) return
    try {
      setVoiceName(window.localStorage.getItem(VOICE_PREFERENCE_KEY) || '')
    } catch {
      // No stored preference; the best available voice is used.
    }
    const load = () => setVoices(englishVoices(window.speechSynthesis.getVoices()))
    load()
    window.speechSynthesis.addEventListener('voiceschanged', load)
    return () => window.speechSynthesis.removeEventListener('voiceschanged', load)
  }, [])

  function chooseVoice(name: string) {
    setVoiceName(name)
    voiceNameRef.current = name
    try {
      if (name) window.localStorage.setItem(VOICE_PREFERENCE_KEY, name)
      else window.localStorage.removeItem(VOICE_PREFERENCE_KEY)
    } catch {
      // Preference just isn't remembered.
    }
  }

  useEffect(() => {
    handsFreeRef.current = handsFree
    try {
      window.localStorage.setItem('lexproof-voice-hands-free', String(handsFree))
    } catch {
      // Voice controls remain usable when storage is unavailable.
    }
  }, [handsFree])

  useEffect(() => {
    if (!awaiting) {
      setSecondsLeft(0)
      return
    }
    const update = () => setSecondsLeft(countdownSeconds(awaiting.expires_at))
    update()
    const interval = window.setInterval(update, 1000)
    return () => window.clearInterval(interval)
  }, [awaiting])

  useEffect(() => () => {
    if (resumeTimeoutRef.current !== null) window.clearTimeout(resumeTimeoutRef.current)
    resumeTimeoutRef.current = null
    const recognition = recognitionRef.current
    recognitionRef.current = null
    recognition?.abort()
    cancelledByUsRef.current = true
    currentUtteranceRef.current = null
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  }, [])

  function addMessage(role: TranscriptMessage['role'], text: string, isError = false) {
    if (!text.trim()) return
    messageIdRef.current += 1
    const message = { id: messageIdRef.current, role, text: text.trim(), isError }
    setMessages((current) => [...current, message])
  }

  function stopSpeaking() {
    cancelledByUsRef.current = true
    currentUtteranceRef.current = null
    if (resumeTimeoutRef.current !== null) {
      window.clearTimeout(resumeTimeoutRef.current)
      resumeTimeoutRef.current = null
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    setSpeaking(false)
  }

  function speak(text: string) {
    if (muted || typeof window === 'undefined' || !('speechSynthesis' in window)) return
    stopSpeaking()
    const utterance = new SpeechSynthesisUtterance(text)
    cancelledByUsRef.current = false
    currentUtteranceRef.current = utterance
    const voice = pickVoice(window.speechSynthesis.getVoices(), voiceNameRef.current)
    if (voice) utterance.voice = voice
    utterance.lang = 'en-US'
    utterance.onstart = () => {
      if (currentUtteranceRef.current === utterance) setSpeaking(true)
    }
    utterance.onend = () => {
      if (currentUtteranceRef.current !== utterance) return
      const naturalEnd = !cancelledByUsRef.current
      currentUtteranceRef.current = null
      setSpeaking(false)
      if (!shouldResumeListening({
        handsFree: handsFreeRef.current,
        paused: handsFreePausedRef.current,
        muted: mutedRef.current,
        naturalEnd,
        sending: sendingRef.current,
        typing: hasUserTypedRef.current,
      })) return
      resumeTimeoutRef.current = window.setTimeout(() => {
        resumeTimeoutRef.current = null
        if (shouldResumeListening({
          handsFree: handsFreeRef.current,
          paused: handsFreePausedRef.current,
          muted: mutedRef.current,
          naturalEnd,
          sending: sendingRef.current,
          typing: hasUserTypedRef.current,
        })) startListening()
      }, 350)
    }
    utterance.onerror = (event) => {
      if (currentUtteranceRef.current !== utterance) return
      currentUtteranceRef.current = null
      setSpeaking(false)
      if (event.error === 'interrupted' || event.error === 'canceled') return
    }
    window.speechSynthesis.speak(utterance)
  }

  function startListening() {
    if (recognitionRef.current) return
    if (resumeTimeoutRef.current !== null) {
      window.clearTimeout(resumeTimeoutRef.current)
      resumeTimeoutRef.current = null
    }
    cancelledByUsRef.current = true
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    currentUtteranceRef.current = null
    setSpeaking(false)
    const Recognition = getSpeechRecognitionConstructor(window)
    if (!Recognition) return
    const recognition = new Recognition()
    let hadError = false
    recognition.lang = 'en-US'
    recognition.continuous = false
    recognition.interimResults = true
    finalTranscriptRef.current = ''
    hasUserTypedRef.current = false
    setInterim('')
    setError('')
    recognition.onresult = (rawEvent) => {
      if (!shouldHandleRecognitionEvent(recognitionRef.current, recognition)) return
      const event = rawEvent as SpeechRecognitionEventLike & {
        results: SpeechRecognitionEventLike['results'] & {
          [index: number]: { isFinal?: boolean; 0?: { transcript: string } }
        }
      }
      let finalPart = ''
      let interimPart = ''
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index]
        const text = result?.[0]?.transcript || ''
        if (result?.isFinal) finalPart += text
        else interimPart += text
      }
      if (finalPart) {
        finalTranscriptRef.current += finalPart
        setDraft(finalTranscriptRef.current.trimStart())
      }
      setInterim(interimPart)
    }
    recognition.onerror = (event) => {
      if (!shouldHandleRecognitionEvent(recognitionRef.current, recognition)) return
      if (event.error === 'aborted') return
      hadError = true
      recognitionRef.current = null
      if (shouldPauseHandsFree(event.error)) {
        handsFreePausedRef.current = true
        setHandsFreePaused(true)
      }
      const message = speechErrorMessage(event.error)
      if (message) setError(message)
      setListening(false)
      setInterim('')
    }
    recognition.onend = () => {
      if (!shouldHandleRecognitionEvent(recognitionRef.current, recognition)) return
      setListening(false)
      setInterim('')
      recognitionRef.current = null
      const finalText = finalTranscriptRef.current
      if (shouldAutoSend(finalText, hadError)) {
        finalTranscriptRef.current = ''
        setDraft('')
        void sendTurn(finalText)
      }
    }
    recognitionRef.current = recognition
    setListening(true)
    recognition.start()
  }

  function toggleMicrophone() {
    if (recognitionRef.current && listening) {
      handsFreePausedRef.current = true
      setHandsFreePaused(true)
      recognitionRef.current.stop()
      return
    }
    if (recognitionRef.current) return
    handsFreePausedRef.current = false
    setHandsFreePaused(false)
    startListening()
  }

  async function sendTurn(utterance: string) {
    const clean = utterance.trim()
    if (!clean || sending) return
    turnNumberRef.current += 1
    hasUserTypedRef.current = false
    stopSpeaking()
    setError('')
    addMessage('you', clean)
    setDraft('')
    setInterim('')
    sendingRef.current = true
    setSending(true)
    try {
      const response = await apiFetch('/api/voice/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildVoiceTurnRequest(clean, sessionId)),
      })
      const payload = await response.json() as VoiceTurnResponse
      if (payload.session_id) setSessionId(payload.session_id)
      if (Array.isArray(payload.tool_trace)) {
        setTrace((previous) => mergeTrace(previous, payload.tool_trace, turnNumberRef.current))
      }
      if (payload.awaiting_confirmation) {
        handsFreeRef.current = false
        setHandsFree(false)
      }
      setAwaiting(payload.awaiting_confirmation || null)
      const answer = payload.speech || payload.display_text || 'I could not complete that turn.'
      addMessage('lexi', answer, !response.ok)
      speak(answer)
      if (!response.ok) setError(answer)
    } catch {
      const message = "I couldn't reach LexProof just now."
      addMessage('lexi', message, true)
      setError(message)
      speak(message)
    } finally {
      sendingRef.current = false
      setSending(false)
      setTraceOpen(true)
    }
  }

  function submitDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void sendTurn(draft)
  }

  function cancelConfirmation() {
    setAwaiting(null)
    void sendTurn('cancel')
  }

  const fallbackMessage = supported ? null : SPEECH_INPUT_FALLBACK
  const ringActive = listening || speaking

  return (
    <main className="fixed inset-x-0 bottom-0 top-14 z-10 flex min-h-0 flex-col overflow-hidden bg-gray-50 px-3 py-3 dark:bg-gray-900 sm:px-5 lg:left-64 lg:top-0 lg:px-7 lg:py-4">
      <div className="mx-auto flex h-full min-h-0 w-full max-w-[1440px] flex-col">
      <header className="mb-3 flex flex-none flex-wrap items-end justify-between gap-3 border-b border-gray-200 pb-3 dark:border-gray-700 lg:mb-4 lg:pb-4">
        <div>
          <p className="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-emerald-700 dark:text-emerald-300">
            <Radio aria-hidden="true" className="h-4 w-4" /> Voice workspace
          </p>
          <h1 className="text-2xl font-semibold text-gray-950 dark:text-white sm:text-3xl">Ask Lexi — simulated Alexa+ experience</h1>
          <p className="mt-1.5 text-sm text-gray-600 dark:text-gray-300">Powered by the LexProof MCP server</p>
        </div>
        <div className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
          <ShieldCheck aria-hidden="true" className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          Signed-in organization context
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto] items-stretch gap-3 lg:grid-cols-[minmax(0,1fr)_320px] lg:grid-rows-1 lg:gap-4">
        <section aria-label="Ask Lexi voice console" className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-[24px] border border-[#283c39] bg-[#101b19] text-[#f1f5ee] shadow-[0_24px_70px_-35px_rgba(8,29,25,0.7)] lg:rounded-[28px]">
          <div className="flex flex-none items-center justify-between border-b border-white/10 px-4 py-3 sm:px-6">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-emerald-300/20 bg-emerald-300/10 text-emerald-200">
                <Radio aria-hidden="true" className="h-4 w-4" />
              </span>
              <div>
                <p className="text-sm font-semibold tracking-normal text-[#f1f5ee]">Ask Lexi</p>
                <p className="mt-0.5 text-[10px] leading-4 text-[#b8ccc1]">Simulated Alexa+ experience · powered by the LexProof MCP server</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  const enabled = !handsFreeRef.current
                  handsFreeRef.current = enabled
                  setHandsFree(enabled)
                }}
                disabled={Boolean(awaiting)}
                aria-pressed={handsFree}
                className={`rounded-full border px-3 py-2 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 disabled:cursor-not-allowed disabled:border-white/10 disabled:text-[#b8ccc1] ${handsFree ? 'border-emerald-200/50 bg-emerald-200/10 text-[#f1f5ee]' : 'border-white/20 text-[#b8ccc1]'}`}
              >
                Hands-free {handsFree ? 'On' : 'Off'}
              </button>
              {voices.length > 1 ? (
                <label className="hidden sm:block">
                  <span className="sr-only">Lexi&apos;s voice</span>
                  <select
                    value={voiceName}
                    onChange={(event) => chooseVoice(event.target.value)}
                    className="max-w-[11rem] truncate rounded-full border border-white/20 bg-transparent px-3 py-2 text-xs text-[#f1f5ee] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 [&>option]:bg-[#101b19]"
                  >
                    <option value="">Best voice (auto)</option>
                    {voices.map((voice) => (
                      <option key={voice.name} value={voice.name}>{voice.name}</option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                type="button"
                onClick={() => setMuted((value) => !value)}
                aria-label={muted ? 'Unmute spoken replies' : 'Mute spoken replies'}
                aria-pressed={muted}
                className="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 text-[#bbc9c1] transition hover:border-emerald-200/40 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
              >
                {muted ? <VolumeX aria-hidden="true" className="h-4 w-4" /> : <Volume2 aria-hidden="true" className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="grid min-h-0 flex-1 gap-3 p-3 sm:p-4 xl:grid-cols-[190px_minmax(0,1fr)] xl:gap-4">
            <div className="hidden min-h-0 flex-col items-center justify-center gap-3 xl:flex">
              <div className={`relative flex h-40 w-40 flex-none items-center justify-center rounded-full border transition duration-500 ${ringActive ? 'border-emerald-200/60 shadow-[0_0_0_10px_rgba(120,235,176,0.06),0_0_55px_rgba(89,223,157,0.35)]' : 'border-white/10 shadow-[0_0_0_10px_rgba(255,255,255,0.02)]'}`}>
                {ringActive && <span aria-hidden="true" className="absolute inset-2 animate-ping rounded-full border border-emerald-200/25 [animation-duration:2.4s]" />}
                <div className={`flex h-28 w-28 items-center justify-center rounded-full border transition duration-500 sm:h-36 sm:w-36 ${ringActive ? 'border-emerald-100/50 bg-[#18392e] text-emerald-100' : 'border-white/10 bg-[#172522] text-[#b8ccc1]'}`}>
                  <Radio aria-hidden="true" className={`h-10 w-10 transition ${ringActive ? 'scale-110' : ''}`} strokeWidth={1.3} />
                </div>
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-[#f1f5ee]">{listening ? 'Listening' : speaking ? 'Speaking' : sending ? 'Thinking' : handsFree && handsFreePaused ? 'Hands-free paused — tap the mic to resume' : 'Ready when you are'}</p>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-[#b8ccc1]">{listening ? 'EN-US / LIVE INPUT' : speaking ? 'EN-US / AUDIO OUTPUT' : 'LEXPROOF / MCP'}</p>
              </div>
            </div>

            <div className="flex min-h-0 min-w-0 flex-col">
              <ol aria-live="polite" aria-relevant="additions text" aria-label="Conversation transcript" className="flex min-h-0 flex-1 flex-col space-y-3 overflow-y-auto overscroll-contain pr-1">
                {messages.length === 0 ? (
                  <li className="flex min-h-0 flex-1 items-center justify-center rounded-2xl border border-dashed border-white/10 px-6 text-center text-sm text-[#b8ccc1]">
                    Ask about a contract, a proof passport, payments, or an approval.
                  </li>
                ) : messages.map((message) => (
                  <li key={message.id} className={`flex ${message.role === 'you' ? 'justify-end' : 'justify-start'}`}>
                    <TranscriptBubble role={message.role} text={message.text} isError={message.isError} />
                  </li>
                ))}
                <li ref={transcriptBottomRef} aria-hidden="true" className="h-px list-none" />
              </ol>

              {interim && <p aria-live="polite" className="mt-1 min-h-5 truncate px-2 text-xs italic text-[#b8ccc1]">{interim}</p>}
              {fallbackMessage && <p className="mt-2 text-xs text-amber-200">{fallbackMessage}</p>}
              {error && <p role="alert" className="mt-3 text-xs text-rose-200">{error}</p>}

              {awaiting && (
                <section aria-labelledby="confirm-title" className="mt-2 flex-none rounded-2xl border border-amber-200/30 bg-[#322a17] p-3 sm:p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.13em] text-amber-200">Approval prepared · no change yet</p>
                      <h2 id="confirm-title" className="mt-2 text-sm font-semibold leading-5 text-[#fff7e6]">{awaiting.summary}</h2>
                    </div>
                    <span aria-live="polite" className="flex-shrink-0 rounded-lg border border-amber-100/20 bg-black/20 px-2.5 py-1.5 font-mono text-xs tabular-nums text-amber-100">
                      {secondsLeft > 0 ? countdownLabel(secondsLeft) : 'Expired'}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                    <p className="text-xs text-amber-100">Confirmation code <strong className="ml-1 font-mono text-sm tracking-[0.1em] text-white">{awaiting.short_code}</strong></p>
                    <div className="flex gap-2">
                      <button type="button" onClick={cancelConfirmation} className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-2 text-xs font-medium text-[#d8e2db] hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-100">
                        <X aria-hidden="true" className="h-3.5 w-3.5" /> Cancel
                      </button>
                      <button type="button" onClick={() => void sendTurn('confirm')} disabled={secondsLeft === 0 || sending} className="inline-flex items-center gap-1.5 rounded-lg bg-amber-200 px-3 py-2 text-xs font-semibold text-[#30260f] hover:bg-amber-100 disabled:cursor-not-allowed disabled:bg-[#5b4d2b] disabled:text-[#fff7e6] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">
                        <Check aria-hidden="true" className="h-3.5 w-3.5" /> Confirm
                      </button>
                    </div>
                  </div>
                </section>
              )}

              <div className="mt-2 flex flex-none flex-wrap gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => void sendTurn(suggestion)} disabled={sending} className="rounded-full border border-white/10 bg-white/[0.035] px-3 py-2 text-left text-[11px] leading-4 text-[#c0cec5] transition hover:border-emerald-200/30 hover:bg-emerald-100/10 hover:text-white disabled:cursor-wait focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200">
                    {suggestion}
                  </button>
                ))}
              </div>

              <form onSubmit={submitDraft} className="mt-2 flex flex-none items-center gap-2 rounded-2xl border border-white/15 bg-[#0b1311] p-2 focus-within:border-emerald-200/40 focus-within:ring-1 focus-within:ring-emerald-200/20">
                {supported && (
                    <button
                    type="button"
                      onClick={toggleMicrophone}
                      disabled={Boolean(awaiting)}
                    aria-label={listening ? 'Stop listening' : 'Start voice input'}
                    aria-pressed={listening}
                    className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200 ${listening ? 'bg-rose-400/15 text-rose-200' : 'text-[#b8ccc1] hover:bg-white/5 hover:text-white'}`}
                  >
                    {listening ? <MicOff aria-hidden="true" className="h-4 w-4" /> : <Mic aria-hidden="true" className="h-4 w-4" />}
                  </button>
                )}
                <input
                  ref={inputRef}
                  value={draft}
                  onChange={(event) => {
                    hasUserTypedRef.current = Boolean(event.target.value)
                    stopSpeaking()
                    setDraft(event.target.value)
                  }}
                  placeholder="Ask Lexi anything about your portfolio…"
                  aria-label="Message Ask Lexi"
                  className="h-10 min-w-0 flex-1 bg-transparent px-1 text-sm text-white placeholder:text-[#b8ccc1] focus:outline-none"
                />
                <button type="submit" disabled={!draft.trim() || sending} aria-label="Send message" className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-emerald-200 text-[#143026] transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">
                  <ArrowUp aria-hidden="true" className="h-4 w-4" />
                </button>
              </form>
              <p className="mt-1 px-1 font-mono text-[9px] text-[#b8ccc1]">TAP THE MIC AND SPEAK · OR TYPE AND PRESS ENTER</p>
            </div>
          </div>
        </section>

        <aside aria-label="MCP tool trace" className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
          <button type="button" onClick={() => setTraceOpen((open) => !open)} aria-expanded={traceOpen} className="flex w-full flex-none items-center justify-between gap-3 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500 md:cursor-default">
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-gray-950 dark:text-white">MCP trace</span>
              <span className="mt-1 block break-all font-mono text-[10px] leading-4 text-gray-500 dark:text-gray-400">{MCP_HEADER}</span>
            </span>
            <ChevronDown aria-hidden="true" className={`h-4 w-4 flex-shrink-0 text-gray-500 transition md:hidden ${traceOpen ? 'rotate-180' : ''}`} />
          </button>
          <div className={`${traceOpen ? 'flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain' : 'hidden'} border-t border-gray-200 dark:border-gray-700 md:flex md:min-h-0 md:flex-1 md:flex-col md:overflow-y-auto md:overscroll-contain`}>
            {trace.length === 0 ? (
              <div className="px-4 py-7 text-center">
                <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 text-gray-500 dark:bg-gray-900 dark:text-gray-400">
                  <Radio aria-hidden="true" className="h-4 w-4" />
                </div>
                <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">Tool calls appear here as Lexi works.</p>
              </div>
            ) : (
              <ol className="divide-y divide-gray-100 dark:divide-gray-700">
                {trace.map((item, index) => item.kind === 'turn' ? (
                  <li key={`turn-${item.turn}-${index}`} className="bg-gray-50 px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-wide text-gray-600 dark:bg-gray-900 dark:text-gray-300">
                    Turn {item.turn}
                  </li>
                ) : (
                  <li key={`${item.turn}-${item.tool}-${index}`} className="px-4 py-3.5">
                    <div className="flex items-center justify-between gap-3">
                      <code className="min-w-0 break-all text-xs font-semibold text-gray-900 dark:text-gray-100">{item.tool}</code>
                      <span className={`flex-shrink-0 rounded-full px-2 py-0.5 font-mono text-[9px] font-bold uppercase ${item.ok ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300' : 'bg-rose-50 text-rose-800 dark:bg-rose-950 dark:text-rose-300'}`}>{item.ok ? 'ok' : 'err'}</span>
                    </div>
                    <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-gray-50 p-2.5 font-mono text-[10px] leading-4 text-gray-600 dark:bg-gray-900 dark:text-gray-300">{formatTraceArguments(item.arguments_summary)}</pre>
                    <p className="mt-2 text-right font-mono text-[10px] tabular-nums text-gray-500 dark:text-gray-400">{Math.max(0, item.latency_ms)} ms</p>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <p className="flex-none border-t border-gray-200 px-4 py-2 text-[10px] leading-4 text-gray-600 dark:border-gray-700 dark:text-gray-300">Calls run as you, under your organization access.</p>
        </aside>
      </div>
      </div>
    </main>
  )
}
