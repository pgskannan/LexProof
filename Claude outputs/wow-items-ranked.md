# LexProof — Next "WOW" Items for the Hackathon (ranked)

*Checked against the actual repo before proposing anything new. Both items from the earlier polish roadmap (`hackathon-polish-roadmap.md`) turned out to already be built — the Merkle-batch "Hybrid Anchoring" simulation is live (`AnchorProofButton.tsx`, `scripts/create_merkle_batch_demo_anchor.py`), and the Reports page's "Metrics that Matter" (review-time savings, L1-vs-L2 anchoring cost, audit-readiness score) is fully built and working. So is the workflow engine + RBAC from earlier today. What's below is genuinely new — nothing here exists in the repo yet (confirmed by grep: no QR code library, no chat/RAG endpoint, no offline-verifier bundle).*

## The pitch these all serve

LexProof's whole differentiator is "AI review you don't have to take on faith — every claim is independently, cryptographically checkable." Everything below either makes that checkability something a judge can *do themselves in 30 seconds*, or extends the same "grounded, cited, provable" idea into a new surface. Nothing below is a generic feature bolt-on — each one is the core pitch, pushed one step further.

## Top 3 — recommended, full Cursor prompts below

### 1. QR-Verify: a scannable, independent proof on every passport
**The moment**: a judge pulls out their own phone, scans a QR code on your screen (or a printed certificate), and gets a real VERIFIED result read live from Sepolia — on their device, with no login, no trusting your laptop.
**Why it's the top pick**: lowest risk, builds entirely on the public-verify page that already works and is already proven live. Turns a feature you already have into a moment judges participate in instead of watch. This is the single highest wow-per-hour item on this list.
**Effort**: small. Client-side QR generation + a printable one-page certificate view. No backend changes to the working anchoring/verification path.

### 2. Ask Your Contracts — a grounded Q&A copilot over your own portfolio
**The moment**: someone asks "which of our contracts have unfavorable governing law clauses?" in plain English, and gets an answer that cites the exact finding IDs and contracts — each citation a live link into the passport/evidence trail. Refuses to answer past what's actually retrieved.
**Why it's a strong pick**: reinforces "not a black box" — the model answers *from* your verified findings, not from vibes, and every claim is one click from its own evidence. This is a live, interactive AI demo moment, which judges remember more than a screenshot.
**Effort**: moderate. No vector DB needed at this data scale (16 contracts, 95 findings) — simple structured retrieval over Firestore is enough. New backend endpoint + a chat UI.

### 3. Independently-Verifiable Proof Package — a download that works even if LexProof disappears tomorrow
**The moment**: "Download verification bundle" on any Legal Passport produces a JSON bundle plus a single self-contained HTML file. Open that HTML file in any browser, anywhere, no LexProof server involved — it recomputes every hash client-side and reads Sepolia directly to confirm the anchor. Red or green, entirely offline from you.
**Why it's a strong pick**: this is the most literal, most defensible version of "verifiable legal intelligence" possible — not a claim, a thing a skeptic can actually run. Strong differentiator for a legal-tech + blockchain judge panel specifically. Reuses the exact client-side hash/verify logic `public-verify/page.tsx` already has proven correct — not new crypto, just repackaged as something portable.
**Effort**: moderate. Mostly assembling data already computed, plus one new self-contained verifier page.

## Two more, worth naming but not fully prompted here (say the word and I'll write these up too)

**4. Portfolio Risk Radar / one-click Board Report** — aggregate the existing findings/metrics data into a printable "Legal Risk Board Report" (heatmap across contracts, trend line, top risks). Strong "this is a real business tool" story for judges evaluating commercial viability; moderate effort, no new plumbing, mostly a content/layout pass on data that already exists.

**5. External Counterparty Portal** — a scoped, no-full-account link that lets the *other side* of a negotiation view redlines and countersign, extending today's RBAC/workflow work with a genuine "both parties cryptographically attested" story. Highest differentiation of the five, but also the highest effort/risk this close to a deadline (new auth flow for non-org users) — good stretch goal if 1–3 land early.

## Not recommended right now

Anything requiring new infrastructure (a real vector DB, a ZK-proof circuit, streaming AI inference, a second blockchain) — all high engineering risk with a fixed deadline, and none of them are things a judge can see or touch in a 5-minute demo the way 1–3 above are. If the project continues past the hackathon, they're worth a real conversation; not now.
