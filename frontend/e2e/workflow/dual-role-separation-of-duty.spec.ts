import { test, expect, type Page } from '@playwright/test'
import { getDualRoleCredentials } from '../helpers/env'
import { loginViaUI, logoutViaUI } from '../auth/login'

// E2E security/workflow follow-up, Phase 3: proves the requires_not_actor
// separation-of-duties rule specifically -- not just a plain role check.
//
// Why this test exists, and how it differs from negative-security.spec.ts's
// 4A: 4A's demo-owner-1 holds ONLY contract_owner, not reviewer, so its
// approval attempt is refused by WorkflowEngine._validate_transition's
// allowed_roles check ("approve" requires [reviewer, admin]) BEFORE that
// function's code ever reaches the requires_not_actor check -- the role
// check runs first (see workflow_engine.py). That proves role enforcement,
// not separation-of-duties enforcement specifically.
//
// demo-dual-role-1 (backend/scripts/create_approval_demo_fixture.py's
// create_dual_role_sod_fixture) genuinely HOLDS the reviewer role, in
// addition to contract_owner, in the SAME org. They create AND submit their
// own proposal (so the workflow instance's created_by == their own uid),
// then attempt to approve it. The role check passes this time -- they are a
// real reviewer -- so the only thing that can still refuse them is
// requires_not_actor: ["created_by"] (workflow_catalog.py's "approve"
// transition). This test proves exactly that: the UI legitimately shows the
// Approve/Reject buttons (unlike 4A/4B, where the Phase 4 UI role gate
// correctly hides them for a non-reviewer), the click still gets a real
// backend 403, and a direct backend call surfaces the SoD-specific error
// detail ("...because they are recorded as created_by").
//
// Fixture required: backend/scripts/create_approval_demo_fixture.py
// --fixture dual-role-sod. Never transitions the proposal itself (it would
// raise if it had -- see the fixture's own status check), so it is stable
// under repeated runs of this test.

const DUAL_ROLE_SOD_CONTRACT_ID = 'demo-dual-role-sod-master-services-agreement'
const DUAL_ROLE_SOD_FINDING_TITLE = 'Liability cap is too low'

function persistedProposalStatus(page: Page, status: 'DRAFT' | 'PROPOSED' | 'APPROVED') {
  return page.getByText('Persisted status', { exact: true }).locator('..').getByText(status, { exact: true })
}

test('dual-role SoD: a user who is both contract_owner and reviewer still cannot approve their own submission (requires_not_actor, real UI + real backend)', async ({ page }) => {
  test.setTimeout(120_000)
  const { dualRoleEmail, dualRolePassword } = getDualRoleCredentials()
  let proposalId = ''
  let authorizationHeader = ''

  await test.step('demo-dual-role-1 (contract_owner + reviewer, same org) logs in and opens their own PROPOSED proposal', async () => {
    await loginViaUI(page, dualRoleEmail, dualRolePassword)
    const [proposalsResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/contracts/${DUAL_ROLE_SOD_CONTRACT_ID}/redline-proposals`) &&
          response.request().method() === 'GET',
      ),
      (async () => {
        await page.goto(`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(DUAL_ROLE_SOD_CONTRACT_ID)}`)
        await page.getByText(DUAL_ROLE_SOD_FINDING_TITLE, { exact: true }).first().click()
        await page.getByRole('button', { name: 'Review Finding' }).click()
        await expect(page).toHaveURL(/\/compliance-command-center\/remediation/)
        await expect(page.getByText('Persisted status', { exact: true })).toBeVisible({ timeout: 30_000 })
      })(),
    ])
    const proposals: Array<{ proposal_id: string }> = await proposalsResponse.json()
    proposalId = proposals.at(-1)?.proposal_id ?? ''
    authorizationHeader = proposalsResponse.request().headers()['authorization'] ?? ''
    expect(proposalId, 'the dual-role-sod fixture must exist -- run backend/scripts/create_approval_demo_fixture.py --fixture dual-role-sod first').not.toBe('')
    expect(authorizationHeader).not.toBe('')
    await expect(persistedProposalStatus(page, 'PROPOSED')).toBeVisible()
  })

  await test.step('Unlike 4A/4B: this identity DOES hold the reviewer role, so the real UI legitimately offers Approve/Reject', async () => {
    // Confirms the Phase 4 UI role gate is discriminating correctly -- it
    // is not simply hiding these buttons from every non-owner-of-the-
    // decision; a genuine reviewer, even one who is also this proposal's
    // creator, still sees them. What has to stop this is the backend's
    // separation-of-duties check specifically, not the UI.
    await expect(page.getByRole('button', { name: 'Approve', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Reject', exact: true })).toBeVisible()
  })

  await test.step('Real UI click: attempts to approve their own submission', async () => {
    await page.getByRole('button', { name: 'Approve', exact: true }).click()
  })

  await test.step('The real backend error is surfaced in the real UI', async () => {
    await expect(page.locator('main').getByRole('alert')).toBeVisible({ timeout: 10_000 })
  })

  await test.step('Direct backend call confirms the exact real 403 and that it names the separation-of-duties field specifically', async () => {
    // WorkflowEngine._validate_transition's requires_not_actor branch
    // raises WorkflowSeparationOfDutiesError("Actor cannot perform Approve
    // because they are recorded as created_by"), which ProposalService.review()
    // re-raises as PermissionError -> a real 403 from
    // api/redline_proposals.py. Asserting the detail text, not just the
    // status code, is what actually distinguishes this from a plain
    // "wrong role" 403 (which would instead say "Role ... cannot perform").
    const response = await page.request.post(`/api/redline-proposals/${proposalId}/review`, {
      headers: { Authorization: authorizationHeader, 'Content-Type': 'application/json' },
      data: { decision: 'APPROVED', comment: 'dual-role SoD test: self-approval attempt' },
    })
    expect(response.status()).toBe(403)
    const body = await response.text()
    expect(body).toContain('created_by')
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
