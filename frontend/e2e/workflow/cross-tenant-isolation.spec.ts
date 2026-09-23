import { test, expect, type Page } from '@playwright/test'
import { getWorkflowE2EEnv, getTenantBCredentials } from '../helpers/env'
import { loginViaUI, logoutViaUI } from '../auth/login'

// E2E security/workflow follow-up, Phase 2: proves real tenant isolation
// through real Firebase auth and real backend authorization -- not a
// parallel/invented tenant model, but a genuinely separate second
// organization built through the same OrganizationService API every real
// org in this app goes through (see
// backend/scripts/create_approval_demo_fixture.py's
// create_cross_tenant_isolation_fixture()).
//
// Tenant A reuses the EXISTING demo-owner-1/demo-reviewer-1 identities and
// org ("lexproof-demo" / "LexProof Demo") already used throughout this
// suite, plus one new dedicated contract
// (demo-cross-tenant-a-master-services-agreement) so this test never shares
// fixture state with golden-path/pending-review/duplicate-approval/
// dual-role-sod. Tenant B ("lexproof-demo-tenant-b" /
// "LexProof Demo Tenant B") is an entirely separate org with its own real
// owner (demo-tenant-b-owner-1) and reviewer (demo-tenant-b-reviewer-1).
//
// Each test proves TWO things for one identity:
//   ALLOWED -- real UI: navigating to their own tenant's contract shows the
//     real finding (GET /api/findings, org-membership-filtered -- see
//     api/findings.py's _visible()).
//   DENIED  -- real backend: a direct, authenticated GET to the OTHER
//     tenant's contract (api/contracts.py's get_contract /
//     _is_visible_to_user), using a real token captured from that exact
//     session, returns the application's real, intended 404 (that endpoint
//     never distinguishes "exists in another org" from "does not exist" --
//     see _is_visible_to_user's comments). No admin token is ever used to
//     simulate a normal user; each identity uses only its own real session.
//
// Six of the task's requested scenarios (Owner A/Reviewer A -> Tenant A
// ALLOWED and -> Tenant B DENIED; Owner B/Reviewer B -> Tenant A DENIED) are
// covered across the four tests below; each test also incidentally proves
// its own tenant's reciprocal ALLOWED case for the other three combinations
// as a sanity check.
//
// Fixture required: backend/scripts/create_approval_demo_fixture.py
// --fixture cross-tenant-isolation.

const ORG_A_NAME = 'LexProof Demo'
const ORG_A_ID = 'lexproof-demo'
const ORG_B_NAME = 'LexProof Demo Tenant B'
const ORG_B_ID = 'lexproof-demo-tenant-b'

const CROSS_TENANT_A_CONTRACT_ID = 'demo-cross-tenant-a-master-services-agreement'
const CROSS_TENANT_A_FINDING_TITLE = 'Liability cap is too low'
const CROSS_TENANT_B_CONTRACT_ID = 'demo-cross-tenant-b-master-services-agreement'
const CROSS_TENANT_B_FINDING_TITLE = 'Payment terms are one-sided'

async function selectOrg(page: Page, orgName: string, orgId: string) {
  const orgSelect = page.getByRole('combobox', { name: 'Organization' })
  await expect(orgSelect.getByRole('option', { name: orgName })).toBeAttached({ timeout: 15_000 })
  await orgSelect.selectOption({ label: orgName })
  await expect(orgSelect).toHaveValue(orgId)
}

// Opens the real findings page for one tenant's contract, confirms the real
// AI finding is visible (proof of ALLOWED access), and captures the real
// Firebase ID token apiFetch (lib/api.ts) attaches to the GET /api/findings
// request this navigation triggers -- reused below for the DENIED direct
// backend call, from this exact session, never fabricated or an admin token.
async function openOwnContractAndCaptureAuth(
  page: Page,
  orgName: string,
  orgId: string,
  contractId: string,
  findingTitle: string,
): Promise<string> {
  await selectOrg(page, orgName, orgId)
  const [findingsResponse] = await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes('/api/findings') && response.url().includes(`contract_id=${contractId}`) && response.request().method() === 'GET',
    ),
    page.goto(`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`),
  ])
  await expect(page.getByText(findingTitle, { exact: true }).first()).toBeVisible({ timeout: 30_000 })
  const authorizationHeader = findingsResponse.request().headers()['authorization'] ?? ''
  expect(authorizationHeader).not.toBe('')
  return authorizationHeader
}

async function expectContractDenied(page: Page, authorizationHeader: string, otherTenantContractId: string) {
  // api/contracts.py's get_contract(): a contract that exists but is not
  // _is_visible_to_user() to this actor returns the SAME 404 as a contract
  // that does not exist at all -- the application's own intended behavior
  // (never leaks "it exists, you just can't see it" via a 403 here).
  const response = await page.request.get(`/api/contracts/${otherTenantContractId}`, {
    headers: { Authorization: authorizationHeader },
  })
  expect(response.status(), await response.text()).toBe(404)
}

test.describe('cross-tenant isolation: real Tenant A vs. real Tenant B', () => {
  test('4E-1: Owner A can access Tenant A\'s contract; cannot access Tenant B\'s contract', async ({ page }) => {
    test.setTimeout(120_000)
    const env = getWorkflowE2EEnv()

    await test.step('Owner A (demo-owner-1) logs in', async () => {
      await loginViaUI(page, env.ownerEmail, env.ownerPassword)
    })

    let token = ''
    await test.step('ALLOWED: real UI shows Tenant A\'s own finding', async () => {
      token = await openOwnContractAndCaptureAuth(page, ORG_A_NAME, ORG_A_ID, CROSS_TENANT_A_CONTRACT_ID, CROSS_TENANT_A_FINDING_TITLE)
    })

    await test.step('Tenant B is not even offered as an org to switch into', async () => {
      const orgSelect = page.getByRole('combobox', { name: 'Organization' })
      await expect(orgSelect.getByRole('option', { name: ORG_B_NAME })).toHaveCount(0)
    })

    await test.step('DENIED: real backend 404 on Tenant B\'s contract, using Owner A\'s own real token', async () => {
      await expectContractDenied(page, token, CROSS_TENANT_B_CONTRACT_ID)
    })

    await test.step('logout', async () => {
      await logoutViaUI(page)
    })
  })

  test('4E-2: Reviewer A can access Tenant A\'s contract; cannot access Tenant B\'s contract', async ({ page }) => {
    test.setTimeout(120_000)
    const env = getWorkflowE2EEnv()

    await test.step('Reviewer A (demo-reviewer-1) logs in', async () => {
      await loginViaUI(page, env.reviewerEmail, env.reviewerPassword)
    })

    let token = ''
    await test.step('ALLOWED: real UI shows Tenant A\'s own finding', async () => {
      token = await openOwnContractAndCaptureAuth(page, ORG_A_NAME, ORG_A_ID, CROSS_TENANT_A_CONTRACT_ID, CROSS_TENANT_A_FINDING_TITLE)
    })

    await test.step('DENIED: real backend 404 on Tenant B\'s contract, using Reviewer A\'s own real token', async () => {
      await expectContractDenied(page, token, CROSS_TENANT_B_CONTRACT_ID)
    })

    await test.step('logout', async () => {
      await logoutViaUI(page)
    })
  })

  test('4E-3: Owner B can access Tenant B\'s contract; cannot access Tenant A\'s contract', async ({ page }) => {
    test.setTimeout(120_000)
    const { tenantBOwnerEmail, tenantBOwnerPassword } = getTenantBCredentials()

    await test.step('Owner B (demo-tenant-b-owner-1) logs in', async () => {
      await loginViaUI(page, tenantBOwnerEmail, tenantBOwnerPassword)
    })

    let token = ''
    await test.step('ALLOWED: real UI shows Tenant B\'s own finding', async () => {
      token = await openOwnContractAndCaptureAuth(page, ORG_B_NAME, ORG_B_ID, CROSS_TENANT_B_CONTRACT_ID, CROSS_TENANT_B_FINDING_TITLE)
    })

    await test.step('Tenant A is not even offered as an org to switch into', async () => {
      const orgSelect = page.getByRole('combobox', { name: 'Organization' })
      await expect(orgSelect.getByRole('option', { name: ORG_A_NAME })).toHaveCount(0)
    })

    await test.step('DENIED: real backend 404 on Tenant A\'s contract, using Owner B\'s own real token', async () => {
      await expectContractDenied(page, token, CROSS_TENANT_A_CONTRACT_ID)
    })

    await test.step('logout', async () => {
      await logoutViaUI(page)
    })
  })

  test('4E-4: Reviewer B can access Tenant B\'s contract; cannot access Tenant A\'s contract', async ({ page }) => {
    test.setTimeout(120_000)
    const { tenantBReviewerEmail, tenantBReviewerPassword } = getTenantBCredentials()

    await test.step('Reviewer B (demo-tenant-b-reviewer-1) logs in', async () => {
      await loginViaUI(page, tenantBReviewerEmail, tenantBReviewerPassword)
    })

    let token = ''
    await test.step('ALLOWED: real UI shows Tenant B\'s own finding', async () => {
      token = await openOwnContractAndCaptureAuth(page, ORG_B_NAME, ORG_B_ID, CROSS_TENANT_B_CONTRACT_ID, CROSS_TENANT_B_FINDING_TITLE)
    })

    await test.step('DENIED: real backend 404 on Tenant A\'s contract, using Reviewer B\'s own real token', async () => {
      await expectContractDenied(page, token, CROSS_TENANT_A_CONTRACT_ID)
    })

    await test.step('logout', async () => {
      await logoutViaUI(page)
    })
  })
})
