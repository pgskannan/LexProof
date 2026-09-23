# LEXPROOF_E2E_VERIFICATION

## Current status

E2E verification is currently BLOCKED pending manual confirmation that Google login works successfully in a normal interactive Chrome browser.

## What has been verified

### Authentication flow evidence

- Frontend Google login is implemented via `signInWithPopup(auth, provider)` in `frontend/lib/auth.ts`.
- Firebase client initialization is configured in `frontend/lib/firebase.ts` using:
  - `NEXT_PUBLIC_FIREBASE_API_KEY`
  - `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`
  - `NEXT_PUBLIC_FIREBASE_PROJECT_ID`
  - `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET`
  - `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID`
  - `NEXT_PUBLIC_FIREBASE_APP_ID`
- Firebase project metadata returned by the live config endpoint confirms:
  - `projectId = 1095554027100`
  - `authorizedDomains = [localhost, lexproof-afc7c.firebaseapp.com, lexproof-afc7c.web.app, 127.0.0.1]`
- Browser automation has confirmed the Google popup flow is blocked in this environment.
- Browser automation evidence showed the app hangs at `Signing in...`, with no `accounts.google.com` OAuth exchange and a Firebase error `auth/popup-closed-by-user`.

### Existing E2E auth support in repo

- `firebase.json` currently defines only Firestore and Storage configuration.
- There is no Firebase Auth emulator configuration in the repository.
- No application code currently uses `connectAuthEmulator`, `signInWithCustomToken`, or an existing E2E test auth fixture for Firebase Auth.

## Manual confirmation required

Please confirm the following in a normal interactive Chrome browser outside this browser automation environment:

1. Open `http://localhost:3000/login`
2. Click `Continue with Google`
3. Complete the Google sign-in flow normally
4. Confirm the app redirects to the authenticated dashboard and the Firebase user is available in the browser

If that succeeds, then the following is true:

- Real Google/Firebase authentication is verified manually.
- No DEV_AUTH_BYPASS is needed.
- No weakening of production authentication is needed.
- The production Google authentication mechanism remains in place.

## Secure deterministic automated E2E strategy after manual verification

Once manual Chrome login is confirmed, the automated E2E setup should use one of the following, in order of preference:

### A. Existing Firebase test/emulator authentication if already supported

- Prefer an existing Firebase Auth emulator or test-auth mechanism already present in the project.
- If the project does not already support this, do not invent a bypass.

### B. Dedicated E2E authentication fixture that creates a legitimate test-authenticated session without Google popup

- Use Firebase Auth APIs only in a dedicated E2E/test-only path.
- Preserve the full application stack: Firebase authenticated identity → AuthProvider → backend token verification → tenant/user resolution → RBAC → application APIs.
- Only replace the external Google popup interaction for automation.
- Never store real Google credentials or user passwords in the repository.
- Never automate a real user’s Google credentials.

### C. Reuse a previously authenticated browser storage state only if it is deterministic, isolated, non-production, and safe

- Only use this if the session state is clearly test-owned and isolated from production data.
- The session must be deterministic and safe for local E2E execution.

## Next step after manual Chrome confirmation

Once manual Chrome login is verified, we can proceed to the deterministic E2E authenticated-session strategy and then resume the Golden Path:

- Login/session
- Contracts
- Contract
- Findings
- Redlines
- Human Review
- Approval
- Publish
- V2 Analysis
- Legal Passport
- Blockchain Anchor
- Audit

## Current blocker

This is currently a BLOCKED E2E verification task because the remaining unknown is the manual interactive Chrome result. The automation environment has clearly proven that the popup-based Google flow is not viable there, but we have not yet received confirmation that the same flow succeeds in a normal browser session.
