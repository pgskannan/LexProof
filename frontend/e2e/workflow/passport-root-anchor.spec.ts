import { test, expect, type Page } from '@playwright/test'
import { getWorkflowE2EEnv } from '../helpers/env'
import { loginViaUI, logoutViaUI } from '../auth/login'

// Passport ROOT anchoring E2E (docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md).
// Proves the real, additive "Blockchain Commitment" panel on the Legal
// Passport page (legal-passport/components/PassportRootAnchorPanel.tsx) end
// to end: real Firebase login, a real freshly-created passport (real
// upload -> real Gemini analysis, same technique as
// workflow/full-lifecycle-real-upload.spec.ts, so every component hash is
// genuinely self-consistent and the passport is genuinely eligible), the
// real extended `POST /api/passports/{id}/verify` response, and -- only when
// eligible AND the additive LexProofPassportRegistry is actually configured
// for this environment -- the real `POST /api/passports/{id}/anchor-root`
// call.
//
// IMPORTANT, read before assuming this test proves a live Sepolia anchor:
// per the approved architecture (docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md),
// actually deploying LexProofPassportRegistry to Sepolia and setting
// ETHEREUM_PASSPORT_REGISTRY_ADDRESS is Phase F -- explicitly PREPARED but
// NOT EXECUTED as part of this implementation, since it requires a funded
// registrar private key and Sepolia RPC credentials this environment does
// not have. Until that deployment happens, the honest, correct, real
// behavior of an otherwise-eligible passport is anchor_status =
// NETWORK_ERROR ("Blockchain network unavailable" in the UI) -- NOT a
// false "Anchored" success. This test asserts on whichever of the two real
// states the environment actually reports (branching in code, not
// papering over it), so it is truthful whether run today (pre-deployment)
// or later (post-deployment, with ETHEREUM_PASSPORT_REGISTRY_ADDRESS set
// and a funded registrar) -- see test.step() below for exactly which branch
// ran and why.
//
// What this file deliberately does NOT attempt, and why:
//   - A FAIL/UNVERIFIABLE passport-root eligibility case: every component
//     hash is computed from the same stored data at passport-creation time,
//     so a genuinely fresh, real passport is always all-PASS immediately
//     after creation. Forcing a FAIL/UNVERIFIABLE case would require direct
//     Firestore tampering after the fact, which this E2E suite's own
//     convention (see full-lifecycle-real-upload.spec.ts's header comment)
//     never does. That state machine (FAIL/UNVERIFIABLE/NOT_ANCHORED/
//     INVALID_PROOF/NETWORK_ERROR/CHAIN_MISMATCH/PASS) is instead
//     exhaustively covered with real backend logic (no mocked eligibility
//     math) in backend/tests/lexproof/passport/
//     test_passport_root_anchor_service.py and
//     test_passport_root_anchor_api.py.
//   - The public, unauthenticated `GET /api/verify/passport/{id}` endpoint:
//     there is no frontend page that surfaces it yet (unlike per-evidence
//     verification's QrVerifyBadge/offline verifier), so there is no real
//     UI flow to drive here. It is covered at the API layer by
//     test_passport_root_anchor_api.py's public_root_existence tests.

const LEXPROOF_DEMO_ORG_ID = 'lexproof-demo'
const LEXPROOF_DEMO_ORG_NAME = 'LexProof Demo'

async function selectLexProofDemoOrg(page: Page) {
  const orgSelect = page.getByRole('combobox', { name: 'Organization' })
  await expect(orgSelect.getByRole('option', { name: LEXPROOF_DEMO_ORG_NAME })).toBeAttached({ timeout: 15_000 })
  await orgSelect.selectOption({ label: LEXPROOF_DEMO_ORG_NAME })
  await expect(orgSelect).toHaveValue(LEXPROOF_DEMO_ORG_ID)
}

function uniqueContractDocument(): { name: string; buffer: Buffer } {
  const marker = `E2E-ANCHOR-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
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
  return { name: `e2e-anchor-${marker}.txt`, buffer: Buffer.from(text, 'utf-8') }
}

function blockchainCommitmentPanel(page: Page) {
  return page.getByTestId('passport-root-anchor-panel')
}

test('passport root anchoring: real eligible passport shows the real on-chain state, and anchors when the registry is configured', async ({ page }) => {
  // Real Gemini analysis plus a real Firebase login/logout cycle cannot fit
  // in Playwright's 30s default -- same budget as full-lifecycle-real-upload
  // .spec.ts, which this test's setup mirrors exactly.
  test.setTimeout(420_000)
  const env = getWorkflowE2EEnv()
  const doc = uniqueContractDocument()
  let contractId = ''
  let passportId = ''

  await test.step('Owner (demo-owner-1): real Firebase login', async () => {
    await loginViaUI(page, env.ownerEmail, env.ownerPassword)
    await selectLexProofDemoOrg(page)
  })

  await test.step('Owner: create a fresh, unique passport by uploading a real document through the real UI', async () => {
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

  await test.step('Owner: the real Passport Integrity check reports full PASS for this freshly-created passport', async () => {
    await expect(page.getByText('PASS / VERIFIED', { exact: true })).toBeVisible({ timeout: 30_000 })
    const passportIdText = await page
      .getByText('Passport ID', { exact: true })
      .locator('..')
      .locator('p')
      .first()
      .textContent()
    passportId = (passportIdText || '').trim()
    expect(passportId, 'could not read the real passport_id from the Passport Information panel').not.toBe('')
  })

  await test.step('Owner: the real, additive Blockchain Commitment panel is present and reports a real anchor_status', async () => {
    const panel = blockchainCommitmentPanel(page)
    await expect(panel).toBeVisible({ timeout: 15_000 })
    // Must be one of the two states a genuinely eligible (all-PASS) passport
    // can honestly be in for this environment right now -- see the
    // file-level comment for why "Anchored" is conditional on Phase F
    // (Sepolia deployment) having happened.
    await expect(
      panel.getByText('Not anchored', { exact: true }).or(panel.getByText('Network unavailable', { exact: true })),
    ).toBeVisible({ timeout: 15_000 })
  })

  const panel = blockchainCommitmentPanel(page)
  const registryConfigured = await panel
    .getByRole('button', { name: 'Anchor to Ethereum Sepolia' })
    .isVisible()
    .catch(() => false)

  if (!registryConfigured) {
    await test.step(
      'Real, honest result: LexProofPassportRegistry is not yet deployed/configured in this environment (Phase F not executed) -- ' +
        'the eligible passport correctly reports "Network unavailable", not a false "Anchored" success',
      async () => {
        await expect(panel.getByText('Network unavailable', { exact: true })).toBeVisible()
        await expect(panel.getByText(/Blockchain network unavailable/i)).toBeVisible()
        await expect(panel.getByRole('button', { name: 'Anchor to Ethereum Sepolia' })).toHaveCount(0)
      },
    )
  } else {
    await test.step('Registry IS configured: perform the real anchor-root action', async () => {
      await panel.getByRole('button', { name: 'Anchor to Ethereum Sepolia' }).click()
      // A real Sepolia transaction: submit + mine + receipt. 60s was too tight --
      // on 2026-09-25 a root anchor took ~3 minutes to mine (since fixed with a
      // priority tip, services/blockchain_fees.py), so allow up to the
      // backend's own 120s receipt wait plus headroom.
      await expect(page.getByText('Passport root anchored on Ethereum Sepolia')).toBeVisible({ timeout: 150_000 })
      await expect(panel.getByText('Anchored', { exact: true })).toBeVisible({ timeout: 15_000 })
      await expect(panel.getByText(/Passport root anchored and matches this fingerprint/i)).toBeVisible()
    })

    await test.step('Persistence, part 1: a plain reload still shows Anchored -- real persisted state, not a React variable', async () => {
      await page.reload()
      await expect(panel.getByText('Anchored', { exact: true })).toBeVisible({ timeout: 30_000 })
    })

    await test.step('Owner: logout', async () => {
      await logoutViaUI(page)
    })

    await test.step('Persistence, part 2: log back in and Anchored still persists after a full session cycle', async () => {
      await loginViaUI(page, env.ownerEmail, env.ownerPassword)
      await selectLexProofDemoOrg(page)
      await page.goto(`/legal-passport?contractId=${encodeURIComponent(contractId)}`)
      await expect(blockchainCommitmentPanel(page).getByText('Anchored', { exact: true })).toBeVisible({ timeout: 30_000 })
    })

    await test.step('Idempotency: re-anchoring an already-anchored passport is refused/hidden, never a second transaction', async () => {
      // Once anchored, the panel's PASS branch renders no anchor button at
      // all (see PassportRootAnchorPanel.tsx) -- this is the UI-level proof
      // that a second click can never happen through the real UI. The
      // underlying server-side first-write-wins guarantee itself is proven
      // directly against a real local Ethereum chain in
      // backend/tests/lexproof/blockchain/test_passport_registry_contract.py
      // and at the service layer in test_passport_root_anchor_service.py.
      await expect(blockchainCommitmentPanel(page).getByRole('button', { name: 'Anchor to Ethereum Sepolia' })).toHaveCount(0)
    })
  }

  await test.step('Owner: logout', async () => {
    await logoutViaUI(page)
  })
})
