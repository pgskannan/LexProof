# LexProof — Demo Master (frozen 2026-09-25)

The single source of truth for recording and presenting the demo. Every ID, route and number below was checked live against the running app on 2026-09-25. If something on screen differs from this sheet, stop and check before recording.

Org: **LexProof Demo** (`lexproof-demo`). Login: `pgskannan@gmail.com`.

---

## 1. Frozen demo assets

| Role in the story | Contract | Contract ID | Version | Passport | What it shows |
|---|---|---|---|---|---|
| **Hero (high risk, full lifecycle)** | CONTRACT_03_SaaS_HighRisk.docx | `a306afbe-5e8e-4048-978f-8d01a47c1b25` | v2 (published) | `b4439def-680c-4f94-8edc-d8e65a7ef968` | Risk 92 (critical) · compliance 25 · Confirmed · 6/12 evidence anchored · plain-English executive brief |
| **Public verify, VERIFIED case** | (CONTRACT_03 v2 evidence) | evidence `7fd45be6-c028-4faf-a548-4158068f4e95` | — | — | VERIFIED + independent Ethereum read matches |
| **Findings & Redlines** | CONTRACT_05_PSA_EscalationTriggers.docx | `c30992f8-26a2-4c72-9d67-f7cc521545c4` | v1 | — | 8 findings (2 critical/3 high/3 medium) · Redlines tab: "Intellectual Property Ownership and License Termination", PROPOSED |
| **Clean contrast (low risk)** | CONTRACT_01_NDA_Clean_LowRisk.docx | `629f4b26-6157-446d-ac0c-03ae39590e6f` | v1 | `1fd094f7-9775-4774-a042-9445360d7988` | Risk 25 · 0 critical/0 high · 3/3 evidence anchored · **offline proof package → VERIFIED 3/3** · passport root **eligible** |
| **Scanned document (OCR + PII)** | OCR_E2E_Scanned_ServiceAgreement_2026-09-25.png | `e4095b49-87e1-4ffb-8147-018a878c411b` | v1 | `bf21168e-b371-4308-9b25-7f153ab96ff4` | `ocr_success` · PII detected (email, phone) · 3 findings: One-Sided Indemnification (HIGH), Unilateral Withholding of Deliverables (MEDIUM), Exclusive Mandatory Arbitration (MEDIUM) · passport root **eligible** · evidence **not anchored** |
| **Status-fix proof point** | CONTRACT_04_PO_Terms_LowRisk.docx | `04e36ef2-…` | v2 (published) | — | List and detail now agree: **Confirmed** |

On-chain:
- Evidence registry `LexProofRegistry`: `0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191` (Sepolia)
- Passport root registry `LexProofPassportRegistry`: **`0x21Ddd03549c2d4fb75336b616f18c34D4a9BFDE6` (deployed, verified 2026-09-25: bytecode has all 7 function selectors; owner/registrar `0xc39dec4d…7764`, the same signer as evidence anchoring; balance ~0.041 Sepolia ETH)**

## 2. Expected numbers on screen (2026-09-25)

| Screen | Value |
|---|---|
| Dashboard: Contracts / Legal passports | 50 / 43 (43/50 in Evidence & Verification; 7 awaiting a passport) |
| Dashboard: Attention Required | **no "stuck on failed analysis" row** (was 10 → 3 → 0) · high/critical findings ≈ 121 (was 92; see §5) · 7 without a passport |
| Why LexProof? funnel | 45 contracts · 169 risks · 25 of 29 redlines reviewed · 5 versions published · 38 of 209 evidence anchored |
| Board Report (default: test/fixture contracts excluded) | 34 contracts · avg risk 77 · 25 high/critical contracts · 17 test/fixture contracts excluded (toggle to include) |

Counts differ slightly between screens because each one scopes differently (the contracts list includes legacy passport-only rows; Why LexProof counts only contracts with an `org_id`). That's known, not a regression. See §5.

## 3. Recording route (≈5 min)

1. **Why LexProof?** (`/dashboard/why-lexproof`): the verifiable chain and the funnel. *Warm it first (see §4).*
2. **Dashboard**: live metrics, Attention Required, real recent activity.
3. **Contracts → upload** (optional live beat): or open the pre-made OCR contract to show scanned-image OCR + PII flags.
4. **CONTRACT_03 detail**: executive brief, V2 Confirmed, 6/12 anchored → **Review findings**.
5. **Findings & Redlines → CONTRACT_05**: severities → Redlines tab (PROPOSED).
6. **Contract Reviews**: human-in-the-loop approval, Share with Counterparty.
7. **Legal Passport (CONTRACT_03 v2)**: risk/compliance, provenance chain, integrity PASS, QR panel.
8. **Public Verify** (`/public-verify?evidence_id=7fd45be6-c028-4faf-a548-4158068f4e95`): VERIFIED + independent Sepolia read.
9. **Offline proof package (CONTRACT_01)**: download bundle → open `verify-offline.html` → VERIFIED 3/3 against Sepolia, no LexProof server involved.
10. **Ask Lexi**: "Summarize all critical findings across my portfolio" → cited answer.
11. **Board Report** (`/dashboard/reports/board`): heatmap, top risks, Print / Save as PDF.

## 4. Rehearsal notes: things that will bite on camera

- **Warm every page once before recording.** The dev server compiles each route on first hit, and a navigation mid-recompile froze the tab for ~30s during rehearsal. Also warm **Why LexProof?**: its first load is ~6s, then it's cached for 60s (~130ms).
- **Contract detail pages take 3–5s** against real Firestore from this machine. Don't click on the page while its skeletons are showing.
- **Don't edit code while the dev server is recording.** Hot reload remounts the page.
- **QR codes encode `localhost:3000`.** A phone scan won't reach them. Show the QR, then open the link in the browser yourself.
- **Hero passport's Root Anchor panel says "Not eligible (evidence UNVERIFIABLE)".** That's a designed state for passports older than evidence snapshots. For the root-anchor beat, use **CONTRACT_01** or the **OCR** passport instead (both eligible).
- **Ask Lexi refusals render as grounded with zero citations** (e.g. when asked to ignore instructions). It refuses correctly, but avoid adversarial prompts on camera.
- **Demo user's roles**: must be `admin, contract_owner` before recording (see the status doc §56).

## 5. Known, accepted inconsistencies (not blockers)

- Findings counts: `/api/findings` (dashboard, board report) now includes findings from the org's contracts that lack an `org_id` stamp (≈193 total). Why LexProof? counts by contract (169). Both are real; they scope differently.
- Contract count: 50 (list, includes legacy passport-only rows) vs 45 (Why LexProof?, org-stamped contracts only).
- ~17 test/fixture contracts live in the demo org (Playwright runs, hardening fixtures, RBAC scenarios). There's no delete path; the Board Report hides them by default with a visible toggle.

## 6. Frozen-state rule

After this sheet is signed off: **no new uploads, analyses, redline publishes or anchors in `lexproof-demo`** except the recording's own live beats. Running the Playwright E2E suite adds an `e2e-full-lifecycle-*` contract, so run it *before* the final freeze, not after.
