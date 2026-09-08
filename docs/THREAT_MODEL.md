# LexProof — Threat Model

*Last updated 2026-09-04. Scoped to the hackathon build as it exists. Written as an honest engineering document, not a compliance checklist — it names real gaps.*

## 1. Assets

| Asset | Why it matters |
|---|---|
| Uploaded contract documents | Potentially confidential business/legal content |
| AI-generated findings & risk scores | Reflect the app's core value proposition; false results undermine trust |
| Redline proposals & publication history | The record of what was changed and by whom |
| Evidence records & their on-chain anchors | The tamper-evidence guarantee the whole product is built around |
| Firebase user accounts / ID tokens | Access control boundary for everything above |
| The blockchain signing key (`BLOCKCHAIN_PRIVATE_KEY`) | Controls who can write new anchors as "LexProof" |
| The `LexProofRegistry` contract's owner/registrar roles | Controls who can ever anchor or re-authorize anchoring |

## 2. Trust boundaries

```
Untrusted: public internet, unauthenticated visitors  ──▶  /api/verify/{id} (read-only, no auth)
                                                         ──▶  /public-verify (browser reads Sepolia directly)
Trusted (Firebase-authenticated): any signed-in user   ──▶  everything under /api/contracts, /api/passports, etc.
                                                             (scoped to that user's own owner_id)
Trusted (backend process only): BLOCKCHAIN_PRIVATE_KEY, Firebase service-account key, GCP credentials
Trusted (contract owner only): setRegistrar() on LexProofRegistry.sol
```

The interesting boundary crossing is the **public verification path**: it's designed to be trustworthy specifically *because* it doesn't require trusting the LexProof backend — the browser reads Ethereum directly. That's a deliberate security property, not just a UX nicety, and it's worth protecting: if `/public-verify` were ever changed to only show the backend's own computed result without the independent on-chain read, its core "you don't have to trust us" claim would quietly disappear.

## 3. Threats considered, and current mitigation

**T1 — An attacker forges or steals a Firebase ID token to act as another user.**
Mitigated by Firebase's own token verification (signature + expiry checked server-side on every request) and per-resource `owner_id` checks. Residual risk: no token revocation-on-suspicious-activity logic beyond what Firebase Auth itself provides; no anomaly detection.

**T2 — An attacker tampers with evidence content after it's been anchored, to make a contract look less risky than it was.**
Mitigated by the `EvidenceRecordRepository` immutability lock (application-level: refuses to write/delete anchored records) and, more fundamentally, by the on-chain hash: even if the lock were bypassed or Firestore were edited directly (e.g., by someone with raw GCP console access), `/public-verify`'s independent hash comparison against Ethereum would surface the mismatch as `TAMPERED` — this was live-demonstrated during development. Residual risk: the immutability lock is application code, not a database-level constraint (see `SECURITY.md` §6 and `LIMITATIONS.md`) — direct Firestore access bypasses it, though the on-chain check still catches the resulting mismatch.

**T3 — The blockchain signing key leaks.**
Not mitigated beyond standard secret-storage hygiene (`SecretStr`, env vars / Secret Manager, never logged). An attacker with this key could submit anchors as "LexProof" until the contract owner calls `setRegistrar(key, false)`. No key rotation procedure, no HSM, no multi-sig. This is the single highest-value secret in the system and the weakest link in the anchoring trust chain — see `ROADMAP.md` for the production-hardening path (KMS-backed signing, or a multi-sig registrar).

**T4 — A malicious or buggy client submits an oversized or malformed file to `/api/contracts`.**
Partially mitigated: file size is capped (`MAX_FILE_SIZE`), content-type and extension are allowlisted (`ALLOWED_TYPES`/`ALLOWED_EXTENSIONS`), and filenames are checked against path-traversal patterns (`extension` parsing rejects a filename containing `/` or `\`). Residual risk: no malware/virus scanning of uploaded documents.

**T5 — Someone probes `/api/verify/{id}` to enumerate evidence IDs or infer information about contracts they don't own.**
Partially mitigated: the endpoint returns only a hash-comparison verdict, never document content or metadata beyond hashes/tx info, and evidence IDs are UUIDs (not sequential/guessable). Residual risk: no rate limiting, so this endpoint could be scripted to enumerate a large ID space cheaply, and there's no logging/alerting on unusual verification-request volume.

**T6 — The AI analysis itself is wrong, and a reviewer trusts it uncritically.**
Not really a security threat, but a real trust-and-safety concern for a legal-tech product: the app's UI and this doc's language should never imply the AI's findings are legal advice or infallible — the Human Review / Approve / Publish step exists specifically so a person, not the AI alone, makes the final call on any redline that ships. See `LIMITATIONS.md`.

**T7 — A contract's whole-passport proof (`registerProof`/`verifyProof`) is claimed as verified when it isn't.**
Currently *not* exploitable in the wrong direction: the gap runs the safe way. No passport has ever been registered (the configured wallet isn't an authorized registrar for that specific function on the deployed contract), so `verifyProof` always correctly reports unverified/reverts rather than falsely reporting success. The UI surfaces this as "unavailable" rather than a false positive. See `LIMITATIONS.md` for the full story and why the demo's trust narrative runs through evidence-level anchoring instead.

## 4. Explicitly out of scope for this threat model

- Insider threats at the cloud-infrastructure level (a GCP/Firebase org admin with direct console access can always read or edit Firestore/Storage content directly — no application-level control can fully prevent this; only the on-chain hash comparison limits the blast radius by making tampering *detectable*).
- Smart-contract-level threats beyond what Solidity/OpenZeppelin's standard patterns (`Ownable`, `ReentrancyGuard` — both used in `LexProofRegistry.sol`) already address. No formal audit has been done.
- Availability/DoS threats against Firebase, Firestore, GCP, or the Sepolia RPC provider themselves — these are third-party dependencies with their own SLAs, not something LexProof's own code can harden against.
- Legal/regulatory risk of the AI's output being relied upon as legal advice — a product/UX and legal-disclaimer question, not a security engineering one, but flagged here because it's the single biggest real-world risk category for this kind of product. See `LIMITATIONS.md`.
