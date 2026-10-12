import { isSpeechRecognitionSupported } from './speechRecognition'

export type VoiceTurnRequest = {
  utterance: string
  session_id?: string
}

export type VoiceToolTrace = {
  tool: string
  arguments_summary: string
  ok: boolean
  latency_ms: number
}

export type VoiceTraceEntry =
  | { kind: 'turn'; turn: number }
  | ({ kind: 'tool'; turn: number } & VoiceToolTrace)

export type AwaitingConfirmation = {
  short_code: string
  summary: string
  expires_at: string
}

export type VoiceTurnResponse = {
  session_id: string
  speech: string
  display_text: string
  tool_trace: VoiceToolTrace[]
  awaiting_confirmation: AwaitingConfirmation | null
}

export const SPEECH_INPUT_FALLBACK = 'Voice input needs Chrome or Edge — type instead'

export function shouldAutoSend(finalText: string, hadError: boolean): boolean {
  return !hadError && finalText.trim().length > 0
}

export function shouldHandleRecognitionEvent<T>(current: T | null, instance: T): boolean {
  return current === instance
}

export function shouldPauseHandsFree(error: string): boolean {
  return error === 'no-speech'
}

export function shouldResumeListening({
  handsFree,
  paused,
  muted,
  naturalEnd,
  sending,
  typing,
}: {
  handsFree: boolean
  paused: boolean
  muted: boolean
  naturalEnd: boolean
  sending: boolean
  typing: boolean
}): boolean {
  return handsFree && !paused && !muted && naturalEnd && !sending && !typing
}

export function readHandsFreePreference(storage?: Pick<Storage, 'getItem'>): boolean {
  try {
    const localStorageRef = storage ?? (typeof window === 'undefined' ? undefined : window.localStorage)
    return localStorageRef?.getItem('lexproof-voice-hands-free') !== 'false'
  } catch {
    return true
  }
}

export function mergeTrace(
  previous: VoiceTraceEntry[],
  turnTrace: VoiceToolTrace[],
  turnNumber: number,
): VoiceTraceEntry[] {
  const currentTurn: VoiceTraceEntry[] = [
    { kind: 'turn', turn: turnNumber },
    ...turnTrace.map((entry) => ({ kind: 'tool' as const, turn: turnNumber, ...entry })),
  ]
  return [...currentTurn, ...previous].slice(0, 50)
}

export function speechInputFallbackMessage(win?: unknown): string | null {
  return isSpeechRecognitionSupported(win) ? null : SPEECH_INPUT_FALLBACK
}

export function buildVoiceTurnRequest(utterance: string, sessionId?: string | null): VoiceTurnRequest {
  const body: VoiceTurnRequest = { utterance: utterance.trim() }
  if (sessionId) body.session_id = sessionId
  return body
}

export function countdownSeconds(expiresAt: string, now = Date.now()): number {
  const timestamp = Date.parse(expiresAt)
  if (!Number.isFinite(timestamp)) return 0
  return Math.max(0, Math.ceil((timestamp - now) / 1000))
}

export function countdownLabel(seconds: number): string {
  const remaining = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(remaining / 60)
  const rest = remaining % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

export function formatTraceArguments(value: string | null | undefined): string {
  if (!value?.trim()) return 'No arguments'
  return value
    .replace(/\bBearer\s+[^\s,;"']+/gi, 'Bearer [redacted]')
    .replace(/("(?:authorization|access_token|bearer_token|confirmation_token|token)"\s*:\s*")[^"]*(")/gi, '$1[redacted]$2')
    .replace(/("confirmation_code"\s*:\s*")(?:[^"]{13,}|[^"]*\.[^"]*)(")/gi, '$1[redacted]$2')
    .replace(/\b(?:authorization|access_token|bearer_token|confirmation_token|token)\s*[=:]\s*[^\s,;"'}]+/gi, 'credential=[redacted]')
    .replace(/(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])/g, '[redacted]')
}

export function mcpHost(apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'): string {
  try {
    return new URL(apiUrl).host
  } catch {
    return apiUrl || 'same host'
  }
}


export type VoiceLike = { name: string; lang: string }

export const VOICE_PREFERENCE_KEY = 'lexproof-voice-name'

// Browser neural voices sound far less robotic than the legacy desktop (SAPI)
// voices that getVoices() often lists first on Windows. Lower score = better.
const PREFERRED_VOICE_PATTERNS: RegExp[] = [
  /\b(aria|jenny|ava|emma|michelle)\b.*natural/i,
  /natural/i,
  /^google us english$/i,
  /\b(samantha|ava|allison)\b/i,
  /online/i,
  /^google/i,
]

export function voiceScore(voice: VoiceLike): number {
  const lang = voice.lang.toLowerCase().replace('_', '-')
  if (!lang.startsWith('en')) return Number.POSITIVE_INFINITY
  const index = PREFERRED_VOICE_PATTERNS.findIndex((pattern) => pattern.test(voice.name))
  let score = index === -1 ? PREFERRED_VOICE_PATTERNS.length : index
  if (lang !== 'en-us') score += 0.5
  if (/desktop/i.test(voice.name)) score += 10
  return score
}

export function englishVoices<T extends VoiceLike>(voices: readonly T[]): T[] {
  return voices
    .filter((voice) => Number.isFinite(voiceScore(voice)))
    .sort((a, b) => voiceScore(a) - voiceScore(b) || a.name.localeCompare(b.name))
}

export function pickVoice<T extends VoiceLike>(voices: readonly T[], preferredName?: string | null): T | undefined {
  if (preferredName) {
    const chosen = voices.find((voice) => voice.name === preferredName)
    if (chosen) return chosen
  }
  return englishVoices(voices)[0]
}
