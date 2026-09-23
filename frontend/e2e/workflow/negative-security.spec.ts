import { test, expect, type Page } from '@playwright/test'
import { getWorkflowE2EEnv, getApproverCredentials } from '../helpers/env'
import { loginViaUI, logoutViaUI } from '../auth/login'

// E2E workflow audit follow-up (Phase 4A/4B/4C): negative/security coverage
// for the real redline-proposal review/approval workflow. Every scenario
// here proves BACKEND enforcement, not just UI hiding -- see each test's own
// comment for exactly which guard it exercises and why. Real Firebase auth
// per identity throughout; no mocked auth.
//
// UI role gating (Phase 4 of the "close remaining gaps" follow-up task)
// added a client-side check to the remediation page: Approve/Reject are now
// gated on the viewer holding the reviewer (or admin) role, not just on
// proposal status (see remediation/page.tsx's `canReview`, and
// lib/roles.ts). That means demo-owner-1 (contract_owner role only) and
// demo-approver-1 (approver role only) no longer see the Approve/Reject
// buttons at all -- the same shape of "button is gone, by design" this file
// already proved for 4C's already-final proposal. 4A/4B were updated
// accordingly: each still proves BOTH layers of defense in depth --
//   1. real UI: the button is genuinely absent for this real, logged-in,
//      wrongly-roled identity (proves the Phase 4 fix landed and works);
//   2. real backend: a direct, authenticated call with a real token
//      captured from that exact session (never fabricated) still gets a
//      real 403 and leaves state unchanged (proves the UI is not the only
//      thing stopping this -- exactly the "UI hiding is NOT security
//      enforcement" requirement).
// This is a strictly stronger proof than the previous version (which could
// only click a button the UI has since correctly started hiding), not a
// weakened one.
//
// Fixtures required (see backend/scripts/create_approval_demo_fixture.py):
//   --fixture pending-review           (used by tests 1 and 2; PROPOSED)
//   --fixture duplicate-approval-denial (used by test 3; already APPROVED)
// 4A/4B never themselves transition the pending-review proposal. If it has
// already been approved through the app, re-seed with
// --fixture pending-review --reset. The duplicate-approval fixture is
// already APPROVED and is stable under repeated runs of 4C.
//
// The remediation page shows proposal status under "Persisted status". After
// Approve it also renders a second identical badge under "Human decision".
// Unscoped getByText('APPROVED') matches both and Playwright strict mode
// fails. Scope to the persisted-status badge.

const PENDING_CONTRACT_ID = 'demo-lexproof-pending-master-services-agreement'
const PENDING_FINDING_TITLE = 'Liability cap is too low'
const DUPLICATE_APPROVAL_CONTRACT_ID = 'demo-duplicate-approval-master-services-agreement'
const DUPLICATE_APPROVAL_FINDING_TITLE = 'Liability cap is too low'

function persistedProposalStatus(page: Page, status: 'DRAFT' | 'PROPOSED' | 'APPROVED') {
  return page.getByText('Persisted status', { exact: true }).locator('..').getByText(status, { exact: true })
}

type OpenedFinding = { proposalId: string; authorizationHeader: string }

// Opens a finding's remediation page and, along the way, captures the real
// Firebase ID token apiFetch (lib/api.ts) attaches to the GET that loads
// this contract's redline proposals -- reused below for a direct backend
// call with that same real, UI-authenticated session's real credentials.
// Never a fabricated or admin token.
async function openFindingAndCaptureAuth(page: Page, contractId: string, findingTitle: string): Promise<OpenedFinding> {
  const [proposalsResponse] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes(`/api/contracts/${contractId}/redline-proposals`) &&
        response.request().method() === 'GET',
    ),
    (async () => {
      await page.goto(`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`)
      await page.getByText(findingTitle, { exact: true }).first().click()
      await page.getByRole('button', { name: 'Review Finding' }).click()
      await expect(page).toHaveURL(/\/compliance-command-center\/remediation/)
      await expect(page.getByText('Persisted status', { exact: true })).toBeVisible({ timeout: 30_000 })
    })(),
  ])
  const proposals: Array<{ proposal_id: string }> = await proposalsResponse.json()
  const proposalId = proposals.at(-1)?.proposal_id ?? ''
  const authorizationHeader = proposalsResponse.request().headers()['authorization'] ?? ''
  return { proposalId, authorizationHeader }
}

test.describe('negative/security: redline-proposal workflow', () => {
  test('4A: contract_owner cannot approve their own submission (real UI hides the button, real backend 403, state unchanged)', async ({ page }) => {
    test.setTimeout(120_000)
    const env = getWorkflowE2EEnv()
    let opened: OpenedFinding = { proposalId: '', authorizationHeader: '' }

    await test.step('Owner (demo-owner-1) logs in and opens their own PROPOSED proposal', async () => {
      await loginViaUI(page, env.ownerEmail, env.ownerPassword)
      opened = await openFindingAndCaptureAuth(page, PENDING_CONTRACT_ID, PENDING_FINDING_TITLE)
      expect(opened.proposalId, 'the pending-review fixture must exist and be PROPOSED').not.toBe('')
      expect(opened.authorizationHeader).not.toBe('')
      await expect(persistedProposalStatus(page, 'PROPOSED')).toBeVisible()
    })

    await test.step('Layer 1 -- real UI: demo-owner-1 holds contract_owner only, not reviewer, so Approve/Reject are not offered at all', async () => {
      // remediation/page.tsx's canReview = isAdmin(roles) || hasRole(roles,
      // 'reviewer'). demo-owner-1 has neither, so the whole "Human review"
      // card -- including these buttons -- is not rendered, mirroring the
      // allowed_roles on the real "approve"/"reject" transitions
      // (workflow_catalog.py: ["reviewer", "admin"]).
      await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Reject', exact: true })).toHaveCount(0)
    })

    await test.step('Layer 2 -- a hidden button is not proof of anything: attempt the real backend call directly, with the real owner session\'s real token', async () => {
      // What actually stops this is WorkflowEngine._validate_transition's
      // role check ("approve" requires reviewer/admin) -- a real 403 from
      // POST /api/redline-proposals/{id}/review, independent of the UI.
      const response = await page.request.post(`/api/redline-proposals/${opened.proposalId}/review`, {
        headers: { Authorization: opened.authorizationHeader, 'Content-Type': 'application/json' },
        data: { decision: 'APPROVED', comment: 'negative-security test: owner attempts to approve own submission' },
      })
      expect(response.status(), await response.text()).toBe(403)
    })

    await test.step('State did not change: reload proves the persisted status is still PROPOSED, not APPROVED', async () => {
      await page.reload()
      await expect(page.getByText('Persisted status', { exact: true })).toBeVisible({ timeout: 30_000 })
      await expect(persistedProposalStatus(page, 'PROPOSED')).toBeVisible()
    })

    await test.step('logout', async () => {
      await logoutViaUI(page)
    })
  })

  test('4B: an org member without the reviewer role cannot approve (unauthorized reviewer, real UI hides the button, real backend 403)', async ({ page }) => {
    test.setTimeout(120_000)
    const { approverEmail, approverPassword } = getApproverCredentials()
    let opened: OpenedFinding = { proposalId: '', authorizationHeader: '' }

    await test.step('demo-approver-1 (approver role, NOT reviewer) logs in and opens the same PROPOSED proposal', async () => {
      await loginViaUI(page, approverEmail, approverPassword)
      opened = await openFindingAndCaptureAuth(page, PENDING_CONTRACT_ID, PENDING_FINDING_TITLE)
      expect(opened.proposalId).not.toBe('')
      expect(opened.authorizationHeader).not.toBe('')
      await expect(persistedProposalStatus(page, 'PROPOSED')).toBeVisible()
    })

    await test.step('Layer 1 -- real UI: demo-approver-1 holds approver only, not reviewer, so Approve/Reject are not offered at all', async () => {
      await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Reject', exact: true })).toHaveCount(0)
    })

    await test.step('Layer 2 -- attempt the real backend call directly, with the real approver session\'s real token -- allowed_roles for this transition is [reviewer, admin]', async () => {
      const response = await page.request.post(`/api/redline-proposals/${opened.proposalId}/review`, {
        headers: { Authorization: opened.authorizationHeader, 'Content-Type': 'application/json' },
        data: { decision: 'APPROVED', comment: 'negative-security test: unauthorized reviewer attempts approval' },
      })
      expect(response.status(), await response.text()).toBe(403)
    })

    await test.step('State did not change: still PROPOSED after reload', async () => {
      await page.reload()
      await expect(page.getByText('Persisted status', { exact: true })).toBeVisible({ timeout: 30_000 })
      await expect(persistedProposalStatus(page, 'PROPOSED')).toBeVisible()
    })

    await test.step('logout', async () => {
      await logoutViaUI(page)
    })

    // This same login also re-proves, incidentally, that env.ownerEmail's
    // denial in test 4A was not a fluke of that one identity -- a second,
    // differently-roled real identity is independently refused the same
    // real transition, at both layers.
  })

  test('4C: an already-APPROVED proposal cannot be approved again (duplicate approval, real backend 409 -- UI has no button to click, by design)', async ({ page }) => {
    test.setTimeout(120_000)
    const env = getWorkflowE2EEnv()
    let opened: OpenedFinding = { proposalId: '', authorizationHeader: '' }

    await test.step('Reviewer logs in and opens the proposal seeded APPROVED by the duplicate-approval-denial fixture', async () => {
      await loginViaUI(page, env.reviewerEmail, env.reviewerPassword)
      opened = await openFindingAndCaptureAuth(page, DUPLICATE_APPROVAL_CONTRACT_ID, DUPLICATE_APPROVAL_FINDING_TITLE)
      expect(opened.proposalId, 'the duplicate-approval-denial fixture must exist -- run backend/scripts/create_approval_demo_fixture.py --fixture duplicate-approval-denial first').not.toBe('')
      expect(opened.authorizationHeader).not.toBe('')
    })

    await test.step('Confirm via the real UI that the proposal already shows APPROVED, and that Approve/Reject are gone (final status hides them, independent of the Phase 4 role gate -- the reviewer here DOES hold the reviewer role)', async () => {
      await expect(persistedProposalStatus(page, 'APPROVED')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Reject', exact: true })).toHaveCount(0)
    })

    await test.step('A hidden button is not proof of anything -- attempt the real backend call directly, with the real reviewer session\'s real token', async () => {
      const response = await page.request.post(`/api/redline-proposals/${opened.proposalId}/review`, {
        headers: {
          Authorization: opened.authorizationHeader,
          'Content-Type': 'application/json',
        },
        data: { decision: 'APPROVED', comment: 'negative-security test: duplicate approval attempt' },
      })
      // ProposalService.review() raises FinalDecisionError for a proposal
      // already APPROVED/REJECTED/PUBLISHED, mapped to HTTP 409 by
      // api/redline_proposals.py's _handle_review_error.
      expect(response.status(), await response.text()).toBe(409)
    })

    await test.step('State still shows exactly the original APPROVED decision after reload -- no duplicate review was recorded', async () => {
      await page.reload()
      await expect(page.getByText('Persisted status', { exact: true })).toBeVisible({ timeout: 30_000 })
      await expect(persistedProposalStatus(page, 'APPROVED')).toBeVisible()
    })

    await test.step('logout', async () => {
      await logoutViaUI(page)
    })
  })
})
