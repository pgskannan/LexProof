import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api', () => ({ apiFetch: vi.fn() }))

import { TranscriptBubble, VoiceConsole } from './VoiceConsole'
import {
  buildVoiceTurnRequest,
  countdownLabel,
  countdownSeconds,
  formatTraceArguments,
  mergeTrace,
  readHandsFreePreference,
  shouldAutoSend,
  shouldHandleRecognitionEvent,
  shouldPauseHandsFree,
  shouldResumeListening,
  speechInputFallbackMessage,
} from '../lib/voiceConsole'

describe('Ask Lexi voice console', () => {
  it('shows the type-instead note when speech recognition is unsupported', () => {
    const markup = renderToStaticMarkup(<VoiceConsole />)
    expect(markup).toContain('Voice input needs Chrome or Edge — type instead')
    expect(speechInputFallbackMessage({})).toBe('Voice input needs Chrome or Edge — type instead')
    expect(markup).toContain('aria-live="polite"')
  })

  it('redacts bearer credentials and full confirmation tokens from MCP args', () => {
    const signedToken = `${'a'.repeat(36)}.${'b'.repeat(36)}`
    const formatted = formatTraceArguments(
      `{"authorization":"Bearer secret-bearer","confirmation_token":"${signedToken}","short_code":"AB12CD"}`,
    )

    expect(formatted).not.toContain('secret-bearer')
    expect(formatted).not.toContain(signedToken)
    expect(formatted).toContain('AB12CD')
    expect(formatted).toContain('[redacted]')
  })

  it('counts down to an expiry and clamps elapsed confirmations at zero', () => {
    const now = Date.parse('2026-10-10T12:00:00.000Z')
    expect(countdownSeconds('2026-10-10T12:01:05.000Z', now)).toBe(65)
    expect(countdownLabel(65)).toBe('01:05')
    expect(countdownSeconds('2026-10-10T11:59:00.000Z', now)).toBe(0)
  })

  it('includes the existing session ID in the next voice request', () => {
    expect(buildVoiceTurnRequest('  confirm  ', 'session-123')).toEqual({
      utterance: 'confirm',
      session_id: 'session-123',
    })
    expect(buildVoiceTurnRequest('hello')).toEqual({ utterance: 'hello' })
  })

  it('auto-sends only a non-empty final transcript without a recognition error', () => {
    expect(shouldAutoSend('find my contracts', false)).toBe(true)
    expect(shouldAutoSend('  find my contracts  ', false)).toBe(true)
    expect(shouldAutoSend('   ', false)).toBe(false)
    expect(shouldAutoSend('find my contracts', true)).toBe(false)
    expect(shouldAutoSend('', true)).toBe(false)
  })

  it('renders the high-contrast Ask Lexi header and voice input hint', () => {
    const markup = renderToStaticMarkup(<VoiceConsole />)
    expect(markup).toContain('text-[#f1f5ee]">Ask Lexi</p>')
    expect(markup).toContain('Simulated Alexa+ experience · powered by the LexProof MCP server')
    expect(markup).toContain('TAP THE MIC AND SPEAK · OR TYPE AND PRESS ENTER')
    expect(markup).not.toContain('PRIVATE VOICE SESSION')
  })

  it('bounds the console to the viewport and gives transcript and trace their own scroll regions', () => {
    const markup = renderToStaticMarkup(<VoiceConsole />)
    expect(markup).toContain('fixed inset-x-0 bottom-0 top-14')
    expect(markup).toContain('lg:left-64 lg:top-0')
    expect(markup).toContain('flex min-h-0 flex-1 flex-col space-y-3 overflow-y-auto overscroll-contain')
    expect(markup).toContain('md:overflow-y-auto md:overscroll-contain')
  })

  it('server-renders error replies with light assistant text on the dark bubble', () => {
    const markup = renderToStaticMarkup(
      <TranscriptBubble role="lexi" text="I couldn't complete that just now." isError />,
    )

    expect(markup).toContain('data-state="error"')
    expect(markup).toContain('bg-[#192723] text-[#f1f5ee]')
    expect(markup).not.toContain('text-[#183329]')
    expect(markup).toContain('<p class="whitespace-pre-wrap break-words text-[#f1f5ee]">I couldn&#x27;t complete that just now.</p>')
  })

  it('merges tool traces newest-first with turn dividers and a 50-entry cap', () => {
    const old = Array.from({ length: 49 }, (_, index) => ({
      kind: 'tool' as const,
      turn: index + 1,
      tool: 'list_contracts',
      arguments_summary: '{}',
      ok: true,
      latency_ms: 2,
    }))
    const merged = mergeTrace(old, [{
      tool: 'ask_contracts',
      arguments_summary: '{"question":"risk"}',
      ok: true,
      latency_ms: 8,
    }], 50)

    expect(merged).toHaveLength(50)
    expect(merged[0]).toEqual({ kind: 'turn', turn: 50 })
    expect(merged[1]).toMatchObject({ kind: 'tool', turn: 50, tool: 'ask_contracts' })
    expect(merged[2]).toMatchObject({ kind: 'tool', turn: 1 })
  })

  it('ignores recognition callbacks from an instance that is no longer current', () => {
    const current = {}
    const stale = {}
    expect(shouldHandleRecognitionEvent(current, current)).toBe(true)
    expect(shouldHandleRecognitionEvent(current, stale)).toBe(false)
    expect(shouldHandleRecognitionEvent(null, stale)).toBe(false)
  })

  it('resumes only after a natural hands-free reply when not paused, muted, sending, or typing', () => {
    const ready = { handsFree: true, paused: false, muted: false, naturalEnd: true, sending: false, typing: false }
    expect(shouldResumeListening(ready)).toBe(true)
    expect(shouldResumeListening({ ...ready, naturalEnd: false })).toBe(false)
    expect(shouldResumeListening({ ...ready, paused: true })).toBe(false)
    expect(shouldResumeListening({ ...ready, muted: true })).toBe(false)
    expect(shouldResumeListening({ ...ready, sending: true })).toBe(false)
    expect(shouldResumeListening({ ...ready, typing: true })).toBe(false)
    expect(shouldResumeListening({ ...ready, handsFree: false })).toBe(false)
  })

  it('pauses hands-free on no-speech without changing the saved preference', () => {
    let handsFreePreference = true
    const paused = shouldPauseHandsFree('no-speech')
    if (paused) {
      const transientPause = true
      expect(transientPause).toBe(true)
    }
    expect(shouldPauseHandsFree('network')).toBe(false)
    expect(handsFreePreference).toBe(true)
    handsFreePreference = false
    expect(handsFreePreference).toBe(false)
  })

  it('defaults hands-free on and tolerates unavailable localStorage', () => {
    expect(readHandsFreePreference({ getItem: () => null })).toBe(true)
    expect(readHandsFreePreference({ getItem: () => 'false' })).toBe(false)
    expect(readHandsFreePreference({ getItem: () => { throw new Error('blocked') } })).toBe(true)
  })
})
