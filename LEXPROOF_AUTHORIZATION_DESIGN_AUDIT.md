# LexProof Authorization Design Audit

## Scope

This is a read-only design audit. No application code, seed data, Firebase configuration, RBAC behavior, or workflow state was changed. The workflow was not executed.

## Executive Finding

`contract.owner_id` is currently overloaded.

At contract creation, it is the Firebase UID of the uploader. The legacy contract, findings, versions, analysis, and executive-summary paths use it as a security ownership boundary. In contrast, the redline workflow resolves the contract organization and uses active organization membership for proposal reads, while using `owner_id` as the proposal creator/business actor for separation of duties and mutation permissions.

The codebase therefore does not implement one consistent semantic. It contains both:

- **A, security ownership:** uploader-only visibility and action checks.
- **B, business/domain ownership:** contract creator recorded as the workflow owner while organization members operate according to role and workflow rules.

The existing organization and RBAC model, plus the redline workflow, support B as the coherent product design for a multi-user organization. The current contract/findings read checks remain A-style legacy checks.

## Evidence

### Contract model and creation

There is no separate strongly typed contract model defining `owner_id`; contracts are persisted as Firestore dictionaries in `backend/app/lexproof/api/contracts.py`.

`_persist_upload()` creates:

- `owner_id: uid` from the authenticated Firebase user;
- optional `org_id` from the validated `X-Org-Id` membership context;
- the same owner identity on the initial version.

This means `owner_id` starts life as **the uploader/creator UID**, not an organization ID and not a role assignment. `org_id` is the explicit tenant field.

### Frontend semantics

The frontend models `contract_owner` as an organization role in `frontend/lib/roles.ts`. `OrgProvider` loads organization membership and role information from `/api/me`; the selected organization is stored separately through `frontend/lib/orgStore.ts`.

The frontend therefore has two distinct concepts:

- organization membership and roles;
- the contract's creator/owner identity.

The contract-review UI uses `admin` or `contract_owner` for sharing/action presentation, which is consistent with `contract_owner` being an action/business role rather than a universal read-visibility requirement.

### RBAC and organization membership

`backend/app/lexproof/services/auth.py` provides the explicit organization boundary through `load_org_member()`. It resolves `get_active_member(org_id, uid)`, returns the member roles, and rejects non-members with `403`.

`require_roles()` then applies action-specific roles. This is the established organization authorization mechanism. `OrganizationService.ensure_member()` and the invite/sync paths provide the legitimate membership lifecycle.

The workflow catalog confirms role-specific actions:

- `contract_owner` or `admin`: submit a proposal for review;
- `reviewer` or `admin`: approve or reject;
- `approver` or `admin`: publish;
- separation-of-duties prevents the creator from approving or publishing their own proposal.

### Admin behavior

`ProposalService.create()` first requires active organization membership, then allows creation when the caller is either the contract `owner_id` or an `admin`. This is direct evidence that an organization admin can operate on a contract owned by another user for workflow purposes.

`ProposalService.list()` and `ProposalService.get()` require active membership in the contract's organization, not equality with `contract.owner_id`.

### Contract GET and list

`backend/app/lexproof/api/contracts.py` uses `_is_visible_to_user(record, uid)` for contract list and contract GET:

```text
not owner_id or owner_id == uid
```

It does not resolve `org_id` membership for these reads. A member of the same organization who is not the uploader is excluded, even if they are an admin, reviewer, approver, or auditor.

Related contract endpoints also use owner equality:

- `GET /api/contracts/{contract_id}/versions` requires `contract.owner_id == uid`;
- `POST /api/contracts/{contract_id}/versions` requires `contract.owner_id == uid`;
- analysis endpoints require contract and version owner equality;
- executive-summary endpoints reject a non-owner;
- remediation and several passport/evidence paths retain owner-based checks.

The adversarial test `backend/tests/test_security_adversarial.py::test_cross_owner_cannot_read_another_users_contract` explicitly codifies this current behavior: a different UID must receive `404`, even when the record has an organization ID.

### Findings GET

`backend/app/lexproof/api/findings.py` applies the same owner-only `_visible(record, uid)` filter. It does not inspect the finding's `org_id`, the parent contract's `org_id`, active membership, or roles.

The focused tests in `backend/tests/test_findings_routes.py` verify per-owner filtering. They do not test an active organization admin or reviewer reading another member's finding.

### Redline Proposal GET/list

`backend/app/lexproof/api/redline_proposals.py` depends only on `get_current_user`, then delegates authorization to `ProposalService`.

`ProposalService.list()` and `get()` call `_require_contract_member()`, which loads the contract, derives its `org_id`, and checks active organization membership. They do not require `contract.owner_id == user_id`.

Proposal creation is broader but action-controlled:

- any active member can be resolved;
- the caller must be the contract owner or hold `admin`;
- workflow transitions then enforce `contract_owner`, `reviewer`, `approver`, and separation-of-duties rules.

This is the strongest existing implementation of the organization/RBAC model and conflicts with the owner-only contract/findings read paths.

## Answers

### 1. What does `owner_id` semantically represent?

Currently it represents the Firebase user who uploaded/created the contract and is also used as a legacy security boundary. In the workflow domain it additionally represents the creator/business owner used for action authorization and separation of duties.

It should not represent the tenant: `org_id` already does that. For a multi-user organization, the coherent semantic is **creator/business owner**, not the sole security principal for every read.

### 2. Should an active organization admin view a contract owned by another user?

Yes. An active admin in the contract's organization should be able to view the contract, versions, findings, and redline proposals, subject to any separate action permission. This is already the model used by `ProposalService` for proposal access and admin actions.

### 3. Should `contract_owner` be required for viewing?

No. `contract_owner` should be an action/business role used where the workflow requires the contract owner to submit or manage a proposal. It should not be required for ordinary visibility. Reviewers, approvers, auditors, and admins may need read access without being the contract owner.

### 4. Is organization membership already the intended security boundary elsewhere?

Yes. `load_org_member()`, `get_active_member()`, organization invites, `/api/me`, organization settings, and redline proposal access all use active organization membership. `org_id` is persisted on uploads when the request supplies a validated organization context.

### 5. Are other endpoints using the same `owner_id` security check?

Yes. The same pattern appears in:

- contract GET/list and version endpoints;
- contract version creation;
- analysis and version-analysis paths;
- executive-summary endpoints;
- findings and translation paths;
- search and time-machine-related visibility helpers;
- remediation;
- passport/evidence retrieval and anchoring paths;
- other owner-scoped user resources such as notifications and saved views.

Not every owner check should be removed: notifications, saved views, and evidence records may intentionally be user-private. The contract aggregate and its contract-scoped findings should be distinguished from those personal resources.

### 6. Minimum consistent authorization rule for contract/finding visibility

For a record with an `org_id`, require an active member of that organization. Use `owner_id` only for creator/business-role and action checks. For legacy records without `org_id`, retain the existing owner-only fallback until they are migrated or explicitly classified.

This rule preserves tenant isolation while allowing legitimate organization collaboration.

## Path Comparison

| Path | Current visibility rule | Role resolution | Design result |
|---|---|---|---|
| Contract GET/list | `owner_id` missing or equals Firebase UID | None | Owner-only legacy behavior; inconsistent with org RBAC |
| Findings GET | `owner_id` missing or equals Firebase UID | None | Owner-only filtering; inconsistent with parent contract tenant boundary |
| Redline Proposal GET/list | Active member of the parent contract's `org_id` | Membership is checked; action roles apply elsewhere | Consistent with organization-scoped collaboration |

## Security Assessment

The current owner-only rule is restrictive rather than permissive for organization members: it causes false denials and blocks legitimate admin/reviewer/approver workflows. Replacing it indiscriminately with organization membership would be unsafe for records that are intentionally personal, so the minimum change must be limited to the contract aggregate and contract-scoped findings/versions, with legacy owner-only fallback where `org_id` is absent.

The adversarial cross-owner test currently protects a single-user ownership model but does not model the organization-admin case. It would need a companion test asserting that a non-owner active organization admin can read an org-owned contract while a non-member cannot.

## Recommended Design

Treat `org_id` plus active organization membership as the tenant security boundary for organization-owned contracts and their contract-scoped findings. Retain `owner_id` as the uploader/creator and business actor. Enforce `contract_owner`, `reviewer`, `approver`, and `admin` only on the actions defined by the workflow or endpoint, not on ordinary reads.

RECOMMENDED AUTHORIZATION RULE:
For org-owned contracts, contract-scoped reads require active membership in `contract.org_id`; `owner_id` controls creator/action permissions, with owner-only fallback for legacy records without `org_id`.

MINIMUM FILES TO CHANGE:
`backend/app/lexproof/api/contracts.py`, `backend/app/lexproof/api/findings.py`, and focused visibility tests in `backend/tests/test_security_adversarial.py` and `backend/tests/test_findings_routes.py`.

SECURITY RISK OF CURRENT RULE:
It treats uploader ownership as the sole read boundary, blocking legitimate tenant members and making contract, findings, and redline authorization inconsistent.

TENANT ISOLATION PRESERVED:
YES

CODE CHANGES:
NONE