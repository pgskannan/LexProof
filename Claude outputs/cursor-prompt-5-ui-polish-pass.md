You are doing a UI polish pass on LexProof — no new features, no backend logic changes, no touching the working core flow (upload → analysis → redline → review → publish → passport → evidence → anchor → verify). This is purely about closing the gap between "functionally complete" and "reads as a finished, enterprise-grade product." Every item below was found by directly using the running app, not guessed.

Before writing any code, read:
- `frontend/app/(authenticated)/layout.tsx` — the persistent sidebar/chrome shared by every authenticated page. This is where the user-identity menu and the org-switcher-everywhere fix both belong.
- `frontend/app/(authenticated)/dashboard/page.tsx` — the "Recent Activity" section's current hardcoded content.
- `frontend/app/(authenticated)/compliance-command-center/page.tsx` — the current bare "No data available" empty state, to use as the reference case for the new empty-state component.
- `frontend/components/ui/` (badge.tsx, button.tsx, card.tsx, skeleton.tsx) — existing design-system primitives. A `skeleton.tsx` already exists; check what it currently does and whether it's actually used anywhere before adding a new one.
- `frontend/lib/auth.ts` and `frontend/components/AuthProvider.tsx` — where the signed-in user's identity (name, email, photoURL — already fetched from Firebase, confirmed present in `firebase:authUser` local state) is already available, so the new user menu reads real data rather than adding a new fetch.
- `backend/app/lexproof/api/__init__.py` (or wherever routes are registered) — to find what a real "recent activity" data source could be (workflow instance history, redline review records, evidence records) before deciding whether this needs a new endpoint or can be assembled from existing ones.

## What to build

### 1. A real, persistent user-identity menu
Add a small user menu to the bottom of the sidebar in `layout.tsx` (where it currently just says "LexProof v1.0"), showing the signed-in user's name/email (and photo if available) with a dropdown containing at minimum "Sign out." Use the same Firebase auth state already driving the rest of the app — do not add a new auth call. This must appear on every authenticated page, not just some.

### 2. Consistent app chrome — org switcher on every page
The "ORGANIZATION" selector currently appears on some pages (Compliance, Contract Reviews, Administration) but not others (confirmed missing on `/dashboard`). Move it into the shared `layout.tsx` sidebar (near the logo, where it already visually sits on the pages that have it) so every authenticated page shows the same chrome, instead of being duplicated per-page. If it's currently implemented per-page, consolidate to one shared component and delete the duplicates.

### 3. A reusable, professional empty-state component
Build one `EmptyState` component (icon + heading + one-line explanation + optional action button) and replace every bare "No data available" / "No contracts available" / similar plain-text empty state with it — Compliance is the primary target, but grep for other instances of this pattern first (e.g., an empty Findings list, an empty counterparty-links list) and convert those too. Each usage should say what the section is *for*, not just that it's empty (e.g., Compliance: "No compliance findings yet — regulatory tracking runs automatically as contracts are analyzed" rather than just "No data available").

### 4. A real "Recent Activity" feed on the Dashboard
Replace the three hardcoded lines in `dashboard/page.tsx` with genuinely recent events, org-scoped, pulled from data that already exists — redline approvals/publications, workflow instance transitions, and evidence/countersignature creation are all already recorded with timestamps. Prefer assembling this from existing endpoints (workflow instance history, redline proposals, evidence records) over adding a new backend aggregation endpoint; only add a new endpoint if assembling client-side turns out to require N+1 calls across contracts, and say so explicitly if you hit that wall rather than quietly building it anyway. Cap at a reasonable number (e.g., 8-10 most recent), newest first, with relative timestamps ("2 hours ago") matching the existing style.

### 5. Loading skeletons instead of bare "Loading..." text
Every "Loading X..." text-only state observed (Contract Reviews' redline list, the Contract Lifecycle page, counterparty-links list, others found by grep for the pattern `Loading ${...}...`) should render a skeleton matching that section's actual shape (card outlines, list-row placeholders) using/extending the existing `skeleton.tsx` primitive, not a spinner or more text. This matters more than usual here because some of these loads can legitimately take 10-60+ seconds under the known backend event-loop hang — a skeleton reads as "working," bare text reads as "stuck."

### 6. Sidebar nested-nav affordance for Administration
"Administration" has two real children (Members, Workflows) that are only reachable by scrolling the sidebar past the fold, with no visual indication they exist. Add a chevron/expand indicator and either default it expanded when the current route is one of its children, or otherwise make it visually obvious there's more there — check how the rest of the sidebar's active/hover states work first and match that pattern rather than inventing a new one.

### 7. Audit confirmation on destructive actions
Check whether rejecting a redline proposal, revoking a counterparty access link, and re-triggering analysis on a failed contract currently fire immediately on click or require confirmation. For any that fire immediately, add a lightweight confirm step (a simple "Are you sure?" dialog is fine — don't build a new modal system if one already exists in `components/ui/`, reuse it). Report which of the three needed it and which already had it.

## Constraints

- Zero changes to any working business logic, API contract, or the core analysis/redline/publish/anchor/verify flow. This is presentation-layer only.
- Don't touch the multi-tenant RBAC, workflow engine, or counterparty-portal backend code at all — if a UI change needs new backend data (item 4's activity feed is the one place this might happen), say so explicitly per the constraint in that item rather than improvising a new endpoint silently.
- Reuse existing design-system primitives (`components/ui/*`) everywhere possible. If something doesn't exist yet (e.g., a dropdown menu for the user identity component, a confirm dialog), check npm dependencies already installed before adding a new library.
- Match the existing visual language (the serif "LexProof" wordmark styling, the card/badge conventions already used throughout) — this is a polish pass, not a redesign.

## Acceptance check

Before calling this done, manually verify: (a) the user-identity menu and org switcher both appear, identically, on Dashboard, Compliance, Contract Reviews, Legal Passport, and Administration; (b) sign-out actually works; (c) Compliance's empty state (and at least one other converted instance) shows the new component, not bare text; (d) Dashboard's Recent Activity shows real, current data — take an action (e.g., approve a redline) and confirm it appears there without a code change; (e) reload Contract Reviews and Contract Lifecycle and confirm a skeleton renders during the load rather than plain "Loading..." text; (f) Administration's Members/Workflows are visually discoverable without scrolling blind; (g) report exactly which of the three destructive actions in item 7 got a new confirm step versus already had one.
