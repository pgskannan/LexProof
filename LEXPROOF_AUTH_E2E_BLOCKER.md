# LEXPROOF_AUTH_E2E_BLOCKER

## Environment

- Frontend: LexProof Next.js app running at http://localhost:3000/login
- Backend: FastAPI app running at http://localhost:8000
- Firebase project: `lexproof-afc7c`
- Browser: Playwright/browser automation session

## Authentication sequence

1. User lands on http://localhost:3000/login
2. User clicks `Continue with Google`
3. Frontend executes `signInWithPopup(auth, provider)` from `frontend/lib/auth.ts`
4. Firebase Auth initializes and creates an auth iframe
5. Browser attempts OAuth popup flow
6. The flow stalls or fails before returning a Firebase user / ID token
7. `onAuthStateChanged` never receives an authenticated user
8. AuthProvider never transitions the app into the authenticated route

## Exact failure point

The execution stops at the Firebase popup OAuth step inside `signInWithPopup(auth, provider)` in `frontend/lib/auth.ts`.

Observed browser behavior:

- The main login page changes to `Signing in...`
- A Firebase auth iframe exists
- No popup is observed by the automation harness reaching `accounts.google.com`
- The popup lifecycle fails with Firebase auth error `auth/popup-closed-by-user`
- The main page never reaches the authenticated dashboard, and `onAuthStateChanged` is never driven by a real Firebase user

## Browser console evidence

Observed console errors:

- `Cross-Origin-Opener-Policy policy would block the window.closed call.`
- `Failed to load resource: the server responded with a status of 401 (Unauthorized)` for `http://localhost:8000/api/preferences/ui`

Observed browser-side auth state:

- Page count increased during the login attempt
- A second page with the same origin (`http://localhost:3000/login`) appeared and contained `Firebase: Error (auth/popup-closed-by-user).`
- The original login page remained on `Signing in...`

## Network evidence

Observed network activity during the login attempt:

- `https://lexproof-afc7c.firebaseapp.com/__/auth/iframe?...` -> HTTP 200
- `https://identitytoolkit.googleapis.com/v1/projects?key=...` -> HTTP 200
- `https://www.googleapis.com/identitytoolkit/v3/relyingparty/getProjectConfig?key=...` -> HTTP 200
- `http://localhost:8000/api/preferences/ui` -> HTTP 401 (unauthenticated request; background noise, not the auth blocker)

Not observed:

- Any request to `accounts.google.com`
- Any request to `securetoken.googleapis.com`
- Any request to `identitytoolkit.googleapis.com` for sign-in or token exchange that would indicate OAuth completed

## Firebase configuration evidence

Frontend configuration source:

- `frontend/.env.local`
- `frontend/lib/firebase.ts`

Current frontend config values:

- `NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSyBF4wDcRtEy8yB9kuKi476AYxzIhjgf9k4`
- `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=lexproof-afc7c.firebaseapp.com`
- `NEXT_PUBLIC_FIREBASE_PROJECT_ID=lexproof-afc7c`
- `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=lexproof-afc7c.firebasestorage.app`
- `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=1095554027100`
- `NEXT_PUBLIC_FIREBASE_APP_ID=1:1095554027100:web:e3968865a8cf8f3f402099`

The app is using `GoogleAuthProvider` and `signInWithPopup(auth, provider)` in `frontend/lib/auth.ts`.

A direct Firebase config endpoint query returned:

- `projectId`: `1095554027100`
- `authorizedDomains`: `[localhost, lexproof-afc7c.firebaseapp.com, lexproof-afc7c.web.app, 127.0.0.1]`

This confirms the Firebase project metadata is loaded and the configured domains include both `localhost` and `127.0.0.1`.

## Root cause

### Classification

- C. Browser popup restriction
- H. Test harness limitation

### Root cause statement

The Firebase project configuration appears consistent, and the frontend is correctly configured to use Google sign-in via Firebase Auth. The actual login attempt does not reach the Google OAuth provider, because the browser automation environment is blocking or mishandling the popup flow used by `signInWithPopup`. The observed `auth/popup-closed-by-user` error, the lack of any `accounts.google.com` requests, and the fact that a direct `window.open('https://accounts.google.com')` test from the page returned `opened = false` indicate that the popup is not completing in this environment.

This is not a LexProof app logic failure at the moment; it is a browser/popup restriction in the automation environment that prevents the real OAuth popup from completing.

## Recommended fix

Smallest correct fix:

1. Validate the Google sign-in flow in a real browser session outside this Playwright/browser-automation harness.
2. If the popup is blocked in the harness, use a non-automated browser or switch the auth test to a redirect-based flow for that environment.
3. Do not change the LexProof application code until the real browser flow is verified.

## Final status

- AUTH E2E STATUS: BLOCKED
- ROOT CAUSE: C/H — browser popup restriction / test harness limitation
- NEXT ACTION: Confirm the login flow in a normal interactive browser session; if it still fails there, then investigate Firebase Console OAuth/provider settings and Google console configuration.
