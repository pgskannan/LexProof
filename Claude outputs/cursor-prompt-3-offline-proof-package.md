You are building an "Independently-Verifiable Proof Package" for LexProof — a download that lets anyone verify a contract's evidence and blockchain anchor with zero trust in LexProof's servers: no API call to LexProof required after the download, just the original contract file, the downloaded bundle, and a direct read against the public Sepolia network. This is the most literal version of LexProof's core pitch ("verifiable," not "trust us") — treat correctness and honesty here as more important than polish.

Before writing any code, read:
- `frontend/app/public-verify/page.tsx` in full — this already does client-side hash recomputation and a direct (backend-bypassing) read against Sepolia. The new offline verifier must reuse this exact logic, not reimplement hashing or chain-reading from scratch. Extract the relevant hashing/verification functions into a shared module if they're currently inline, so both `public-verify` and the new offline verifier call the same code.
- Whatever backend service computes evidence/document/policy hashes at publish time (check `backend/app/lexproof/domains/passport/evidence_service.py` and `integrity.py` from earlier context) — the offline bundle's hashes must be byte-for-byte the same values, computed the same way, or the offline verifier will produce false mismatches.
- `frontend/app/(authenticated)/legal-passport/page.tsx` for where to add the new "Download verification bundle" action, and what passport/evidence data is already available on that page to build the bundle from.

## What to build

### 1. Backend: `GET /api/passports/{passport_id}/proof-package`
Auth: same org-scoped check as other passport endpoints (reuse existing passport-access authorization; don't invent a new rule).

Returns a JSON bundle containing everything needed to verify this passport with no further LexProof API calls:
- Contract metadata (name, version, passport ID).
- Document hash, policy hash, analysis hash — whatever the existing integrity check already computes at publish time, with the exact algorithm named (e.g. `sha256`) so the verifier can reproduce it.
- Every evidence item: its ID, its hash, and its full anchor metadata (network, contract address, transaction hash, block number) for anything actually anchored.
- The `verification_snapshot` (from the `§21b` integrity fix — check `passport/service.py`) if present, since that's the authoritative source for what should match, not a live re-query.
- A `bundle_generated_at` timestamp and a short `how_to_verify` string.

### 2. A standalone, self-contained offline verifier page
Build this as its own static HTML file (e.g. `frontend/public/verify-offline.html` or generated as a Next.js static export page) containing all its own JS inline or bundled — no dependency on the LexProof backend being up, and no dependency on being served from LexProof's own domain (someone should be able to save this file and open it from their local disk and have it still work, aside from the Sepolia RPC call itself). It must:
- Let the user pick the downloaded bundle JSON file (file input).
- Let the user optionally pick the original contract document file, and recompute its hash client-side to compare against the bundle's stated document hash.
- For each anchored evidence item in the bundle, independently query Sepolia (via the same public RPC approach `public-verify/page.tsx` already uses — reuse that exact call pattern, same contract ABI/address handling) to confirm the on-chain data actually matches what the bundle claims (hash, transaction, block).
- Render a clear VERIFIED / MISMATCH / COULD NOT REACH CHAIN result per item, plus an overall summary, using the same visual language (colors/labels) `public-verify` already established so it reads as the same product, not a different tool.
- Include a short, plain-language explanation at the top: what this page does, why it doesn't need LexProof's server, and what a mismatch would mean.

### 3. Wire up the download
- "Download verification bundle" button on the Legal Passport page (Overview tab is fine) that fetches the JSON from step 1 and triggers a browser download (`bundle-<passportId>.json`).
- Right next to it, a "Download offline verifier" link/button that serves the static HTML from step 2 (`verify-offline.html`) as a download too, so a user ends up with both files and clear instructions ("open verify-offline.html, load this bundle, optionally add the original document").
- Consider (not required, use judgment) bundling both into a single `.zip` via a small client-side zip library if that's meaningfully better UX than two separate downloads — don't add a new backend dependency for this if a client-side approach works.

## Constraints

- Do not modify the existing anchoring pipeline or the existing `public-verify` page's behavior — this is additive. If you extract shared hashing/verification logic into a common module, `public-verify` should end up calling the shared module too (so there's exactly one implementation of "how we verify," not two that could drift), but its user-facing behavior must stay identical.
- The offline verifier's Sepolia read must be genuinely independent — same principle `public-verify` already follows (direct chain read, not proxied through LexProof's backend). Don't quietly route it through a LexProof API.
- Be honest in the UI about what "offline" means here: verifying against Sepolia still requires *some* network call to a public RPC endpoint (not to LexProof) — say that plainly rather than overclaiming "fully offline."

## Acceptance check

Before calling this done, manually verify: (a) download a bundle for the primary demo passport, then open the offline verifier in a completely separate browser profile with LexProof's dev server stopped — confirm it still correctly reports VERIFIED for the anchored evidence (proving it isn't secretly calling the LexProof backend); (b) tamper with one hash value inside a locally-edited copy of the downloaded bundle JSON and confirm the offline verifier correctly reports a mismatch instead of silently passing; (c) confirm `public-verify`'s existing behavior (all four statuses: VERIFIED/TAMPERED/EVIDENCE_NOT_FOUND/ANCHOR_NOT_FOUND) is unchanged after any shared-module refactor.
