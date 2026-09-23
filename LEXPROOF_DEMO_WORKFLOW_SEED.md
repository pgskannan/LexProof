# LexProof Demo Workflow Seed

This document captures a deterministic, real-workflow approval scenario for the LexProof demo environment. It intentionally stays on the application’s normal decision path: create an org, create a contract/version, persist a finding, create a redline proposal, and approve it without publishing.

## Scenario

- Organization: `demo-approval-workflow`
- Contract: `Demo Master Services Agreement`
- Contract ID: `demo-master-services-agreement`
- Version ID: `demo-master-services-agreement-v1`
- Finding ID: `demo-liability-cap-finding`
- Proposal: created from the finding by the contract owner
- Reviewer: `demo-reviewer-1` approves the redline
- Approver: `demo-approver-1` is present and authorized, but the proposal is not published in this scenario

## Why this scenario is valid

- The finding is attached to the same contract and version as the proposal.
- The evidence quote matches the source contract text exactly once.
- The workflow engine is allowed to enforce owner/reviewer split and role checks.
- The proposal is stored as a real redline proposal and the review is persisted as a real review record.
- The final state remains a real approval state, not a mock or synthetic UI-only state.

## Seed script

The deterministic seed is implemented in the backend script:

- `backend/scripts/create_approval_demo_fixture.py`

This script reuses stable IDs and is safe to rerun. It does not change approval logic, auth, or UI. It uses the app’s real Firestore repositories plus the real `OrganizationService` and `ProposalService` flows.

## Verification performed

The script was executed against the local LexProof backend environment and printed the results below:

- `PROPOSAL_STATUS: APPROVED`
- `WORKFLOW_STATE: approved`
- `REVIEW_DECISION: APPROVED`
- `PUBLISHED_VERSION_ID: None`
- `READY_FOR_MANUAL_REVIEW: yes`

That confirms the contract is in a valid pending approval / approved-but-not-published state, matching the intended demo workflow without bypassing the normal approval path.

## Expected demo experience

In the live app, this scenario is intended to show:

1. The contract exists and has a valid current version.
2. A finding appears for the contract/version pair.
3. The redline proposal can be created and appears in the review queue.
4. A reviewer can approve it.
5. The workflow remains in `approved` rather than `published` until an approver explicitly publishes.
6. The audit trail and deployment state remain coherent and contract-scoped.

## Operational note

This is purposely a single scenario, not a broad dataset seed. It is meant to be deterministic, readable, and easy to verify in a demo or presentation environment.
