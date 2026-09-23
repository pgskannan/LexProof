import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  User,
} from "firebase/auth"
import { firebaseAuth } from "./firebase"

export const AUTH_INITIALIZING = "AUTH_INITIALIZING" as const
export const AUTHENTICATED = "AUTHENTICATED" as const
export const UNAUTHENTICATED = "UNAUTHENTICATED" as const

export type AuthState = typeof AUTH_INITIALIZING | typeof AUTHENTICATED | typeof UNAUTHENTICATED

const provider = new GoogleAuthProvider()

export const auth = firebaseAuth

// Existing Google sign-in. Unchanged.
export const login = () => signInWithPopup(auth, provider)
export const logout = () => signOut(auth)
export type CurrentUser = User

// Email/Password sign-in via Firebase Authentication (the same provider-agnostic
// Firebase Auth instance used by Google sign-in above). Returns a real Firebase
// UserCredential; the app never issues or inspects a token itself -- the
// resulting ID token is obtained the same way it already is for Google, via
// the Firebase SDK's own onAuthStateChanged/getIdToken machinery.
export const loginWithEmailPassword = (email: string, password: string) =>
  signInWithEmailAndPassword(auth, email, password)

// Maps Firebase Auth error codes to short, user-facing text. Never surfaces
// the raw Firebase error message, a stack trace, or any credential value.
export function mapFirebaseAuthError(error: unknown): string {
  const code =
    typeof error === "object" && error !== null && "code" in error
      ? String((error as { code?: unknown }).code)
      : ""

  switch (code) {
    case "auth/invalid-email":
      return "Enter a valid email address."
    case "auth/user-not-found":
    case "auth/wrong-password":
    case "auth/invalid-credential":
      return "Incorrect email or password."
    case "auth/user-disabled":
      return "This account has been disabled."
    case "auth/too-many-requests":
      return "Too many attempts. Please wait a moment and try again."
    case "auth/network-request-failed":
      return "Network error. Check your connection and try again."
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      return "Sign-in was cancelled."
    default:
      return "Unable to sign in. Please check your credentials and try again."
  }
}

let currentAuthState: AuthState = AUTH_INITIALIZING

export function getAuthState(): AuthState {
  return currentAuthState
}

export function setAuthState(nextState: AuthState) {
  currentAuthState = nextState
}

export function waitForAuthReady(): Promise<User | null> {
  if (auth.currentUser) {
    setAuthState(AUTHENTICATED)
    return Promise.resolve(auth.currentUser)
  }

  if (currentAuthState === UNAUTHENTICATED) {
    return Promise.resolve(null)
  }

  return new Promise((resolve) => {
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    let unsubscribe: (() => void) | undefined

    const cleanup = () => {
      if (timeoutId) clearTimeout(timeoutId)
      unsubscribe?.()
    }

    unsubscribe = onAuthStateChanged(auth, (user) => {
      cleanup()
      const nextState = user ? AUTHENTICATED : UNAUTHENTICATED
      setAuthState(nextState)
      resolve(user ?? null)
    })

    timeoutId = setTimeout(() => {
      cleanup()
      const user = auth.currentUser ?? null
      setAuthState(user ? AUTHENTICATED : UNAUTHENTICATED)
      resolve(user)
    }, 5000)
  })
}
