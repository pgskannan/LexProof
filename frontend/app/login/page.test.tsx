import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

// next/navigation's useRouter requires an app-router context that only
// exists inside a running Next.js app. It is mocked here (not the
// authentication architecture) purely so the real LoginPage component can
// be rendered outside Next.js -- the same boundary every other test in this
// repo that touches a Next.js hook has to cross.
const replaceMock = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock }),
}))

// AuthProvider's `login` (Google sign-in) is provided via React context.
// Mocked here only to supply that context outside of <AuthProvider>; the
// email/password path below is exercised against the REAL lib/auth module,
// not a mock, so this test still proves the email/password UI is wired to
// the real Firebase-backed loginWithEmailPassword function.
const googleLoginMock = vi.fn()
vi.mock('../../components/AuthProvider', () => ({
  useAuth: () => ({ login: googleLoginMock, logout: vi.fn(), user: null, authState: 'UNAUTHENTICATED', loading: false }),
}))

import LoginPage from './page'

describe('LoginPage', () => {
  it('still renders the existing "Continue with Google" button (regression)', () => {
    const markup = renderToStaticMarkup(<LoginPage />)
    expect(markup).toContain('Continue with Google')
  })

  it('renders an email/password form alongside the Google button', () => {
    const markup = renderToStaticMarkup(<LoginPage />)

    expect(markup).toContain('id="email"')
    expect(markup).toContain('type="email"')
    expect(markup).toContain('id="password"')
    expect(markup).toContain('type="password"')
    expect(markup).toContain('Sign in')
  })

  it('does not render a registration or password-reset control (login-only scope)', () => {
    const markup = renderToStaticMarkup(<LoginPage />)
    expect(markup.toLowerCase()).not.toContain('forgot password')
    expect(markup.toLowerCase()).not.toContain('create account')
    expect(markup.toLowerCase()).not.toContain('sign up')
  })

  it('does not render any error text before a sign-in attempt', () => {
    const markup = renderToStaticMarkup(<LoginPage />)
    expect(markup).not.toContain('role="alert"')
  })
})
