import { test as base, type Page } from '@playwright/test'
import { getE2EEnv } from '../helpers/env'
import { loginViaUI } from '../auth/login'

// Phase 3J-A: a single fixture that performs a REAL login (real login page,
// real Firebase email/password auth, real redirect) before handing the test
// an already-authenticated page. Kept intentionally minimal -- one fixture,
// no seeded org/contract/workflow state (that is explicitly out of scope
// for this phase; see the Phase 3I E2E readiness audit).

type Fixtures = {
  authenticatedPage: Page
}

export const test = base.extend<Fixtures>({
  authenticatedPage: async ({ page }, use) => {
    const env = getE2EEnv()
    await loginViaUI(page, env.userEmail, env.userPassword)
    await use(page)
  },
})

export { expect } from '@playwright/test'
