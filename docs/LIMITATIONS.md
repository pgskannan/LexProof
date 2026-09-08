# LexProof — Known Limitations

*Last updated 2026-09-04. This is a deliberately honest list, compiled from real bugs found and either fixed or documented across the project's development sessions. Where something was fixed, that's noted — this file is not just a list of open problems.*

## 1. Passport-level on-chain proof is never actually registered (open, by design decision)

`LexProofRegistry.sol` has two independent anchoring primitives: per-evidence-item anchoring (`anchorEvidence`/`verifyEvidence`, fully working — see below) and a separate whole-passport proof (`registerProof`/`verifyProof`). The second one is built into the contract and the backend, but:
- No frontend action anywhere calls `POST /api/passports/{id}/anchor` (which would call `registerProof`) — it was never wired to a UI button.
- The wallet currently configured for on-chain writes is not an authorized registrar for that specific contract instance (a genuine on-chain permission gap, confirmed via a live revert: `"Not authorized registrar"`).

As a result, the Contract Time Machine page's "Verify Version History" feature (which calls `verifyProof`) will always return unavailable/failed for every contract — this isn't contract-specific or a regression, it's unconditional. **This was a deliberate decision, not an oversight**: redeploying a fresh contract instance (which would make the current wallet both owner and registrar) was identified as a viable fix but explicitly not taken, because the working evidence-level anchoring path already fully covers the product's core trust claim. The whole-passport proof primitive remains a real gap for a production version — see `ROADMAP.md`.

## 2. No role-based access control

Every authenticated Firebase user has full read/write access to their own contracts, with no finer-grained roles (reviewer vs. approver vs. read-only, for instance). Fine for a single-user hackathon demo; a real deployment with multiple people on one legal team would need this.

## 3. Timestamp timezone bug — FIXED

Several timestamp fields (`ContractPassport.created_at`, evidence `created_at`/`verified_at`, and some compliance-monitoring timestamps) were generated with `datetime.utcnow()` — a timezone-naive value that serializes without a UTC offset marker. Browsers parsing that string via `new Date(...)` interpreted it as *local* time rather than UTC, silently shifting it by the browser's UTC offset. This surfaced most visibly as the Reports page showing a nonsensical "4 hr 0 min" AI-analysis-time / "0% time saved" metric, when the real analysis took seconds. **Fixed**: all affected call sites now use `datetime.now(timezone.utc)`. New records created after the fix carry correct timestamps; records created before the fix retain their original (offset) values.

## 4. Internal Evidence Verification page could hang indefinitely — FIXED

The frontend's shared `apiFetch` helper waited on Firebase's `onAuthStateChanged` callback with no timeout. In an edge case (a long-lived browser tab, a stale auth listener), that callback could simply never fire again, leaving any page's action button stuck on a loading spinner forever with no error shown — most visibly on the internal `/dashboard/verification` page's "Verify Evidence" button. **Fixed**: a 5-second defensive timeout now falls back to whatever the current auth state is, so the request always eventually goes out (and gets a normal 401 if auth genuinely isn't available) rather than hanging silently.

## 5. Publish-then-anchor failure handling — FIXED

Originally, if a redline's evidence-anchoring step failed or was slow (e.g., real Sepolia network congestion) during the publish flow, the whole publish request could be reported to the user as failed — even though the actual version-creation/publish had already committed successfully in Firestore. **Fixed**: publish now always reports success once its own writes are committed; evidence-anchoring status is tracked and shown separately, with a Retry action if it didn't complete inline. Live-verified under genuine (not simulated) multi-minute Sepolia congestion.

## 6. Backend could block its whole event loop on a slow blockchain call — FIXED

Synchronous `web3.py` calls (backed by a `requests`-based HTTP provider) running inside `async def` FastAPI route handlers with no `asyncio.to_thread`/executor wrapping meant one slow on-chain round-trip could stall the entire server — including totally unrelated requests and even CORS preflight `OPTIONS` calls. **Fixed**: every such call reachable from a route handler is now wrapped in `asyncio.to_thread(...)`. Verified with a direct concurrent-request timing test (an unrelated request completing in ~330ms while a slow anchor call was still in flight) and reconfirmed under real Sepolia congestion.

## 7. Evidence-anchor transaction-hash resolution — FIXED (five distinct bugs)

An evidence item's on-chain anchor lookup (resolving which transaction anchored it, for display) went through five separate, compounding bugs before it worked reliably: a wrong ABI file path silently falling back to a stub with no event definitions; a web3.py 7.x keyword-argument rename; an RPC provider's undocumented 10-block range cap on `eth_getLogs`; a raw-filter topic-encoding issue requiring a hand-built filter instead of the high-level API; and a `0x`-prefix mismatch between the stored hash format and the decoded event's hash format. All five are fixed; the anchor-lookup path now uses a binary-search-based block estimate (from the contract's own on-chain timestamp) plus a narrow scan window, with 429-rate-limit backoff. Live-verified against multiple real, independently-confirmed anchors.

## 8. No production-grade rate limiting

The public `/api/verify/{id}` endpoint (and, less critically, every other endpoint) has no rate limiting. Not a problem for a demo; would need addressing (an API gateway, a per-IP limiter, or similar) before any public production deployment with meaningful traffic.

## 9. Test-data accumulation in Firestore

Repeated development/testing sessions accumulated roughly 40 contracts (and their associated versions, passports, findings, and evidence) in the `contracts` collection beyond the two that matter for the demo. A cleanup script (`backend/scripts/cleanup_test_contracts.py`) exists to remove these — dry-run by default, protects the primary demo contract and the fixture contract used by two demo scripts, and skips anything with anchored evidence unless explicitly told to include it. Not yet run (deliberately: this is a destructive, irreversible operation and is left for a human to review and confirm).

## 10. No third-party smart-contract audit

`LexProofRegistry.sol` uses standard, well-reviewed OpenZeppelin primitives (`Ownable`, `ReentrancyGuard`) and has a straightforward, narrow surface area (anchor, verify, register/verify proof, registrar management), but has not been through a formal third-party security audit. Fine for a Sepolia testnet demo; would be a hard requirement before handling real value or real legal records on mainnet.

## 11. AI findings are not legal advice

The AI-generated risk findings, scores, and redline suggestions are a drafting/review aid, not a substitute for a qualified reviewer's judgment — which is exactly why the product's core workflow requires a human Approve/Reject/Publish step before anything ships. This is a product-design choice already built into the app (not a gap to fix), but worth stating explicitly here: nothing in LexProof's UI or output should be presented to an end customer as legal advice.

## 12. Known cosmetic/UX rough edges

- One older contract's `/dashboard/contracts/{id}` lifecycle page has been observed hanging on load (40+ seconds, never confirmed to finish) for a specific pre-existing test contract; the equivalent `/legal-passport` route for the same contract loads fine. Not investigated further (low priority, off the main demo path).
- The contract-lifecycle summary page's "Human Review"/"Redline" stage tiles may not always reflect which specific proposal was published, when a contract has multiple proposals on the same version. Observed once, low severity, not root-caused.
