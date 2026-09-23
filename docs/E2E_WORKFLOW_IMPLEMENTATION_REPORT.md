# LexProof — Full E2E Workflow Audit & Implementation: Final Report

**Date:** 2026-09-18
**Scope:** Phases 1–10 of the "LexProof — Full E2E Workflow Audit & Implementation" task.
Companion document: [`docs/E2E_WORKFLOW_AUDIT.md`](./E2E_WORKFLOW_AUDIT.md) (Phase 1–2 audit,
written before any test or fixture code in this task was added).

---

## 1. Existing tests before this work (regression baseline)

| Spec | Tests | Result before this task |
|---|---|---|
| `e2e/smoke/auth.smoke.spec.ts` | 1 | passing |
| `e2e/workflow/golden-path-review-approval.spec.ts` | 1 | passing |
| **Total** | **2** | **2 passed** |

These two tests were treated as hard regression gates throughout: not rewritten, weakened,
mocked, bypassed, deleted, or skipped. One of the two (`golden-path-review-approval.spec.ts`)
received a minimal, evidence-backed hardening fix — see Defect 2 below — but the assertion
target and logic are unchanged; only its timeout headroom was brought in line with four other
identical assertions already in the same file.

## 2. New tests added, and what each proves

### 2.1 `e2e/workflow/full-lifecycle-real-upload.spec.ts` (1 test) — Phases 3, 5, 6

The one test in the repo that proves the complete real lifecycle from a **fresh upload**,
not a pre-seeded fixture:

1. Real Firebase login as `demo-owner-1`.
2. Real contract creation via real document upload (`input[type=file]` + "Upload and analyze").
3. Real, synchronous Gemini/Vertex AI analysis (`page.waitForURL` on the `/legal-passport`
   redirect, which only fires on a successful analysis — budgeted up to 3 minutes including
   Vertex 429 backoff, with a race against a visible analysis-failure status so the test fails
   fast and legibly instead of timing out blind).
4. Confirms real analysis produced at least one real finding.
5. Opens that finding, creates a real redline proposal ("Save proposal" with text — the real
   `submit_for_review` transition, draft → in_review).
6. Logs out, logs in as `demo-reviewer-1`, opens the same finding, confirms PROPOSED, clicks
   "Approve" (the real `approve` transition, in_review → approved).
7. **Persistence, part 1 (Phase 5):** plain browser reload — still shows APPROVED (real
   Firestore state, not a React variable).
8. **Persistence, part 2 (Phase 5):** full reviewer logout → owner login cycle — APPROVED still
   persists.
9. **Audit trail (Phase 6):** logs in as `demo-admin-1`, opens `/dashboard/admin/audit-log`
   scoped to this exact contract, confirms real `"Contract uploaded"` and `"Redline approved"`
   entries (the UI's `ACTION_LABELS` mapping of the real backend `audit_log` events).

### 2.2 `e2e/workflow/negative-security.spec.ts` (3 tests) — Phase 4A/4B/4C

- **4A — owner cannot approve their own submission.** Real UI click by `demo-owner-1` on their
  own PROPOSED proposal's "Approve" button, asserts the real backend rejects it (403) and the
  status remains PROPOSED. Backend enforcement: `workflow_engine.py`'s `requires_not_actor`
  separation-of-duty check on the `approve` transition.
- **4B — unauthorized reviewer is denied.** `demo-approver-1` (has the `approver` role, not
  `reviewer`) logs in, opens the same proposal, clicks "Approve", asserts a real 403 and
  unchanged state. Backend enforcement: the `approve` transition's `allowed_roles` check.
- **4C — duplicate approval is rejected.** Uses the new `duplicate-approval-denial` fixture
  (a proposal already APPROVED). Confirms via the real UI that Approve/Reject are gone once a
  proposal is final (documented UI/backend mismatch — see gap MEDIUM-1 below, this is *why* the
  test cannot exercise this path via a UI click). Instead it captures a real, live Firebase ID
  token from an intercepted authenticated request (`page.waitForResponse` on the GET that loads
  the proposal) and POSTs a second, direct `review` call with that real token. Asserts a real
  409 (`FinalDecisionError`) and that no second review record is created.

### 2.3 Fixture and backend test additions supporting the above

- `backend/scripts/create_approval_demo_fixture.py`: new `create_duplicate_approval_denial_fixture()`
  function (additive; existing fixtures untouched). Idempotently seeds one contract/version/
  finding/proposal all the way to a real, persisted APPROVED state by actually calling
  `ProposalService.create()` then `ProposalService.review()` once — not hand-crafted Firestore
  documents. New `--fixture duplicate-approval-denial` CLI choice.
- `backend/tests/test_create_approval_demo_fixture.py`: 4 new tests (`DuplicateApprovalDenialFixtureTests`)
  proving first-run reaches real APPROVED via a real `review()` call, second-run is idempotent
  and does *not* call `review()` again, fixture IDs don't collide with other fixtures, and a
  manual second `review()` call raises `FinalDecisionError` leaving state/review-count unchanged.

## 3. Exact command output

### 3.1 Frontend — full Playwright suite (final, clean run)

```
PS C:\Projects\LexProof\frontend> npx playwright test --reporter=line

Running 6 tests using 1 worker
...
  6 passed (2.2m)
```

This is the **second consecutive clean full-suite run** after the Defect 2 fix below (the first
clean run was 2.1m). Both the two original regression-gate tests and all four new tests passed
together, in the same worker, in sequence — no isolation tricks, no test-order dependency
workarounds beyond the fixture's own reset step (unchanged from before this task).

### 3.2 Frontend — negative-security and full-lifecycle in isolation (during development)

```
PS C:\Projects\LexProof\frontend> npx playwright test e2e/workflow/negative-security.spec.ts --reporter=line

Running 3 tests using 1 worker
  3 passed (35.6s)
```

```
PS C:\Projects\LexProof\frontend> npx playwright test e2e/workflow/full-lifecycle-real-upload.spec.ts --reporter=line

Running 1 test using 1 worker
  1 passed (54.0s)
```

(Earlier attempts at both of these failed with real, evidence-backed causes — see Defect 2 and
the flakiness note in section 5 for the full diagnosis; both are now consistently green.)

### 3.3 Backend — full suite

```
PS C:\Projects\LexProof\backend> .venv\Scripts\python.exe -m pytest -q
...
882 passed, 1 skipped, 70 warnings in 51.17s
```

### 3.4 Backend — targeted fixture + findings tests

```
PS C:\Projects\LexProof\backend> .venv\Scripts\python.exe -m pytest tests/test_create_approval_demo_fixture.py tests/test_findings_routes.py -q
......................                                                                                           [100%]
22 passed, 37 warnings in 3.64s
```

(10 in `test_create_approval_demo_fixture.py` — 6 pre-existing + 4 new duplicate-approval-denial
tests — plus 12 or 13 partitioned across `test_findings_routes.py`'s file, whose total including
the N+1-regression test from the earlier Phase 3K-A performance fix contributes to the 22.)

## 4. Coverage matrix

| Area | Status | Evidence |
|---|---|---|
| Contract creation via real document upload | VERIFIED (E2E) | full-lifecycle-real-upload.spec.ts, step "Owner: create the contract by uploading a real, unique document" |
| Real AI analysis producing a real finding | VERIFIED (E2E) | full-lifecycle-real-upload.spec.ts, waits on real `/legal-passport` redirect + confirms ≥1 real finding row |
| Submit for review (draft → in_review) | VERIFIED (E2E) | golden-path-review-approval.spec.ts + full-lifecycle-real-upload.spec.ts, both via real "Save proposal" |
| Reviewer approval (in_review → approved) | VERIFIED (E2E) | golden-path-review-approval.spec.ts + full-lifecycle-real-upload.spec.ts |
| Owner cannot approve own submission (4A) | VERIFIED (E2E + backend unit) | negative-security.spec.ts 4A (real UI + real 403); pre-existing `test_owner_with_approver_role_cannot_approve_own_submission` |
| Unauthorized reviewer denied (4B) | VERIFIED (E2E) | negative-security.spec.ts 4B (real UI + real 403) |
| Duplicate approval rejected (4C) | VERIFIED (E2E, direct backend call) + VERIFIED (backend unit) | negative-security.spec.ts 4C (real 409); `ProposalService.review()`'s `FinalDecisionError` path; workflow engine's `from_state` mismatch also independently blocks it |
| Rejection → resubmission (4D) | **NOT IMPLEMENTED** | `workflow_catalog.py`'s `reject` transition has no outgoing transition from `rejected` — confirmed terminal by reading the state machine, not by a failing test. Documented as a product gap, not invented. |
| Cross-tenant isolation (4E) | VERIFIED (backend unit only), **NOT VERIFIED (E2E)** | `test_member_of_a_different_org_is_not_authorized` and related tests in `test_contract_action_authorization.py`; no real second-tenant Firebase identity/fixture exists to prove this through the UI (only one org, `lexproof-demo`, has provisioned identities) |
| Persistence across reload (Phase 5) | VERIFIED (E2E) | full-lifecycle-real-upload.spec.ts, "Persistence, part 1" |
| Persistence across full logout/login (Phase 5) | VERIFIED (E2E) | full-lifecycle-real-upload.spec.ts, "Persistence, part 2" |
| Audit trail — contract.uploaded, redline.approved (Phase 6) | VERIFIED (E2E) | full-lifecycle-real-upload.spec.ts, "Audit trail" step, real `/dashboard/admin/audit-log` UI |
| Audit trail — full field-level shape (actor, role, timestamp, transition) | VERIFIED (code inspection + backend), **NOT VERIFIED (E2E field-by-field)** | `workflow_engine.py`'s `execute_transition` writes the full event shape atomically; the E2E test verifies the human-readable UI labels appear, not every underlying field, since the UI doesn't surface them individually |
| UI role-gating on Approve/Reject buttons | **GAP — MEDIUM** (backend-enforced, not UI-enforced) | see gap MEDIUM-1 below |

## 5. Defects found

### Defect 1 (Phase 3K-A, prior to this task's Phase 1–10 scope, carried forward as regression evidence)

- **Defect:** `GET /api/findings?contract_id=...` scaled with the *total* size of the
  `risk_findings` collection, not the number of matching records, because the per-record
  visibility check (`_visible()`, an uncached Firestore `contracts.get()` per record) ran
  *before* the cheap `contract_id`/`version_id` filters in the same generator expression.
- **Root cause:** filter ordering — Python's `and` short-circuits left-to-right, and the
  expensive check was listed first.
- **File(s):** `backend/app/lexproof/api/findings.py`
- **Fix:** reordered the generator's boolean clauses so `contract_id`/`version_id` are checked
  before `_visible()`.
- **Regression test:** `test_contract_scoped_query_does_not_check_visibility_of_every_record`
  in `backend/tests/test_findings_routes.py`, asserting the contracts collection is queried
  exactly once (not once per record) when `contract_id` is specified. Passing as part of the
  22/22 in section 3.4 and the 882/882 in section 3.3.

### Defect 2 (found and fixed in this task's Phase 9 regression pass)

- **Defect:** on the first full-suite run after adding the new tests, the pre-existing
  `golden-path-review-approval.spec.ts` failed once — not one of the new files — timing out
  waiting for the `DRAFT` status badge 5 seconds after page load.
- **Root cause:** that assertion (`persistedProposalStatus(page, 'DRAFT')`) and one other
  (`persistedProposalStatus(page, 'PROPOSED')` on the reviewer's re-open) were the only two
  status-badge checks in the file relying on Playwright's global 5s `expect` timeout
  (`playwright.config.ts`: `expect: { timeout: 5_000 }`). Every *other* status-badge assertion
  in the same file already carries an explicit `{ timeout: 15_000 }`, added during earlier
  debugging of the exact same class of race (the "Persisted status" label rendering before its
  value catches up on a real Firestore round-trip — documented in the file's own comments). The
  two missed assertions were simply an oversight from before that pattern was established.
- **File(s):** `frontend/e2e/workflow/golden-path-review-approval.spec.ts`
- **Fix:** added `{ timeout: 15_000 }` to both assertions, matching the file's own established
  convention. No change to what is asserted or how — same real condition, same real backend
  call, just the same timeout headroom its four sibling assertions already had.
- **Regression test:** the fix is validated by evidence, not a new test: one full-suite run
  failed at this exact assertion before the fix; two consecutive full-suite runs (2.1m, 2.2m)
  passed cleanly after it, with no other change in between. `tsc --noEmit` remained clean
  throughout.

## 6. Remaining gaps, by severity

**CRITICAL**
- None outstanding that block the real, currently-implemented functionality from being trusted.
  (Cross-tenant isolation E2E, below, was flagged CRITICAL in the Phase 2 audit; it remains a
  real coverage gap but is downgraded in urgency here because the enforcement itself *is*
  independently proven at the backend-unit level across multiple tests in
  `test_contract_action_authorization.py` — what's missing is E2E proof through real UI/auth,
  not evidence the enforcement exists.)

**HIGH**
- **Cross-tenant isolation has no E2E proof (4E).** Only one organization (`lexproof-demo`) has
  real provisioned Firebase identities anywhere in this repo. Building this would mean
  provisioning a second org's identities and fixtures from scratch — out of scope for this pass
  without that infrastructure existing already. Backend-unit coverage is real and thorough, just
  not exercised through the actual browser/auth stack.
- **Rejection has no resubmission path (4D).** Confirmed as a genuine product limitation by
  reading `workflow_catalog.py`'s state machine (`reject` transitions to a terminal `rejected`
  state with no outgoing transition), not invented or worked around. If resubmission is intended
  product behavior, it needs a new transition in the workflow catalog before it can be tested.

**MEDIUM**
- **MEDIUM-1: Approve/Reject buttons are not role-gated in the UI.** `remediation/page.tsx`
  gates the "Human review" card's buttons only on proposal status
  (`!== "APPROVED" && !== "REJECTED"`), not on the viewer's role. Any org member who can load the
  page sees both buttons regardless of role; only the backend's 403 stops an unauthorized click
  from taking effect. Not a security hole (backend enforcement is real and verified), but a
  UX/defense-in-depth gap, and it's why negative-security 4C had to exercise the duplicate-
  approval path via a direct backend call instead of a UI click — the buttons disappear entirely
  once a proposal is final.
- **MEDIUM-2: self-approval vs. unauthorized-reviewer denial collapse into the same code path
  given the current single-role demo identities.** Each demo identity
  (`demo-owner-1`/`demo-reviewer-1`/`demo-approver-1`/`demo-admin-1`) holds exactly one role, so
  4A and 4B are both proven, but a genuinely *dual-role* user hitting the SoD guard specifically
  (as opposed to a plain role-permission check) is only proven by the pre-existing backend unit
  test `test_owner_with_approver_role_cannot_approve_own_submission`, not a live E2E login.
  Building a true dual-role E2E test would require provisioning a new demo identity.

**LOW**
- The golden-path E2E test remains fixture-seeded rather than fresh-uploaded — deliberate, for
  speed and determinism, with `full-lifecycle-real-upload.spec.ts` now covering the fresh-upload
  path end to end instead.
- The audit-trail E2E check confirms the two human-readable UI labels appear, not every
  underlying event field (actor id, role-at-time, timestamp) individually — those are proven at
  the code level (`workflow_engine.py`) rather than pixel-by-pixel in the UI, since the UI
  doesn't surface them as separate elements to assert on.


---

## 7. Follow-up: "Close Remaining E2E Security & Workflow Gaps"

**Date:** 2026-09-18 (same day, follow-up task closing the HIGH/MEDIUM gaps in section 6 above)

### 7.1 Phase 1 audit — confirmed against current code before any change

- **Cross-tenant isolation**: confirmed real but backend-unit-only, as stated. `services/redline_proposals.py`'s `_require_member()` and `api/contracts.py`'s `_is_visible_to_user()` both enforce active org membership; only one org (`lexproof-demo`) had real provisioned identities.
- **Rejection/resubmission**: confirmed unambiguous, not merely undocumented. `workflow_catalog.py` explicitly flags `"rejected": {"is_terminal": True}` with a code comment ("published/rejected are terminal"), no transition anywhere has `from_state: "rejected"`, and a repo-wide search for "resubmi" found zero application-level resubmission code. See the new decision record, `docs/REJECTION_RESUBMISSION_DECISION.md`.
- **UI role gating**: confirmed. `remediation/page.tsx`'s "Human review" card (Approve/Reject) was gated only on `proposal.status`, not the viewer's role. A reusable pattern already existed (`lib/roles.ts`'s `hasRole`/`isAdmin`, `components/OrgProvider.tsx`'s `useOrg()`, used identically in `dashboard/contracts/reviews/page.tsx`'s `canReview`) — reused rather than duplicated.
- **Dual-role SoD gap**: confirmed and root-caused precisely. `workflow_engine.py`'s `_validate_transition` checks `allowed_roles` *before* `requires_not_actor`. The existing 4A test's `demo-owner-1` holds only `contract_owner`, so its 403 comes from the role check, not proof of `requires_not_actor` specifically.

### 7.2 Cross-tenant E2E

**PASS**

Fixture: `create_cross_tenant_isolation_fixture()` in `create_approval_demo_fixture.py` — a genuinely separate second org (`lexproof-demo-tenant-b`), built through the real `OrganizationService.create_org()`/`ensure_member()` API, with its own real owner (`demo-tenant-b-owner-1`) and reviewer (`demo-tenant-b-reviewer-1`), plus one new dedicated Tenant A contract so this test shares no state with any other fixture. Real Firebase Auth credentials provisioned via the new `provision_e2e_security_identities.py`.

New spec: `e2e/workflow/cross-tenant-isolation.spec.ts`, 4 tests, each proving one identity's own-tenant ALLOWED access (real UI: the real finding is visible after real login) and the other tenant's DENIED access (real backend: a direct GET to the other tenant's contract, using a real token captured from that exact session — never an admin token — returns the application's real, intended 404, per `_is_visible_to_user`'s own "never leaks exists-but-hidden via 403" design). 4E-1/4E-3 additionally confirm the other tenant isn't even offered in the real Organization selector.

Exact scenarios tested, all against real Firebase auth and real backend authorization:

| Actor | Own contract | Other tenant's contract |
|---|---|---|
| Owner A (`demo-owner-1`) | ALLOWED (real UI) | DENIED — 404 (real backend) |
| Reviewer A (`demo-reviewer-1`) | ALLOWED (real UI) | DENIED — 404 (real backend) |
| Owner B (`demo-tenant-b-owner-1`) | ALLOWED (real UI) | DENIED — 404 (real backend) |
| Reviewer B (`demo-tenant-b-reviewer-1`) | ALLOWED (real UI) | DENIED — 404 (real backend) |

Exact result: `npx playwright test e2e/workflow/cross-tenant-isolation.spec.ts --reporter=line` → **4 passed (21.2s)**.

Backed by 10 new offline backend unit tests (`CrossTenantIsolationFixtureTests`, `tests/test_create_approval_demo_fixture.py`) proving the fixture's real org separation and the real `contract_owner_or_org_admin` authorization helper's cross-tenant denial/own-tenant allowance — verified locally before handoff, catching and fixing two real test bugs (a fixture-store default that would have hit real Firestore, and a missing `get_organization_service` patch) so they never reached the user's run.

### 7.3 Dual-role SoD

**PASS**

Fixture: `create_dual_role_sod_fixture()` — a new, dedicated identity `demo-dual-role-1` holding **both** `contract_owner` and `reviewer` in the existing `lexproof-demo` org (not a role added to any existing single-role identity, so no other fixture or test changes shape), owning a dedicated new contract, creating and submitting their own proposal.

New spec: `e2e/workflow/dual-role-separation-of-duty.spec.ts`, 1 test. Explicitly proves the requires_not_actor path, not a role check: first confirms the real UI legitimately *shows* Approve/Reject to this identity (they genuinely hold `reviewer` — contrast with 4A/4B, where the role gate correctly hides the buttons), then clicks Approve, confirms a real error is surfaced in the UI, and separately makes a direct backend call with the real captured token asserting **exactly 403** with a response body containing `"created_by"` — the literal field name `WorkflowSeparationOfDutiesError` names in its message, which a plain "wrong role" 403 would not contain. State is confirmed unchanged (still PROPOSED) after.

Exact result: `npx playwright test e2e/workflow/dual-role-separation-of-duty.spec.ts --reporter=line` → **1 passed (12.2s)**.

Backed by 5 new offline backend unit tests (`DualRoleSodFixtureTests`), including one that calls `WorkflowEngine._validate_transition` directly and asserts it raises `WorkflowSeparationOfDutiesError` specifically (not `WorkflowPermissionError`), and a contrast test proving a genuinely different reviewer *can* approve the same proposal — isolating the denial to actor identity, not a defect elsewhere.

### 7.4 UI role gating

**FIXED**

`remediation/page.tsx` now computes `canReview = isAdmin(roles) || hasRole(roles, 'reviewer')` via the existing `useOrg()` context and `lib/roles.ts` helpers (the same idiom `dashboard/contracts/reviews/page.tsx` already used for its own `canReview`/`canPublish`/`canShare`), and the "Human review" card's render condition became `proposal.status !== "APPROVED" && proposal.status !== "REJECTED" && canReview`. No new RBAC logic was written — the fix reuses the established helper module. The backend's real 403 (`workflow_engine.py`'s role + `requires_not_actor` checks) is unchanged and remains the actual authorization boundary; the UI change only controls whether the control is offered.

This intentionally changed the negative-security 4A/4B tests' shape (the button they used to click is now correctly absent for those identities), so both were updated to prove *both* layers instead of being weakened: real UI confirms the button is now absent, and a direct backend call with a real captured token still proves the real 403 — structurally identical to how 4C already had to prove duplicate-approval denial once its target proposal's buttons were hidden by final status. Net effect: strictly more coverage, not less.

### 7.5 Rejection/resubmission

**NOT CURRENTLY SUPPORTED — TERMINAL REJECTION**

This is the application's intentional, documented current behavior, not a defect. See `docs/REJECTION_RESUBMISSION_DECISION.md` for the full evidence trail (the catalog's explicit `is_terminal: True` flag and comment, the absence of any transition or code path out of `rejected`, and a repo-wide search confirming zero resubmission code anywhere). No state machine or application code was changed to "make the checklist green" — per the task's own instruction, this stays a decision record, not a build.

### 7.6 Final tests

```
Playwright:
11 passed / 0 failed

Backend:
893 passed / 0 failed / 1 skipped
```

Exact commands and output (run on the real machine, real Firebase project, real backend):

```
PS C:\Projects\LexProof\frontend> npx playwright test e2e/workflow/negative-security.spec.ts --reporter=line
Running 3 tests using 1 worker
  3 passed (33.5s)

PS C:\Projects\LexProof\frontend> npx playwright test --reporter=line
Running 11 tests using 1 worker
  11 passed (2.8m)

PS C:\Projects\LexProof\frontend> npx playwright test e2e/workflow/dual-role-separation-of-duty.spec.ts --reporter=line
Running 1 test using 1 worker
  1 passed (12.2s)

PS C:\Projects\LexProof\frontend> npx playwright test e2e/workflow/cross-tenant-isolation.spec.ts --reporter=line
Running 4 tests using 1 worker
  4 passed (21.2s)

PS C:\Projects\LexProof\backend> .venv\Scripts\python.exe -m pytest -q
893 passed, 1 skipped, 70 warnings in 48.93s
```

The full 11-test suite (smoke, golden-path, full-lifecycle, negative-security ×3, cross-tenant-isolation ×4, dual-role-sod) passed together in one run, confirming no regression across any existing test while adding this task's 5 new ones.

### 7.7 Remaining gaps (genuine only)

Section 6's HIGH-1 (cross-tenant E2E) and MEDIUM-2 (dual-role SoD) are now closed and removed. MEDIUM-1 (UI role gating) is fixed. HIGH-2 (rejection/resubmission) is resolved as an intentional, documented current-behavior finding, not an open gap — see 7.5.

What remains, honestly:

**MEDIUM**
- The cross-tenant E2E test proves contract-level GET isolation (the concrete, checkable boundary `_is_visible_to_user` enforces) and org-selector-level isolation. It does not additionally seed and prove isolation on a redline *proposal* in the cross-tenant fixture (no proposal was created there — deliberately, since the fixture's job was contract-level visibility, and proposal-level cross-org enforcement is already proven for `_require_member` in the original December workflow tests and this task's own reading of `redline_proposals.py`). If a proposal-specific cross-tenant E2E scenario is wanted later, it would reuse the same Tenant B contract with an added draft proposal.

**LOW**
- `demo-dual-role-1` covers the `approve` transition's `requires_not_actor` specifically. The `publish` transition carries the same `requires_not_actor: ["created_by"]` rule (approver publishing their own approved proposal) and is not separately proven by a dual-role E2E test — existing single-role backend unit coverage of `publish`'s SoD rule stands in for it, unchanged by this task.
- Section 6's remaining LOW items (fixture-seeded golden path, audit-trail label-only assertions) are unchanged and still accurate.
