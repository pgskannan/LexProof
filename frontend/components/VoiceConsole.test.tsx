import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api', () => ({ apiFetch: vi.fn() }))

import { VoiceConsole } from './VoiceConsole'
import {
  buildVoiceTurnRequest,
  countdownLabel,
  countdownSeconds,
  formatTraceArguments,
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
})
