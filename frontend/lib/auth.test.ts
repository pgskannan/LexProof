import { describe, expect, it, vi, beforeEach } from 'vitest'

const signInWithEmailAndPasswordMock = vi.fn()

vi.mock('firebase/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('firebase/auth')>()
  return {
    ...actual,
    signInWithEmailAndPassword: (...args: unknown[]) => signInWithEmailAndPasswordMock(...args),
  }
})

import {
  auth,
  AUTH_INITIALIZING,
  AUTHENTICATED,
  UNAUTHENTICATED,
  getAuthState,
  loginWithEmailPassword,
  mapFirebaseAuthError,
  setAuthState,
  waitForAuthReady,
} from './auth'

describe('auth state helpers', () => {
  it('starts in the initializing state until Firebase restores a user', () => {
    expect(AUTH_INITIALIZING).toBe('AUTH_INITIALIZING')
    expect(getAuthState()).toBe(AUTH_INITIALIZING)
  })

  it('updates the auth state when Firebase reports a user', () => {
    setAuthState(AUTHENTICATED)
    expect(getAuthState()).toBe(AUTHENTICATED)

    setAuthState(UNAUTHENTICATED)
    expect(getAuthState()).toBe(UNAUTHENTICATED)
  })

  it('resolves immediately when a user is already available', async () => {
    const existingUser = { getIdToken: vi.fn().mockResolvedValue('token') }
    const originalCurrentUser = auth.currentUser
    Object.defineProperty(auth, 'currentUser', { configurable: true, value: existingUser })

    try {
      await expect(waitForAuthReady()).resolves.toBe(existingUser)
      expect(getAuthState()).toBe(AUTHENTICATED)
    } finally {
      Object.defineProperty(auth, 'currentUser', { configurable: true, value: originalCurrentUser })
      setAuthState(AUTH_INITIALIZING)
    }
  })
})

describe('loginWithEmailPassword', () => {
  beforeEach(() => {
    signInWithEmailAndPasswordMock.mockReset()
  })

  it('delegates to the official Firebase signInWithEmailAndPassword API with the shared auth instance', async () => {
    const fakeCredential = { user: { uid: 'uid-123', email: 'demo-admin@lexproof.local' } }
    signInWithEmailAndPasswordMock.mockResolvedValueOnce(fakeCredential)

    const result = await loginWithEmailPassword('demo-admin@lexproof.local', 'super-secret')

    // Verifies the wrapper calls Firebase's own API rather than any
    // custom/local credential check -- Firebase Authentication remains the
    // single source of truth. This is a code-contract test: it does not
    // exercise a live Firebase project or issue a real ID token.
    expect(signInWithEmailAndPasswordMock).toHaveBeenCalledTimes(1)
    expect(signInWithEmailAndPasswordMock).toHaveBeenCalledWith(auth, 'demo-admin@lexproof.local', 'super-secret')
    expect(result).toBe(fakeCredential)
  })

  it('propagates rejection from Firebase without swallowing or replacing it', async () => {
    const firebaseError = Object.assign(new Error('Firebase: Error (auth/wrong-password).'), {
      code: 'auth/wrong-password',
    })
    signInWithEmailAndPasswordMock.mockRejectedValueOnce(firebaseError)

    await expect(loginWithEmailPassword('demo-admin@lexproof.local', 'wrong')).rejects.toBe(firebaseError)
  })
})

describe('mapFirebaseAuthError', () => {
  it('maps invalid-credential style errors to a generic, non-revealing message', () => {
    for (const code of ['auth/wrong-password', 'auth/user-not-found', 'auth/invalid-credential']) {
      const message = mapFirebaseAuthError({ code })
      expect(message).toBe('Incorrect email or password.')
      // Must never leak which half (email vs password) was wrong, and never
      // include the raw Firebase code or message text.
      expect(message).not.toContain('auth/')
    }
  })

  it('maps other known Firebase Auth error codes to friendly text', () => {
    expect(mapFirebaseAuthError({ code: 'auth/invalid-email' })).toBe('Enter a valid email address.')
    expect(mapFirebaseAuthError({ code: 'auth/user-disabled' })).toBe('This account has been disabled.')
    expect(mapFirebaseAuthError({ code: 'auth/too-many-requests' })).toContain('Too many attempts')
  })

  it('falls back to a safe generic message for unknown errors and never echoes raw error content', () => {
    const rawError = new Error('some internal Firebase stack trace detail')
    const message = mapFirebaseAuthError(rawError)
    expect(message).toBe('Unable to sign in. Please check your credentials and try again.')
    expect(message).not.toContain('internal Firebase stack trace')
  })

  it('handles non-object/non-Error inputs safely', () => {
    expect(mapFirebaseAuthError(undefined)).toBe('Unable to sign in. Please check your credentials and try again.')
    expect(mapFirebaseAuthError('plain string')).toBe('Unable to sign in. Please check your credentials and try again.')
  })
})
