import { describe, expect, it } from 'vitest'
import { defaultApiBase, embedSnippet, widgetScriptUrl } from './embedWidget'

describe('widgetScriptUrl', () => {
  it('appends the widget filename and trims a trailing slash on the origin', () => {
    expect(widgetScriptUrl('https://app.lexproof.example/')).toBe(
      'https://app.lexproof.example/lexproof-verify-widget.js',
    )
  })
})

describe('defaultApiBase', () => {
  it('uses the configured API base when one is provided', () => {
    expect(defaultApiBase('https://app.lexproof.example', 'https://api.lexproof.example/')).toBe(
      'https://api.lexproof.example',
    )
  })

  it('falls back to the frontend origin when no API base is configured', () => {
    expect(defaultApiBase('https://app.lexproof.example', '')).toBe('https://app.lexproof.example')
    expect(defaultApiBase('https://app.lexproof.example', undefined)).toBe('https://app.lexproof.example')
  })
})

describe('embedSnippet', () => {
  it('builds the two-tag HTML snippet with the API base and no verify-page link', () => {
    const snippet = embedSnippet({
      evidenceId: 'evd-123',
      scriptOrigin: 'https://app.lexproof.example',
      apiBase: 'https://api.lexproof.example',
    })
    expect(snippet).toBe(
      '<script src="https://app.lexproof.example/lexproof-verify-widget.js" data-api-base="https://api.lexproof.example" async></script>\n' +
        '<div class="lexproof-verify" data-lexproof-evidence-id="evd-123"></div>',
    )
  })

  it('includes a data-lexproof-verify-page attribute when a verify-page origin is given', () => {
    const snippet = embedSnippet({
      evidenceId: 'evd-123',
      scriptOrigin: 'https://app.lexproof.example',
      apiBase: 'https://api.lexproof.example',
      verifyPageOrigin: 'https://app.lexproof.example/',
    })
    expect(snippet).toContain('data-lexproof-verify-page="https://app.lexproof.example/public-verify"')
  })
})
