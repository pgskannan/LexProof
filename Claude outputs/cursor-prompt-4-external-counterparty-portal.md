You are building an "External Counterparty Portal" for LexProof — a scoped, link-based way for the *other side* of a contract negotiation (who has no LexProof account and should never need one) to view a redline proposal and cryptographically countersign it, extending today's workflow engine and evidence/passport model rather than replacing any of it. This is explicitly the highest-risk item of this batch — keep scope narrow and additive. If something here turns out to need more than a link-based token model, stop and flag it rather than building a second full auth system.

Before writing any code, read:
- `frontend/app/public-verify/page.tsx` — this is the existing pattern for a page that works with NO Firebase Auth session. The new counterparty page follows the same shape: a route outside `(authenticated)`, no login wall, access controlled by something in the URL instead.
- `backend/app/lexproof/services/workflow_engine.py` and `services/workflow_catalog.py` — the existing `contract_redline_approval` definition and `execute_transition` logic. Do not add a new state to this definition. The counterparty's countersignature is evidence *about* the existing approved/published proposal, not a new step in the internal approval workflow — keep those concerns separate.
- `backend/app/lexproof/domains/passport/evidence_service.py` and `integrity.py` — how an evidence item is created and hashed today, since a countersignature will be recorded the same way (a new evidence item type, not a new bespoke table).
- `backend/app/lexproof/services/organizations.py` / `roles.py` — org-scoped auth for the *internal* side of this (creating a link is something an org member does, and must be authorized normally).

## What to build

### 1. Backend: scoped, token-based access links
New Firestore collection `external_access_links`: `{ token, org_id, contract_id, contract_version, redline_proposal_id, created_by, created_at, expires_at, revoked: bool, counterparty_name, counterparty_email, permissions: ["view","comment","countersign"] }`. `token` is a long random opaque string (not a JWT, not derived from anything guessable) — it IS the credential, so generate it with real cryptographic randomness and never log it in full.

- `POST /api/orgs/{org_id}/contracts/{contract_id}/counterparty-links` (org-scoped, `get_current_org_member`, require `admin` or `contract_owner` role): creates a link for a given redline proposal, returns the token and the full shareable URL. Set a sensible default expiry (e.g. 14 days) and let the caller override it.
- `GET /api/external/{token}` (no Firebase Auth — the token itself is the auth): validates the token is unexpired and unrevoked, returns read-only data: contract name, the redline proposal's before/after clause diff (reuse whatever the existing Contract Reviews page already fetches for this), current status, and whether this link has already been used to countersign.
- `POST /api/external/{token}/comment`: appends a comment tied to this link (store who — by counterparty_name off the link record — and when). Rate-limit or otherwise guard against abuse (e.g. a simple max-comments-per-link cap) since this endpoint has no account behind it.
- `POST /api/external/{token}/countersign`: records a new evidence item on the contract (reuse `evidence_service`'s creation path) of a distinct type (e.g. `counterparty_countersignature`), hashing `{token_id (not the raw token), contract_version, redline_proposal_id, counterparty_name, timestamp, an attestation statement they must have typed or checked}`. Mark the link as used for countersignature (idempotent — a second attempt should fail cleanly, not create a duplicate evidence item). Do NOT invent on-chain anchoring for this evidence item as part of this task — it should flow into the same evidence list an org member could later choose to anchor through the existing, already-working anchoring button, exactly like any other evidence item.
- All four endpoints: validate the token server-side on every call (existence, not expired, not revoked) — never trust anything else in the request to identify the link.

### 2. Frontend: the counterparty's page
- New route `frontend/app/counterparty/[token]/page.tsx` (public, no auth wall — follow `public-verify`'s pattern for a page with no Firebase session).
- Shows: contract name, the redline's before/after clause diff (reuse existing diff-rendering component/logic from Contract Reviews if one already exists as a reusable piece — don't duplicate the diff logic), a comment box, and a "Countersign" action that requires the counterparty to type their name and check an explicit attestation checkbox ("I have reviewed this redline and agree to be bound by it") before the button is enabled.
- After countersigning, show a confirmation with the evidence ID that was created, and make clear this is now part of the permanent, evidence-backed record — tie the language back to LexProof's existing "cryptographically recorded" framing rather than introducing new terminology.
- If the token is invalid/expired/revoked, show a clear, calm error state — not a generic 404 or crash.

### 3. Frontend: generating a link (internal side)
- On the existing Contract Reviews page (or the contract Lifecycle page — whichever already shows a given redline proposal in enough detail to attach this action to), add a "Share with counterparty" action for org members with the right role, opening a small form (counterparty name/email, optional expiry override) that calls the endpoint from step 1 and shows the resulting shareable link with a copy button.
- Show existing links for a proposal (created date, expiry, whether it's been countersigned yet) so a user isn't guessing whether they already sent one.

## Constraints

- No new authentication system. The counterparty never gets a Firebase account, a password, or an org membership — the link token is the entire access model, by design, for exactly this one narrow purpose.
- Do not change `contract_redline_approval`'s states or transitions. A countersignature is evidence attached to an already-existing proposal/version, not a new workflow step — keep the internal approval workflow and this external-facing feature decoupled.
- Rate-limit or otherwise bound the unauthenticated endpoints (`GET /api/external/{token}`, the comment and countersign endpoints) against abuse — even a simple in-memory or Firestore-backed request-count guard is fine; don't leave them fully open with no limits.
- Match this repo's existing service/route separation and Firestore access patterns — no new database technology.

## Acceptance check

Before calling this done, manually verify: (a) a generated link opens correctly in a fresh browser with no LexProof session and shows the right redline; (b) countersigning creates exactly one new evidence item, visible afterward in the normal Legal Passport Evidence tab like any other evidence item; (c) attempting to countersign twice through the same link either no-ops cleanly or is blocked, not duplicated; (d) an expired or revoked token is rejected with a clear message rather than a crash; (e) the internal `contract_redline_approval` workflow instance for that proposal is completely unaffected by any of this — its state, transitions, and history are identical to before the counterparty ever touched the link.
