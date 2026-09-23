/**
 * Thin wrapper around the browser's native Web Speech API
 * (SpeechRecognition / webkitSpeechRecognition). This needs no external
 * service, API key, or credential -- it runs entirely in the browser -- so
 * unlike this backlog's other "stub now, wire in real credentials later"
 * items, voice input is fully real today with nothing to swap in later.
 * Support varies by browser (Chrome/Edge: yes, Firefox/Safari: historically
 * no), so every caller must feature-detect with
 * `isSpeechRecognitionSupported()` and hide the affordance entirely when
 * unsupported, rather than show a button that silently does nothing.
 */

export type SpeechRecognitionResultLike = {
  length: number
  [index: number]: { [index: number]: { transcript: string } }
}

export type SpeechRecognitionEventLike = {
  results: SpeechRecognitionResultLike
}

export type SpeechRecognitionErrorEventLike = {
  error: string
}

export type SpeechRecognitionInstance = {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onend: (() => void) | null
}

export type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance

type SpeechWindow = {
  SpeechRecognition?: SpeechRecognitionConstructor
  webkitSpeechRecognition?: SpeechRecognitionConstructor
}

/** Returns the browser's SpeechRecognition constructor, preferring the
 * standard name over the vendor-prefixed one, or null when neither exists
 * (SSR, or a browser without support). Accepts an explicit `win` so this is
 * testable without a real browser. */
export function getSpeechRecognitionConstructor(
  win: unknown = typeof window !== 'undefined' ? window : undefined,
): SpeechRecognitionConstructor | null {
  const candidate = win as SpeechWindow | undefined
  return candidate?.SpeechRecognition ?? candidate?.webkitSpeechRecognition ?? null
}

export function isSpeechRecognitionSupported(win?: unknown): boolean {
  return getSpeechRecognitionConstructor(win) !== null
}

/** Concatenates every result's top transcript into one string -- the
 * running transcript-so-far for an in-progress (interimResults: true)
 * recognition session. */
export function transcriptFrom(event: SpeechRecognitionEventLike): string {
  let transcript = ''
  for (let i = 0; i < event.results.length; i++) {
    transcript += event.results[i]?.[0]?.transcript ?? ''
  }
  return transcript
}

/** Human-readable message for a SpeechRecognition error event's `.error`
 * code. Returns '' for "aborted", since that's the expected outcome of the
 * user clicking stop themselves and should not surface as an error. */
export function speechErrorMessage(code: string): string {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'Microphone access was denied. Allow microphone access to use voice input.'
    case 'no-speech':
      return "Didn't catch that — no speech detected."
    case 'audio-capture':
      return 'No microphone was found.'
    case 'network':
      return 'A network error interrupted voice recognition.'
    case 'aborted':
      return ''
    default:
      return 'Voice input failed. Try typing your question instead.'
  }
}
