import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'

const { authMock } = vi.hoisted(() => ({
  authMock: { currentUser: null as null | { getIdToken: (forceRefresh?: boolean) => Promise<string> } },
}))

vi.mock('../lib/auth', () => ({ auth: authMock }))

import { ConnectAssistantPanel, assistantMcpUrl, copyCurrentFirebaseToken } from './ConnectAssistantPanel'

describe('ConnectAssistantPanel', () => {
  beforeEach(() => {
    authMock.currentUser = null
  })

  it('renders the endpoint, protocol, tools, token warning, and Inspector setup', () => {
    const markup = renderToStaticMarkup(<ConnectAssistantPanel />)
    expect(markup).toContain('MCP 2025-11-25 · Streamable HTTP')
    expect(markup).toContain('http://localhost:8000/mcp')
    expect(markup).toContain('upcoming_obligations')
    expect(markup).toContain('prepare_decision')
    expect(markup).toContain('confirm_decision')
    expect(markup).toContain('Expires in about 1 hour. Treat it like a password.')
    expect(markup).toContain('Authorization: Bearer &lt;token&gt;')
  })

  it('uses the configured API URL without adding a duplicate slash', () => {
    expect(assistantMcpUrl('https://api.example.test/')).toBe('https://api.example.test/mcp')
  })

  it('force-refreshes the signed-in user token and copies it without retaining it', async () => {
    const user = { getIdToken: vi.fn().mockResolvedValue('short-lived-token') }
    const clipboard = { writeText: vi.fn().mockResolvedValue(undefined) }
    authMock.currentUser = user

    await expect(copyCurrentFirebaseToken(authMock.currentUser, clipboard)).resolves.toBe(true)
    expect(user.getIdToken).toHaveBeenCalledWith(true)
    expect(clipboard.writeText).toHaveBeenCalledWith('short-lived-token')
    expect(JSON.stringify(authMock)).not.toContain('short-lived-token')
  })

  it('does not copy when there is no signed-in user', async () => {
    const clipboard = { writeText: vi.fn().mockResolvedValue(undefined) }
    await expect(copyCurrentFirebaseToken(null, clipboard)).resolves.toBe(false)
    expect(clipboard.writeText).not.toHaveBeenCalled()
  })
})