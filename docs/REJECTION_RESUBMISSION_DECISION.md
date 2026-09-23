# Decision Record: Rejection / Resubmission

**Date:** 2026-09-18
**Status:** Decided from existing evidence — REJECTED is intentionally terminal.
**Related:** `docs/E2E_WORKFLOW_AUDIT.md` (HIGH gap 4D), `docs/E2E_WORKFLOW_IMPLEMENTATION_REPORT.md`.

## Current behavior

REJECTED is **terminal**. There is no transition anywhere in the codebase that moves a
proposal or its workflow instance out of the `rejected` state.

```
DRAFT --submit_for_review--> IN_REVIEW --approve--> APPROVED --publish--> PUBLISHED
                                  |
                                  +--reject--> REJECTED   (terminal, no further transition)
```

This is **Option A** as posed in the follow-up task, not Option B (reject → owner edits →
resubmit → re-review → approve).

## Evidence from code

1. **`backend/app/lexproof/services/workflow_catalog.py`** — the state itself is explicitly
   flagged terminal, with a comment stating the intent directly:
   ```python
   {"id": "published", "name": "Published", "is_initial": False, "is_terminal": True},
   {"id": "rejected", "name": "Rejected", "is_initial": False, "is_terminal": True},
   ```
   ```python
   # draft/published/rejected have no SLA -- draft is un-owned busywork,
   # published/rejected are terminal -- only the two states that represent
   # someone's pending action on someone else's behalf carry one.
   ```
   `CONTRACT_REDLINE_TRANSITIONS` has exactly one transition with `from_state: "rejected"`
   — none. No `"resubmit"`, `"reopen"`, or `"revise"` transition id exists anywhere in the
   catalog.

2. **`backend/app/lexproof/services/workflow_engine.py`**'s `_validate_transition` enforces
   `from_state` matching against the instance's current state for *every* transition
   attempt — even if a caller invented a client-side "resubmit" action today, the engine
   would reject it as `"Transition {id} is not legal from state rejected"` (`WorkflowTransitionError`)
   because no transition definition has `from_state: "rejected"`.

3. **`backend/app/lexproof/services/redline_proposals.py`**'s `ProposalService.update()`
   explicitly blocks edits to a finalized proposal:
   ```python
   if <finalized>:
       raise FinalDecisionError(f"Finalized proposal cannot be edited: {proposal_id}")
   ```
   REJECTED is one of the three statuses (`APPROVED`/`REJECTED`/`PUBLISHED`) this guards
   against. So even the underlying proposal text cannot be changed once rejected, separate
   from the workflow-instance state question.

4. **Frontend** — `remediation/page.tsx` has no resubmission-adjacent control. The only
   post-decision UI is the "Human decision" review-result display; no button, route, or form
   references reopening, revising, or resubmitting a rejected proposal.

5. **Repo-wide search** — `grep -rni "resubmi"` across `backend/app`, `backend/tests`,
   `docs/`, and `frontend/app`/`frontend/e2e`/`frontend/lib` turns up zero references to
   resubmission in application or product-facing code. The only matches anywhere in the repo
   are unrelated (`test_recover_confirmed_transaction_persists_without_resubmitting` in the
   blockchain-anchor test suite, and one `docs/BACKEND_AUDIT.md` line about Ethereum
   *transaction* resubmission — neither concerns the proposal workflow).
   `docs/E2E_WORKFLOW_AUDIT.md` (written before this task, Phase 1–2 of the prior audit)
   independently reached the same conclusion: *"rejected is a terminal state... the full
   cycle... cannot be implemented [without a product decision]"*.

No file in the repository — code, tests, or docs — describes or implies Option B. The
evidence is unambiguous, not merely silent, so this is a documented current-behavior finding,
not an invented interpretation.

## Implications

- A rejected proposal is a dead end today: the only way to revisit that finding is for the
  contract owner to create an **entirely new** redline proposal against the same finding
  (`ProposalService.create()` has no uniqueness constraint preventing a second proposal for
  the same `finding_id`), which starts a **new** workflow instance at `draft`, independent of
  the rejected one. This is a workaround available today, not a first-class "resubmit" flow —
  the rejected proposal's own record and audit trail remain untouched and permanently REJECTED.
- No UI encourages or exposes this workaround; a contract owner would have to independently
  discover it by re-opening the same finding.
- This is consistent with — not a bug in — the workflow's separation-of-duties design:
  REJECTED being terminal means a reviewer's rejection is a final, auditable decision, not one
  that can be silently reworked into an approval through repeated resubmission.

## What would be required to support resubmission (Option B), if ever decided

This is scoping information only — nothing below is built, and nothing here should be read as
a recommendation to build it.

1. A new transition in `CONTRACT_REDLINE_TRANSITIONS`, e.g. `"reopen_for_revision"`:
   `from_state: "rejected"`, `to_state: "draft"`, `allowed_roles: ["contract_owner", "admin"]`
   (mirroring `submit_for_review`'s role set, since it's the same actor re-entering the front
   of the cycle).
2. `ProposalService.update()`'s finalized-proposal guard would need to distinguish "rejected,
   now reopened" from "still rejected" — likely by checking the *workflow instance's* current
   state rather than the proposal's cached `status` field, or by clearing/versioning the
   rejection decision when reopened.
3. A decision on whether the **existing** `review` record (the REJECTED decision) is kept as
   permanent history (recommended, consistent with `execute_transition`'s append-only history
   events) or whether a new review cycle needs its own review record, distinct from the first.
4. Frontend UI: a "Revise and resubmit" control on the remediation page for a REJECTED
   proposal, gated the same way the Phase 4 fix now gates Approve/Reject (role + status).
5. A decision on SLA/escalation semantics for the reopened `draft`/`in_review` states (the
   catalog already defines SLA hours for `in_review`; re-entering it a second time would need
   the same clock to apply, or an explicit decision that it doesn't).
6. New regression tests at both the backend (`workflow_engine`/`redline_proposals` unit level)
   and E2E level proving the full reject → revise → resubmit → re-review → approve cycle,
   without weakening the existing terminal-rejection tests for cases where resubmission is
   *not* invoked.

## Open product decision

None required for this task — the current behavior (Option A, terminal rejection) is
unambiguous from the code and is treated as intentional, not a defect. If product ownership
later wants Option B, the "what would be required" section above is the starting scope.
