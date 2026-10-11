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
