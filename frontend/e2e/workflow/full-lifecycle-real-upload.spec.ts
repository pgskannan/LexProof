import { test, expect, type Page } from '@playwright/test'
import { getWorkflowE2EEnv, getAdminCredentials } from '../helpers/env'
import { loginViaUI, logoutViaUI } from '../auth/login'

// E2E workflow audit follow-up (Phase 3): the ONE test in this repo that
// proves the complete real lifecycle starting from a fresh upload, not a
// pre-seeded fixture -- real contract creation, real document upload, real
// Gemini AI analysis producing a real finding, real redline-proposal
// creation and submission, real reviewer approval, real persistence across
// reload AND a full logout/login cycle, and a real audit-trail check.
//
// This is deliberately SEPARATE from workflow/golden-path-review-approval.
// spec.ts, which stays fast and deterministic (pre-seeded fixture) and
// remains the primary CI regression gate. This test depends on live Vertex
// AI/Gemini availability and can take 1-2 minutes for the analysis step
// alone -- run it when you want end-to-end proof of the real upload path,
// not on every save.
//
// Because the AI-generated finding's exact title is not deterministic, this
// test opens whichever finding is FIRST in the (freshly uploaded, single-
// document) list rather than matching specific text -- the golden-path and
// negative-security specs already prove exact-finding-selection behavior
// against deterministic fixtures.

const LEXPROOF_DEMO_ORG_ID = 'lexproof-demo'
const LEXPROOF_DEMO_ORG_NAME = 'LexProof Demo'
const PROPOSED_TEXT =
  'The total liability cap for any claim shall be the greater of $700,000 or ' +
  'eighteen (18) months of fees paid in the preceding year.'

function persistedProposalStatus(page: Page, status: 'DRAFT' | 'PROPOSED' | 'APPROVED' | 'Not saved') {
  return page.getByText('Persisted status', { exact: true }).locator('..').getByText(status, { exact: true })
}

async function selectLexProofDemoOrg(page: Page) {
  // demo-owner-1 belongs to more than one org. Upload stamps X-Org-Id onto
  // the new contract; proposal create refuses contracts with no org_id
  // ("Contract is not assigned to an organization"). Select the shared demo
  // org before upload so owner, reviewer, and admin can all see this contract.
  const orgSelect = page.getByRole('combobox', { name: 'Organization' })
  await expect(orgSelect.getByRole('option', { name: LEXPROOF_DEMO_ORG_NAME })).toBeAttached({ timeout: 15_000 })
  await orgSelect.selectOption({ label: LEXPROOF_DEMO_ORG_NAME })
  await expect(orgSelect).toHaveValue(LEXPROOF_DEMO_ORG_ID)
}

function uniqueContractDocument(): { name: string; buffer: Buffer } {
  const marker = `E2E-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const text = `MASTER SERVICES AGREEMENT (${marker})

This Master Services Agreement (this "Agreement") is entered into by and between
Acme Advisory Group and Northwind Systems, Inc. (the "Parties").

1. SERVICES. Provider will deliver the professional services described in the
Statement of Work.

2. LIABILITY CAP. The total liability cap for any claim is $100,000.

3. TERM. This Agreement will continue until terminated in accordance with Section 7.

4. CONFIDENTIALITY. Each Party shall maintain the confidentiality of non-public
information disclosed in connection with this Agreement.

5. PAYMENT. Customer will pay Fees within thirty (30) days after invoice.
`
  return { name: `e2e-full-lifecycle-${marker}.txt`, buffer: Buffer.from(text, 'utf-8') }
}

test('full lifecycle: real upload -> real AI analysis -> real finding -> submit -> approve -> persistence -> audit trail', async ({ page }) => {
  // Real Gemini analysis plus four Firebase logins cannot fit in Playwright's
  // 30s default, or even test.slow()'s 90s triple. Analysis alone is budgeted
  // at up to 3 minutes (including Vertex 429 backoff).
  test.setTimeout(360_000)
  const env = getWorkflowE2EEnv()
  // Read admin credentials up front so a missing E2E_ADMIN_* fails before
  // a live Gemini analysis, not after it.
  const admin = getAdminCredentials()
  const doc = uniqueContractDocument()
  let contractId = ''

  await test.step('Owner (demo-owner-1): real Firebase login', async () => {
    await loginViaUI(page, env.ownerEmail, env.ownerPassword)
    await selectLexProofDemoOrg(page)
  })

  await test.step('Owner: create the contract by uploading a real, unique document through the real UI', async () => {
    await page.goto('/dashboard/contracts')
    await expect(page.getByRole('combobox', { name: 'Organization' })).toHaveValue(LEXPROOF_DEMO_ORG_ID)
    await expect(page.getByRole('button', { name: 'Upload and analyze' })).toBeEnabled()
    await page.locator('input[type="file"]').setInputFiles({
      name: doc.name,
      mimeType: 'text/plain',
      buffer: doc.buffer,
    })
    await page.getByRole('button', { name: 'Upload and analyze' }).click()
  })

  await test.step('Owner: wait for the real Gemini analysis to finish (redirects to the legal passport only on success)', async () => {
    // Do not wait the full analysis budget if Vertex already failed in the UI
    // (429 Resource exhausted used to sit here until the 90s test timeout).
    const analysisFailed = page.getByRole('status').filter({ hasText: /failed|429|exhausted/i })
    await Promise.race([
      page.waitForURL(/\/legal-passport\?contractId=/, { timeout: 180_000 }),
      analysisFailed.waitFor({ state: 'visible', timeout: 180_000 }).then(async () => {
        const detail = ((await page.getByRole('status').textContent()) || '').trim()
        throw new Error(`Gemini analysis did not complete: ${detail || 'unknown error'}`)
      }),
    ])
    const url = new URL(page.url())
    contractId = url.searchParams.get('contractId') ?? ''
    expect(contractId, 'no contractId query param after a successful upload+analyze redirect').not.toBe('')
  })

  await test.step('Owner: open the findings list for this exact new contract and confirm real analysis produced at least one finding', async () => {
    await page.goto(`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`)
    await expect(
      page.locator('table tbody tr').first(),
      'real Gemini analysis of the uploaded document produced no findings -- cannot continue the lifecycle test without at least one',
    ).toBeVisible({ timeout: 30_000 })
  })

  await test.step('Owner: open the first real finding and create a real redline proposal for it', async () => {
    await page.locator('table tbody tr').first().click()
    await page.getByRole('button', { name: 'Review Finding' }).click()
    await expect(page).toHaveURL(/\/compliance-command-center\/remediation/)
    // No proposal exists yet for a brand-new finding -- the badge says so.
    await expect(persistedProposalStatus(page, 'Not saved')).toBeVisible({ timeout: 30_000 })
  })

  await test.step('Owner: the real "Save proposal" action creates AND submits the proposal in one step (non-empty text)', async () => {
    const proposed = page.getByLabel('Proposed text')
    await proposed.fill(PROPOSED_TEXT)
    await expect(proposed).toHaveValue(PROPOSED_TEXT)
    await page.getByRole('button', { name: 'Save proposal' }).click()
    await expect(
      persistedProposalStatus(page, 'PROPOSED'),
      'Save with non-empty proposed text must submit for review (PROPOSED), not keep an empty DRAFT',
    ).toBeVisible({ timeout: 15_000 })
  })

  await test.step('Owner: logout', async () => {
    await logoutViaUI(page)
  })

  await test.step('Reviewer (demo-reviewer-1): real Firebase login, open the SAME contract/finding, approve', async () => {
    await loginViaUI(page, env.reviewerEmail, env.reviewerPassword)
    await selectLexProofDemoOrg(page)
    await page.goto(`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`)
    await page.locator('table tbody tr').first().click()
    await page.getByRole('button', { name: 'Review Finding' }).click()
    await expect(page).toHaveURL(/\/compliance-command-center\/remediation/)
    await expect(persistedProposalStatus(page, 'PROPOSED')).toBeVisible({ timeout: 30_000 })
    await page.getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(persistedProposalStatus(page, 'APPROVED')).toBeVisible({ timeout: 15_000 })
  })

  await test.step('Persistence (Phase 5), part 1: a plain browser refresh still shows APPROVED -- this is real persisted Firestore state, not a React state variable', async () => {
    await page.reload()
    await expect(persistedProposalStatus(page, 'APPROVED')).toBeVisible({ timeout: 30_000 })
  })

  await test.step('Reviewer: logout', async () => {
    await logoutViaUI(page)
  })

  await test.step('Persistence (Phase 5), part 2: logout, log back in as the owner, and APPROVED still persists after a full session cycle', async () => {
    await loginViaUI(page, env.ownerEmail, env.ownerPassword)
    await selectLexProofDemoOrg(page)
    await page.goto(`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`)
    await page.locator('table tbody tr').first().click()
    await page.getByRole('button', { name: 'Review Finding' }).click()
    await expect(persistedProposalStatus(page, 'APPROVED')).toBeVisible({ timeout: 30_000 })
  })

  await test.step('Owner: logout', async () => {
    await logoutViaUI(page)
  })

  await test.step('Audit trail (Phase 6): admin logs in and sees real audit-log entries for this exact contract, in the real UI', async () => {
    await loginViaUI(page, admin.adminEmail, admin.adminPassword)
    await selectLexProofDemoOrg(page)
    await page.goto(`/dashboard/admin/audit-log?contract_id=${encodeURIComponent(contractId)}`)
    // ACTION_LABELS in the real audit-log page maps these exact backend
    // action strings (services/audit.py / api/contracts.py / api/
    // redline_proposals.py) to this exact human-readable text.
    await expect(page.getByText('Contract uploaded', { exact: true }).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Redline approved', { exact: true }).first()).toBeVisible()
    await logoutViaUI(page)
  })
})
