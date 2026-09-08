# LexProof — Security

*Last updated 2026-09-04. This describes the security posture of the hackathon build as it actually exists — not an aspirational target. See `THREAT_MODEL.md` for the threat analysis this posture is meant to address, and `LIMITATIONS.md` for known gaps.*

## 1. Authentication

- Every backend route except the public `GET /api/verify/{evidence_id}` requires a Firebase ID token, sent as `Authorization: Bearer <token>` and verified on every request (`services/firebase_auth.py` → `verify_firebase_token`), not just at login. There is no session/cookie state on the backend — it's stateless bearer-token auth per request, consistent with Firebase's model.
- A missing or invalid token returns `401 Unauthorized`; a token that doesn't decode to a UID is also rejected (`get_current_user` in `services/auth.py`).
- The frontend's `apiFetch` helper (`frontend/lib/api.ts`) attaches the current Firebase user's ID token to every request, refreshing it via the Firebase client SDK as needed. It has a 5-second defensive timeout on the auth-state wait, so a stale auth listener degrades to an unauthenticated (401) request rather than hanging the UI forever.

## 2. Authorization

- Ownership is enforced at the data level: every `contracts` document carries an `owner_id` (the uploader's Firebase UID), and route handlers check `contract.get("owner_id") == uid` before allowing reads or writes on that contract's versions, findings, redlines, or passport. See `app/lexproof/api/contracts.py` for the pattern, repeated across the other resource routers.
- There is currently a single implicit role (any authenticated Firebase user can upload, analyze, review, and publish for their own contracts). There's no admin/reviewer/read-only role separation — see `LIMITATIONS.md`.
- The public verification endpoint (`/api/verify/{id}`) is intentionally unauthenticated and read-only by design — that's the point of a public verification portal — and returns only hash-comparison results, never document content, findings text, or PII.

## 3. Data integrity

- **Evidence immutability**: once an evidence item has been anchored on-chain, `EvidenceRecordRepository` (a specialized wrapper around the generic Firestore repository) refuses to `set()` or `delete()` it — raising a `ValueError` instead — so nothing in the running application can silently rewrite or remove evidence after it's been committed to the blockchain. This is enforced in code, not just convention: even an internal bug or a careless script hits this guard. (The `cleanup_test_contracts.py` script explicitly respects this lock rather than working around it — see its docstring.)
- **On-chain anchoring**: each evidence item's content hash is written to the `LexProofRegistry` smart contract via `anchorEvidence`, gated by an `onlyRegistrar` modifier so only an authorized wallet can write new anchors. Verification (`verifyEvidence`/`getEvidenceAnchor`) is a public, unrestricted read.
- **Independent client-side verification**: `/public-verify` reads the anchor directly from Ethereum Sepolia in the browser (via `ethers.js` against a public RPC endpoint), not just through the LexProof backend — so a verifier doesn't have to trust the backend's word for what's on-chain, only the public blockchain state itself.
- **Passport integrity**: each Legal Passport bundles a document hash, policy hash, analysis hash, and evidence hash into one composite passport hash, and the UI's Passport Integrity panel independently checks each component.

## 4. Secrets and credentials

- Firebase service-account credentials and the blockchain signing key are read from environment variables (`backend/.env`, never committed) or, in a deployed environment, GCP Secret Manager (`repositories/secret_manager.py`). `settings.py` uses Pydantic's `SecretStr` for `firebase_private_key` and `blockchain_private_key` so they're not accidentally logged or repr'd in plaintext.
- `ETHEREUM_PRIVATE_KEY`/`BLOCKCHAIN_PRIVATE_KEY` (aliased to the same setting) controls the wallet used for all on-chain writes (`anchorEvidence`, `registerProof`). This is a single shared operational key for the whole backend — there's no per-user or per-contract signing key, and no hardware-backed key management (HSM/KMS) in this build. Losing or leaking this key would let an attacker submit arbitrary anchors as "LexProof" until the contract owner revokes its registrar role.
- No secrets are ever sent to the frontend; the frontend only ever holds a Firebase ID token (scoped, short-lived, revocable) and public contract-address/RPC-endpoint configuration.

## 5. Network security

- CORS is configured via `cors_origin_list()` in settings (environment-driven allowlist), not a wildcard `*`, so arbitrary origins cannot call the authenticated API from a browser.
- All backend blockchain calls that could block are wrapped in `asyncio.to_thread(...)` so a slow/congested RPC call cannot become a denial-of-service vector against unrelated requests sharing the same event loop.
- The public verification portal and endpoint accept only an evidence ID as input — no file upload, no arbitrary query execution, minimal attack surface.

## 6. Explicitly out of scope for this build

These are deliberate, documented gaps, not oversights — see `LIMITATIONS.md` for detail on each and `ROADMAP.md` for what a production hardening pass would need to add:

- No role-based access control beyond single-owner-per-contract.
- No rate limiting on the public `/api/verify/{id}` endpoint.
- No multi-signature or HSM-backed blockchain signing key.
- No encryption-at-rest beyond what Firestore/Cloud Storage provide by default (no field-level or client-side encryption of contract content).
- No formal audit of the `LexProofRegistry.sol` smart contract by a third party.
- No SOC2/GDPR/legal-privilege compliance program (see `THREAT_MODEL.md` and `ROADMAP.md`).
- No automated dependency/vulnerability scanning wired into CI for this build.
