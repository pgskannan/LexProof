# LexProof — Full End-to-End Manual Test Pass (2026-09-07)

*Live manual walkthrough of every major use case against the running app (localhost:3000 / localhost:8000) and real Sepolia. This pass found one significant navigation bug (Legal Passport is currently unreachable from the main nav) and one pre-existing data issue (a contract stuck in a failed-analysis state), and reconfirmed the status of every previously-known limitation.*

## Summary

Ran a fresh click-through of every screen in the app: Dashboard, Contracts (list + a failed-analysis contract), Contract Lifecycle, Contract Time Machine, AI Findings, Contract Reviews, Legal Passport (Overview/Evidence/Fingerprint), Blockchain Proof, Verification (public deep-link + manual portal), Compliance, Reports, and Administration.

One new **high-severity navigation bug** was found and root-caused: the sidebar's "Legal Passport" link is wired to a dead placeholder route and currently cannot reach the real Legal Passport page through any in-app UI path. One new **medium-severity data issue** was found: a demo contract has been stuck in a failed-analysis state (no passport) since before this session. Everything else reconfirms the app's previously-documented state — no regressions found elsewhere, and the §16 contracts-list dedup fix is still holding.

## New findings

### 1. [HIGH] "Legal Passport" nav link is dead — the real page is unreachable through normal navigation

**Symptom**: Clicking "Legal Passport" in the sidebar (or navigating to `/dashboard/legal-passport` with any query parameters — `contractId`, `passportId`, tried both) always lands back on the Contracts list. Clicking a contract's name/card on the Contracts page opens its Lifecycle page instead of a passport. The Lifecycle page's own "Legal Passport" stage card is the only stage card with no "Open stage" link, unlike every other stage (Evidence, Blockchain Anchored, Public Verification, etc. all have one).

**Root cause** (confirmed in source): `frontend/app/(authenticated)/dashboard/legal-passport/page.tsx` is a 13-line stub:
```tsx
useEffect(() => { router.replace('/dashboard/contracts'); }, [router]);
```
It unconditionally redirects away, ignoring any query string. The real, fully-working Legal Passport UI (Overview/Evidence/Fingerprint tabs, integrity banner, "Verify Publicly") lives at a *different* route — `frontend/app/(authenticated)/legal-passport/page.tsx` (no `/dashboard` prefix) — and requires **both** `contractId` and `contractVersion` query params (`/legal-passport?contractId=...&contractVersion=2`); passing only one causes that page's own guard to redirect to `/dashboard/contracts` too.

Once the correct URL (with both params) is hit directly, the real page works perfectly — verified below.

**Impact**: Right now, nobody using the app through its own UI — sidebar nav, Contracts list, or the Lifecycle page — can reach the Legal Passport feature at all. It's fully functional but effectively hidden.

**Suggested fix** (any one of these closes the gap):
- Point the sidebar's `Legal Passport` link at `/legal-passport` and have it carry the current/selected contract's `contractId` + `contractVersion`, or
- Add the missing "Open stage" link to the Lifecycle page's `LEGAL PASSPORT` card, pointing at `/legal-passport?contractId={id}&contractVersion={version}`, or
- Make the `/dashboard/legal-passport` stub forward its query params to `/legal-passport` instead of redirecting to Contracts.

**Verified working once reached correctly** (`/legal-passport?contractId=797b61c9-4d50-41f6-b095-078561545fbd&contractVersion=2`):
- Overview tab: Risk 92, Compliance 25, 5 Evidence items, integrity banner (still showing the documented pre-fix FAIL — see reconfirmed items below).
- Evidence tab: findings render with risk/compliance impact badges, evidence IDs, "Verify Publicly" buttons.
- Fingerprint tab: document and policy SHA-256 hashes render correctly.

### 2. [MEDIUM] CONTRACT_08_JointVenture_ExecApproval.docx is stuck with no passport — both V2 and V3 analysis failed

Contract `d756f4a0-218e-4697-ab61-63022e5a26d3` shows a **"failed"** badge on the Contracts list. Its Lifecycle page shows: V1 complete; V2 published on 8/30 but its re-analysis **failed**; V3 published on 9/1 but **also failed**. No passport exists for either published version. The UI offers a "Retry" button on the failed analysis stage — not clicked during this pass, since retrying is a side-effecting action.

This predates this session (timestamps are 8/30 and 9/1) and wasn't previously flagged in the project's docs. Worth a look at backend logs around those timestamps to find why analysis kept failing on this specific contract, and whether "Retry" would actually fix it or just fail again.

## Reconfirmed — still present, no change

- **Time Machine 404 bug** (first found 2026-09-06): `GET /api/time-machine/history/797b61c9-...` still returns 404, still shows "No passport versions found" despite this contract having real, confirmed passport history. Reconfirmed this pass via a fresh network trace (3 GET 404s).
- **Passport integrity FAIL banner** for pre-fix passports (documented 2026-09-05/06): still shows `FAIL / INTEGRITY CHECK FAILED — Evidence ✗ package mismatch` on the primary demo passport. The underlying fix only applies to passports published after it landed; this is the same open item awaiting your decision (repair script / republish / leave as documented limitation) from the earlier report.
- **Compliance Command Center**: still "No data available" — no seeded demo data, not a defect.
- **Reports — "LexProof AI Analysis (measured)"**: still shows "Not available" for demo contracts — the estimated-manual-review side works, no persisted measured-AI-time figure exists to compare against.
- **Transient backend/event-loop hang** (§2c residual risk): reproduced twice this pass — once on Contract Reviews' redline-proposals fetch, once on Reports' metrics fetch. Both got stuck on a spinner for roughly 10–15 seconds, then self-resolved and rendered correctly with no restart needed. Same known risk, not a new defect.
- **"Blockchain Proof" and "Verification" nav items both route to `/dashboard/verification`**: reconfirmed, not a bug.
- **Contracts list dedup fix (§16/Finding A)**: reconfirmed holding — exactly one row per real contract (16 total) plus the two genuinely-orphaned IDs, each once.

## Confirmed working, no issues

- **Dashboard**: seeded totals correct (7 contract records, 3 primary versions, 95 AI findings), Recent Activity feed renders.
- **AI Findings**: totals correct (95 / 28 critical / 44 high / 22 medium / 1 low); search box filters correctly (tested "liability"); expand-finding shows evidence quote and risk impact.
- **Contract Reviews**: redline proposal (original clause vs. AI-proposed redline) renders correctly; full audit trail renders (`APPROVED by ... on ...` → `Published as version ... by ... on ...`); "Retry evidence anchoring" option present (not clicked).
- **Contract Lifecycle**: all stage cards, version history (V1/V2 detail), "Open Time Machine" link all render correctly for the primary demo contract.
- **Public Verification** — both paths confirmed VERIFIED with matching on-chain/recomputed hashes and real Ethereum Sepolia metadata (network, contract address, anchor time, transaction hash):
  - Deep link (`/public-verify?evidence_id=...`): auto-populates and auto-verifies.
  - Manual portal (`/dashboard/verification`): typed evidence ID + Verify Evidence button.
- **Administration**: System & Anchoring Status page shows Firebase / Google Cloud / Vertex AI all "Configured", plus live Ethereum anchoring config (network, chain ID, registry contract, Gemini model).

## Not re-tested this pass

- Actual file upload / "Upload and analyze" flow (not exercised, to avoid creating new data mid-test).
- Approving/publishing a *new* redline (read-only pass; existing published redlines were inspected, none newly approved or published).
- The failed contract's "Retry" button (side-effecting; flagged for your decision instead).
