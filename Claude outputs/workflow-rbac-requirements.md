# LexProof — Workflow Engine & User/Role Management: Requirements

*Drafted 2026-09-07. Confirmed against the actual codebase (not assumptions): today there is no workflow engine and no role model. The redline → human review → approve → publish sequence is hardcoded in `backend/app/lexproof/services/redline_proposals.py`, `reviewer_id` is a free-text string with no identity or permission check behind it, and `get_current_user` (`backend/app/lexproof/services/auth.py`) only verifies a Firebase ID token — any signed-in Google account can do anything. There is also no organization/tenant concept anywhere in the schema.*

## 1. Goals

Replace the single hardcoded approval sequence with a **generic, reusable workflow engine** — any process (contract approval, compliance remediation, future ones) is defined as data (states, transitions, required roles) rather than code — and add **real user and role management** with **multi-tenant** isolation, on LexProof's existing stack (FastAPI + Firestore + Next.js + Firebase Auth). No new infrastructure.

## 2. Current state (confirmed in source, 2026-09-07)

- **Auth**: Firebase "Continue with Google" only. `get_current_user` returns raw Firebase claims (`uid`, `email`, etc.) — no role, no org, no permission of any kind.
- **"Workflow"**: `redline_proposals.py`'s `review()` method is the entire approval flow — a two-state (`APPROVED`/`REJECTED`) decision on a proposal, hardcoded, not configurable, not reusable for anything else. `reviewer_id` is passed in by the client with no check that the caller *is* that reviewer or is authorized to review anything.
- **No `users` collection, no `roles` collection, no `organizations` collection.** Every contract, passport, and proposal is globally visible to every authenticated user.
- The word "workflow" elsewhere in the codebase is just UI copy (a link labeled "Open review workflow") or an unrelated MVP feature (`compliance/remediation.py`'s "Simulate Regulatory Change" flow) — not shared infrastructure.

## 3. Scope

### In scope
1. A generic workflow engine: definitions, instances, transitions, history — usable for contract approval today and any future process without new backend code per process.
2. User management: invite, list, deactivate, assign role(s), scoped to an organization.
3. Role management: 5 standard roles with fixed permission sets (below), assignable per user per organization.
4. Multi-tenancy: every organization's users, roles, workflow definitions, and workflow instances are isolated from every other organization's.
5. Migrating the existing contract-approval pipeline to run *on* the new engine, as the first real workflow definition — not a parallel system.
6. An admin UI: manage org members and roles, view/edit workflow definitions, view audit history of every workflow instance.
7. Backend authorization enforced on every endpoint that touches org-scoped data — not just UI-level hiding.

### Out of scope (phase 2+, note but don't build now)
- A visual/no-code workflow-definition builder (ship workflow definitions as versioned JSON/YAML config first; a drag-and-drop editor is a later layer on the same data model).
- Custom/ad-hoc roles beyond the 5 standard ones, or a granular per-permission editor.
- SSO/SAML, billing per tenant, cross-org sharing of a single contract.
- Parallel/quorum approvals (e.g. "2 of 3 approvers") — design the data model to allow adding this later, but ship single-approver-per-step first.

## 4. Roles (standard 5, fixed permission sets)

| Role | Can do |
|---|---|
| **Admin** | Manage org members, assign roles, create/edit workflow definitions, full read/write on all org contracts and workflow instances, view audit logs. |
| **Contract Owner** | Upload/own contracts, initiate workflow instances on their own contracts, view full history on contracts they own, cannot approve their own submissions. |
| **Reviewer** | Perform the "review" step of a workflow instance assigned to them (comment, request changes, advance/reject a step defined as reviewer-gated). Read access to contracts in review. |
| **Approver** | Perform the "approve"/"publish" step of a workflow instance assigned to them. Read access to contracts pending their approval and their org's history. |
| **Auditor / Viewer** | Read-only access to all contracts, passports, evidence, and workflow history in their org. Cannot transition any workflow step. |

A user can hold more than one role in an org (e.g. Admin + Approver), but the engine must still enforce **separation of duties**: the actor who submits/owns a contract version cannot also approve the same instance, even if they hold the Approver role generally.

## 5. Data model (Firestore, multi-tenant)

All new collections are **top-level, org-scoped by an `org_id` field** (Firestore doesn't nest well for this kind of cross-cutting query — filter by `org_id` rather than nesting under an org document), with composite indexes on `(org_id, ...)` for every list query.

```
organizations/{org_id}
  name, created_at, created_by, status (active/suspended)

organizations/{org_id}/members/{user_id}   -- subcollection is fine here, it's always read scoped to one org
  roles: [Role]            -- one user can hold multiple roles in this org
  status: active/invited/deactivated
  invited_by, joined_at

users/{user_id}             -- global identity record, keyed by Firebase uid
  email, display_name, created_at
  org_memberships: [org_id]  -- denormalized for "which orgs am I in" without a collection-group query

workflow_definitions/{definition_id}
  org_id, name, version, is_active
  states: [{ id, name, is_initial, is_terminal }]
  transitions: [{ id, from_state, to_state, action_name, allowed_roles: [Role], requires_not_actor: [field_ref] }]
  created_by, created_at

workflow_instances/{instance_id}
  org_id, definition_id, definition_version
  entity_type (e.g. "contract_version"), entity_id   -- what this instance is tracking
  current_state, status (in_progress/completed/cancelled)
  created_by, created_at, updated_at

workflow_instances/{instance_id}/history/{event_id}   -- append-only, never edited
  transition_id, from_state, to_state, actor_id, actor_roles_at_time, comment, occurred_at
```

`Role` is a fixed enum: `admin | contract_owner | reviewer | approver | auditor`.

Firebase custom claims carry `org_id` + `roles` (refreshed on role change, short TTL) so the *frontend* can gate UI immediately, but every backend endpoint independently re-checks against Firestore — custom claims are a UX convenience, never the source of truth for authorization.

## 6. Functional requirements

### 6.1 Organizations & membership
- Create an org (first Admin becomes org owner).
- Invite a user by email (creates a `members` doc in `invited` status; becomes `active` on first sign-in matching that email).
- Deactivate a member (their sessions lose access on next token refresh; existing workflow history is preserved, not deleted).
- A user can belong to more than one org; every API call and every list query is scoped to one org at a time (selected org in the session/UI, validated server-side against actual membership — never trust an org_id the client sends without checking membership).

### 6.2 Roles
- Assign/remove one or more of the 5 fixed roles to a member (Admin-only action).
- Every backend endpoint declares which roles + which relationship to the resource (owner / assigned reviewer / assigned approver) it requires, and rejects anything else with 403.
- Separation-of-duties check (§4) enforced at the transition-execution layer, not just the UI.

### 6.3 Workflow engine (generic)
- **Definition CRUD** (Admin only): create/edit/version a workflow definition as the JSON shape in §5. Editing an in-use definition creates a new version; running instances keep executing under the version they started on.
- **Instance lifecycle**: starting a workflow instance is triggered by a domain event (e.g. "redline proposal submitted for review") — the engine itself doesn't know about contracts, it just tracks `entity_type`/`entity_id` plus state.
- **Transition execution**: given an instance + a requested transition + the calling user, the engine checks (a) the transition is legal from the current state, (b) the caller holds one of `allowed_roles` for this org, (c) the separation-of-duties rule, then applies the transition, appends an immutable history event, and returns the new state.
- **Query**: list instances by org + entity_type + status + assigned-to-me; get full history for one instance.
- The engine has zero contract-specific logic in it — it should be plausible to define a second, unrelated workflow (e.g. compliance remediation approval) using the same tables and code, with no backend changes beyond a new definition document.

### 6.4 Migrate the existing approval pipeline
- Define a `"contract_redline_approval"` workflow definition equivalent to today's flow: `draft → in_review → approved → published` (plus `rejected`), with `reviewer`/`approver` role gates matching current behavior.
- `redline_proposals.py`'s `review()` and the publish step become thin callers of the generic engine's transition-execution API, rather than owning the state transition logic themselves.
- Write a one-time migration script that backfills `org_id` onto every existing contract/passport/proposal record (default: a single "LexProof Demo" org containing all current data and the current user as Admin), and creates a `workflow_instances` doc + history event for every proposal that already has a `review` recorded, so no history is lost.

### 6.5 Admin UI (Next.js)
- `/dashboard/admin/members` — list org members, invite, assign/remove roles, deactivate.
- `/dashboard/admin/workflows` — list workflow definitions, view/edit as structured form (states/transitions/roles), view version history.
- Per-contract "Workflow" panel (extends the existing Lifecycle page) — shows the live instance's current state, who it's assigned to, and full history, driven by the generic instance/history data instead of the current hardcoded proposal fields.
- Role-gated navigation: a Reviewer/Approver/Auditor should not see admin-only nav items or actions they can't perform (UI convenience only — backend is the real gate per §6.2).

### 6.6 Auditability
- `workflow_instances/*/history` is append-only (write-once from the backend, no update/delete endpoint exposed).
- Every transition event records actor, actor's roles *at the time*, timestamp, and optional comment — sufficient to reconstruct "who approved what, under what role, when" for any past instance, matching LexProof's existing evidence/passport philosophy of tamper-evident records.

## 7. Non-functional requirements

- **Scalability**: composite Firestore indexes for every `(org_id, ...)` list query; paginate all list endpoints; no unfiltered collection scans (this repo already has a documented perf issue from exactly that pattern — don't repeat it).
- **Configurability**: workflow definitions are data, versioned, editable without a deploy. Adding a 6th role later should be a config/enum change, not a rearchitecture (design the `allowed_roles` field as a list of strings now, even though only 5 values are valid today).
- **Security**: backend-enforced authorization on every org-scoped endpoint; custom claims are a UX cache only; separation-of-duties enforced server-side; no client-supplied `org_id`/`role` ever trusted without a server-side membership check.
- **Backward compatibility**: existing demo data (contracts, passports, evidence, the two in-flight proposals) must survive the migration with no data loss and no change to their existing IDs/URLs.
- **Testability**: unit tests for the transition-execution logic (legal/illegal transitions, role checks, separation-of-duties) independent of any specific workflow definition; integration test proving the migrated contract-approval flow behaves identically to today's hardcoded one.
- **Observability**: every transition and every role/permission denial should be visible in backend logs with org_id + actor + action, to debug "why can't this user do X" quickly.

## 8. Suggested phasing

1. **Foundation**: `organizations`, `users`, `members` collections; org-scoped auth dependency (replaces/wraps `get_current_user`); migration script assigning existing data to one default org; Admin can invite/assign roles via API (UI can follow).
2. **Engine core**: `workflow_definitions` + `workflow_instances` + history collections; transition-execution service with role + separation-of-duties checks; unit tests.
3. **Migrate contract approval**: define `contract_redline_approval`, cut `redline_proposals.py` over to call the engine, backfill history for existing proposals, live-verify identical behavior to today.
4. **Admin UI**: members page, workflow-definitions page, per-contract workflow panel, role-gated nav.
5. **Polish**: audit-log views, assigned-to-me queues per role, notification hooks (email/webhook on assignment — stub is fine for the hackathon).

## 9. Open questions for you before Cursor starts

- Should the very first Admin of the default "LexProof Demo" org be your account specifically (by email), or should the migration script prompt for who to assign?
- Any real second organization to test multi-tenant isolation with, or is a second *synthetic* test org (with fixture data) enough to prove isolation works?
- Notification delivery (email on "you've been assigned to review X") — build a real send now, or a logged stub for later wiring?
