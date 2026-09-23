import { test, expect } from '@playwright/test'
import { getE2EEnv } from '../helpers/env'
import { loginViaUI, logoutViaUI } from '../auth/login'

// Phase 3J-A smoke test -- proves the E2E foundation end to end using the
// REAL LexProof frontend, REAL Firebase email/password authentication, and
// the REAL running backend. No mocked Firebase, no fake token, no test-only
// auth bypass, no seeded org/contract/workflow data. This deliberately does
// NOT touch the contract workflow, Reviewer/Approver roles, or blockchain --
// that is Phase 3J-B and beyond.
//
// Requires both the frontend (npm run dev) and the backend (uvicorn) to
// already be running locally, and E2E_USER_EMAIL / E2E_USER_PASSWORD to be
// set to a real, already-provisioned LexProof user. See e2e/README.md.

test('real login -> real Firebase auth -> real backend -> authenticated navigation -> logout', async ({ page }) => {
  const env = getE2EEnv()

  await test.step('1-2. browser launches and the real LexProof frontend loads', async () => {
    const response = await page.goto('/')
    expect(response, 'the frontend dev server did not respond at all').not.toBeNull()
  })

  await test.step('3. an unauthenticated visitor is sent to the real login page', async () => {
    // AuthProvider (components/AuthProvider.tsx) redirects any signed-out
    // visitor away from a protected route to /login. No session exists yet
    // in this fresh browser context, so landing on a protected route proves
    // the real redirect guard, not a mock.
    await page.goto('/dashboard')
    await page.waitForURL('**/login**', { timeout: 15_000 })
    await expect(page.locator('#email')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
  })

  let apiRequestSeen = false
  page.on('request', (request) => {
    if (request.url().includes('/api/')) apiRequestSeen = true
  })

  await test.step('4-6. real credentials submit through the real form and Firebase authenticates', async () => {
    // loginViaUI fills #email/#password and clicks the real "Sign in"
    // button; it throws with the real page's own role="alert" text if
    // Firebase rejects the credentials, rather than assuming success.
    await loginViaUI(page, env.userEmail, env.userPassword)
    await expect(page).toHaveURL(/\/dashboard/)
  })

  await test.step('7. the authenticated page makes real requests to the real backend', async () => {
    // OrgProvider calls GET /api/me (via lib/api.ts's apiFetch, which attaches
    // a real Firebase ID token as Authorization: Bearer <token>) as soon as
    // the user is authenticated. app/api/[...path] proxies /api/* to
    // NEXT_PUBLIC_API_URL -- a real network hop to the real backend, not a mock.
    await expect.poll(() => apiRequestSeen, {
      message: 'no request to /api/* was observed after authenticating -- the authenticated page never called the real backend',
      timeout: 10_000,
    }).toBe(true)
  })

  await test.step('8. the authenticated session survives navigation', async () => {
    await page.goto('/dashboard/contracts')
    // A dropped session would bounce back to /login (same AuthProvider guard
    // exercised in step 3); staying on an authenticated route proves the
    // session, not just the one page load right after sign-in.
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('[data-tour="account-menu"]')).toBeVisible()
  })

  await test.step('9. logout works through the real UI', async () => {
    await logoutViaUI(page)
    await expect(page).toHaveURL(/\/login/)
    // Confirms the session is actually gone, not just that the page navigated.
    await page.goto('/dashboard')
    await page.waitForURL('**/login**', { timeout: 15_000 })
  })

  // 10. browser ends cleanly: Playwright tears down the context/browser
  // automatically at the end of the test; no explicit action needed, and
  // reaching this point with no thrown error/timeout is the proof.
})
