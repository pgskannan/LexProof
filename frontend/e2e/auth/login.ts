import { expect, type Page } from '@playwright/test'

// Phase 3J-A: drives the REAL LexProof login page (frontend/app/login/page.tsx)
// through its actual email/password form -- no mocked Firebase, no injected
// token, no test-only bypass. Selectors are taken directly from that page's
// real markup (#email, #password, the "Sign in" submit button, and the
// role="alert" error element), so a change to the real login UI will make
// this helper fail loudly rather than silently drift from the app.
//
// Phase 3J-A forensic diagnosis (post-hoc correction): the login page's own
// top-level element is <main> (app/login/page.tsx), and its real error is
// the only role="alert" element inside it. Sonner's global <Toaster/>
// (app/layout.tsx) is mounted as a SIBLING of the page content, not inside
// it, but also exposes a role="alert" node -- so an unscoped
// page.getByRole('alert') can resolve to Sonner's unrelated, empty alert
// instead of the real one, producing a content-free "(no message)" failure.
// Scoping to main excludes Sonner's node entirely and is structural, not a
// cosmetic/text-based guess -- it will not silently re-break if the error
// copy changes.
//
// Email/password is used instead of "Continue with Google" because Google's
// OAuth popup flow has known browser-automation/COOP restrictions (see
// Phase 3I authentication audit) -- this is a test-infrastructure choice,
// not a weakening of the app's own authentication, which is untouched.

// First-run OnboardingTour (role="dialog" name="Product tour") auto-starts
// when GET /api/preferences/ui returns tour_completed: false. That GET is
// async and can resolve after dashboard is already showing, so the overlay
// may appear in the middle of a later click. Playwright's locator handler
// dismisses it through the real "Skip tour" button whenever it intercepts
// an action -- including after a remount on navigation, if the PATCH has
// not landed yet. Registered once per page because loginViaUI runs twice
// in the golden-path test (owner, then reviewer).
const pagesWithTourHandler = new WeakSet<Page>()

export async function dismissProductTourWhenShown(page: Page): Promise<void> {
  if (pagesWithTourHandler.has(page)) return
  pagesWithTourHandler.add(page)
  await page.addLocatorHandler(page.getByRole('dialog', { name: 'Product tour' }), async (tour) => {
    await tour.getByRole('button', { name: 'Skip tour' }).click()
  })
}

export async function loginViaUI(page: Page, email: string, password: string): Promise<void> {
  await dismissProductTourWhenShown(page)
  await page.goto('/login')
  await expect(page.locator('#email')).toBeVisible()

  await page.locator('#email').fill(email)
  await page.locator('#password').fill(password)

  const alert = page.locator('main').getByRole('alert')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()

  // Race the real outcomes: either Firebase authenticates and the app
  // redirects to /dashboard, or the real login page renders its real
  // role="alert" error. Whichever happens first is reported as-is -- this
  // helper never assumes success.
  await Promise.race([
    page.waitForURL('**/dashboard**', { timeout: 15_000 }),
    alert.waitFor({ state: 'visible', timeout: 15_000 }),
  ])

  if (await alert.isVisible().catch(() => false)) {
    const message = (await alert.textContent()) || '(no message)'
    throw new Error(`LexProof login failed: real login page reported "${message}"`)
  }

  await expect(page).toHaveURL(/\/dashboard/)
}

// Opens the account menu (data-tour="account-menu", from
// frontend/components/Navigation.tsx) and clicks the real "Sign out" menu
// item, which calls the real AuthProvider logout -> Firebase signOut.
export async function logoutViaUI(page: Page): Promise<void> {
  await page.locator('[data-tour="account-menu"]').click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()
  await page.waitForURL('**/login**', { timeout: 10_000 })
}
