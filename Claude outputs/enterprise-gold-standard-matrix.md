# LexProof — Enterprise "Gold Standard" Feature & Polish Matrix

*Compiled 2026-09-07. Validated against the actual running app (localhost:3000/8000) and the accumulated findings across every session in this engagement — not a generic checklist. "✅ Have" means directly confirmed working this engagement; "⚠️ Partial" means it exists but with a known gap; "❌ Missing" means checked and genuinely absent.*

## How to read this

Three tiers, same convention product teams use going into a real enterprise sale or a judged demo:

- **Must-have** — table stakes. Missing or broken here actively undermines trust or blocks a real deployment. Fix before anything else.
- **Should-have** — expected at a "gold standard" bar. Absence doesn't break the product but reads as unfinished to a sophisticated evaluator (an enterprise buyer, a judge who's seen a lot of demos).
- **Nice-to-have** — genuine delighters. Skip these without guilt if time is short.

---

## Must-have — validated

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Core workflow (upload → AI analysis → redline → human review → publish → passport → evidence → anchor → public verify) works end to end | ✅ Have | Verified live repeatedly across every session; this is the product's spine and it holds. |
| 2 | Multi-tenant org isolation + RBAC (5 roles, org-scoped auth, separation-of-duties) | ✅ Have | Built, 27/27 tests passing, migrated, live-verified (§24/§25). |
| 3 | Independently-verifiable evidence (client-side hash recompute + direct Sepolia read, not proxied through the backend) | ✅ Have | Confirmed multiple times, all 4 statuses (VERIFIED/TAMPERED/EVIDENCE_NOT_FOUND/ANCHOR_NOT_FOUND). This is the core differentiator and it's solid. |
| 4 | Every Legal Passport reachable from the UI it's supposed to be reachable from | ❌ Missing | **[HIGH, open]** Sidebar "Legal Passport" link is a dead stub that redirects to Contracts. The real page only works via a direct URL with query params. This is a must-fix — it's the product's namesake feature and the primary nav link to it doesn't work. |
| 5 | Passport integrity check reads correctly — no false "TAMPERED"/"FAIL" on a legitimate, untouched passport | ❌ Missing on existing data | **[open decision, not yet acted on]** Every passport published before the §21 fix still shows a false-positive integrity FAIL. The fix is live for new publishes, but every pre-existing demo passport still fails. For a product whose entire pitch is "verifiable, don't take it on faith," a FAIL banner on a real, untampered record is close to a worst-case first impression. Needs the repair-script decision made (option (a) in `e2e-test-report.md`) rather than staying "documented and known." |
| 6 | No transient 5xx/hang visible during a live demo or real usage | ⚠️ Partial | The §2c synchronous-blockchain-call-blocking-the-event-loop hang is well-documented, self-resolving, and non-data-lossy — but it's been reproduced on nearly every session, including one 60+ second episode this session. An enterprise buyer (or a judge) hitting a cold page during a live demo and seeing a multi-second spinner or a 503 is a real, visible failure even though nothing breaks underneath. This needs the actual async fix, not another round of "confirmed it self-resolves." |
| 7 | Signed-in user can see who they are and sign out from anywhere in the app | ❌ Missing | Checked the persistent chrome on Dashboard, Compliance, Administration: the sidebar footer only shows "LexProof v1.0" — no avatar, name, email, or sign-out control anywhere. This is genuinely table-stakes for any multi-user app, let alone one that just added multi-tenant org membership. |
| 8 | Consistent app chrome (the same header/context elements) on every authenticated page | ❌ Missing | The "ORGANIZATION: LexProof Demo" selector appears on Compliance, Contract Reviews, and Administration — but not on Dashboard, the very first page a signed-in user lands on. Small, but it's the kind of inconsistency a sophisticated evaluator notices immediately. |
| 9 | A contract stuck in a genuinely broken state doesn't sit there silently | ⚠️ Partial | CONTRACT_08 has two versions permanently stuck on "failed" analysis with a "Retry" button that's never been exercised. Not fixed, not surfaced anywhere as a system-health signal (no alert, no dashboard indicator) — just a quiet failed badge a user has to notice on the contracts list. |
| 10 | Time Machine works for every contract that has real history | ❌ Missing for one contract | `797b61c9-...`'s history endpoint 404s despite confirmed real passport/evidence history elsewhere in the app. Real, unresolved defect (§22, reconfirmed §23). |

**Must-have score: 4 of 10 fully clean, 2 partial, 4 with a known open gap.** None of the 4 gaps are hard — all are already root-caused or clearly scoped — but none should be left for "later" if this is meant to read as enterprise-grade rather than hackathon-grade.

---

## Should-have — validated

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Empty states explain what's missing and what to do next | ❌ Missing | Compliance shows bare gray text: **"No data available."** No icon, no explanation of what this page is for, no CTA. Contracts list showed "No contracts available" during a loading race with the same bare treatment. This is the single most common "hackathon vs. enterprise" tell — professional empty states are a solved, well-known pattern the app doesn't use anywhere yet. |
| 2 | Dashboard reflects real, live activity | ❌ Missing | "Recent Activity" shows three hardcoded seed-data lines ("CONTRACT-000001 v3 analyzed," "CPRA scenario loaded," "Three passport versions available") that never change — confirmed static across multiple sessions and multiple real actions taken in between (redline approvals, a real countersignature was recorded today). A user's first impression of the product's pulse is fake data. |
| 3 | Loading states use skeletons, not bare text | ❌ Missing | Every loading state observed this engagement is plain text ("Loading redline proposals...", "Loading contract lifecycle...", "Loading links..."). Given the known §2c hang can stretch these to 10-60+ seconds, a skeleton (or at minimum a spinner + elapsed-time-aware message) would meaningfully soften how broken a slow load feels — cheap, high-leverage fix. |
| 4 | Destructive / high-stakes actions require confirmation | ⚠️ Not validated | Redline rejection, revoking a counterparty link, and re-running analysis on a contract are all plausible one-click actions — not confirmed whether any of them have a confirm step. Worth an explicit audit as part of the next polish pass rather than assuming either way. |
| 5 | Notifications for state changes relevant to the signed-in user | ❌ Missing | No notification affordance anywhere (no bell icon, no toast on background events). A reviewer who approves something, or an admin whose counterparty just countersigned, has no signal short of manually reloading the right page. |
| 6 | Global search across contracts/findings | ❌ Missing | At 16+ contracts and 95+ findings and growing, there's no way to search by name, clause type, or finding category from anywhere except scrolling a dropdown. Fine at demo scale; a real gap at real scale. |
| 7 | Nested nav sections have a visible expand/collapse affordance | ⚠️ Partial | "Administration" has two real children (Members, Workflows) reachable only by scrolling the sidebar past the fold — no chevron, no visual grouping, no indicator there's more below. They work once found; they're not discoverable. |
| 8 | Every "Metrics that Matter" / Reports row has real data behind it | ⚠️ Partial | "LexProof AI Analysis (measured)" still shows "Not available" — the estimated-manual-review comparison is real, the measured-AI-time comparison isn't wired to persist. |
| 9 | A visible audit/activity log beyond a single workflow instance's history | ❌ Missing | Per-proposal workflow history exists and renders well (confirmed live, §25/§26). There's no cross-cutting "everything that happened in this org, recently" view — which matters more now that there's real multi-user RBAC to audit. |
| 10 | Settings / org profile page | ❌ Missing | No page for org name/branding, notification preferences, default expiry for counterparty links, etc. — everything is currently either hardcoded or set per-action (e.g., counterparty link expiry defaults to 14 days with no org-level override). |

---

## Nice-to-have

Genuinely optional — list them for completeness, don't chase them before the must/should items above:

- Dark mode
- Command palette / keyboard shortcuts (⌘K-style contract or finding jump-to)
- CSV/PDF export of the Reports page
- Saved filters/views on the Contracts and Findings lists
- A first-run onboarding tour
- Mobile-optimized layout (not independently verified this session — window-resize testing didn't reliably reflow in this sandbox; worth a real device-toolbar check separately, but low priority for a product that's realistically used at a desk)
- Customizable/reorderable dashboard widgets
- Per-user notification preferences (email/in-app)

---

## Net read

The **substance** is genuinely enterprise-grade already: real multi-tenant RBAC with a generic workflow engine, real cryptographic evidence with independent verification, a real external-counterparty flow with a defensible token security model. That's the hard 80% and it's done well.

What's missing is almost entirely **the last-mile polish that separates "built by engineers, for engineers" from "ready for a buyer or a judge who's seen a hundred of these"**: no visible user identity, fake activity data, plain-text empty states and loading states, inconsistent chrome, and four still-open bugs that are each individually small but collectively read as "not quite finished." None of these require new architecture — they're exactly the kind of pass a UI-polish-focused Cursor session is good at, which is what the accompanying prompt targets.
