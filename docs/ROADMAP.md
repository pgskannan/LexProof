# LexProof — Roadmap

*Last updated 2026-09-04. What's built for the hackathon vs. what's explicitly deferred as future work.*

## 1. Built and working today

- Upload → AI analysis (Vertex AI) → risk/compliance scoring → findings with evidence.
- Human Review / Approve / Reject / Publish redline workflow, producing a new contract version.
- Legal Passport: document/policy/analysis/evidence hashing into one composite passport hash, with a live integrity panel.
- Per-evidence-item on-chain anchoring to Ethereum Sepolia, with retry if the initial anchor attempt is slow/fails.
- Public verification portal (`/public-verify`): backend hash comparison **plus** an independent client-side read directly against Ethereum — the "you don't have to trust our backend" proof point.
- Internal Evidence Verification page (`/dashboard/verification`) as an authenticated alternative to the public page.
- Contract Time Machine: version history, risk/compliance deltas, hash comparison between versions.
- Reports page ("Metrics that Matter"): review-time savings, L1-vs-L2 anchoring cost model, audit-readiness score — all computed from real data plus clearly-labeled, user-editable assumptions (not hidden constants).
- Hybrid Anchoring architecture: a working schema (`anchoring_method` field supporting both direct per-item anchors and a `MERKLE_BATCH` mode) plus a demo script illustrating the batched-Merkle-root approach a production version would use to cut per-item anchoring cost.
- A cleanup script for accumulated test data, and this documentation set.

## 2. Near-term hardening (before any real production use)

- Wire up passport-level `registerProof`/`verifyProof` properly: either grant the operational wallet registrar access on a real contract deployment, or redesign around a role the team actually controls from day one. See `LIMITATIONS.md` §1.
- Real rate limiting on the public verification endpoint and, more generally, an API gateway layer.
- Role-based access control beyond single-owner-per-contract (reviewer / approver / read-only roles for a real legal team).
- Move the blockchain signing key off a plain env var / Secret Manager string and onto a KMS-backed signer or a multi-sig registrar — see `THREAT_MODEL.md` §3 (T3).
- A real implementation of Hybrid (Merkle-batch) anchoring — the current script is a demonstration of the data model and UI treatment, not a production batching pipeline (no real batch-submission job, no batch-proof verification path yet).
- Third-party security audit of `LexProofRegistry.sol` before any mainnet deployment.
- CI-integrated dependency/vulnerability scanning.

## 3. Explicitly deferred, not started

These were identified during development as real future-work items and consciously not pursued for the hackathon build:

- **Mainnet (or a cheaper L2) deployment** — the demo deliberately runs on Sepolia testnet, no real cost. A production deployment would need a real cost/chain decision (see the Reports page's own L1-vs-L2 cost model as a starting point for that conversation).
- **Real Merkle batching in production** — beyond the demo-only mock in §1, actually submitting batched anchors and verifying individual items against a batch's Merkle root in the live anchoring path.
- **Firestore/GCP de-centralization** — the current build is single-project, single-cloud. No plan yet for data residency options, multi-region, or reducing the degree of trust placed in one cloud vendor.
- **Contract content confidentiality** — uploaded documents and their extracted text currently live in Firestore/Cloud Storage in plaintext (protected by GCP's standard access controls, not client-side/field-level encryption). A real deployment handling sensitive commercial contracts would likely want encryption-at-rest with customer-managed keys, at minimum.
- **Decentralizing the anchoring authority** — right now, only LexProof's own operational wallet can write anchors (`onlyRegistrar`). A more decentralized trust model (e.g., multiple independent registrars, or a permissionless anchoring scheme) is a real design question for a product whose whole pitch is independent verifiability.
- **AI legal liability / disclaimers** — a legal (not just engineering) workstream: clear user-facing language that AI findings are a drafting aid, not legal advice, plus whatever liability/insurance posture a real legal-tech product in this space needs.
- **SOC2 / GDPR / legal-privilege compliance program** — none of this has been started; it's a substantial, separate workstream (policies, audits, data-processing agreements) that only makes sense once there's a real customer base to build it for.
- **Reducing dependency on Etherscan/Alchemy-specific behavior** — the anchor-lookup fix (`LIMITATIONS.md` §7) had to work around several provider-specific quirks (block-range caps, rate limits). A production version might want a more provider-agnostic RPC strategy or a redundant-provider fallback.

## 4. Explicit non-goals

- LexProof does not aim to replace a lawyer's judgment — the human Approve/Reject/Publish step is a permanent part of the design, not a temporary hackathon shortcut.
- LexProof does not aim to be its own blockchain or run its own consensus — it deliberately anchors to an existing, independently-operated chain (Ethereum) specifically so its integrity claims don't depend on trusting LexProof's own infrastructure.
