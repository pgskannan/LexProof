You are implementing a generic workflow engine plus multi-tenant user/role management for LexProof, an existing FastAPI + Firestore + Next.js (App Router) + Firebase Auth app. Do not introduce new infrastructure (no Postgres, no separate state-machine library, no new auth provider) — build this entirely on the current stack.

Before writing any code, read these existing files so your design fits the real codebase rather than an assumed one:
- `backend/app/lexproof/services/auth.py` and `backend/app/lexproof/api/auth.py` (current auth dependency — you will extend, not replace, this)
- `backend/app/lexproof/services/redline_proposals.py` and `backend/app/lexproof/api/redline_proposals.py` (the hardcoded approval flow you're replacing the internals of)
- `frontend/app/(authenticated)/dashboard/contracts/reviews/page.tsx` and `frontend/app/(authenticated)/dashboard/contracts/[contractId]/page.tsx` (current review UI you'll be adapting)
- `frontend/app/login/page.tsx` (current auth entry point)
- Whatever Firestore client/repository pattern the rest of `backend/app/lexproof` already uses — match its conventions, don't invent a new data-access style.

## What to build

### 1. Multi-tenant foundation
- Firestore collections: `organizations/{org_id}`, `organizations/{org_id}/members/{user_id}` (subcollection, holds `roles: string[]`, `status`), `users/{user_id}` (global identity, `org_memberships: string[]`).
- Extend the existing `get_current_user` FastAPI dependency (don't replace its Firebase-token verification) with an org-scoped variant, e.g. `get_current_org_member(org_id: str = ...)`, that: verifies the Firebase token as today, then checks Firestore that this uid is an active member of `org_id`, and returns the user's roles in that org. Every new endpoint below depends on this, not on raw `get_current_user`.
- Roles are a fixed Python enum / TS union: `admin | contract_owner | reviewer | approver | auditor`. A user can hold multiple roles in one org.
- Never trust an `org_id` or `role` sent by the client without independently checking Firestore membership server-side. Firebase custom claims may cache `org_id`/`roles` for frontend UX, but they are not the authorization source of truth — the backend always re-checks.

### 2. Generic workflow engine (must have zero contract-specific logic)
Collections:
- `workflow_definitions/{definition_id}`: `org_id`, `name`, `version`, `is_active`, `states: [{id, name, is_initial, is_terminal}]`, `transitions: [{id, from_state, to_state, action_name, allowed_roles: string[], requires_not_actor: string[]}]`.
- `workflow_instances/{instance_id}`: `org_id`, `definition_id`, `definition_version`, `entity_type`, `entity_id`, `current_state`, `status`, `created_by`, timestamps.
- `workflow_instances/{instance_id}/history/{event_id}`: append-only — `transition_id`, `from_state`, `to_state`, `actor_id`, `actor_roles_at_time`, `comment`, `occurred_at`. No update/delete endpoint should ever touch this subcollection.

Build a `WorkflowEngine` service (pure, no FastAPI/HTTP concerns) with roughly this shape:
- `create_definition(org_id, name, states, transitions, created_by) -> definition`
- `start_instance(org_id, definition_id, entity_type, entity_id, created_by) -> instance` (instance begins at the definition's `is_initial` state)
- `execute_transition(instance_id, transition_id, actor_id, actor_roles, comment=None) -> instance`: validates the transition is legal from `current_state`, that `actor_roles` intersects `allowed_roles`, applies any `requires_not_actor` separation-of-duties check (e.g. the actor cannot be the same user recorded as `created_by` on the entity being approved), then updates `current_state` and appends a history event — all in a single Firestore transaction so state + history never diverge.
- `get_instance_history(instance_id) -> list[event]`
- `list_instances(org_id, entity_type=None, status=None, assigned_role=None) -> list[instance]` — paginated, backed by composite indexes you add to `firestore.indexes.json` (or wherever this repo defines them).

Write unit tests for the engine in isolation (illegal transition rejected, wrong role rejected, separation-of-duties rejected, valid transition updates state + appends exactly one history event) using a fake/in-memory Firestore or the emulator — whichever this repo already has set up for tests; check for an existing test-setup pattern before adding a new one.

### 3. Migrate the existing contract-approval flow onto the engine
- Define a `contract_redline_approval` workflow definition matching today's behavior: states `draft → in_review → approved → published` plus `rejected`, with `reviewer` gating the review transition and `approver`/`admin` gating publish, matching what `redline_proposals.py` does today.
- Refactor `redline_proposals.py`'s `review()` (and the publish path) to call `WorkflowEngine.execute_transition` instead of writing status fields directly — keep its public API/response shape as close to identical as possible so the frontend doesn't need a rewrite, just wire it to the new source of truth.
- Write a one-time, idempotent migration script (Python, runnable via the same convention as any existing scripts in this repo — check `backend/` for a `scripts/` folder or similar) that:
  - Creates one default organization ("LexProof Demo") if it doesn't already exist.
  - Assigns every existing contract/passport/proposal record an `org_id` pointing at it.
  - Makes the current user (pass their email as an argument) an Admin member of it.
  - For every existing redline proposal that already has a recorded `review`, creates the corresponding `workflow_instances` doc + one history event, so no history is lost.
  - Is safe to re-run without creating duplicates.

### 4. Admin UI (Next.js, matching this repo's existing page/style conventions — check how `frontend/app/(authenticated)/dashboard/*` pages are structured before adding new ones)
- `/dashboard/admin/members`: list org members with their roles, invite by email, assign/remove roles (Admin only — redirect or show a 403 state for non-admins, but remember the backend is the real gate, not this check).
- `/dashboard/admin/workflows`: list workflow definitions for the org, view a definition's states/transitions in a readable structured form, create a new version.
- Extend the existing contract Lifecycle page (`[contractId]/page.tsx`) with a "Workflow" section that shows the live `workflow_instances` state + full history for that contract's current approval instance, replacing/supplementing the current hardcoded `reviewer_id`/`review` display.
- Role-gate navigation (hide admin-only links from non-admins) as a UX nicety — not a security boundary.

## Constraints and expectations

- Match existing code style, error-handling patterns, and Firestore access patterns already used in this repo — don't introduce a different ORM/pattern for the new collections.
- Every new/changed backend endpoint must be authorized server-side against real Firestore membership + role data, every time, with no shortcuts for "it's just the demo."
- Preserve all existing demo data and IDs — the migration must be additive (new `org_id` fields, new workflow-engine records) not destructive.
- After implementing, do a manual pass proving: (a) a user with only the `reviewer` role gets a 403 calling the approve/publish endpoint directly, (b) the contract owner cannot approve their own submission even if also holding the `approver` role, (c) the existing "primary demo contract" walkthrough (upload → analyze → redline → review → approve → publish → passport → verify) still works end to end after the migration, driven through the new engine.
- If anything above is ambiguous once you're in the actual code (e.g. how this repo does Firestore transactions, or where scripts/tests already live), follow the repo's existing convention rather than guessing a new one, and flag anything you had to make an explicit judgment call on.

Ask me before starting if any of this needs clarification; otherwise implement it in the phased order above (foundation → engine core → migrate approval flow → admin UI) so each phase is independently testable against the running app.
