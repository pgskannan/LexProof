# LexProof E2E Workflow Audit

Date: 2026-09-18
Scope: the redline-proposal review/approval lifecycle (LexProof's real implementation
of "contract review and approval") -- contract upload, AI-generated findings, redline
proposals, the generic workflow engine, RBAC, audit/history, and the two currently
passing Playwright tests.

This audit is based on reading the actual implementation (not assumptions):
`backend/app/lexproof/services/workflow_engine.py`, `workflow_catalog.py`,
`redline_proposals.py`, `organizations.py`, `roles.py`, `services/audit.py`,
`api/redline_proposals.py`, `api/contracts.py`, `api/audit_log.py`, `api/findings.py`,
the frontend remediation/findings/contracts/audit-log pages, the E2E helpers in
`frontend/e2e/`, and the backend unit test suite (866 tests).

---

## 1. Current E2E coverage

Two Playwright specs exist and both currently pass (`npx playwright test` -> 2 passed).

### `e2e/smoke/auth.smoke.spec.ts`

- **What it tests:** the authentication/session foundation only -- unauthenticated
  redirect to `/login`, real Firebase email/password sign-in through the real login
  form, a real authenticated call to `/api/me`, session survival across navigation,
  and real logout (session actually cleared, not just a page change).
- **Authentication:** real Firebase Auth (email/password), no mocking, no bypass.
- **Roles involved:** one generic authenticated user (`E2E_USER_EMAIL`), no
  org-role-specific behavior exercised.
- **APIs exercised:** implicitly `/api/me` (observed via a generic "any `/api/*`
  request fired" check, not asserted on response content).
- **UI workflow exercised:** login form, dashboard load, navigation, logout.
- **What is real:** everything -- real frontend, real backend, real Firebase.
- **What is mocked/stubbed:** nothing.
- **Not covered:** contracts, findings, redline proposals, workflow transitions, RBAC,
  audit trail, persistence of business data, tenant isolation.

### `e2e/workflow/golden-path-review-approval.spec.ts`

- **What it tests:** the owner-submits / reviewer-approves half of the redline
  workflow (`draft -> in_review -> approved`), starting from a deterministic,
  pre-seeded fixture (`backend/scripts/create_approval_demo_fixture.py --fixture
  golden-path`) rather than a fresh upload.
- **Authentication:** real Firebase Auth, two distinct role-scoped identities
  (`demo-owner-1`, `demo-reviewer-1`), logging in and out through the real UI between
  roles.
- **Roles involved:** `contract_owner` (demo-owner-1), `reviewer` (demo-reviewer-1).
- **APIs exercised (indirectly, through real UI actions):** `PATCH
  /api/redline-proposals/{id}` (the real "Submit for review" action, labeled "Save
  proposal" in the UI) and `POST /api/redline-proposals/{id}/review` (the real
  "Approve" action).
- **UI workflow exercised:** findings page (contract-scoped) -> finding row -> "Review
  Finding" -> remediation page -> fill proposed text -> "Save proposal" -> assert
  status badge "PROPOSED" -> logout -> reviewer login -> same page -> "Approve" ->
  assert status badge "APPROVED".
- **What is real:** everything the UI touches -- real Firebase auth per role, real
  backend, real Firestore-backed workflow engine, real separation-of-duties/role
  enforcement (implicitly, by virtue of using two real distinct identities), real
  status transition.
- **What is mocked/stubbed:** nothing. The finding/proposal/contract data is
  pre-seeded (not created through the UI in this test), which is a deliberate,
  documented determinism tradeoff from an earlier phase, not a mock.
- **Not covered:** contract creation/upload, AI analysis, rejection, resubmission,
  publish, duplicate-approval rejection, unauthorized-reviewer rejection,
  self-approval rejection, persistence across refresh/logout-login, audit trail,
  cross-tenant isolation.

### Naming note carried over from the fixture/test's own comments

There is no literal "Submit for Review" or "Review Approval" UI text anywhere in the
codebase (confirmed by grep, zero matches). The real UI action names are **"Save
proposal"** (with non-empty text, on a draft proposal -- triggers the real
`submit_for_review` transition) and **"Approve"** (triggers the real `approve`
transition). This audit and the new tests below use the app's real labels, not the
generic labels from the task description that requested this audit.

---

## 2. Complete workflow map (real implementation, real names)

LexProof's "contract creation" and "document upload" are **the same single action**:
`POST /api/contracts` (`upload_contract` in `api/contracts.py`) creates the `contracts`
document and its first `contract_versions` document together, from an uploaded file.
There is no separate "create empty contract, then upload a file into it" flow.

Findings are not user-authored; they are produced by AI analysis
(`POST /api/contracts/{id}/analyze`, Gemini/Vertex AI), which the frontend's "Upload
and analyze" button calls automatically, synchronously, right after upload.

A "redline proposal" -- LexProof's real unit of review/approval -- is created against
one specific finding and is what actually carries a workflow state. **There is no
contract-level or version-level "PENDING_REVIEW"/"APPROVED" status** in this app; those
states belong to each individual redline proposal (and, underneath it, to a workflow
instance keyed `(org_id, "redline_proposal", proposal_id)`).

Real states (`workflow_catalog.py: CONTRACT_REDLINE_STATES`) and the proposal-facing
status label each one displays as (`PROPOSAL_STATUS_BY_STATE`):

```
draft       -> "DRAFT"       (initial state)
in_review   -> "PROPOSED"
approved    -> "APPROVED"
rejected    -> "REJECTED"    (terminal)
published   -> "PUBLISHED"   (terminal)
```

Real transitions (`CONTRACT_REDLINE_TRANSITIONS`), each with the real allowed roles
and real separation-of-duties rule:

```
submit_for_review : draft     -> in_review  | roles: contract_owner, admin | no SoD rule
approve           : in_review -> approved   | roles: reviewer, admin      | actor != created_by
reject            : in_review -> rejected   | roles: reviewer, admin      | no SoD rule
publish           : approved  -> published  | roles: approver, admin     | actor != created_by
```

Full real golden path, mapped onto the task's requested generic steps:

```
OWNER (contract_owner)
  |
  Login                                     -- real Firebase auth
  v
Create Contract + Upload Document            -- ONE action: POST /api/contracts
  |                                             (UI: "Upload and analyze" button)
  v
[automatic] AI analysis (Gemini)             -- POST /api/contracts/{id}/analyze,
  |                                             produces risk_findings documents
  v
Owner opens a finding -> "Review Finding"    -- creates (or opens) a redline_proposal
  |                                             tied to that finding
  v
Submit for Review == "Save proposal"         -- PATCH /api/redline-proposals/{id}
  | (with non-empty proposed_text, from draft)  -> workflow transition submit_for_review
  v
PROPOSED  (== in_review)
  |
REVIEWER (reviewer role)
  |
  Login
  v
Find Pending Contract == findings page,      -- GET /api/findings?contract_id=...
  filtered by contract_id
  v
Open Contract -> "Review Finding"            -- same remediation page, same proposal
  v
Review == "Approve" button                   -- POST /api/redline-proposals/{id}/review
  |                                             {decision: "APPROVED"}
  v
APPROVED
  |
OWNER
  |
  Login / Refresh
  v
Verify APPROVED                              -- Badge shows "APPROVED" (persisted
  |                                             Firestore state, not local state)
  v
Verify Approval History                      -- GET /api/redline-proposals/{id}/review
  |                                             record (redline_reviews collection);
  |                                             also workflow instance history
  v
Verify Audit Trail                           -- GET /api/audit-log (admin/auditor UI
                                                 at /dashboard/admin/audit-log),
                                                 actions "contract.uploaded",
                                                 "redline.approved"/"redline.rejected",
                                                 "redline.published"
```

There are actually **two** independent, real audit mechanisms, both worth testing:

1. **Workflow-instance history** (`workflow_engine.py: execute_transition`) -- every
   transition writes an event (`event_id, instance_id, transition_id, from_state,
   to_state, actor_id, actor_roles_at_time, comment, occurred_at`) into
   `workflow_instances/{instance_id}/history`, in the **same Firestore transaction**
   as the state change itself. This is the ground-truth, always-on record.
2. **Flat cross-cutting audit log** (`services/audit.py: record_audit_event`) -- a
   separate, best-effort (try/except-wrapped, never blocks the action it records)
   human-readable feed in the `audit_log` collection, written from the API layer for
   `contract.uploaded`, `redline.created`, `redline.approved`/`redline.rejected`,
   `redline.published`. Readable through a real, role-gated UI page
   (`/dashboard/admin/audit-log`, admin/auditor only).

---

## 3. Workflow gaps and VERIFIED items

### VERIFIED (already correct, evidence below)

- **Duplicate approval is rejected at two independent layers.**
  `ProposalService.review()` explicitly raises `FinalDecisionError` (-> HTTP 409) if
  `proposal.status` is already `APPROVED`/`REJECTED`/`PUBLISHED`, *before* even calling
  the workflow engine. Independently, `WorkflowEngine._validate_transition` also
  refuses any transition whose `from_state` doesn't match the instance's actual
  `current_state` (`approve`'s `from_state` is `in_review`, not `approved`), so even a
  hypothetical caller that bypassed the service layer would still be blocked by the
  state machine itself. Backend unit coverage exists
  (`test_rejected_review_persists_and_final_decision_is_immutable`), but there was no
  E2E proof of this before this audit, since the UI hides the Approve/Reject buttons
  entirely once a proposal reaches a final status (see gap below) -- a real E2E test
  of this needs to bypass the UI on purpose, via a direct authenticated call, which is
  exactly what the task's own instructions require ("a hidden UI button is not
  sufficient").

- **Self-approval (separation of duties) is enforced by the backend, not just hidden
  in the UI.** `approve` and `publish` both carry `requires_not_actor: ["created_by"]`,
  checked in `WorkflowEngine._validate_transition` (bypassed only for `admin`).
  Backend unit coverage: `test_owner_with_approver_role_cannot_approve_own_submission`
  (`tests/test_redline_proposals.py`). See the UI/backend mismatch noted below,
  though -- this matters for how the new E2E test proves it.

- **Tenant isolation is enforced at the service layer for every proposal/finding/
  contract operation**, via `OrganizationService.get_active_member(org_id, uid)`
  checks in `_require_member`/`_require_contract_member`
  (`redline_proposals.py`) and the equivalent `_visible()` helpers in
  `contracts.py`/`findings.py`. Extensive backend unit coverage exists:
  `test_member_of_a_different_org_is_not_authorized`,
  `test_member_of_foreign_org_cannot_create_version`,
  `test_member_of_foreign_org_cannot_analyze_contract`,
  `test_member_of_foreign_org_cannot_use_explicit_version_analyze_endpoint`
  (`tests/test_contract_action_authorization.py`), and more.

- **Audit trail is real and durable**, written in the same transaction as the state
  change it records (workflow history) or as a best-effort, failure-isolated write
  (flat audit log) -- not a UI-only construct.

### GAPS (concrete, evidence-based, not manufactured)

- **CRITICAL -- no E2E fixture/test proves tenant isolation end-to-end.** Only one
  organization (`lexproof-demo`) has real, provisioned Firebase identities in this
  repo. Cross-tenant isolation is thoroughly unit-tested (see above) but has never
  been exercised through two real logged-in browser sessions against two real orgs.
  Building this requires new fixture infrastructure (a second org + at least one new
  real Firebase identity), which this audit intentionally does not invent on its own
  -- see the Defects/Remaining-gaps section for the concrete next step.

- **HIGH -- rejection has no resubmission path.** `rejected` is a terminal state in
  `CONTRACT_REDLINE_STATES` (`is_terminal: true`), and `CONTRACT_REDLINE_TRANSITIONS`
  defines no transition whose `from_state` is `rejected`. Once a proposal is rejected,
  `ProposalService.update()` also refuses further edits
  (`FinalDecisionError` for any status in `{APPROVED, REJECTED, PUBLISHED}`). This is
  a real, current product gap, not a test gap -- the task's Phase 4D scenario
  (reject -> owner edits -> resubmit -> re-review -> approve) **cannot be implemented
  today** without a product/workflow change, which is out of this audit's scope.
  Documented here rather than invented.

- **MEDIUM -- UI/backend mismatch: the Approve/Reject buttons are not role-gated in
  the UI.** `remediation/page.tsx` shows the "Human review" card (with both Approve
  and Reject buttons) to *any* user who can load the page -- there is no
  `roles.includes('reviewer')` (or similar) check hiding these buttons from a
  contract_owner-only user. The backend correctly rejects the action either way (a
  `contract_owner`-only actor gets a real 403 for wrong role on `approve`/`reject`),
  so there is no actual security hole -- but a user who is not entitled to review will
  see actionable-looking buttons that always fail, which is a real UX/defense-in-depth
  gap worth fixing independently of this audit.

- **MEDIUM -- "unauthorized reviewer" and "self-approval" collapse into the same
  code path with the current demo identities.** `demo-owner-1` holds only the
  `contract_owner` role, so an E2E attempt for `demo-owner-1` to approve their own
  submission is genuinely blocked, but by the **role check**
  (`WorkflowPermissionError`, "Role contract_owner cannot perform Approve") rather
  than by the deeper **separation-of-duties check**
  (`WorkflowSeparationOfDutiesError`, which only fires for an actor who *does* hold an
  allowed role but is also the proposal's `created_by`). Both are real, backend-
  enforced 403s and both are worth proving, but they are not the same guarantee. The
  backend unit suite already proves the deeper SoD guard directly
  (`test_owner_with_approver_role_cannot_approve_own_submission`, using a fake actor
  who holds both roles). Proving the SoD guard specifically through a real E2E login
  would require a new demo identity provisioned with both `contract_owner` and
  `reviewer` roles -- not invented in this audit; see Remaining gaps.

- **LOW -- the golden-path E2E test still starts from a pre-seeded fixture, not a
  fresh upload.** This was a deliberate, documented tradeoff in an earlier phase (real
  AI analysis is slow and depends on live Vertex AI/Gemini availability, which would
  make the existing regression-gate test slow and non-deterministic). A *separate*,
  new test that exercises the real upload -> real AI analysis -> real finding path is
  the right way to close this gap without weakening the existing fast, deterministic
  regression gate -- see Phase 3 below.

- **Not a gap, but worth recording precisely:** publish (`approved -> published`) is
  fully implemented (real content substitution, new contract version, publication
  audit record) but is out of scope for this audit's E2E additions, which focus on
  the review/approval half of the lifecycle the task described.

---

## 4. What this audit does NOT cover

Per the task's own instruction not to manufacture gaps or invent functionality: this
audit deliberately stops at reading and mapping the real implementation. Everything
above is sourced from the actual files, not assumed from the task's generic ASCII
diagrams. The next phases (new E2E tests, negative/security coverage, persistence and
audit-trail verification, the regression gate, and the final coverage matrix) are
tracked and reported separately as they are implemented and actually run.
