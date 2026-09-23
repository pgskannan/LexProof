# LexProof browser E2E (Phase 3J-A foundation)

Minimal Playwright foundation. Proves real login -> real Firebase auth ->
real backend -> authenticated navigation -> logout. Does **not** yet cover
the contract workflow (Contract Owner -> Reviewer -> Approver -> ...),
Reviewer/Approver actions, or blockchain anchoring -- that is a later phase.

## Prerequisites

1. Backend running locally (real backend, real Firestore/Firebase project --
   there is no separate E2E backend): `uvicorn ...` on the port your
   `frontend/.env.local`'s `NEXT_PUBLIC_API_URL` points at (`http://localhost:8000`
   by default).
2. Frontend running locally: `npm run dev` (default `http://localhost:3000`).
3. A real, already-provisioned LexProof user (email/password). This phase
   does **not** seed one -- use an existing account, ideally a dedicated
   test/QA user rather than a real customer.
4. Copy `.env.e2e.local.example` to `.env.e2e.local` and fill in
   `E2E_USER_EMAIL` / `E2E_USER_PASSWORD`. That file is git-ignored.

## Running

```
npm run test:e2e          # headless, list reporter
npx playwright test --headed        # watch it run
npx playwright test --debug         # step through interactively
npx playwright show-report          # after a CI run (html reporter)
```

## Structure

- `playwright.config.ts` -- config (chromium only, localhost-only baseURL
  guard, trace/screenshot/video on failure).
- `e2e/helpers/env.ts` -- validates required env vars with a clear error.
- `e2e/auth/login.ts` -- drives the real login page's real email/password
  form; a `logoutViaUI` counterpart for the real "Sign out" menu item.
- `e2e/fixtures/auth.fixture.ts` -- an `authenticatedPage` fixture for
  *future* tests that need to start already signed in (not used by the
  smoke test itself, since that test deliberately also proves the
  unauthenticated redirect).
- `e2e/smoke/auth.smoke.spec.ts` -- the one smoke test for this phase.

## Authentication

Real Firebase email/password sign-in only, through the real login page.
No mocked Firebase, no injected/fake token, no test-only auth bypass, no
hard-coded credentials. Google popup sign-in is intentionally not automated
here (known OAuth-popup/COOP friction under browser automation) -- this is a
test-infrastructure choice only; the app's Google sign-in itself is untouched.

## Environment safety

LexProof has one Firebase project (`lexproof-afc7c`) and no separate
E2E/staging deployment or a deployed production URL in this repository.
`playwright.config.ts` refuses to run against any non-`localhost`/`127.0.0.1`
`E2E_BASE_URL` unless `E2E_ALLOW_REMOTE=true` is set explicitly. Use a
dedicated test user, never a real customer's credentials.
