# LexProof Workflow Approval Audit

## Scope
This is a read-only implementation audit of the complete contract approval workflow in the current LexProof codebase. No code was changed, no data was seeded, and no auth bypass was used.

The current repository does not contain separate approval workflow files named exactly as the original design implied. The live implementation is distributed across the generic workflow engine, redline proposal service, contract-version creation, analysis/anchoring, and the UI/API layers that consume those services.

## Source of truth by area

### Contract lifecycle / upload / versioning
- `backend/app/lexproof/api/contracts.py`
- `backend/app/lexproof/services/contract_versions.py`
- `backend/app/lexproof/services/version_analysis.py`

### Approval workflow engine
- `backend/app/lexproof/services/redline_proposals.py`
- `backend/app/lexproof/services/workflow_catalog.py`
- `backend/app/lexproof/services/workflow_engine.py`
- `backend/app/lexproof/api/workflows.py`
- `backend/app/lexproof/api/redline_proposals.py`

### Audit / state projection / public proof
- `backend/app/lexproof/services/audit.py`
- `backend/app/lexproof/api/audit_log.py`
- `backend/app/lexproof/services/published_version_status.py`
- `backend/app/lexproof/frontend/lib/contractLifecycle.ts`

### Live UI entry points
- `frontend/app/(authenticated)/dashboard/contracts/[contractId]/page.tsx`
- `frontend/app/(authenticated)/dashboard/contracts/reviews/page.tsx`
- `frontend/app/(authenticated)/dashboard/admin/audit-log/page.tsx` (or equivalent audit-log route in the current UI)

---

## End-to-end workflow trace

### 1) Contract upload
Observed implementation:
- `api/contracts.py` creates a contract record, version 1, and stores the original document text plus extracted text/OCR state.
- `services/contract_versions.py` is the durable version-creation boundary used later for V2 publication.

Classification: WORKING

Relevant evidence:
- `api/contracts.py` writes `contracts` + `contract_versions` records.
- `create_contract_version()` creates a child version without mutating the source version.

### 2) Version 1 analysis
Observed implementation:
- `api/contracts.py` exposes `POST /contracts/{contract_id}/analyze` and `POST /contracts/{contract_id}/versions/{version_id}/analyze`.
- `VersionAnalysisService.analyze_version()` runs Gemini analysis, writes findings, creates a legal passport, creates evidence items, and optionally anchors evidence.

Classification: WORKING

Key behavior:
- The analysis path is idempotent and reuses prior analysis snapshots.
- It sets `analysis_status` to `processing`, then `complete` or `failed`.
- It can fail on bad AI output, missing document text, or blockchain anchoring errors, but that failure is surfaced as an analysis failure rather than silently overwriting prior publish state.

### 3) Findings persistence and scoping
Observed implementation:
- Findings are stored with `contract_id`, `version_id`, and owner metadata.
- `api/findings.py` filters by `contract_id`.
- `published_version_status.py` also scopes evidence to the proposal/finding when calculating proof state.

Classification: WORKING

Key behavior:
- Findings are contract-scoped and version-aware.
- Redline proposals validate that a finding belongs to the same contract and source version.

### 4) Redline proposal creation
Observed implementation:
- `ProposalService.create()` validates contract membership, source version ownership, finding relationship, and evidence ownership.
- It initializes a generic workflow instance via `_ensure_instance()` and starts the redline approval definition if needed.

Classification: WORKING

Key behavior:
- The proposal stores `contract_id`, `source_version_id`, `finding_id`, `evidence_id`, and workflow instance metadata.
- It creates the workflow definition on demand (`CONTRACT_REDLINE_APPROVAL`) and starts an instance.
- The proposal state transitions are mapped through `PROPOSAL_STATUS_BY_STATE`.

### 5) Review workflow (`draft -> in_review -> approved/rejected`)
Observed implementation:
- `workflow_catalog.py` defines the state machine.
- `workflow_engine.py` enforces `allowed_roles`, `requires_not_actor`, and SLA/escalation.
- `ProposalService.review()` uses the workflow engine to execute `submit_for_review`, `approve`, or `reject`.

Classification: WORKING

Key behavior:
- Role separation is enforced in the generic workflow engine.
- The creator cannot approve their own proposal.
- The workflow instance history is separate from the flat audit log.

### 6) Publish approved redline as V2
Observed implementation:
- `ProposalService.publish()` checks that the proposal is `APPROVED`, requires a persisted approved review, validates exact text replacement against the source document, then calls `create_contract_version()`.
- It sets the proposal `status` to `PUBLISHED`, stores `published_version_id`, stores a publication audit record, then schedules post-publish analysis.

Classification: PARTIAL

Why this is only partial:
- The durable publish operation does succeed at the data layer.
- However, the publish audit event path is incomplete: the publish response/audit call does not carry `contract_id`, so the contract-scoped audit trail is lost.
- This is the first concrete break in the workflow data path that is externally visible in the audit UI.

### 7) Post-publish analysis and anchoring
Observed implementation:
- `ProposalService.publish()` marks `analysis_status` as `pending` (or `not_attempted`) and schedules `run_post_publish_analysis()`.
- `VersionAnalysisService.analyze_version()` re-runs analysis for the newly published V2, generates/updates passport/evidence, and optionally anchors evidence.

Classification: PARTIAL

Why this is only partial:
- The system is intentionally designed so publish is durable even if analysis/anchoring later fails.
- That is a good semantic separation, but it also means the final proof state can remain `processing`, `failed`, or `action_required` after the publish has already succeeded.
- The UI is designed to show this honestly via `proof_status` and `recommended_action`.

### 8) Contract-scoped audit / activity layer
Observed implementation:
- `services/audit.py` supports `contract_id` on every audit entry.
- `api/audit_log.py` already supports `contract_id` filtering.

Classification: BROKEN / NOT WIRED

Observed browser evidence:
- The live audit log page rendered as the global organization audit feed.
- The contract detail page was visible, but no contract-scoped audit/activity view was observed in the authenticated browser session.

Root cause:
- The publish endpoint writes an audit event using `result.get("contract_id")` in `api/redline_proposals.py`, but the `publish()` return object from `ProposalService.publish()` currently does not include `contract_id`.
- That means the `audit_log` entry written at publish time is missing the contract reference, so contract-scoped filtering cannot recover it.

### 9) Populated redline review path
Observed implementation:
- The review console in `frontend/app/(authenticated)/dashboard/contracts/reviews/page.tsx` is wired to `/api/contracts/{contract_id}/redline-proposals`.
- The backend `list()` method returns proposals scoped to the contract.

Classification: NOT TESTED / BLOCKED BY DATA

Observed browser evidence:
- The page rendered the empty state: “No redline proposals yet”.
- No populated reviewable redline fixture was present in the current authenticated session.

This is not a code defect by itself; it is a missing seeded scenario in the current local environment.

---

## First broken transition

### Broken transition
Publish success -> contract-scoped audit record

### Why it is the first broken transition
The redline publish transition itself does commit the new contract version and mark the proposal as published. The break is in the audit handoff immediately after that commit:

- `ProposalService.publish()` returns a result payload that does not include `contract_id`.
- `api/redline_proposals.py` then records the publish audit event with `contract_id=result.get("contract_id")`.
- `audit_log` filtering and the contract-scoped audit UI rely on `contract_id` being present.

So the workflow reaches the correct durable state, but the audit trail is incomplete and the contract-scoped audit view cannot be reliably reconstructed from the organization-wide audit feed.

---

## Root cause

### Exact root cause
In `backend/app/lexproof/api/redline_proposals.py`:
- `publish_redline_proposal()` records a publish audit event with `contract_id=result.get("contract_id")`.

In `backend/app/lexproof/services/redline_proposals.py`:
- `ProposalService.publish()` returns:
  - `proposal_id`
  - `status`
  - `source_version_id`
  - `published_version_id`
  - `published_by`
  - `published_at`
  - `analysis_status`
- It does not include `contract_id`.

Because `result.get("contract_id")` is therefore `None`, the audit log entry written for the publish action lacks the contract association.

### Files involved
- `backend/app/lexproof/services/redline_proposals.py`
- `backend/app/lexproof/api/redline_proposals.py`
- `backend/app/lexproof/services/audit.py`
- `backend/app/lexproof/api/audit_log.py`
- `frontend/app/(authenticated)/dashboard/admin/audit-log/page.tsx` (UI is expected to consume contract-scoped audit feed once the backend data is correct)

---

## Minimum fix required

### Fix target
1. Add `contract_id` to the `publish()` return payload in `ProposalService.publish()`.
2. Add `contract_id` to the `RedlinePublicationResponse` model in `api/redline_proposals.py`.
3. Use that returned `contract_id` when recording the publish audit event.
4. Re-run the browser flow to verify that the audit log page can now be filtered/rendered per contract.

### Recommended code-level change
In `backend/app/lexproof/services/redline_proposals.py`, extend the publish response payload with the proposal’s `contract_id`.

In `backend/app/lexproof/api/redline_proposals.py`, the publish endpoint should either:
- return the `contract_id` in the response model, and/or
- write the audit event using `proposal.get("contract_id")` directly.

This is the smallest fix that restores the contract-scoped audit trail without changing approval logic or authentication.

---

## Demo data to seed after the audit

To verify the full approval path after the audit fix, seed the following minimal dataset:

### Organization / roles
- One org with a contract owner, reviewer, and approver user.
- Roles should be distinct so the workflow separation-of-duties rules are active.

### Contract
- Contract name: `Demo Contract A`
- Contract ID: any stable ID created by the upload flow
- Version 1 with a real document text body and an existing passport/analysis result

### Finding
- One persisted finding attached to version 1
- The finding must have:
  - `contract_id`
  - `version_id`
  - `evidence_quote` that matches the source contract text exactly once

### Proposal
- One redline proposal created from that finding
- Proposal status starts as `PROPOSED`/`in_review` after submission

### Review
- One reviewer decision: `APPROVED`
- A persisted review record is required before publish

### Publish
- Approver publishes the proposal to create V2
- After publish, the system should yield:
  - `published_version_id`
  - `analysis_status` in `pending` / `processing` / `complete`
  - a `publication_audits` record with `contract_id`

---

## E2E scenario to run after the fix

### Scenario: contract approval workflow with contract-scoped audit
1. Log in as the contract owner.
2. Upload a contract and wait for version 1 analysis to complete.
3. Open the findings page and create one redline proposal that references a valid finding.
4. Confirm the proposal appears in the contract review page.
5. Log in as the reviewer and approve the redline.
6. Log in as the approver and publish the approved proposal.
7. Confirm that the contract detail page shows:
   - V2 is now the current version
   - the workflow instance reflects the `published` state
   - the published V2 is available in version history
8. Confirm that the publish path records a contract-scoped audit event in the audit log.
9. Confirm that the contract detail page / legal passport view shows the newly published version and its evidence/anchor status.
10. If anchoring succeeds, confirm the public verification page can verify the evidence.

### Expected results
- The contract-scoped audit log contains the publish event for that contract.
- The contract review page has a real proposal to review (after the seed exists).
- The contract lifecycle page shows a coherent V1 -> V2 progression.
- The proof status reflects either `processing`, `failed`, or `confirmed` without changing the durable publish state.

---

## Live browser evidence already observed

### Observed in the authenticated browser session
- `http://localhost:3000/dashboard/admin/audit-log`
  - Rendered as the global organization audit log.
- `http://localhost:3000/dashboard/contracts/fbc19202-7ca1-4d7c-896b-e08b673915a3`
  - Contract detail page rendered successfully.
- `http://localhost:3000/dashboard/contracts/reviews`
  - Rendered the empty state: “No redline proposals yet”.

### Current status of UI gaps from the live session
- Contract-scoped audit log: OPEN
- Populated contract reviews / redline review path: BLOCKED by missing seeded proposal data

---

## Bottom line
The current implementation already has the real approval workflow machinery in place and the underlying data model is largely correct. The first visible break is not the approval engine itself; it is the contract-scoped audit trail around the publish transition, which currently loses `contract_id` when the publish audit event is written.

That is the first fix to make before claiming the full workflow is end-to-end validated.
