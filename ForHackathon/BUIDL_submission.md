# DoraHacks BUIDL submission — LexProof (BLI Legal Tech Hackathon 2)

Paste each block into the matching field on "Submit BUIDL". Deadline: 31 Oct 2026, 9:01 PM ET.

## Basic fields

- **BUIDL name:** LexProof
- **Tagline / one-liner:** AI finds the risk. LexProof proves what happened.
- **Logo:** square PNG of the LexProof shield (use the logo from the site header or ForHackathon/ads/ cropped)
- **Tracks:** LegalTech & RegTech (primary); AI x Blockchain (if multiple tracks are allowed)
- **Bounty:** Chainlink — Best workflow with CRE
- **GitHub:** https://github.com/pgskannan/LexProof
- **Website / live demo:** https://www.lexproofsolutions.com
- **Demo video (YouTube):** https://youtu.be/C1T8wUGipdk
- **Pitch deck:** [paste the shared deck link or upload the PDF export]
- **Contact:** kannan.ganesan@lexproofsolutions.com
- **For profit?** Yes — per-workspace SaaS (pricing below)

## Description (markdown)

### The problem

AI contract review is fast, but it leaves no proof. When a finding, a redline or an approval is questioned months later, by an auditor, a regulator, a counterparty or a court, there is no independent way to show the record wasn't changed afterwards. Audit logs live inside the vendor's own system.

### What LexProof does

LexProof reviews contracts with AI, routes every proposed change through enforced human approval, and seals the result into a **Legal Passport**: a tamper-evident record whose SHA-256 fingerprint is anchored on Ethereum. Anyone can verify it in their own browser, without a login and without trusting LexProof's servers.

- **Proof of process:** AI analysis → findings → human decision → published version → evidence fingerprint → Ethereum anchor, as one record.
- **Verify without trusting us:** the browser recomputes the fingerprint and reads the anchor straight from Sepolia. Change one character and the verdict flips from VERIFIED to ROOT MISMATCH instantly.
- **Enforced human approval:** a different person must approve every redline; separation of duties applies to admins too.
- **Privacy-preserving:** only 32-byte fingerprints go on chain, never contract text or personal data.
- **Continuous monitoring with Chainlink CRE:** a CRE workflow re-checks stored evidence against both on-chain registries every 10 minutes and alerts on any mismatch.
- **Also:** Ask Lexi (answers only from verified findings, with citations), counterparty portal without accounts, Board Report, OCR for scanned contracts.

### Try it in 2 minutes (no account)

1. Open the **Tamper Test**: https://www.lexproofsolutions.com/public-verify/tamper and load the demo passport: **VERIFIED** in under a second.
2. Change any part (contract text, review policy, AI analysis, evidence): **ROOT MISMATCH**. Restore it: VERIFIED again.
3. Check the anchor yourself on Etherscan — both contracts are source-verified:
   - LexProofPassportRegistry: https://sepolia.etherscan.io/address/0x21Ddd03549c2d4fb75336b616f18c34D4a9BFDE6#code
   - LexProofRegistry: https://sepolia.etherscan.io/address/0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191#code

**Judge login (read-only, explore everything, changes disabled):** https://www.lexproofsolutions.com/login — `judge@lexproof.demo` / [password]

### Chainlink CRE (bounty)

The **LexProof Proof Monitor** (`cre/`) is a CRE workflow used as LexProof's verification orchestration layer: cron trigger → HTTP fetch of LexProof's public verify API under DON consensus → direct reads of both Sepolia registries → VERIFIED / ROOT_VERIFIED / MISMATCH verdicts and an alert flag.

- Simulated with CRE CLI against the **live production API** on 3 Oct 2026: 5 of 5 anchored items verified (3 evidence items, 2 passport roots), `alert: false` — `cre/SIMULATION_RESULT_2026-10-03.md`.
- Tamper drill (`--target drill-settings`) on 4 Oct 2026: a proof package with one altered hex digit returns ROOT_MISMATCH and `alert: true` (3 verified, 1 problem) — `cre/SIMULATION_RESULT_DRILL_2026-10-04.md`.

### Track fit

| Track | How LexProof fits |
|---|---|
| LegalTech & RegTech: legal automation | AI review, enforced approval and sealing run as one automated contract workflow |
| LegalTech & RegTech: on-chain legal docs | Each contract gets a Legal Passport whose root is anchored on Ethereum |
| LegalTech & RegTech: data privacy | Only 32-byte fingerprints go on chain, never contract text or personal data |
| AI x Blockchain | Off-chain AI analysis, made verifiable by on-chain anchors and a Chainlink CRE monitor |

### Today vs next

Today: server-enforced separation of duties plus tamper-evident evidence (tamper-evident, not tamper-proof: any change is detectable, and the on-chain copy can't be rewritten). Next: passkey-signed approvals, live CRE deployment, mainnet or L2 through a gas-sponsoring relayer.

### Tech stack

Next.js (Vercel) · FastAPI on Google Cloud Run · Firebase Auth + Firestore · Google Gemini via Vertex AI · Solidity (OpenZeppelin 5) on Ethereum Sepolia · ethers.js · Chainlink CRE (TypeScript SDK) · Tesseract OCR

### Business model

Per-workspace SaaS, anchoring fees included, customers never hold crypto. Public Verify free · Starter $149/mo · Team $499/mo · Enterprise from $1,500/mo · 14-day free trial.

### Honest limitations

Running on the Ethereum Sepolia testnet for the hackathon; the production path is mainnet or an L2 through a gas-sponsoring relayer. LexProof provides AI-assisted analysis for information only, not legal advice.

### Team

Kannan Ganesan — founder, LexProof Solutions. 25+ years in SAP Ariba and source-to-pay; builds AI products for procurement and legal teams.
