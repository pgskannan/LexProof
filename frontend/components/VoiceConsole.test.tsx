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
  shouldAutoSend,
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
  })
})
