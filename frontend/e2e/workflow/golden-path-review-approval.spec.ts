import { test, expect, type Page } from '@playwright/test'
import { getWorkflowE2EEnv } from '../helpers/env'
import { resetGoldenPathFixture } from '../helpers/resetGoldenPathFixture'
import { loginViaUI, logoutViaUI } from '../auth/login'

// Phase 3K-A: proves the first half of the real, role-separated LexProof
// golden-path workflow through the actual browser UI -- real Firebase
// email/password auth per role, the real backend, and the real
// separation-of-duties enforcement (services/workflow_engine.py's
// requires_not_actor rule on the "approve" transition). No mocked auth, no
// API calls made by this test to transition state, no direct Firestore
// writes, and no admin account is used for either action.
//
// Starts from the Phase 3J-B deterministic fixture (backend/scripts/
// create_approval_demo_fixture.py --fixture golden-path), which seeds
// exactly one proposal for org "lexproof-demo" / contract
// "demo-golden-path-master-services-agreement", left at the workflow's
// initial "draft" state (see workflow_catalog.py's CONTRACT_REDLINE_STATES).
//
// A naming note, confirmed by reading the actual frontend source before
// writing any selector below (there is no literal "Submit for Review" or
// "Review Approval" button anywhere in this codebase -- grepped for both
// strings, zero matches): the UI's real action names are "Save proposal"
// and "Approve". Both trigger the exact backend transitions the task names:
//   - "Save proposal" with non-empty proposed text -> PATCH
//     /api/redline-proposals/{id} -> ProposalService.update() -> workflow
//     transition "submit_for_review" (draft -> in_review) when the
//     proposal was still in draft. This IS the real Submit for Review
//     action, just not labeled that in the UI.
//   - "Approve" -> POST /api/redline-proposals/{id}/review -> workflow
//     transition "approve" (in_review -> approved). This IS the real
//     Review Approval action.
// The proposal's user-facing status badge mirrors the workflow state via
// PROPOSAL_STATUS_BY_STATE (workflow_catalog.py): draft -> "DRAFT",
// in_review -> "PROPOSED", approved -> "APPROVED" -- so this test asserts
// on those exact displayed strings as its evidence of the underlying
// workflow state, since that badge is the UI's only surfaced
// representation of it.

const GOLDEN_PATH_ORG_ID = 'lexproof-demo'
const GOLDEN_PATH_ORG_NAME = 'LexProof Demo'
const GOLDEN_PATH_CONTRACT_ID = 'demo-golden-path-master-services-agreement'
const GOLDEN_PATH_CONTRACT_NAME = 'Demo Golden Path Master Services Agreement'
const GOLDEN_PATH_FINDING_TITLE = 'Liability cap is too low'
const GOLDEN_PATH_PROPOSED_TEXT =
  'The total liability cap for any claim shall be the greater of $750,000 or eighteen (18) months of fees paid in the preceding year.'

// The remediation page shows the proposal status under "Persisted status".
// After a successful Approve it also renders a second identical badge under
// "Human decision" (the review decision). Unscoped getByText('APPROVED')
// therefore matches two nodes and Playwright strict mode fails -- even
// though the transition succeeded. Scope to the persisted-status badge,
// which is the UI's representation of the workflow state this test proves.
function persistedProposalStatus(page: Page, status: 'DRAFT' | 'PROPOSED' | 'APPROVED') {
  return page.getByText('Persisted status', { exact: true }).locator('..').getByText(status, { exact: true })
}

test('golden path: owner submits for review, reviewer approves -- real UI, real Firebase auth per role', async ({ page }) => {
  // Two real Firebase logins plus the findings/remediation round-trip cannot
  // fit in Playwright's 30s default, even when /api/findings is fast.
  // The DRAFT re-seed talks to Firestore on top of that.
  test.setTimeout(180_000)

  const env = getWorkflowE2EEnv()

  await test.step('Re-seed the golden-path fixture at DRAFT (a prior run leaves it APPROVED)', async () => {
    resetGoldenPathFixture()
  })

  async function openGoldenPathFinding() {
    // Client-side nav from the already-authenticated shell. page.goto() is a
    // full document load: it re-inits Firebase and remounts the dashboard,
    // which starts GET /api/findings for the whole org. That request was
    // still in flight when the findings page asked for this one contract,
    // so Total stayed "—" and waitForResponse never saw a completed
    // contract-scoped reply.
    // demo-owner-1 / demo-reviewer-1 belong to more than one org. OrgProvider
    // keeps the stored localStorage org (or /api/me orgs[0]) after login, and
    // GET /api/contracts is scoped to that X-Org-Id. The golden-path fixture
    // lives in "LexProof Demo" (lexproof-demo); the screenshot of this failure
    // had "Demo Master Services Agreement" selected, so the picker only listed
    // demo-master-services-agreement. Switch through the real Organization
    // combobox -- the same control a human uses -- before opening the picker.
    const orgSelect = page.getByRole('combobox', { name: 'Organization' })
    await expect(orgSelect.getByRole('option', { name: GOLDEN_PATH_ORG_NAME })).toBeAttached({ timeout: 15_000 })
    await orgSelect.selectOption({ label: GOLDEN_PATH_ORG_NAME })
    await expect(orgSelect).toHaveValue(GOLDEN_PATH_ORG_ID)

    await page.getByRole('link', { name: 'Findings & Redlines' }).click()
    await expect(page).toHaveURL(/\/dashboard\/ai-analysis\/findings/)
    await page.getByRole('button', { name: 'Select a contract' }).click()
    // Do not type into search until the contracts list has loaded. Filling
    // immediately filters contracts=[] and the picker shows "No contracts
    // match" even though GET /api/contracts is still in flight.
    const contractOption = page.getByRole('button', { name: GOLDEN_PATH_CONTRACT_NAME })
    await expect(contractOption).toBeVisible({ timeout: 30_000 })
    await contractOption.click()
    await expect(page).toHaveURL(new RegExp(`contract_id=${GOLDEN_PATH_CONTRACT_ID}`))
    const finding = page.getByText(GOLDEN_PATH_FINDING_TITLE, { exact: true }).first()
    await expect(finding).toBeVisible({ timeout: 30_000 })
    await finding.click()
    await page.getByRole('button', { name: 'Review Finding' }).click()
    await expect(page).toHaveURL(/\/compliance-command-center\/remediation/)
    await expect(page.getByText('Persisted status', { exact: true })).toBeVisible({ timeout: 30_000 })
  }

  // --- Owner: draft -> in_review -------------------------------------

  await test.step('Owner (demo-owner-1): real Firebase login', async () => {
    await loginViaUI(page, env.ownerEmail, env.ownerPassword)
    await expect(page).toHaveURL(/\/dashboard/)
  })

  await test.step('Owner: open the deterministic golden-path contract/proposal via the normal UI', openGoldenPathFinding)

  await test.step('Owner: verify the proposal starts DRAFT', async () => {
    // Explicit timeout, matching every other status-badge assertion in this
    // file: the "Persisted status" label can render before its value catches
    // up on a real Firestore round-trip, and the global 5s expect timeout
    // has been observed to be too tight for that under real backend load
    // (e.g. immediately after other E2E tests exercised the backend).
    await expect(
      persistedProposalStatus(page, 'DRAFT'),
      'golden-path fixture must be DRAFT (a prior run left it PROPOSED/APPROVED; re-seed with --fixture golden-path --reset)',
    ).toBeVisible({ timeout: 15_000 })
  })

  await test.step('Owner: perform the real Submit-for-review action ("Save proposal" with text)', async () => {
    const proposed = page.getByLabel('Proposed text')
    await proposed.fill(GOLDEN_PATH_PROPOSED_TEXT)
    await expect(proposed).toHaveValue(GOLDEN_PATH_PROPOSED_TEXT)
    await page.getByRole('button', { name: 'Save proposal' }).click()
  })

  await test.step('Owner: verify the resulting in_review state (displayed as PROPOSED)', async () => {
    await expect(persistedProposalStatus(page, 'PROPOSED')).toBeVisible({ timeout: 15_000 })
  })

  await test.step('Owner: logout', async () => {
    await logoutViaUI(page)
  })

  // --- Reviewer: in_review -> approved --------------------------------

  await test.step('Reviewer (demo-reviewer-1): real Firebase login', async () => {
    await loginViaUI(page, env.reviewerEmail, env.reviewerPassword)
    await expect(page).toHaveURL(/\/dashboard/)
  })

  await test.step('Reviewer: open the SAME deterministic contract/proposal via the normal UI', openGoldenPathFinding)

  await test.step('Reviewer: verify the persisted in_review state (PROPOSED) from the owner step', async () => {
    // Same reasoning as the DRAFT check above: give the status badge's value
    // real headroom instead of the global 5s default.
    await expect(persistedProposalStatus(page, 'PROPOSED')).toBeVisible({ timeout: 15_000 })
  })

  await test.step('Reviewer: perform the real Review Approval action ("Approve")', async () => {
    await page.getByRole('button', { name: 'Approve', exact: true }).click()
  })

  await test.step('Reviewer: verify the resulting approved state', async () => {
    await expect(persistedProposalStatus(page, 'APPROVED')).toBeVisible({ timeout: 15_000 })
  })

  await test.step('Reviewer: logout', async () => {
    await logoutViaUI(page)
  })
})
